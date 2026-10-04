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


def test_cli_previews_prints_checkpoints_before_extraction_error(tmp_path, monkeypatch):
    p = make(tmp_path)
    def boom(p): raise RuntimeError("Нужен пакет omnivoice[ui]")
    monkeypatch.setattr(previews, "extract_previews", boom)
    r = CliRunner().invoke(app, ["previews", "-p", str(p.root)])
    assert r.exit_code == 1 and "эпоха 20" in r.output and "omnivoice[ui]" in r.output
    assert r.output.index("эпоха 20") < r.output.index("omnivoice[ui]")


# ---------- piper-shaped events: audio of a validation first, then its val scalars + "epoch" ----------
PHRASES = ["Твоя душа принадлежит мне!", "Кто-то идёт!", "Раз.", "Два.", "Три."]


def piper_events(logdir, epochs, step0=1000, audio_step0=2, mos=None, mel=None, train_only=()):
    """epochs: absolute epoch numbers validated in this run (one validation each, like piper)."""
    logdir.mkdir(parents=True, exist_ok=True)
    w = EventFileWriter(str(logdir))
    for i, e in enumerate(epochs):
        a_step, s_step = audio_step0 + 2 * i, step0 + i
        if e in train_only:  # a train-side log at its own step before the validation
            w.add_event(Event(step=s_step, summary=Summary(value=[Summary.Value(tag="loss_g", simple_value=40.0)])))
            w.add_event(Event(step=s_step, summary=Summary(value=[Summary.Value(tag="epoch", simple_value=e)])))
        for text in PHRASES:
            audio = Summary.Audio(sample_rate=22050, num_channels=1, length_frames=100,
                                  encoded_audio_string=wav_bytes()[:-1] + bytes([e % 256]), content_type="audio/wav")
            w.add_event(Event(step=a_step, summary=Summary(value=[Summary.Value(tag=text, audio=audio)])))
        for tag, v in (("val_mel", (mel or {}).get(e, 0.5)), ("val_mos", (mos or {}).get(e, 2.0)), ("epoch", e)):
            w.add_event(Event(step=s_step, summary=Summary(value=[Summary.Value(tag=tag, simple_value=v)])))
    w.close()


def piper_project(tmp_path):
    p = Project.create(tmp_path / "p", name="p", language="ru")
    logs = p.train_dir / "lightning_logs"
    piper_events(logs / "version_0", [4140, 4141, 4142], step0=464732, audio_step0=2,
                 mos={4140: 3.98, 4141: 3.5, 4142: 2.2}, mel={4140: 0.68, 4141: 0.6, 4142: 0.55})
    piper_events(logs / "version_1", [4143, 4144, 4145], step0=464735, audio_step0=8,
                 mos={4143: 2.1, 4144: 2.36, 4145: 2.3}, mel={4143: 0.5, 4144: 0.35, 4145: 0.4}, train_only=(4144,))
    return p


def test_epoch_metrics_and_series_map_steps_to_epochs(tmp_path):
    p = piper_project(tmp_path)
    m = previews.epoch_metrics(p)
    assert sorted(m) == [4140, 4141, 4142, 4143, 4144, 4145]
    assert m[4144] == pytest.approx({"val_mel": 0.35, "val_mos": 2.36})
    assert [(e, round(v, 2)) for e, v in previews.loss_series(p, "val_mos", offset=4139)] == [
        (1, 3.98), (2, 3.5), (3, 2.2), (4, 2.1), (5, 2.36), (6, 2.3)]
    assert [e for e, _ in previews.loss_series(p)] == [4140, 4141, 4142, 4143, 4144, 4145]


def test_events_are_read_incrementally(tmp_path, monkeypatch):
    p = piper_project(tmp_path)
    previews.epoch_metrics(p)
    logs = p.train_dir / "lightning_logs"
    piper_events(logs / "version_2", [4146], step0=464740, audio_step0=14)
    assert 4146 in previews.epoch_metrics(p)
    reads = []
    real = previews._EventFile._read_new
    monkeypatch.setattr(previews._EventFile, "_read_new", lambda self: reads.append(self) or real(self))
    previews.epoch_metrics(p)
    assert reads == []  # unchanged files are not read again
    assert all(ef.offset == ef.path.stat().st_size for ef in previews._event_files(p))


def test_later_version_wins_and_scalars_without_epoch_are_ignored(tmp_path):
    p = Project.create(tmp_path / "p", name="p", language="ru")
    logs = p.train_dir / "lightning_logs"
    piper_events(logs / "version_10", [7], mos={7: 3.0})
    piper_events(logs / "version_9", [7, 8], mos={7: 1.0, 8: 1.5})
    _scalars(logs / "version_2", [(5, 9.0)], tag="val_mos")  # no "epoch" scalar: can't be placed
    assert previews.loss_series(p, "val_mos") == [(7, 3.0), (8, 1.5)]


def test_listen_extracts_the_epoch_phrases_once(tmp_path):
    p = piper_project(tmp_path)
    epoch, items = previews.listen(p, 4144)
    assert epoch == 4144 and [t for t, _ in items] == PHRASES
    assert all(f.read_bytes()[:4] == b"RIFF" and f.read_bytes()[-1] == 4144 % 256 for _, f in items)
    assert items[0][1].parent == p.train_dir / "previews" / "epoch_4144"
    items[0][1].write_bytes(b"keep")
    previews._INDEX.clear()
    assert previews.listen(p, 4144) == (4144, items) and items[0][1].read_bytes() == b"keep"


