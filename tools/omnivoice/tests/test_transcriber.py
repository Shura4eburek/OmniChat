from omnivoice import transcriber, dataset
from omnivoice.dataset import Segment
from omnivoice.project import Project

def fake(results):
    return lambda wav: results[wav.stem]

def test_fills_text_confidence_and_flags(tmp_path):
    p = Project.create(tmp_path / "p", name="p", language="ru")
    dataset.save(p, [Segment("a", "", 2.0), Segment("b", "", 2.0)])
    n = transcriber.transcribe_project(p, recognizer=fake({
        "a": [("Тест 1.", -0.1, 0.01)], "b": [("[шум] хм", -1.5, 0.7)]}))
    s = {x.id: x for x in dataset.load(p)}
    assert n == 2
    assert s["a"].text == "Тест один." and "check" not in s["a"].flags and s["a"].confidence > 0.9
    assert "check" in s["b"].flags and "stage_direction" in s["b"].flags

def test_transcribe_keeps_manual_edits_on_rerun(tmp_path):
    p = Project.create(tmp_path / "p", name="p", language="ru")
    dataset.save(p, [Segment("a", "Моя правка", 2.0, edited=True), Segment("b", "", 2.0)])
    transcriber.transcribe_project(p, recognizer=fake({"b": [("Второй", -0.2, 0.0)]}))
    assert transcriber.transcribe_project(p, recognizer=fake({})) == 0
    s = {x.id: x for x in dataset.load(p)}
    assert s["a"].text == "Моя правка" and s["b"].text == "Второй" and len(s) == 2

def test_check_flag_not_duplicated(tmp_path):
    p = Project.create(tmp_path / "p", name="p", language="ru")
    dataset.save(p, [Segment("a", "", 2.0)])
    transcriber.transcribe_project(p, recognizer=fake({"a": [("", -2.0, 0.9)]}))
    assert dataset.load(p)[0].flags.count("check") == 1

import pytest

def test_unreadable_wav_is_russian_error_and_progress_is_saved(tmp_path):
    p = Project.create(tmp_path / "p", name="p", language="ru")
    dataset.save(p, [Segment("a", "", 2.0), Segment("b", "", 2.0)])
    def rec(wav):
        if wav.stem == "b":
            raise ValueError("bad wav")
        return [("Первая", -0.1, 0.0)]
    with pytest.raises(RuntimeError, match="фразу b"):
        transcriber.transcribe_project(p, recognizer=rec)
    assert dataset.load(p)[0].text == "Первая"

def test_saves_every_25_segments(tmp_path, monkeypatch):
    p = Project.create(tmp_path / "p", name="p", language="ru")
    dataset.save(p, [Segment(f"s{i}", "", 2.0) for i in range(60)])
    saves = []
    real = dataset.save
    monkeypatch.setattr(dataset, "save", lambda pp, segs: (saves.append(1), real(pp, segs)))
    assert transcriber.transcribe_project(p, recognizer=lambda wav: [("Да", -0.1, 0.0)]) == 60
    assert len(saves) == 3   # after 25, after 50, final

def test_whisper_load_failure_is_russian(monkeypatch):
    import sys, types
    class WM:
        def __init__(self, *a, **k): raise OSError("download failed")
    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=WM))
    monkeypatch.setitem(sys.modules, "ctranslate2", types.SimpleNamespace(get_cuda_device_count=lambda: 0))
    with pytest.raises(RuntimeError, match="Whisper"):
        transcriber._default_recognizer("ru", None)

def test_cli_transcribe_error_is_clean(tmp_path, monkeypatch):
    from typer.testing import CliRunner
    from omnivoice.cli import app
    p = Project.create(tmp_path / "p", name="p", language="ru")
    def boom(*a, **k): raise RuntimeError("Не удалось загрузить модель Whisper")
    monkeypatch.setattr(transcriber, "transcribe_project", boom)
    r = CliRunner().invoke(app, ["transcribe", "-p", str(p.root)])
    assert r.exit_code == 1 and "Whisper" in r.output


# ---------------- shared Whisper loading / word recogniser ----------------
import types
import numpy as np


def _fake_whisper(monkeypatch, cuda: int, fail_on=(), calls=None):
    class WM:
        def __init__(self, name, device, compute_type):
            if device in fail_on:
                raise RuntimeError(f"{device} broken")
            self.name, self.device = name, device
            if calls is not None:
                calls.append((name, device, compute_type))
        def transcribe(self, audio, **kw):
            if calls is not None:
                calls.append(kw)
            W = lambda s, e, t, p: types.SimpleNamespace(start=s, end=e, word=t, probability=p)
            segs = [types.SimpleNamespace(start=0.0, end=1.0, avg_logprob=-0.1, no_speech_prob=0.02,
                                          words=[W(0.1, 0.5, " Привет,", 0.9), W(0.6, 1.0, " мир.", 0.8)]),
                    types.SimpleNamespace(start=1.5, end=2.0, avg_logprob=-0.2, no_speech_prob=0.7,
                                          words=[W(1.5, 2.0, " Да.", 0.5)])]
            return iter(segs), types.SimpleNamespace(duration=2.0)
    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=WM))
    monkeypatch.setitem(sys.modules, "ctranslate2", types.SimpleNamespace(get_cuda_device_count=lambda: cuda))
    monkeypatch.setattr(transcriber, "_cuda_libs_missing", lambda: None)

import sys


def test_word_recognizer_returns_words_with_progress(monkeypatch):
    calls = []
    _fake_whisper(monkeypatch, cuda=1, calls=calls)
    run = transcriber.word_recognizer("ru", None)
    seen = []
    words = run(np.zeros(16000, np.float32), progress=seen.append)
    assert calls[0] == ("large-v3", "cuda", "float16")
    kw = calls[1]
    assert kw["language"] == "ru" and kw["word_timestamps"] is True and kw["vad_filter"] is True
    assert [(w.start, w.end, w.text, w.prob) for w in words] == [
        (0.1, 0.5, " Привет,", 0.9), (0.6, 1.0, " мир.", 0.8), (1.5, 2.0, " Да.", 0.5)]
    assert words[2].no_speech == 0.7
    assert seen == [0.5, 1.0]


def test_whisper_falls_back_to_cpu_when_cuda_fails(monkeypatch):
    calls, logs = [], []
    _fake_whisper(monkeypatch, cuda=1, fail_on=("cuda",), calls=calls)
    transcriber.word_recognizer("ru", None, log=logs.append)
    assert calls[0] == ("medium", "cpu", "int8")
    assert any("CPU" in m for m in logs)


def test_assess_flags_low_confidence_and_no_speech():
    text, flags = transcriber.assess("Тест 1.", "ru", 0.9, suspicious=False)
    assert text == "Тест один." and "check" not in flags
    assert "check" in transcriber.assess("Тест", "ru", 0.4, suspicious=False)[1]
    assert transcriber.assess("Тест", "ru", 0.9, suspicious=True)[1].count("check") == 1


def test_missing_cuda_libraries_mean_cpu_without_trying_gpu(monkeypatch):
    calls, logs = [], []
    _fake_whisper(monkeypatch, cuda=1, calls=calls)
    monkeypatch.setattr(transcriber, "_cuda_libs_missing", lambda: "cublas64_12.dll")
    transcriber.load_whisper(None, log=logs.append)
    assert calls == [("medium", "cpu", "int8")]
    assert any("cublas64_12.dll" in m and "CPU" in m for m in logs)
