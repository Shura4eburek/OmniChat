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
    monkeypatch.setattr(train, "_clean_base", lambda ckpt, run, be=None: ckpt)

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
    for part in ["--gpus all", "python3 -W ignore /omnivoice_compat/fit.py --omnivoice-base-epoch 4139 "
                 "--omnivoice-last-every 10 fit", ":/omnivoice_compat:ro", "--data.voice_name glados", "--data.espeak_voice ru",
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

def test_no_env_message(tmp_path):
    p = Project.create(tmp_path / "p", name="p", language="ru")
    with pytest.raises(train.TrainError, match=r"Нет среды обучения — нажми «Установить зависимости» \(omnivoice setup\)"):
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
    assert "--trainer.max_epochs 5140" in " ".join(fake.calls[-1])

def test_fit_failure_leaves_step_unset(tmp_path, monkeypatch):
    p = _setup_train(tmp_path, monkeypatch)
    fake = Fake({"fit.py": (3, "")})
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
    assert not any("fit.py" in " ".join(c) for c in fake.calls)
    assert p.steps["train"] is False
    assert len(calls) == stop_at

def test_should_stop_false_still_trains(tmp_path, monkeypatch):
    p = _setup_train(tmp_path, monkeypatch)
    fake = Fake({})
    code = train.train_project(p, env=train.Env(True, True, "RTX", 12000), run=fake, should_stop=lambda: False)
    assert code == 0 and any("fit.py" in " ".join(c) for c in fake.calls)

ENV12 = train.Env(True, True, "RTX", 12000)

class OomFake(Fake):
    """`fit.py` fails with a CUDA OOM line until the batch drops to `ok_at`."""
    def __init__(self, ok_at=None):
        super().__init__({}); self.ok_at = ok_at; self.batches = []
    def __call__(self, cmd, **kw):
        self.calls.append(cmd)
        if "fit.py" in " ".join(cmd):
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
    fits = [" ".join(c) for c in fake.calls if "fit.py" in " ".join(c)]
    assert "--ckpt_path /ckpt/a/b.ckpt" in fits[0] and "last.ckpt" in fits[1]

def test_oom_retry_after_no_resume_ignores_old_run(tmp_path, monkeypatch):
    p = _setup_train(tmp_path, monkeypatch)
    last = p.train_dir / "lightning_logs/version_0/checkpoints/last.ckpt"; last.parent.mkdir(parents=True); last.write_bytes(b"x")
    import os; os.utime(last, (1, 1))  # an older run
    fake = OomFake(ok_at=8)
    train.train_project(p, env=ENV12, run=fake, batch=16, resume=False)
    fits = [" ".join(c) for c in fake.calls if "fit.py" in " ".join(c)]
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
        polls.append(1); return len(polls) > 5   # 4 preparation polls + the pre-launch one pass, the retry poll stops
    assert train.train_project(p, env=ENV12, run=fake, batch=16, should_stop=should_stop) == train.STOPPED
    assert fake.batches == [16]

def test_non_oom_failure_is_not_retried(tmp_path, monkeypatch):
    p = _setup_train(tmp_path, monkeypatch)
    fake = Fake({"fit.py": (1, "Some other error\n")})
    assert train.train_project(p, env=ENV12, run=fake) == 1
    assert sum("fit.py" in " ".join(c) for c in fake.calls) == 1

def test_display_edits_during_training_survive(tmp_path, monkeypatch):
    p = _setup_train(tmp_path, monkeypatch)
    class EditingFake(Fake):
        def __call__(self, cmd, **kw):
            if "fit.py" in " ".join(cmd):   # the UI saves new display fields while training runs
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
    (d / "epoch=1100-val_mel=0.3000.ckpt").write_bytes(b"x"); (d / "last.ckpt").write_bytes(b"x")
    fake, lines = Fake({}), []
    assert train.train_project(p, epochs=1000, env=ENV12, run=fake, on_line=lines.append) == 0
    assert lines == ["Цель уже достигнута (эпоха 1101) — увеличь --epochs"]
    assert not any("fit.py" in " ".join(c) or c[:2] == ["docker", "rm"] for c in fake.calls)
    assert Project.load(p.root).steps["train"] is False

def test_target_not_reached_or_unknown_trains(tmp_path, monkeypatch):
    p = _setup_train(tmp_path, monkeypatch)
    p.base_checkpoint = "x/epoch=100-step=1.ckpt"
    d = p.train_dir / "lightning_logs/version_1/checkpoints"; d.mkdir(parents=True)
    (d / "last.ckpt").write_bytes(b"x")   # epoch unknown → proceed
    fake = Fake({})
    train.train_project(p, epochs=1000, env=ENV12, run=fake)
    (d / "epoch=1099-val_mel=0.3000.ckpt").write_bytes(b"x")
    fake2 = Fake({})
    train.train_project(p, epochs=1000, env=ENV12, run=fake2)
    assert any("fit.py" in " ".join(c) for c in fake.calls) and any("fit.py" in " ".join(c) for c in fake2.calls)

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
    joined = [" ".join(c) for c in fake.calls if c[0] != "wsl"]  # the WSL probe comes first and isn't ready
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


# ---------------- WSL backend ----------------
from omnivoice import wslenv

WSL_PY = ["wsl", "-d", "omnivoice", "-u", "root", "--exec", "/opt/omnivoice/venv/bin/python"]
ENV_WSL = train.Env(False, True, "RTX", 12000, backend="wsl")


class WslFake:
    """Simulates wsl.exe (UTF-16 own output, UTF-8 inside the distro), host nvidia-smi and docker."""
    def __init__(self, ready=True, wsl_gpu=True, docker=True, docker_gpu=True, host_gpu=True):
        self.ready, self.wsl_gpu, self.docker, self.docker_gpu, self.host_gpu = ready, wsl_gpu, docker, docker_gpu, host_gpu
        self.calls = []

    def __call__(self, cmd, **kw):
        self.calls.append(cmd)
        j = " ".join(cmd)
        def r(code, out=""):
            return subprocess.CompletedProcess(cmd, code, stdout=out, stderr="")
        if cmd[:2] == ["wsl", "--status"]: return r(0, "Default Version: 2".encode("utf-16-le"))
        if cmd[:2] == ["wsl", "--version"]: return r(0, "WSL version: 2.3.26.0\n".encode("utf-16-le"))
        if cmd[:3] == ["wsl", "-l", "-q"]: return r(0, "Ubuntu-24.04\nomnivoice\n".encode("utf-16-le"))
        if "cat /opt/omnivoice/READY" in j: return r(0, wslenv.ENV_VERSION.encode() if self.ready else b"old")
        if cmd[0] == "wsl" and "nvidia-smi" in j: return r(0 if self.wsl_gpu else 1)
        if cmd[0] == "nvidia-smi": return r(0, "NVIDIA GeForce RTX 4070, 12282\n") if self.host_gpu else r(1)
        if j == "docker info": return r(0 if self.docker else 1)
        if cmd[:2] == ["docker", "run"] and "nvidia-smi" in j: return r(0 if self.docker_gpu else 1)
        return r(0)


def test_detect_env_prefers_ready_wsl_with_gpu():
    fake = WslFake()
    env = train.detect_env(fake)
    assert env.backend == "wsl" and env.gpu and env.gpu_name == "NVIDIA GeForce RTX 4070" and env.vram_mib == 12282
    assert not any(c[0] == "docker" for c in fake.calls)  # the slow docker probe is skipped


@pytest.mark.parametrize("kw", [dict(ready=False), dict(wsl_gpu=False)])
def test_detect_env_falls_back_to_docker(kw):
    env = train.detect_env(WslFake(**kw))
    assert env.backend == "docker" and env.docker and env.gpu


@pytest.mark.parametrize("kw", [dict(ready=False, docker=False), dict(ready=False, docker_gpu=False)])
def test_detect_env_no_backend(kw, tmp_path):
    env = train.detect_env(WslFake(**kw))
    assert env.backend is None and train.backend_for(env) is None
    p = Project.create(tmp_path / "p", name="p", language="ru")
    with pytest.raises(train.TrainError, match="Нет среды обучения — нажми «Установить зависимости»"):
        train.train_project(p, env=env, run=Fake({}))


def test_backend_for_legacy_env():
    assert train.backend_for(train.Env(True, True, "RTX", 12000)) == "docker"
    assert train.backend_for(train.Env(True, False, None, None)) is None
    assert train.backend_for(ENV_WSL) == "wsl"


def test_wsl_fit_command_exact(tmp_path):
    p = Project.create(tmp_path / "glados", name="glados", language="ru")
    r = wslenv.wsl_path(p.root.resolve())
    cmd = train.WSL.fit(p, "/mnt/c/cache/checkpoints/a/b.ckpt", 24, 3000, resume=False)
    assert cmd == WSL_PY + ["-W", "ignore", wslenv.wsl_path(train.FIT_SCRIPT), "--omnivoice-base-epoch", "4139",
        "--omnivoice-last-every", "10", "fit",
        "--data.voice_name", "glados", "--data.csv_path", f"{r}/train/train.csv",
        "--data.audio_dir", f"{r}/segments/", "--model.sample_rate", "22050", "--data.espeak_voice", "ru",
        "--data.cache_dir", f"{r}/train/cache/", "--data.config_path", f"{r}/train/config.json",
        "--data.batch_size", "24", "--trainer.max_epochs", "3000", "--trainer.default_root_dir", f"{r}/train/",
        "--ckpt_path", "/mnt/c/cache/checkpoints/a/b.ckpt"]
    assert r.startswith("/mnt/")


def test_wsl_fit_resumes_from_last_ckpt(tmp_path):
    p = Project.create(tmp_path / "g", name="g", language="ru")
    last = p.train_dir / "lightning_logs/version_0/checkpoints/last.ckpt"; last.parent.mkdir(parents=True); last.write_bytes(b"x")
    cmd = train.WSL.fit(p, "/mnt/c/base.ckpt", 16, 10, resume=True)
    assert cmd[-1] == wslenv.wsl_path(last.resolve())
    assert cmd[-1].endswith("/train/lightning_logs/version_0/checkpoints/last.ckpt")


def test_wsl_clean_command_exact(tmp_path, monkeypatch):
    monkeypatch.setenv("OMNIVOICE_CACHE", str(tmp_path))
    ckpt = tmp_path / "checkpoints/ru/x/epoch=4139-step=1.ckpt"; ckpt.parent.mkdir(parents=True); ckpt.write_bytes(b"x")
    calls = []
    def run(cmd, **kw):
        calls.append(cmd); (ckpt.parent / "epoch=4139-step=1.clean.ckpt").write_bytes(b"y")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
    out = _REAL_CLEAN(ckpt, run, train.WSL)
    assert out.name == "epoch=4139-step=1.clean.ckpt"
    assert calls == [WSL_PY + ["/opt/omnivoice/clean_ckpt.py", wslenv.wsl_path(ckpt.resolve()),
                               wslenv.wsl_path(out.resolve())]]


def test_wsl_export_command_exact(tmp_path):
    p = Project.create(tmp_path / "p", name="p", language="ru")
    ck = tmp_path / "elsewhere" / "m.ckpt"; ck.parent.mkdir(); ck.write_bytes(b"x")
    assert train.WSL.export(p, ck) == WSL_PY + [
        "-m", "piper.train.export_onnx", "--checkpoint", wslenv.wsl_path(ck.resolve()),
        "--output-file", wslenv.wsl_path((p.export_dir / "model.onnx").resolve())]


def test_wsl_export_project_uses_wsl_when_ready(tmp_path):
    p = Project.create(tmp_path / "p", name="p", language="ru")
    last = p.train_dir / "lightning_logs/version_0/checkpoints/last.ckpt"; last.parent.mkdir(parents=True); last.write_bytes(b"x")
    fake = WslFake(docker=False)
    assert train.export_project(p, run=fake) == p.export_dir / "model.onnx"
    assert fake.calls[-1][:len(WSL_PY)] == WSL_PY and "piper.train.export_onnx" in fake.calls[-1]
    assert not any(c[0] == "docker" for c in fake.calls)


def test_wsl_train_project_end_to_end(tmp_path, monkeypatch):
    p = _setup_train(tmp_path, monkeypatch)
    fake = Fake({})
    assert train.train_project(p, env=ENV_WSL, run=fake) == 0 and p.steps["train"] is True
    fit = fake.calls[-1]
    assert fit[:len(WSL_PY)] == WSL_PY
    assert fit[fit.index("--ckpt_path") + 1] == wslenv.wsl_path((tmp_path / "cache/checkpoints/a/b.ckpt").resolve())
    assert not any(c[0] == "docker" for c in fake.calls)  # no image build, no `docker rm`


def test_wsl_oom_retry(tmp_path, monkeypatch):
    p = _setup_train(tmp_path, monkeypatch)
    fake, lines = OomFake(ok_at=6), []
    assert train.train_project(p, env=ENV_WSL, run=fake, batch=24, on_line=lines.append) == 0
    assert fake.batches == [24, 12, 6] and "Не хватило видеопамяти — уменьшаю батч до 12 и продолжаю" in lines
    assert all(c[0] == "wsl" for c in fake.calls)


def test_wsl_unmappable_project_path_is_russian(tmp_path, monkeypatch):
    p = _setup_train(tmp_path, monkeypatch)
    def boom(x):
        raise wslenv.WslError("Путь недоступен из WSL")
    monkeypatch.setattr(wslenv, "wsl_path", boom)
    with pytest.raises(train.TrainError, match="недоступен из WSL"):
        train.train_project(p, env=ENV_WSL, run=Fake({}))


def test_stop_commands():
    class P: name = "glados"
    assert train.WSL.stop(P()) == ["wsl", "-d", "omnivoice", "-u", "root", "--exec", "pkill", "-f", "piper_compat/fit.py|piper.train"]
    assert train.DOCKER.stop(P()) == ["docker", "stop", "omnivoice-train-glados"]


def test_stop_training_uses_active_backend(tmp_path, monkeypatch):
    p = _setup_train(tmp_path, monkeypatch)
    stops = []
    def run(cmd, **kw):
        stops.append(cmd); return subprocess.CompletedProcess(cmd, 0)
    train.stop_training(p, run=run)   # nothing running: the legacy docker stop (a no-op)
    seen = []
    class Stopper(Fake):
        def __call__(self, cmd, **kw):
            if "fit.py" in " ".join(cmd):
                train.stop_training(p, run=run)   # the UI Stop while the fit runs
                seen.append(1)
            return super().__call__(cmd, **kw)
    train.train_project(p, env=ENV_WSL, run=Stopper({}))
    assert seen == [1]
    assert stops == [train.DOCKER.stop(p), wslenv.wsl_cmd("pkill", "-f", "piper_compat/fit.py|piper.train")]
    train.stop_training(p, run=run)   # finished: forgotten again
    assert stops[-1] == train.DOCKER.stop(p)


def test_stream_ctrl_c_runs_backend_stop(monkeypatch):
    def lines_then_ctrl_c():
        yield "epoch 1\n"
        raise KeyboardInterrupt
    class Proc:
        def __init__(self, *a, **k): self.stdout = lines_then_ctrl_c()
        def wait(self, timeout=None): return 0
    monkeypatch.setattr(train.subprocess, "Popen", Proc)
    ran, lines = [], []
    monkeypatch.setattr(train.subprocess, "run", lambda cmd, **kw: ran.append(cmd))
    stop = wslenv.wsl_cmd("pkill", "-f", "piper_compat/fit.py|piper.train")
    assert train._stream(["x"], lines.append, stop) == 130
    assert ran == [stop] and lines == ["epoch 1", "Обучение остановлено — продолжить: omnivoice train"]


def test_wsl_ready_without_gpu_and_no_docker_explains_driver(tmp_path):
    env = train.detect_env(WslFake(wsl_gpu=False, docker=False))
    assert env.backend is None and env.wsl_ready and env.wsl_gpu is False
    p = Project.create(tmp_path / "p", name="p", language="ru")
    with pytest.raises(train.TrainError) as e:
        train.train_project(p, env=env, run=Fake({}))
    assert str(e.value) == ("Среда WSL готова, но не видит видеокарту NVIDIA — обнови драйвер NVIDIA "
                            "и перезапусти компьютер (или используй Colab)")


def test_detect_env_records_wsl_state():
    env = train.detect_env(WslFake())
    assert env.wsl_ready and env.wsl_gpu is True
    env = train.detect_env(WslFake(ready=False))
    assert not env.wsl_ready and env.backend == "docker"
    assert train.Env(True, True, "RTX", 12000).wsl_ready is False  # old-style construction still works


def test_should_stop_after_clean_base(tmp_path, monkeypatch):
    p = _setup_train(tmp_path, monkeypatch)
    polls = []
    def should_stop():
        polls.append(1); return len(polls) >= 4   # csv, download, prepare pass; the post-clean poll stops
    fake = Fake({})
    assert train.train_project(p, env=ENV_WSL, run=fake, should_stop=should_stop) == train.STOPPED
    assert not any("fit.py" in " ".join(c) for c in fake.calls) and len(polls) == 4


@pytest.mark.parametrize("exc", [FileNotFoundError("docker"), OSError("nope")])
def test_stop_training_without_docker_is_quiet(tmp_path, exc):
    p = Project.create(tmp_path / "p", name="p", language="ru")
    def run(cmd, **kw):
        raise exc
    assert train.stop_training(p, run=run) is None

def test_target_epochs_counts_base_as_done(tmp_path):
    p = Project.create(tmp_path / "t", name="t", language="ru")
    p.base_checkpoint = "x/epoch=4139-step=1.ckpt"
    assert train.target_epochs(p, 2) == 4142   # epochs 4140 and 4141 are the 2 new ones


def test_train_logs_checkpoint_size_only_when_downloading(tmp_path, monkeypatch):
    p = Project.create(tmp_path / "p", name="p", language="ru")
    monkeypatch.setattr(dataset, "piper_csv", lambda p, out: 5)
    monkeypatch.setenv("OMNIVOICE_CACHE", str(tmp_path / "cache"))
    ck = tmp_path / "cache" / "checkpoints" / p.base_checkpoint
    def ensure(path, progress=None):
        ck.parent.mkdir(parents=True, exist_ok=True); ck.write_bytes(b"x"); return ck
    monkeypatch.setattr(checkpoints, "ensure", ensure)
    monkeypatch.setattr(train, "cache_dir", lambda: tmp_path / "cache")
    env = train.Env(True, True, "RTX", 12000)
    lines = []
    assert train.train_project(p, env=env, run=Fake({}), on_line=lines.append) == 0
    assert checkpoints.LABEL in lines and "МБ" in checkpoints.LABEL
    lines.clear()
    train.train_project(p, env=env, run=Fake({}), on_line=lines.append, resume=False)
    assert checkpoints.LABEL not in lines  # already cached


def test_fit_script_options_and_schedule():
    from omnivoice.piper_compat import fit
    argv = ["--omnivoice-base-epoch", "2436", "--omnivoice-last-every", "10", "fit", "--data.batch_size", "24"]
    assert fit.pop_int(argv, "--omnivoice-base-epoch", 0) == 2436 and fit.pop_int(argv, "--omnivoice-last-every", 1) == 10
    assert argv == ["fit", "--data.batch_size", "24"] and fit.pop_int(argv, "--missing", 7) == 7
    # warm-up: max(20, 5 % of the planned epochs) after the base, as the checkpoints page hides
    assert fit.warmup_end(2436, 2437 + 100) == 2437 + 20 and fit.warmup_end(2436, 2437 + 1000) == 2437 + 50
    assert [e for e in range(2437, 2467) if fit.last_due(e, 2467, 10, False)] == [2439, 2449, 2459, 2466]
    assert fit.last_due(2440, 2467, 10, stopping=True)


def test_graceful_stop_returns_stopped_and_clears_the_request(tmp_path, monkeypatch):
    p = _setup_train(tmp_path, monkeypatch)
    (p.train_dir / train.STOP_FILE).write_text("")   # left by an earlier run: must not stop this one
    def run(cmd, **kw):
        if "fit.py" in " ".join(cmd):
            assert not (p.train_dir / train.STOP_FILE).exists()
            train.request_stop(p)                      # the Stop button while fit.py runs
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
    assert train.train_project(p, env=ENV12, run=run, batch=16) == train.STOPPED
    assert not (p.train_dir / train.STOP_FILE).exists() and not p.steps.get("train")


def test_sparse_last_ckpt_epoch_comes_from_its_note(tmp_path):
    from tests.test_previews import ckpts
    p = Project.create(tmp_path / "p", name="p", language="ru")
    d = ckpts(p, "version_0", ["epoch=4200-val_mel=0.3000.ckpt", "last.ckpt"])
    (d / "last.epoch").write_text("4195")
    from omnivoice import previews
    assert next(r for r in previews.rank_checkpoints(p) if r.last).epoch == 4195
