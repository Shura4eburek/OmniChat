import subprocess, pytest
from pathlib import Path
from omnivoice import train, checkpoints, dataset, download
from omnivoice.dataset import Segment
from omnivoice.project import Project

class Fake:
    def __init__(self, codes): self.codes, self.calls = codes, []
    def __call__(self, cmd, **kw):
        self.calls.append(cmd)
        key = next((k for k in self.codes if k in " ".join(cmd)), None)
        code, out = self.codes.get(key, (0, ""))
        return subprocess.CompletedProcess(cmd, code, stdout=out, stderr="")

_REAL_CLEAN = train._clean_base

@pytest.fixture(autouse=True)
def _no_ckpt_clean(monkeypatch):
    monkeypatch.setattr(train, "_clean_base", lambda ckpt, run: ckpt)

def test_clean_base_runs_cleaner_once(tmp_path, monkeypatch):
    monkeypatch.setenv("OMNIVOICE_CACHE", str(tmp_path))
    ckpt = tmp_path / "checkpoints/ru/x/epoch=4139-step=1.ckpt"; ckpt.parent.mkdir(parents=True); ckpt.write_bytes(b"x")
    calls = []
    def run(cmd, **kw):
        calls.append(cmd); (ckpt.parent / "epoch=4139-step=1.clean.ckpt").write_bytes(b"y")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
    out = _REAL_CLEAN(ckpt, run)
    assert out.name == "epoch=4139-step=1.clean.ckpt"
    assert "/opt/omnivoice/clean_ckpt.py" in calls[0] and "/ckpt/ru/x/epoch=4139-step=1.ckpt" in calls[0]
    assert _REAL_CLEAN(ckpt, run) == out and len(calls) == 1

def test_clean_base_failure_is_russian(tmp_path, monkeypatch):
    monkeypatch.setenv("OMNIVOICE_CACHE", str(tmp_path))
    ckpt = tmp_path / "checkpoints/a.ckpt"; ckpt.parent.mkdir(parents=True); ckpt.write_bytes(b"x")
    run = lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, stdout="", stderr="boom")
    with pytest.raises(train.TrainError, match="Не удалось подготовить базовую модель"):
        _REAL_CLEAN(ckpt, run)

def test_checkpoint_url_encodes_equals():
    assert checkpoints.url("ru/ru_RU/irina/medium/epoch=4139-step=929464.ckpt").endswith(
        "ru/ru_RU/irina/medium/epoch%3D4139-step%3D929464.ckpt")

def test_batch_size():
    assert [train.batch_size_for(v) for v in (None, 6000, 12282, 24000)] == [16, 8, 24, 32]

def test_no_gpu_suggests_colab(tmp_path):
    p = Project.create(tmp_path / "p", name="p", language="ru")
    env = train.Env(docker=True, gpu=False, gpu_name=None, vram_mib=None)
    with pytest.raises(train.TrainError, match="Colab"):
        train.train_project(p, env=env, run=Fake({}))

def test_fit_command_args(tmp_path):
    p = Project.create(tmp_path / "glados", name="glados", language="ru")
    cmd = train.fit_command(p, "/ckpt/base.ckpt", batch=24, max_epochs=3000, resume=False)
    joined = " ".join(cmd)
    for part in ["--gpus all", "python3 -m piper.train fit", "--data.voice_name glados", "--data.espeak_voice ru",
                 "--data.csv_path /work/train/train.csv", "--data.audio_dir /work/segments/",
                 "--model.sample_rate 22050", "--data.batch_size 24", "--trainer.max_epochs 3000",
                 "--ckpt_path /ckpt/base.ckpt"]:
        assert part in joined, part

def test_resume_uses_last_ckpt(tmp_path):
    p = Project.create(tmp_path / "g", name="g", language="ru")
    last = p.train_dir / "lightning_logs/version_0/checkpoints/last.ckpt"; last.parent.mkdir(parents=True); last.write_bytes(b"x")
    cmd = train.fit_command(p, "/ckpt/base.ckpt", batch=16, max_epochs=10, resume=True)
    assert "/work/train/lightning_logs/version_0/checkpoints/last.ckpt" in cmd