def test_listen_nearest_epoch_and_nothing(tmp_path):
    p = piper_project(tmp_path)
    assert previews.listen(p, 4200)[0] == 4145
    q = Project.create(tmp_path / "q", name="q", language="ru")
    assert previews.listen(q, 5) == (None, [])


def ckpts(p, version, names):
    d = p.train_dir / "lightning_logs" / version / "checkpoints"
    d.mkdir(parents=True, exist_ok=True)
    for i, n in enumerate(names):
        (d / n).write_bytes(b"x" * (10 + i))
    return d


def _age(path):
    import os, time
    old = time.time() - 100
    os.utime(path, (old, old))


def test_rank_checkpoints_best_first(tmp_path):
    p = piper_project(tmp_path)
    d0 = ckpts(p, "version_0", ["epoch=4140-val_mos=3.9800.ckpt", "epoch=4142-val_mel=0.5500.ckpt", "last.ckpt"])
    ckpts(p, "version_1", ["epoch=4144-val_mel=0.3500.ckpt", "epoch=4144-val_mos=2.3600.ckpt",
                           "epoch=4143-val_mos=2.1000.ckpt", "last.ckpt"])
    _age(d0 / "last.ckpt")
    rows = previews.rank_checkpoints(p)
    assert [(r.epoch, r.best_mos, r.best_mel, r.last) for r in rows][:3] == [
        (4140, True, False, False), (4145, False, False, True), (4144, False, True, False)]
    last1 = next(r for r in rows if r.last)
    assert last1.mos == pytest.approx(2.3) and last1.mel == pytest.approx(0.4)
    assert [r.epoch for r in rows].count(4144) == 1  # val_mel + val_mos files of one epoch: same weights
    assert not any(r.old_last for r in rows)  # the older run's last.ckpt repeats epoch 4142: not listed twice


def test_rank_checkpoints_hides_warmup_and_sorts_by_epoch(tmp_path):
    p = Project.create(tmp_path / "p", name="p", language="ru")  # base checkpoint: epoch=4139
    b = 4139
    ckpts(p, "version_0", [f"epoch={b + 3}-val_mos=3.9800.ckpt", f"epoch={b + 12}-val_mel=0.2000.ckpt",
                           f"epoch={b + 50}-val_mos=2.9000.ckpt", f"epoch={b + 60}-val_mos=2.5000.ckpt",
                           f"epoch={b + 80}-val_mel=0.3000.ckpt", f"epoch={b + 99}-val_mos=2.7000.ckpt"])
    rows = previews.rank_checkpoints(p)
    # warm-up = max(20, 5% of 99): +3 and +12 still sound like the base voice -> neither listed nor «best»
    assert [(r.epoch - b, r.best_mos, r.best_mel) for r in rows] == [
        (50, True, False), (80, False, True), (99, False, False), (60, False, False)]


def test_rank_checkpoints_only_warmup_keeps_everything(tmp_path):
    p = Project.create(tmp_path / "p", name="p", language="ru")
    ckpts(p, "version_0", ["epoch=4142-val_mos=3.9800.ckpt", "epoch=4151-val_mos=2.0000.ckpt"])
    rows = previews.rank_checkpoints(p)
    assert [(r.epoch, r.best_mos) for r in rows] == [(4142, True), (4151, False)]


def test_rank_checkpoints_without_events_uses_names(tmp_path):
    p = Project.create(tmp_path / "p", name="p", language="ru")
    ckpts(p, "version_0", ["epoch=10-val_mel=0.5000.ckpt", "epoch=20-val_mos=2.5000.ckpt", "last.ckpt"])
    rows = previews.rank_checkpoints(p)
    assert rows[0].epoch == 20 and rows[0].best_mos and rows[0].mos == 2.5
    assert any(r.best_mel and r.epoch == 10 for r in rows)


def test_prune_keeps_best_mos_best_mel_and_newest_last(tmp_path):
    p = piper_project(tmp_path)
    d0 = ckpts(p, "version_0", ["epoch=4140-val_mos=3.9800.ckpt", "epoch=4142-val_mel=0.5500.ckpt", "last.ckpt"])
    d1 = ckpts(p, "version_1", ["epoch=4144-val_mel=0.3500.ckpt", "epoch=4144-val_mos=2.3600.ckpt",
                                "epoch=4143-val_mos=2.1000.ckpt", "last.ckpt"])
    _age(d0 / "last.ckpt")
    keep, drop = previews.prune_plan(p)
    assert sorted(keep) == sorted([d0 / "epoch=4140-val_mos=3.9800.ckpt", d1 / "epoch=4144-val_mel=0.3500.ckpt",
                                   d1 / "last.ckpt"])
    size = sum(f.stat().st_size for f in drop)
    assert previews.delete_checkpoints(drop) == (4, size)
    assert sorted((p.train_dir / "lightning_logs").rglob("*.ckpt")) == sorted(keep)
    assert previews.prune_plan(p)[1] == []



def test_recently_written(tmp_path):
    import time
    p = Project.create(tmp_path / "p", name="p", language="ru")
    assert not previews.recently_written(p)
    d = ckpts(p, "version_0", ["last.ckpt"])
    assert previews.recently_written(p)
    assert not previews.recently_written(p, now=time.time() + 600)
