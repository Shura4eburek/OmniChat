"""Fine-tuning piper in one of two backends: the own WSL2 distro «omnivoice» (preferred, see wslenv)
or a Docker image (fallback). The training loop (OOM retry, relative epochs, target check, Stop) is
backend-agnostic; a backend only builds command lines (see DockerBackend / WslBackend)."""
from __future__ import annotations
import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from omnivoice import checkpoints, dataset, wslenv
from omnivoice.paths import cache_dir

IMAGE = "omnivoice-train:0.1"
DOCKER_DIR = Path(__file__).resolve().parent / "piper_compat"
VENV_PY = f"{wslenv.ROOT}/venv/bin/python"
CLEAN_SCRIPT = "/opt/omnivoice/clean_ckpt.py"  # same path in the Docker image and in the WSL distro
NO_ENV = "Нет среды обучения — нажми «Установить зависимости» (omnivoice setup)"
WSL_NO_GPU = ("Среда WSL готова, но не видит видеокарту NVIDIA — обнови драйвер NVIDIA "
              "и перезапусти компьютер (или используй Colab)")

class TrainError(Exception):
    pass

@dataclass
class Env:
    docker: bool
    gpu: bool  # the chosen backend sees an NVIDIA GPU (for "docker": `docker run --gpus all` works)
    gpu_name: str | None
    vram_mib: int | None
    backend: str | None = None  # "wsl" | "docker" | None (no usable training environment)
    wsl_ready: bool = False  # the omnivoice distro is provisioned (READY marker matches)
    wsl_gpu: bool | None = None  # nvidia-smi works inside it (None: not checked)

def _docker_ok(run) -> bool:
    try:
        return run(["docker", "info"], capture_output=True, text=True, timeout=20).returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False

def _wsl_ready(run) -> wslenv.EnvStatus | None:
    try:
        return wslenv.status(run)
    except Exception:  # a broken WSL must never hide the Docker fallback
        return None

def detect_env(run=subprocess.run) -> Env:
    """WSL distro ready + GPU → "wsl"; else Docker with a GPU → "docker"; else backend None.
    gpu_name / vram_mib come from the host nvidia-smi (batch size) whatever the backend."""
    name = vram = None
    try:
        r = run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=20)
        if r.returncode == 0 and r.stdout.strip():
            n, v = r.stdout.strip().splitlines()[0].rsplit(",", 1)
            name, vram = n.strip(), int(float(v))
    except (FileNotFoundError, subprocess.TimeoutExpired):
        name = vram = None
    st = _wsl_ready(run)
    wsl_ready = bool(st and st.ready)
    wsl_gpu = st.gpu if wsl_ready else None  # status() already ran WSL.gpu_ok
    if wsl_ready and wsl_gpu:
        return Env(False, True, name, vram, "wsl", True, True)  # the slow Docker probe isn't needed
    docker = _docker_ok(run)
    gpu = docker and name is not None and DOCKER.gpu_ok(run)
    return Env(docker, gpu, name, vram, "docker" if gpu else None, wsl_ready, wsl_gpu)

def backend_for(env: Env) -> str | None:
    if env.backend in BACKENDS:
        return env.backend
    if env.backend is None and env.docker and env.gpu:
        return "docker"  # an Env built without a backend (older callers): Docker was the only one
    return None

def batch_size_for(vram_mib: int | None) -> int:
    if vram_mib is None: return 16
    if vram_mib < 8000: return 8
    if vram_mib < 12000: return 16
    if vram_mib < 20000: return 24
    return 32

def build_image(run=subprocess.run) -> None:
    if run(["docker", "build", "-t", IMAGE, str(DOCKER_DIR)]).returncode != 0:
        raise TrainError("Сборка Docker-образа не удалась (см. вывод выше)")

def _container(p, host: Path) -> str:
    return "/work/" + host.resolve().relative_to(p.root.resolve()).as_posix()

def last_checkpoint(p) -> Path | None:
    found = sorted(p.train_dir.glob("lightning_logs/*/checkpoints/last.ckpt"), key=lambda f: f.stat().st_mtime)
    return found[-1] if found else None

