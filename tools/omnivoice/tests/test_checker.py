import numpy as np
import pytest
from unittest.mock import patch
from typer.testing import CliRunner
from omnivoice import checker, dataset, audio
from omnivoice.dataset import Segment
from omnivoice.project import Project
from omnivoice.cli import app

def wav(p, sid, sec, amp=0.2):
    audio.write_wav(p.segments_dir / f"{sid}.wav", (amp * np.sin(np.arange(int(sec * 22050)) / 5)).astype(np.float32))

def test_report(tmp_path):
    p = Project.create(tmp_path / "p", name="p", language="ru")
    wav(p, "ok", 3); wav(p, "short", 0.5); wav(p, "loud", 2, amp=1.5); wav(p, "drop", 3)
    dataset.save(p, [Segment("ok", "Хорошо", 3), Segment("short", "Да", 0.5), Segment("loud", "", 2),
                     Segment("drop", "x", 3, dropped=True)])
    r = checker.check_project(p, phonemize=lambda t: list(t))
    assert r.phrases == 3
    assert "too_short" in r.per_segment["short"]
    assert {"clipping", "empty_text"} <= set(r.per_segment["loud"])
    assert any("Мало данных" in w for w in r.warnings) and r.errors
    assert not p.steps["check"]

def test_unspeakable(tmp_path):
    p = Project.create(tmp_path / "p", name="p", language="ru")
    wav(p, "a", 3); dataset.save(p, [Segment("a", "☃", 3)])
    r = checker.check_project(p, phonemize=lambda t: [])
    assert "unspeakable" in r.per_segment["a"]

def test_missing_audio(tmp_path):
    p = Project.create(tmp_path / "p", name="p", language="ru")
    dataset.save(p, [Segment("a", "text", 3)])  # No WAV file created
    r = checker.check_project(p, phonemize=lambda t: list(t))
    assert "missing_audio" in r.per_segment["a"]
    assert any("Нет аудио" in e for e in r.errors)
    assert r.errors  # Has errors

def test_default_phonemizer_importerror(tmp_path):
    p = Project.create(tmp_path / "p", name="p", language="ru")
    wav(p, "a", 3)
    dataset.save(p, [Segment("a", "text", 3)])

    # Monkeypatch to simulate ImportError
    with patch('omnivoice.checker._default_phonemizer', return_value=None):
        r = checker.check_project(p)

    assert any("Фонемизатор не установлен" in w for w in r.warnings)
    assert "unspeakable" not in r.per_segment.get("a", [])

def test_raising_phonemizer(tmp_path):
    p = Project.create(tmp_path / "p", name="p", language="ru")
    wav(p, "a", 3); wav(p, "b", 3)
    dataset.save(p, [Segment("a", "text1", 3), Segment("b", "text2", 3)])

    def bad_phon(t):
        raise RuntimeError("phonemizer error")

    r = checker.check_project(p, phonemize=bad_phon)
    assert "unspeakable" in r.per_segment["a"]
    assert "unspeakable" in r.per_segment["b"]
    assert any("Фонемизатор падает на всех фразах" in w for w in r.warnings)

def test_too_long(tmp_path):
    p = Project.create(tmp_path / "p", name="p", language="ru")
    wav(p, "a", 16)  # > 15.3 seconds
    dataset.save(p, [Segment("a", "text", 16)])
    r = checker.check_project(p, phonemize=lambda t: list(t))
    assert "too_long" in r.per_segment["a"]

def test_success_marks_check(tmp_path):
    p = Project.create(tmp_path / "p", name="p", language="ru")
    # Create 10+ minutes of audio (no errors)
    for i in range(3):
        wav(p, f"s{i}", 4)
    dataset.save(p, [Segment(f"s{i}", f"text {i}", 4) for i in range(3)])

    r = checker.check_project(p, phonemize=lambda t: list(t))
    assert not r.errors
    assert p.steps["check"] is True

def test_cli_check_with_errors(tmp_path):
    p = Project.create(tmp_path / "p", name="p", language="ru")
    wav(p, "a", 2)
    dataset.save(p, [Segment("a", "", 2)])  # Empty text = error

    runner = CliRunner()
    result = runner.invoke(app, ["check", "--project", str(p.root)])
    assert result.exit_code == 1
    assert "Есть фразы без текста" in result.output

def test_check_marks_without_clobbering_display(tmp_path):
    p = Project.create(tmp_path / "p", name="p", language="ru")
    wav(p, "ok", 3); dataset.save(p, [Segment("ok", "Хорошо", 3)])
    other = Project.load(p.root); other.display["description"] = "из UI"; other.save()
    checker.check_project(p, phonemize=lambda t: list(t))
    q = Project.load(p.root)
    assert q.steps["check"] is True and q.display["description"] == "из UI" and p.steps["check"] is True
