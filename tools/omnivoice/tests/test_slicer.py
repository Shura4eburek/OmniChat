import numpy as np
from omnivoice import slicer, dataset
from omnivoice.project import Project

def test_slice_writes_segments_and_is_idempotent(tmp_path, monkeypatch):
    p = Project.create(tmp_path / "p", name="p", language="ru")
    (p.raw_dir / "clip.mp4").write_bytes(b"fake")
    sr = 22050
    x = np.concatenate([np.zeros(sr), 0.2 * np.sin(np.arange(3 * sr) / 10), np.zeros(sr)]).astype(np.float32)
    monkeypatch.setattr(slicer, "_decode", lambda path: x)
    monkeypatch.setattr(slicer, "_speech", lambda y: [(1.0, 4.0)])
    monkeypatch.setattr(slicer, "_normalize", lambda y: y)
    monkeypatch.setattr(slicer.deps, "ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(slicer.transcriber, "has_whisper", lambda: False)
    assert slicer.slice_project(p) == 1
    assert slicer.slice_project(p) == 0
    segs = dataset.load(p)
    assert [s.id for s in segs] == ["clip_0000"] and abs(segs[0].duration - 3.3) < 0.05
    assert segs[0].source == "clip.mp4"
    assert p.steps["slice"]


def _setup(tmp_path, monkeypatch, names=("a.mp4",)):
    p = Project.create(tmp_path / "p", name="p", language="ru")
    for n in names:
        (p.raw_dir / n).write_bytes(b"fake")
    sr = 22050
    x = np.concatenate([np.zeros(sr), 0.2 * np.sin(np.arange(3 * sr) / 10), np.zeros(sr)]).astype(np.float32)
    monkeypatch.setattr(slicer, "_speech", lambda y: [(1.0, 4.0)])
    monkeypatch.setattr(slicer, "_normalize", lambda y: y)
    monkeypatch.setattr(slicer.deps, "ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(slicer.transcriber, "has_whisper", lambda: False)
    return p, x


def test_decode_failure_is_russian_runtime_error(tmp_path, monkeypatch):
    import subprocess
    p, _ = _setup(tmp_path, monkeypatch, ("bad.mp4",))
    def boom(*a, **k):
        raise subprocess.CalledProcessError(1, "ffmpeg", stderr="Invalid data \xff".encode())
    monkeypatch.setattr(slicer.subprocess, "run", boom)
    import pytest
    with pytest.raises(RuntimeError, match="ffmpeg не смог прочитать bad.mp4"):
        slicer.slice_project(p)


def test_progress_survives_failure_on_second_file(tmp_path, monkeypatch):
    import json, pytest
    p, x = _setup(tmp_path, monkeypatch, ("a.mp4", "b.mp4"))
    def dec(path, label=None):
        if path.name == "b.mp4":
            raise RuntimeError("ffmpeg не смог прочитать b.mp4: x")
        return x
    monkeypatch.setattr(slicer, "_decode", dec)
    with pytest.raises(RuntimeError):
        slicer.slice_project(p)
    assert [s.id for s in dataset.load(p)] == ["a_0000"]
    assert list(json.loads((p.raw_dir / ".sliced.json").read_text())) == ["a.mp4"]


def test_corrupt_marker_is_ignored(tmp_path, monkeypatch):
    p, x = _setup(tmp_path, monkeypatch)
    (p.raw_dir / ".sliced.json").write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(slicer, "_decode", lambda path, label=None: x)
    assert slicer.slice_project(p) == 1


def test_limit_peak():
    loud = np.array([0.0, 1.8, -0.5], dtype=np.float32)
    out = slicer._limit_peak(loud)
    assert abs(float(np.max(np.abs(out))) - 0.99) < 1e-6 and out.dtype == np.float32
    quiet = np.array([0.1, -0.5], dtype=np.float32)
    assert slicer._limit_peak(quiet) is quiet
    assert len(slicer._limit_peak(np.zeros(0, np.float32))) == 0


def test_slice_limits_peak_after_normalisation(tmp_path, monkeypatch):
    import soundfile as sf
    p, x = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(slicer, "_decode", lambda path, label=None: x)
    monkeypatch.setattr(slicer, "_normalize", lambda y: y * 10)   # pushes the 0.2 sine to 2.0
    assert slicer.slice_project(p) == 1
    y, _ = sf.read(p.segments_dir / "a_0000.wav")
    assert 0.97 < np.max(np.abs(y)) <= 0.99 + 1e-3


def test_slice_ids_case_insensitive(tmp_path, monkeypatch):
    from omnivoice.dataset import Segment
    p, x = _setup(tmp_path, monkeypatch, ("a.mp4",))
    dataset.save(p, [Segment("A_0000", "x", 1.0)])
    monkeypatch.setattr(slicer, "_decode", lambda path, label=None: x)
    slicer.slice_project(p)
    assert [s.id for s in dataset.load(p)] == ["A_0000", "a_0001"]


def test_slice_marks_without_clobbering_display(tmp_path, monkeypatch):
    p, x = _setup(tmp_path, monkeypatch)
    other = Project.load(p.root); other.display["description"] = "d"; other.save()
    monkeypatch.setattr(slicer, "_decode", lambda path, label=None: x)
    slicer.slice_project(p)
    q = Project.load(p.root)
    assert q.steps["slice"] and q.display["description"] == "d" and p.steps["slice"]


# ---------------- transcript-driven slicing ----------------
from omnivoice.segments import Word


def _words(*lines):
    out = []
    for text, start, dur in lines:
        toks = text.split(); step = dur / len(toks)
        out += [Word(start + i * step, start + (i + 1) * step - 0.05, " " + t, prob=0.95) for i, t in enumerate(toks)]
    return out


def _once(words):
    """Fake recogniser: `words` for the whole file, nothing for re-recognised gaps."""
    calls = []
    def rec(audio16, progress=None):
        calls.append(1)
        return words if len(calls) == 1 else []
    return rec


def _speechy(seconds=8.0):
    sr = 22050
    return (0.2 * np.sin(np.arange(int(seconds * sr)) / 10)).astype(np.float32)


def test_slice_with_recognizer_cuts_by_sentences_and_fills_text(tmp_path, monkeypatch):
    p, _ = _setup(tmp_path, monkeypatch, ("clip.m4a",))
    x = _speechy()
    monkeypatch.setattr(slicer, "_decode", lambda path, label=None: x)
    monkeypatch.setattr(slicer, "_speech", lambda y: (_ for _ in ()).throw(AssertionError("no VAD")))
    words = _words(("Привет, подопытный 1.", 0.5, 3.0), ("Тест начнётся сейчас!", 3.62, 3.0))
    seen = []
    def rec(audio16, progress=None):
        assert audio16.dtype == np.float32
        if abs(len(audio16) - 8 * 16000) > 50:
            return []
        progress(1.0)
        return words
    logs = []
    n = slicer.slice_project(p, recognizer=rec, log=logs.append, progress=lambda f, fr: seen.append(fr))
    assert n == 2
    segs = dataset.load(p)
    assert [s.id for s in segs] == ["clip_0000", "clip_0001"]
    assert [s.text for s in segs] == ["Привет, подопытный один.", "Тест начнётся сейчас!"]
    assert all(s.confidence and s.confidence > 0.9 and "check" not in s.flags for s in segs)
    assert all(s.source == "clip.m4a" for s in segs)
    assert abs(segs[0].duration - ((3.535 - 0.35) + 0.3)) < 0.02   # cut span + 150 ms pad each side
    assert seen[0] == 0.0 and seen[-1] == 1.0
    assert any("распозна" in m for m in logs)
    assert p.steps["slice"]


def test_slice_flags_low_confidence_and_no_speech(tmp_path, monkeypatch):
    p, _ = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(slicer, "_decode", lambda path, label=None: _speechy())
    low = [Word(0.5, 2.0, " Что-то", prob=0.3), Word(2.05, 3.0, " там.", prob=0.4)]
    ghost = [Word(4.0, 5.5, " Спасибо", no_speech=0.9), Word(5.55, 6.5, " за просмотр.", no_speech=0.9)]
    slicer.slice_project(p, recognizer=_once(low + ghost))
    segs = dataset.load(p)
    assert len(segs) == 2 and all("check" in s.flags for s in segs)
    assert segs[0].confidence < 0.6


def test_slice_isolate_feeds_vocals_to_recognizer(tmp_path, monkeypatch):
    p, _ = _setup(tmp_path, monkeypatch)
    vocals = tmp_path / "vocals.wav"
    monkeypatch.setattr(slicer, "_isolate", lambda path, out: vocals)
    decoded = []
    def dec(path, label=None):
        decoded.append(path); return _speechy()
    monkeypatch.setattr(slicer, "_decode", dec)
    assert slicer.slice_project(p, isolate=True,
                                recognizer=_once(_words(("Только голос.", 1.0, 2.0)))) == 1
    assert decoded == [vocals] and dataset.load(p)[0].text == "Только голос."


def test_slice_without_whisper_falls_back_to_vad_and_says_so(tmp_path, monkeypatch):
    p, x = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(slicer, "_decode", lambda path, label=None: x)
    logs = []
    assert slicer.slice_project(p, log=logs.append) == 1
    assert dataset.load(p)[0].text == ""
    assert any("отдельно" in m for m in logs)


def test_transcribe_after_slice_redoes_nothing(tmp_path, monkeypatch):
    from omnivoice import transcriber
    p, _ = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(slicer, "_decode", lambda path, label=None: _speechy())
    slicer.slice_project(p, recognizer=_once(_words(("Готово.", 1.0, 1.5))))
    def boom(*a, **k): raise AssertionError("must not recognise again")
    assert transcriber.transcribe_project(p, recognizer=boom) == 0
    assert dataset.load(p)[0].text == "Готово."


def test_slice_file_without_words_adds_nothing_but_is_marked(tmp_path, monkeypatch):
    import json
    p, x = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(slicer, "_decode", lambda path, label=None: x)
    logs = []
    assert slicer.slice_project(p, recognizer=_once([]), log=logs.append) == 0
    assert "a.mp4" in json.loads((p.raw_dir / ".sliced.json").read_text())
    assert any("a.mp4" in m for m in logs)


def test_borderline_no_speech_with_confident_words_is_not_flagged(tmp_path, monkeypatch):
    p, _ = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(slicer, "_decode", lambda path, label=None: _speechy())
    words = [Word(0.5, 1.5, " Говори,", prob=0.95, no_speech=0.52), Word(1.6, 2.4, " глупец!", prob=0.97, no_speech=0.52)]
    slicer.slice_project(p, recognizer=_once(words))
    assert "check" not in dataset.load(p)[0].flags


def test_slice_recognises_speech_whisper_skipped(tmp_path, monkeypatch):
    p, _ = _setup(tmp_path, monkeypatch)
    sr = 22050
    x = np.zeros(8 * sr, np.float32)
    for a, b in ((0.5, 2.0), (3.0, 5.5)):
        x[int(a * sr):int(b * sr)] = 0.2 * np.sin(np.arange(int((b - a) * sr)) / 10)
    monkeypatch.setattr(slicer, "_decode", lambda path, label=None: x)
    calls = []
    def rec(audio16, progress=None):
        calls.append(len(audio16) / 16000)
        if len(calls) == 1:                       # whole file: the first line is missing
            return _words(("Никто не смеет мне приказывать!", 3.0, 2.5))
        return _words(("Во славу Плети!", 0.1, 1.5))  # relative to the re-recognised piece
    slicer.slice_project(p, recognizer=rec)
    assert [s.text for s in dataset.load(p)] == ["Во славу Плети!", "Никто не смеет мне приказывать!"]
    assert len(calls) == 2 and calls[1] < 2.5


def test_gap_recognition_ignores_fragments_of_neighbouring_words(tmp_path, monkeypatch):
    p, _ = _setup(tmp_path, monkeypatch)
    sr = 22050
    x = np.zeros(6 * sr, np.float32)
    x[int(1.0 * sr):int(3.0 * sr)] = 0.2 * np.sin(np.arange(2 * sr) / 10)   # Whisper put the word late
    monkeypatch.setattr(slicer, "_decode", lambda path, label=None: x)
    calls = []
    def rec(audio16, progress=None):
        calls.append(1)
        if len(calls) == 1:
            return [Word(1.8, 3.0, " Фростморн!", prob=0.95)]
        return [Word(0.0, 0.6, " ФРОСТ"), Word(0.6, 0.6, "-МО"), Word(0.6, 0.6, "-")]
    slicer.slice_project(p, recognizer=rec)
    assert len(calls) == 2 and [s.text for s in dataset.load(p)] == ["Фростморн!"]