def fit_args(p, ckpt: str, batch: int, max_epochs: int, root: str) -> list[str]:
    return ["python3", "-m", "piper.train", "fit",
            "--data.voice_name", p.name,
            "--data.csv_path", f"{root}/train/train.csv",
            "--data.audio_dir", f"{root}/segments/",
            "--model.sample_rate", str(p.sample_rate),
            "--data.espeak_voice", p.espeak_voice,
            "--data.cache_dir", f"{root}/train/cache/",
            "--data.config_path", f"{root}/train/config.json",
            "--data.batch_size", str(batch),
            "--trainer.max_epochs", str(max_epochs),
            "--trainer.default_root_dir", f"{root}/train/",
            "--ckpt_path", ckpt]

def container_name(p) -> str:
    return "omnivoice-train-" + re.sub(r"[^A-Za-z0-9_.-]", "_", p.name)

def base_epoch(p) -> int:
    m = re.search(r"epoch=(\d+)", p.base_checkpoint)
    return int(m.group(1)) if m else 0

def fit_command(p, ckpt_in_container: str, batch: int, max_epochs: int, resume: bool) -> list[str]:
    last = last_checkpoint(p) if resume else None
    ckpt = _container(p, last) if last else ckpt_in_container
    return ["docker", "run", "--rm", "--name", container_name(p), "--gpus", "all", "--shm-size=8g",
            "-v", f"{p.root.resolve()}:/work", "-v", f"{(cache_dir() / 'checkpoints').resolve()}:/ckpt",
            # torch.hub cache: the UTMOS quality model (~400 MB) is downloaded once, not every run
            "-v", f"{(cache_dir() / 'torch-hub').resolve()}:/root/.cache/torch",
            IMAGE, *fit_args(p, ckpt, batch, max_epochs, "/work")]

def export_command(p, ckpt_container_path: str, extra_mount: Path | None = None) -> list[str]:
    extra = ["-v", f"{extra_mount.resolve()}:/ckptin"] if extra_mount else []
    return ["docker", "run", "--rm", "-v", f"{p.root.resolve()}:/work", *extra, IMAGE,
            "python3", "-m", "piper.train.export_onnx", "--checkpoint", ckpt_container_path,
            "--output-file", "/work/export/model.onnx"]


class DockerBackend:
    name = "docker"

    def gpu_ok(self, run) -> bool:
        try:
            have = run(["docker", "image", "inspect", IMAGE], capture_output=True, timeout=20).returncode == 0
            return run(["docker", "run", "--rm", "--gpus", "all",
                        IMAGE if have else "nvidia/cuda:12.6.0-base-ubuntu22.04", "nvidia-smi"],
                       capture_output=True, text=True, timeout=120).returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def prepare(self, run) -> None:
        _ensure_image(run)

    def base_ckpt(self, ckpt: Path) -> str:
        return "/ckpt/" + ckpt.resolve().relative_to((cache_dir() / "checkpoints").resolve()).as_posix()

    def fit(self, p, ckpt: str, batch: int, max_epochs: int, resume: bool) -> list[str]:
        return fit_command(p, ckpt, batch, max_epochs, resume)

    def clean(self, src: Path, dst: Path) -> list[str]:
        root = (cache_dir() / "checkpoints").resolve()
        rel, rel_dst = (x.resolve().relative_to(root).as_posix() for x in (src, dst))
        return ["docker", "run", "--rm", "-v", f"{root}:/ckpt", IMAGE,
                "python3", CLEAN_SCRIPT, f"/ckpt/{rel}", f"/ckpt/{rel_dst}"]

    def export(self, p, ckpt: Path) -> list[str]:
        try:
            return export_command(p, _container(p, ckpt))
        except ValueError:  # outside the project: mount its folder
            return export_command(p, "/ckptin/" + Path(ckpt).name, Path(ckpt).resolve().parent)

    def before_fit(self, p) -> list[str] | None:
        return ["docker", "rm", "-f", container_name(p)]  # a container left by a crashed run

    def stop(self, p) -> list[str]:
        return ["docker", "stop", container_name(p)]


def _wp(path) -> str:
    try:
        return wslenv.wsl_path(Path(path).resolve())
    except wslenv.WslError as e:
        raise TrainError(str(e)) from e


