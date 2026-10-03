from __future__ import annotations
import math
from omnivoice import dataset
from omnivoice.hints import NEED_PREP
from omnivoice.textnorm import normalize_text

SAVE_EVERY = 25  # segments between intermediate saves, so a crash loses little work

def _default_recognizer(language: str, model: str | None):
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise RuntimeError(NEED_PREP) from e
    try:
        import ctranslate2
        cuda = ctranslate2.get_cuda_device_count() > 0
    except Exception:
        cuda = False
    name = model or ("large-v3" if cuda else "medium")
    try:
        wm = WhisperModel(name, device="cuda" if cuda else "cpu", compute_type="float16" if cuda else "int8")
    except Exception as e:
        raise RuntimeError(f"Не удалось загрузить модель Whisper «{name}»: {e}. "
                           "Проверь интернет (модель скачивается при первом запуске) и имя --model") from e
    def run(wav):
        segs, _ = wm.transcribe(str(wav), language=language, beam_size=5, vad_filter=False)
        return [(s.text, s.avg_logprob, s.no_speech_prob) for s in segs]
    return run

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
            text, flags = normalize_text(raw, p.language)
            flags = list(flags)
            conf = math.exp(sum(lp for _, lp, _ in parts) / len(parts)) if parts else 0.0
            if (conf < 0.6 or any(ns > 0.5 for _, _, ns in parts) or not parts) and "check" not in flags:
                flags.append("check")
            s.text, s.confidence, s.flags = text, round(conf, 3), flags
            done += 1
            if done % SAVE_EVERY == 0:
                dataset.save(p, segments)
    finally:
        if done:
            dataset.save(p, segments)
    return done
