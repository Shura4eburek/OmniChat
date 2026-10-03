from __future__ import annotations
import math, os
from omnivoice import dataset
from omnivoice.hints import NEED_PREP
from omnivoice.segments import Word
from omnivoice.textnorm import normalize_text

SAVE_EVERY = 25  # segments between intermediate saves, so a crash loses little work
CHECK_BELOW = 0.6     # confidence under this gets the `check` flag
NO_SPEECH_ABOVE = 0.5
# Whole-file recognition (VAD-filtered): Whisper's own no_speech_threshold; 0.5 flagged real lines
NO_SPEECH_WORDS_ABOVE = 0.6

def has_whisper() -> bool:
    import importlib.util
    try:
        return importlib.util.find_spec("faster_whisper") is not None
    except (ImportError, ValueError):
        return False

def _open(name: str, cuda: bool):
    from faster_whisper import WhisperModel
    return WhisperModel(name, device="cuda" if cuda else "cpu", compute_type="float16" if cuda else "int8")

def _cuda_libs_missing() -> str | None:
    """CTranslate2 counts the GPU even when cuBLAS/cuDNN are absent and then fails mid-recognition;
    on Windows check the DLLs up front. Returns the first missing library or None."""
    import sys
    if sys.platform != "win32":
        return None
    import ctypes
    for dll in ("cublas64_12.dll", "cudnn_ops64_9.dll"):
        try:
            ctypes.WinDLL(dll)
        except OSError:
            return dll
    return None

def load_whisper(model: str | None, log=None):
    """WhisperModel on CUDA when available (large-v3), else CPU (medium); a failing CUDA load falls
    back to CPU. Returns (model, cuda)."""
    try:
        import faster_whisper  # noqa: F401
    except ImportError as e:
        raise RuntimeError(NEED_PREP) from e
    try:
        import ctranslate2
        cuda = ctranslate2.get_cuda_device_count() > 0
    except Exception:
        cuda = False
    missing = _cuda_libs_missing() if cuda else None
    if missing:
        cuda = False
        if log: log(f"Видеокарта есть, но нет библиотеки CUDA {missing} — Whisper работает на CPU, это медленнее")
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    name = model or ("large-v3" if cuda else "medium")
    if cuda:
        try:
            return _open(name, True), True
        except Exception as e:
            if log: log(f"Whisper не запустился на видеокарте ({e}) — работаю на CPU, это медленнее")
            name = model or "medium"
    try:
        return _open(name, False), False
    except Exception as e:
        raise RuntimeError(f"Не удалось загрузить модель Whisper «{name}»: {e}. "
                           "Проверь интернет (модель скачивается при первом запуске) и имя --model") from e

def _default_recognizer(language: str, model: str | None):
    wm, _ = load_whisper(model)
    def run(wav):
        segs, _ = wm.transcribe(str(wav), language=language, beam_size=5, vad_filter=False)
        return [(s.text, s.avg_logprob, s.no_speech_prob) for s in segs]
    return run

def word_recognizer(language: str, model: str | None, log=None):
    """Whole-file recogniser for slicing: run(audio_16k, progress=None) -> list[Word] with word
    timestamps (VAD-filtered, timeline of the input). progress(frac) after every Whisper segment.
    A CUDA failure during recognition (e.g. missing cuBLAS/cuDNN) retries once on CPU."""
    state = {}
    state["wm"], state["cuda"] = load_whisper(model, log)

    def once(audio, progress):
        segs, info = state["wm"].transcribe(audio, language=language, beam_size=5,
                                            word_timestamps=True, vad_filter=True)
        out: list[Word] = []
        dur = float(getattr(info, "duration", 0) or 0)
        for s in segs:
            out.extend(Word(float(w.start), float(w.end), w.word, float(w.probability), float(s.no_speech_prob))
                       for w in (s.words or []))
            if progress and dur > 0:
                progress(min(1.0, float(s.end) / dur))
        return out

    def run(audio, progress=None):
        try:
            return once(audio, progress)
        except Exception as e:
            if not state["cuda"]:
                raise
            if log: log(f"Whisper не смог работать на видеокарте ({e}) — перехожу на CPU, это медленнее")
            try:
                state["wm"], state["cuda"] = _open(model or "medium", False), False
            except Exception as e2:
                raise RuntimeError(f"Не удалось загрузить модель Whisper на CPU: {e2}") from e2
            return once(audio, progress)
    return run

def word_confidence(words: list[Word]) -> float:
    """Geometric mean of word probabilities (comparable to exp(avg_logprob))."""
    if not words:
        return 0.0
    return math.exp(sum(math.log(max(w.prob, 1e-6)) for w in words) / len(words))

def assess(raw: str, language: str, conf: float, suspicious: bool) -> tuple[str, list[str]]:
    """Normalised text plus flags; low confidence / no-speech / empty text add `check` once."""
    text, flags = normalize_text(raw, language)
    flags = list(flags)
    if (conf < CHECK_BELOW or suspicious or not raw.strip()) and "check" not in flags:
        flags.append("check")
    return text, flags

def transcribe_project(p, model: str | None = None, recognizer=None, progress=None) -> int:
    segments = dataset.load(p)
    todo = [s for s in segments if not s.edited and not s.text.strip() and not s.dropped]
    if not todo:
        return 0
    rec = recognizer or _default_recognizer(p.language, model)
    done = 0
    try:
        for i, s in enumerate(todo):
            if progress: progress(s.id, i / len(todo))
            try:
                parts = list(rec(p.segments_dir / f"{s.id}.wav"))
            except Exception as e:
                raise RuntimeError(f"Не удалось распознать фразу {s.id} (файл segments/{s.id}.wav повреждён "
                                   f"или не читается): {e}") from e
            raw = " ".join(t.strip() for t, _, _ in parts)
            conf = math.exp(sum(lp for _, lp, _ in parts) / len(parts)) if parts else 0.0
            text, flags = assess(raw, p.language, conf,
                                 suspicious=any(ns > NO_SPEECH_ABOVE for _, _, ns in parts) or not parts)
            s.text, s.confidence, s.flags = text, round(conf, 3), flags
            done += 1
            if done % SAVE_EVERY == 0:
                dataset.save(p, segments)
    finally:
        if done:
            dataset.save(p, segments)
    return done