class WslBackend:
    """Runs inside the «omnivoice» distro; Windows files are reached through /mnt/<drive>/…"""
    name = "wsl"

    def gpu_ok(self, run) -> bool:
        return wslenv.gpu_ok(run)

    def prepare(self, run) -> None:
        pass  # provisioned by `omnivoice setup` (wslenv.ensure_ready)

    def base_ckpt(self, ckpt: Path) -> str:
        return _wp(ckpt)

    def fit(self, p, ckpt: str, batch: int, max_epochs: int, resume: bool) -> list[str]:
        last = last_checkpoint(p) if resume else None
        args = fit_args(p, _wp(last) if last else ckpt, batch, max_epochs, _wp(p.root))
        return wslenv.wsl_cmd(VENV_PY, *args[1:])  # fit_args starts with the Docker image's python3

    def clean(self, src: Path, dst: Path) -> list[str]:
        return wslenv.wsl_cmd(VENV_PY, CLEAN_SCRIPT, _wp(src), _wp(dst))

    def export(self, p, ckpt: Path) -> list[str]:
        return wslenv.wsl_cmd(VENV_PY, "-m", "piper.train.export_onnx", "--checkpoint", _wp(ckpt),
                              "--output-file", _wp(p.export_dir / "model.onnx"))

    def before_fit(self, p) -> list[str] | None:
        return None

    def stop(self, p) -> list[str]:
        return wslenv.wsl_cmd("pkill", "-f", "piper.train")


DOCKER, WSL = DockerBackend(), WslBackend()
BACKENDS = {b.name: b for b in (DOCKER, WSL)}
_ACTIVE: dict[str, str] = {}  # container_name(p) → backend of the run in progress (for stop_training)


def stop_training(p, run=subprocess.run, timeout: int = 60):
    """Stop p's training in whichever backend runs it (the UI Stop button). Before a backend is
    chosen nothing has been launched; the legacy `docker stop` is then a harmless no-op."""
    active = _ACTIVE.get(container_name(p))
    if active:
        return run(BACKENDS[active].stop(p), capture_output=True, timeout=timeout)
    try:
        return run(DOCKER.stop(p), capture_output=True, timeout=timeout)
    except OSError:  # no Docker installed (FileNotFoundError is an OSError): nothing to stop
        return None


def _stream(cmd: list[str], on_line, stop_cmd: list[str] | None = None) -> int:
    # WSL_UTF8: wsl.exe's own messages in UTF-8 too (the training output itself is UTF-8 anyway)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            encoding="utf-8", errors="replace", env={**os.environ, "WSL_UTF8": "1"})
    try:
        for line in proc.stdout:
            if on_line: on_line(line.rstrip())
        return proc.wait()
    except KeyboardInterrupt:
        if stop_cmd:
            try:
                subprocess.run(stop_cmd, capture_output=True, timeout=120)
            except (OSError, subprocess.SubprocessError):
                pass
        try:
            proc.wait(timeout=30)
        except Exception:
            proc.kill()
        if on_line: on_line("Обучение остановлено — продолжить: omnivoice train")
        return 130

def _ensure_image(run) -> None:
    if run(["docker", "image", "inspect", IMAGE], capture_output=True).returncode != 0:
        build_image(run)