def test_empty_dataset_is_an_error(tmp_path):
    p = Project.create(tmp_path / "p", name="p", language="ru")
    env = train.Env(docker=True, gpu=True, gpu_name="RTX", vram_mib=12000)
    with pytest.raises(train.TrainError, match="фраз"):
        train.train_project(p, env=env, run=Fake({}))

def test_no_docker_message(tmp_path):
    p = Project.create(tmp_path / "p", name="p", language="ru")
    with pytest.raises(train.TrainError, match="Docker не найден"):
        train.train_project(p, env=train.Env(False, False, None, None), run=Fake({}))

def test_export_without_checkpoint(tmp_path):
    p = Project.create(tmp_path / "p", name="p", language="ru")
    with pytest.raises(train.TrainError, match="чекпойнт"):
        train.export_project(p, run=Fake({}))

def test_export_command_and_result(tmp_path):
    p = Project.create(tmp_path / "p", name="p", language="ru")
    last = p.train_dir / "lightning_logs/version_0/checkpoints/last.ckpt"; last.parent.mkdir(parents=True); last.write_bytes(b"x")
    fake = Fake({})
    out = train.export_project(p, run=fake)
    assert out == p.export_dir / "model.onnx"
    assert "--checkpoint /work/train/lightning_logs/version_0/checkpoints/last.ckpt" in " ".join(fake.calls[-1])

def test_train_success_marks_step(tmp_path, monkeypatch):
    p = Project.create(tmp_path / "p", name="p", language="ru")
    monkeypatch.setattr(dataset, "piper_csv", lambda p, out: 5)
    cache = tmp_path / "cache"
    ck = cache / "checkpoints" / "a" / "b.ckpt"; ck.parent.mkdir(parents=True); ck.write_bytes(b"x")
    monkeypatch.setattr(checkpoints, "ensure", lambda path, progress=None: ck)
    monkeypatch.setattr(train, "cache_dir", lambda: cache)
    fake = Fake({})
    code = train.train_project(p, env=train.Env(True, True, "RTX", 12000), run=fake)
    assert code == 0 and p.steps["train"] is True
    assert "--ckpt_path /ckpt/a/b.ckpt" in " ".join(fake.calls[-1])

def test_ensure_network_failure_is_russian(tmp_path, monkeypatch):
    import urllib.error
    monkeypatch.setenv("OMNIVOICE_CACHE", str(tmp_path))
    def boom(*a, **k): raise urllib.error.URLError("down")
    monkeypatch.setattr(download.urllib.request, "urlopen", boom)
    with pytest.raises(checkpoints.CheckpointError, match="https://huggingface.co"):
        checkpoints.ensure("ru/x=1.ckpt")

def test_ensure_restarts_when_range_ignored(tmp_path, monkeypatch):
    monkeypatch.setenv("OMNIVOICE_CACHE", str(tmp_path))
    part = tmp_path / "checkpoints" / "x.ckpt.part"; part.parent.mkdir(parents=True); part.write_bytes(b"OLD")
    class R:
        status = 200; headers = {"Content-Length": "3"}
        def __init__(self): self.data = [b"NEW", b""]
        def read(self, n): return self.data.pop(0)
        def __enter__(self): return self
        def __exit__(self, *a): pass
    monkeypatch.setattr(download.urllib.request, "urlopen", lambda req, timeout=None: R())
    assert checkpoints.ensure("x.ckpt").read_bytes() == b"NEW"

def _setup_train(tmp_path, monkeypatch):
    p = Project.create(tmp_path / "p", name="p", language="ru")
    monkeypatch.setattr(dataset, "piper_csv", lambda p, out: 5)
    cache = tmp_path / "cache"
    ck = cache / "checkpoints" / "a" / "b.ckpt"; ck.parent.mkdir(parents=True); ck.write_bytes(b"x")
    monkeypatch.setattr(checkpoints, "ensure", lambda path, progress=None: ck)
    monkeypatch.setattr(train, "cache_dir", lambda: cache)
    return p

