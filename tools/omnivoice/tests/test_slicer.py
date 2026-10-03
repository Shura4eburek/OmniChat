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
    monkeypatch.setattr(slicer.shutil, "which", lambda n: "ffmpeg")
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
    monkeypatch.setattr(slicer.shutil, "which", lambda n: "ffmpeg")
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