def _clean_base(ckpt: Path, run, be=None) -> Path:
    """Old rhasspy checkpoints carry hparams newer Lightning rejects; make a cleaned sibling once."""
    clean = ckpt.with_name(ckpt.stem + ".clean.ckpt")
    if clean.is_file():
        return clean
    r = run((be or DOCKER).clean(ckpt, clean), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0 or not clean.is_file():
        tail = (r.stderr or "")[-300:]
        raise TrainError(f"Не удалось подготовить базовую модель: {tail}")
    return clean

STOPPED = 130  # returned when should_stop() asked to abort before the container started
MIN_BATCH = 4
_OOM_MARKERS = ("CUDA out of memory", "OutOfMemoryError")


def newest_epoch(p) -> int | None:
    """Highest epoch among checkpoints whose name carries one (last.ckpt alone is unknown)."""
    from omnivoice import previews
    epochs = [c.epoch for c in previews.list_checkpoints(p) if c.metric is not None]
    return max(epochs) if epochs else None


def _run_fit(cmd, run, on_line, stop_cmd) -> int:
    if run is subprocess.run:
        return _stream(cmd, on_line, stop_cmd)
    r = run(cmd)  # injected runner (tests): replay its stdout as log lines
    for line in (getattr(r, "stdout", "") or "").splitlines():
        on_line(line)
    return r.returncode


def train_project(p, epochs: int = 1000, resume: bool = True, run=subprocess.run, env: Env | None = None,
                  on_line=None, batch: int | None = None, progress=None, should_stop=None) -> int:
    """should_stop: optional callable polled between the preparation steps (dataset csv, checkpoint
    download, image build); True aborts with STOPPED before any training process is launched."""
    stop = should_stop or (lambda: False)
    env = env or detect_env(run)
    name = backend_for(env)
    if name is None:
        if env.wsl_ready and env.wsl_gpu is False and not (env.docker and env.gpu):
            raise TrainError(WSL_NO_GPU)
        why = " (Docker не видит видеокарту NVIDIA)" if env.docker and not env.gpu else ""
        raise TrainError(f"{NO_ENV}{why} или обучай в Colab: omnivoice train --colab")
    be = BACKENDS[name]
    if dataset.piper_csv(p, p.train_dir / "train.csv") == 0:
        raise TrainError("Нет ни одной фразы с текстом для обучения")
    target = base_epoch(p) + epochs
    if resume:
        done = newest_epoch(p)  # Lightning's epoch=N in checkpoint names is 0-based
        if done is not None and done + 1 >= target:
            if on_line: on_line(f"Цель уже достигнута (эпоха {done + 1}) — увеличь --epochs")
            return 0
    if stop():
        return STOPPED
    try:
        ckpt = checkpoints.ensure(p.base_checkpoint, progress=progress)
    except checkpoints.CheckpointError as e:
        raise TrainError(str(e)) from e
    if stop():
        return STOPPED
    be.prepare(run)
    if stop():
        return STOPPED
    ckpt = _clean_base(ckpt, run, be)
    if stop():
        return STOPPED
    base_ckpt = be.base_ckpt(ckpt)
    bs = batch or batch_size_for(env.vram_mib)
    key = container_name(p)
    _ACTIVE[key] = be.name
    try:
        return _fit_loop(p, be, run, on_line, stop, base_ckpt, bs, target, resume)
    finally:
        _ACTIVE.pop(key, None)


def _fit_loop(p, be, run, on_line, stop, base_ckpt: str, bs: int, target: int, resume: bool) -> int:
    started = time.time()
    while True:
        oom = False
        def handle(line: str) -> None:
            nonlocal oom
            if any(m in line for m in _OOM_MARKERS):
                oom = True
            if on_line: on_line(line)
        cmd = be.fit(p, base_ckpt, bs, target, resume)
        pre = be.before_fit(p)
        if pre:
            try:
                run(pre, capture_output=True)
            except Exception:
                pass
        code = _run_fit(cmd, run, handle, be.stop(p))
        if code in (0, STOPPED) or not oom:
            break
        if stop():
            return STOPPED
        if bs <= MIN_BATCH:
            raise TrainError(f"Не хватило видеопамяти даже с батчем {bs}. Закрой другие программы, "
                             "использующие видеокарту, или обучай в Colab: omnivoice train --colab")
        bs = max(MIN_BATCH, bs // 2)
        last = last_checkpoint(p)
        # resume only from a checkpoint this run wrote, never from an older run after --no-resume
        resume = resume or (last is not None and last.stat().st_mtime >= started)
        if on_line: on_line(f"Не хватило видеопамяти — уменьшаю батч до {bs} и продолжаю")
    if code == 0:
        p.mark_fresh("train")
    return code

def export_project(p, ckpt: Path | None = None, run=subprocess.run) -> Path:
    ckpt = ckpt or last_checkpoint(p)
    if ckpt is None:
        raise TrainError("Нет чекпойнтов — сначала обучи модель")
    st = _wsl_ready(run)  # export needs no GPU: a ready distro is enough
    if st and st.ready:
        be = WSL
    elif _docker_ok(run):
        be = DOCKER
    else:
        raise TrainError("Нет среды для экспорта в ONNX — нажми «Установить зависимости» (omnivoice setup), "
                         "запусти Docker Desktop или экспортируй в Colab")
    be.prepare(run)
    p.export_dir.mkdir(parents=True, exist_ok=True)
    if run(be.export(p, Path(ckpt))).returncode != 0:
        raise TrainError("Экспорт в ONNX не удался")
    return p.export_dir / "model.onnx"