def test_epochs_are_relative_to_base(tmp_path, monkeypatch):
    p = _setup_train(tmp_path, monkeypatch)
    p.base_checkpoint = "ru/ru_RU/irina/medium/epoch=4139-step=929464.ckpt"
    fake = Fake({})
    train.train_project(p, epochs=1000, env=train.Env(True, True, "RTX", 12000), run=fake)
    assert "--trainer.max_epochs 5139" in " ".join(fake.calls[-1])

def test_fit_failure_leaves_step_unset(tmp_path, monkeypatch):
    p = _setup_train(tmp_path, monkeypatch)
    fake = Fake({"piper.train fit": (3, "")})
    code = train.train_project(p, env=train.Env(True, True, "RTX", 12000), run=fake)
    assert code == 3 and p.steps["train"] is False

def test_cli_propagates_exit_code(tmp_path, monkeypatch):
    from typer.testing import CliRunner
    from omnivoice.cli import app
    p = _setup_train(tmp_path, monkeypatch)
    monkeypatch.setattr(train, "train_project", lambda *a, **k: 3)
    r = CliRunner().invoke(app, ["train", "-p", str(p.root)])
    assert r.exit_code == 3

def test_export_ckpt_outside_project(tmp_path):
    p = Project.create(tmp_path / "p", name="p", language="ru")
    out = tmp_path / "elsewhere" / "m.ckpt"; out.parent.mkdir(); out.write_bytes(b"x")
    fake = Fake({})
    train.export_project(p, out, run=fake)
    j = " ".join(fake.calls[-1])
    assert "/ckptin" in j and "--checkpoint /ckptin/m.ckpt" in j

class _R:
    def __init__(self, chunks, status=200, length=None):
        self.status, self.data = status, list(chunks) + [b""]
        self.headers = {"Content-Length": str(length if length is not None else sum(map(len, chunks)))}
    def read(self, n): return self.data.pop(0)
    def __enter__(self): return self
    def __exit__(self, *a): pass

def test_ensure_truncated_download_keeps_part(tmp_path, monkeypatch):
    monkeypatch.setenv("OMNIVOICE_CACHE", str(tmp_path))
    monkeypatch.setattr(download.urllib.request, "urlopen", lambda req, timeout=None: _R([b"ab"], length=10))
    with pytest.raises(checkpoints.CheckpointError, match="оборвалась"):
        checkpoints.ensure("x.ckpt")
    assert (tmp_path / "checkpoints" / "x.ckpt.part").read_bytes() == b"ab"

def test_ensure_416_promotes_part(tmp_path, monkeypatch):
    import urllib.error
    monkeypatch.setenv("OMNIVOICE_CACHE", str(tmp_path))
    part = tmp_path / "checkpoints" / "x.ckpt.part"; part.parent.mkdir(parents=True); part.write_bytes(b"FULL")
    def boom(req, timeout=None): raise urllib.error.HTTPError("u", 416, "range", {}, None)
    monkeypatch.setattr(download.urllib.request, "urlopen", boom)
    assert checkpoints.ensure("x.ckpt").read_bytes() == b"FULL" and not part.exists()

@pytest.mark.parametrize("stop_at", [1, 2, 3])
def test_should_stop_aborts_before_container(tmp_path, monkeypatch, stop_at):
    p = _setup_train(tmp_path, monkeypatch)
    calls = []
    def should_stop():
        calls.append(1); return len(calls) >= stop_at
    fake = Fake({})
    code = train.train_project(p, env=train.Env(True, True, "RTX", 12000), run=fake, should_stop=should_stop)
    assert code == train.STOPPED == 130
    assert not any("piper.train" in " ".join(c) for c in fake.calls)
    assert p.steps["train"] is False
    assert len(calls) == stop_at

def test_should_stop_false_still_trains(tmp_path, monkeypatch):
    p = _setup_train(tmp_path, monkeypatch)
    fake = Fake({})
    code = train.train_project(p, env=train.Env(True, True, "RTX", 12000), run=fake, should_stop=lambda: False)
    assert code == 0 and any("piper.train" in " ".join(c) for c in fake.calls)

