import io, wave, struct
import pytest
pytest.importorskip("tensorboard")
from tensorboard.summary.writer.event_file_writer import EventFileWriter
from tensorboard.compat.proto.summary_pb2 import Summary
from tensorboard.compat.proto.event_pb2 import Event
from typer.testing import CliRunner
from omnivoice import previews
from omnivoice.cli import app
from omnivoice.project import Project


def wav_bytes():
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(22050); w.writeframes(struct.pack("<100h", *range(100)))
    return buf.getvalue()


def make(tmp_path):
    p = Project.create(tmp_path / "p", name="p", language="ru")
    logdir = p.train_dir / "lightning_logs/version_0"; (logdir / "checkpoints").mkdir(parents=True)
    for name in ["epoch=10-val_mel=0.5000.ckpt", "epoch=20-val_mel=0.4000.ckpt", "last.ckpt", "junk.ckpt"]:
        (logdir / "checkpoints" / name).write_bytes(b"x")
    w = EventFileWriter(str(logdir))
    audio = Summary.Audio(sample_rate=22050, num_channels=1, length_frames=100, encoded_audio_string=wav_bytes(),
                          content_type="audio/wav")
    w.add_event(Event(step=500, summary=Summary(value=[Summary.Value(tag="Привет", audio=audio)])))
    w.add_event(Event(step=500, summary=Summary(value=[Summary.Value(tag="loss_disc_all", simple_value=1.5)])))
    w.close()
    return p


def test_extract_previews_and_checkpoints(tmp_path):
    p = make(tmp_path)
    out = previews.extract_previews(p)
    assert list(out) == [500] and out[500][0].read_bytes()[:4] == b"RIFF"
    cps = previews.list_checkpoints(p)
    assert [c.epoch for c in cps if c.metric] == [20, 10] and any(c.path.name == "last.ckpt" for c in cps)
    assert cps[0].path.name == "last.ckpt" and all(c.path.name != "junk.ckpt" for c in cps)
    assert previews.loss_series(p) == [(500, 1.5)]


def test_idempotent_and_missing_logs(tmp_path):
    p = make(tmp_path)
    out = previews.extract_previews(p)
    wav = out[500][0]; wav.write_bytes(b"keep")
    previews.extract_previews(p)
    assert wav.read_bytes() == b"keep"
    q = Project.create(tmp_path / "q", name="q", language="ru")
    assert previews.extract_previews(q) == {} and previews.list_checkpoints(q) == []


def test_missing_tensorboard(tmp_path, monkeypatch):
    p = make(tmp_path)
    monkeypatch.setitem(__import__("sys").modules, "tensorboard.backend.event_processing.event_accumulator", None)
    with pytest.raises(RuntimeError, match=r"omnivoice\[ui\]"):
        previews.extract_previews(p)


def test_cli_previews(tmp_path):
    p = make(tmp_path)
    r = CliRunner().invoke(app, ["previews", "-p", str(p.root)])
    assert r.exit_code == 0 and "эпоха 20" in r.output and "Превью: 1" in r.output


def _scalars(logdir, points, tag="loss_disc_all"):
    logdir.mkdir(parents=True, exist_ok=True)
    w = EventFileWriter(str(logdir))
    for step, v in points:
        w.add_event(Event(step=step, summary=Summary(value=[Summary.Value(tag=tag, simple_value=v)])))
    w.close()


def test_loss_series_merges_versions_numerically(tmp_path):
    p = Project.create(tmp_path / "p", name="p", language="ru")
    logs = p.train_dir / "lightning_logs"
    _scalars(logs / "version_10", [(300, 3.0), (400, 4.0)])
    _scalars(logs / "version_2", [(100, 1.0), (300, 9.0)])
    _scalars(logs / "version_9", [(200, 2.0)])
    assert previews.loss_series(p) == [(100, 1.0), (200, 2.0), (300, 3.0), (400, 4.0)]


def test_cli_previews_prints_checkpoints_before_extraction_error(tmp_path, monkeypatch):
    p = make(tmp_path)
    def boom(p): raise RuntimeError("Нужен пакет omnivoice[ui]")
    monkeypatch.setattr(previews, "extract_previews", boom)
    r = CliRunner().invoke(app, ["previews", "-p", str(p.root)])
    assert r.exit_code == 1 and "эпоха 20" in r.output and "omnivoice[ui]" in r.output
    assert r.output.index("эпоха 20") < r.output.index("omnivoice[ui]")