ENV12 = train.Env(True, True, "RTX", 12000)

class OomFake(Fake):
    """`piper.train fit` fails with a CUDA OOM line until the batch drops to `ok_at`."""
    def __init__(self, ok_at=None):
        super().__init__({}); self.ok_at = ok_at; self.batches = []
    def __call__(self, cmd, **kw):
        self.calls.append(cmd)
        if "piper.train" in " ".join(cmd):
            bs = int(cmd[cmd.index("--data.batch_size") + 1]); self.batches.append(bs)
            if self.ok_at is None or bs > self.ok_at:
                return subprocess.CompletedProcess(cmd, 1, stdout="torch.OutOfMemoryError: CUDA out of memory.\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

def test_oom_halves_batch_and_resumes(tmp_path, monkeypatch):
    p = _setup_train(tmp_path, monkeypatch)
    fake, lines = OomFake(ok_at=6), []
    code = train.train_project(p, env=ENV12, run=fake, batch=24, on_line=lines.append)
    assert code == 0 and fake.batches == [24, 12, 6]
    assert "Не хватило видеопамяти — уменьшаю батч до 12 и продолжаю" in lines
    assert Project.load(p.root).steps["train"] is True

def test_oom_retry_resumes_from_last_checkpoint(tmp_path, monkeypatch):
    p = _setup_train(tmp_path, monkeypatch)
    last = p.train_dir / "lightning_logs/version_0/checkpoints/last.ckpt"; last.parent.mkdir(parents=True); last.write_bytes(b"x")
    fake = OomFake(ok_at=8)
    import os, time
    future = time.time() + 3600; os.utime(last, (future, future))  # written by this run
    train.train_project(p, env=ENV12, run=fake, batch=16, resume=False)
    fits = [" ".join(c) for c in fake.calls if "piper.train" in " ".join(c)]
    assert "--ckpt_path /ckpt/a/b.ckpt" in fits[0] and "last.ckpt" in fits[1]

def test_oom_retry_after_no_resume_ignores_old_run(tmp_path, monkeypatch):
    p = _setup_train(tmp_path, monkeypatch)
    last = p.train_dir / "lightning_logs/version_0/checkpoints/last.ckpt"; last.parent.mkdir(parents=True); last.write_bytes(b"x")
    import os; os.utime(last, (1, 1))  # an older run
    fake = OomFake(ok_at=8)
    train.train_project(p, env=ENV12, run=fake, batch=16, resume=False)
    fits = [" ".join(c) for c in fake.calls if "piper.train" in " ".join(c)]
    assert all("last.ckpt" not in f for f in fits)

def test_oom_at_minimum_batch_is_russian_error(tmp_path, monkeypatch):
    p = _setup_train(tmp_path, monkeypatch)
    fake = OomFake()
    with pytest.raises(train.TrainError, match="видеопамяти"):
        train.train_project(p, env=ENV12, run=fake, batch=16)
    assert fake.batches == [16, 8, 4]

def test_oom_retry_respects_should_stop(tmp_path, monkeypatch):
    p = _setup_train(tmp_path, monkeypatch)
    fake, polls = OomFake(), []
    def should_stop():
        polls.append(1); return len(polls) > 3   # the 3 preparation polls pass, the retry poll stops
    assert train.train_project(p, env=ENV12, run=fake, batch=16, should_stop=should_stop) == train.STOPPED
    assert fake.batches == [16]

def test_non_oom_failure_is_not_retried(tmp_path, monkeypatch):
    p = _setup_train(tmp_path, monkeypatch)
    fake = Fake({"piper.train fit": (1, "Some other error\n")})
    assert train.train_project(p, env=ENV12, run=fake) == 1
    assert sum("piper.train" in " ".join(c) for c in fake.calls) == 1

def test_display_edits_during_training_survive(tmp_path, monkeypatch):
    p = _setup_train(tmp_path, monkeypatch)
    class EditingFake(Fake):
        def __call__(self, cmd, **kw):
            if "piper.train" in " ".join(cmd):   # the UI saves new display fields while training runs
                q = Project.load(p.root); q.display["description"] = "Новое описание"; q.save()
            return super().__call__(cmd, **kw)
    assert train.train_project(p, env=ENV12, run=EditingFake({})) == 0
    q = Project.load(p.root)
    assert q.display["description"] == "Новое описание" and q.steps["train"] is True
    assert p.steps["train"] is True

def test_target_already_reached_skips_docker(tmp_path, monkeypatch):
    p = _setup_train(tmp_path, monkeypatch)
    p.base_checkpoint = "x/epoch=100-step=1.ckpt"
    d = p.train_dir / "lightning_logs/version_1/checkpoints"; d.mkdir(parents=True)
    (d / "epoch=1099-val_mel=0.3000.ckpt").write_bytes(b"x"); (d / "last.ckpt").write_bytes(b"x")
    fake, lines = Fake({}), []
    assert train.train_project(p, epochs=1000, env=ENV12, run=fake, on_line=lines.append) == 0
    assert lines == ["Цель уже достигнута (эпоха 1100) — увеличь --epochs"]
    assert not any("piper.train" in " ".join(c) or c[:2] == ["docker", "rm"] for c in fake.calls)
    assert Project.load(p.root).steps["train"] is False

def test_target_not_reached_or_unknown_trains(tmp_path, monkeypatch):
    p = _setup_train(tmp_path, monkeypatch)
    p.base_checkpoint = "x/epoch=100-step=1.ckpt"
    d = p.train_dir / "lightning_logs/version_1/checkpoints"; d.mkdir(parents=True)
    (d / "last.ckpt").write_bytes(b"x")   # epoch unknown → proceed
    fake = Fake({})
    train.train_project(p, epochs=1000, env=ENV12, run=fake)
    (d / "epoch=1098-val_mel=0.3000.ckpt").write_bytes(b"x")
    fake2 = Fake({})
    train.train_project(p, epochs=1000, env=ENV12, run=fake2)
    assert any("piper.train" in " ".join(c) for c in fake.calls) and any("piper.train" in " ".join(c) for c in fake2.calls)

def test_detect_env_nvidia_smi_timeout_means_no_gpu():
    def run(cmd, **kw):
        assert kw.get("timeout")
        if cmd[0] == "nvidia-smi":
            raise subprocess.TimeoutExpired(cmd, kw["timeout"])
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
    env = train.detect_env(run)
    assert env.docker and not env.gpu and env.gpu_name is None and env.vram_mib is None

def test_export_without_docker_is_russian_error(tmp_path):
    p = Project.create(tmp_path / "p", name="p", language="ru")
    last = p.train_dir / "lightning_logs/version_0/checkpoints/last.ckpt"; last.parent.mkdir(parents=True); last.write_bytes(b"x")
    fake = Fake({"docker info": (1, "")})
    with pytest.raises(train.TrainError, match="Docker"):
        train.export_project(p, run=fake)
    assert not any("export_onnx" in " ".join(c) for c in fake.calls)

def test_export_builds_missing_image(tmp_path):
    p = Project.create(tmp_path / "p", name="p", language="ru")
    last = p.train_dir / "lightning_logs/version_0/checkpoints/last.ckpt"; last.parent.mkdir(parents=True); last.write_bytes(b"x")
    fake = Fake({"image inspect": (1, "")})
    train.export_project(p, run=fake)
    joined = [" ".join(c) for c in fake.calls]
    assert joined[0] == "docker info" and any(j.startswith("docker build") for j in joined)
    assert "export_onnx" in joined[-1]

def test_cli_build_needs_no_project(tmp_path, monkeypatch):
    from typer.testing import CliRunner
    from omnivoice.cli import app
    called = []
    monkeypatch.setattr(train, "build_image", lambda run=None: called.append(1))
    monkeypatch.chdir(tmp_path)
    r = CliRunner().invoke(app, ["train", "--build"])
    assert r.exit_code == 0 and called == [1]
