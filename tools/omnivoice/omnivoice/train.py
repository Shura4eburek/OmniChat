from __future__ import annotations
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from omnivoice import checkpoints, dataset
from omnivoice.paths import cache_dir

IMAGE = "omnivoice-train:0.1"
DOCKER_DIR = Path(__file__).resolve().parent / "piper_compat"

class TrainError(Exception):
    pass

@dataclass
class Env:
    docker: bool
    gpu: bool
    gpu_name: str | None
    vram_mib: int | None

def detect_env(run=subprocess.run) -> Env:
    try:
        docker = run(["docker", "info"], capture_output=True, text=True, timeout=20).returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        docker = False
    name = vram = None
    try:
        r = run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=20)
        if r.returncode == 0 and r.stdout.strip():
            n, v = r.stdout.strip().splitlines()[0].rsplit(",", 1)
            name, vram = n.strip(), int(float(v))
    except (FileNotFoundError, subprocess.TimeoutExpired):
        name = vram = None
    gpu = False
    if docker and name:
        try:
            have = run(["docker", "image", "inspect", IMAGE], capture_output=True, timeout=20).returncode == 0
            gpu = run(["docker", "run", "--rm", "--gpus", "all",
                       IMAGE if have else "nvidia/cuda:12.6.0-base-ubuntu22.04", "nvidia-smi"],
                      capture_output=True, text=True, timeout=120).returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            gpu = False
    return Env(docker, gpu, name, vram)

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

def _stream(cmd: list[str], on_line, name: str | None = None) -> int:
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            encoding="utf-8", errors="replace")
    try:
        for line in proc.stdout:
            if on_line: on_line(line.rstrip())
        return proc.wait()
    except KeyboardInterrupt:
        if name:
            try:
                subprocess.run(["docker", "stop", name], capture_output=True, timeout=120)
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

def _clean_base(ckpt: Path, run) -> Path:
    """Old rhasspy checkpoints carry hparams newer Lightning rejects; make a cleaned sibling once."""
    clean = ckpt.with_name(ckpt.stem + ".clean.ckpt")
    if clean.is_file():
        return clean
    root = (cache_dir() / "checkpoints").resolve()
    rel = ckpt.resolve().relative_to(root).as_posix()
    rel_clean = clean.resolve().relative_to(root).as_posix()
    r = run(["docker", "run", "--rm", "-v", f"{root}:/ckpt", IMAGE,
             "python3", "/opt/omnivoice/clean_ckpt.py", f"/ckpt/{rel}", f"/ckpt/{rel_clean}"],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
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


def _run_fit(cmd, run, on_line, name) -> int:
    if run is subprocess.run:
        return _stream(cmd, on_line, name)
    r = run(cmd)  # injected runner (tests): replay its stdout as log lines
    for line in (getattr(r, "stdout", "") or "").splitlines():
        on_line(line)
    return r.returncode


def train_project(p, epochs: int = 1000, resume: bool = True, run=subprocess.run, env: Env | None = None,
                  on_line=None, batch: int | None = None, progress=None, should_stop=None) -> int:
    """should_stop: optional callable polled between the preparation steps (dataset csv, checkpoint
    download, image build); True aborts with STOPPED before any container is launched."""
    stop = should_stop or (lambda: False)
    env = env or detect_env(run)
    if not env.docker:
        raise TrainError("Docker не найден. Установи Docker Desktop или используй Colab: omnivoice train --colab")
    if not env.gpu:
        raise TrainError("Docker не видит видеокарту NVIDIA. Используй Colab: omnivoice train --colab")
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
    _ensure_image(run)
    if stop():
        return STOPPED
    ckpt = _clean_base(ckpt, run)
    base_ckpt = "/ckpt/" + ckpt.resolve().relative_to((cache_dir() / "checkpoints").resolve()).as_posix()
    bs = batch or batch_size_for(env.vram_mib)
    name = container_name(p)
    started = time.time()
    while True:
        oom = False
        def handle(line: str) -> None:
            nonlocal oom
            if any(m in line for m in _OOM_MARKERS):
                oom = True
            if on_line: on_line(line)
        cmd = fit_command(p, base_ckpt, bs, target, resume)
        try:
            run(["docker", "rm", "-f", name], capture_output=True)
        except Exception:
            pass
        code = _run_fit(cmd, run, handle, name)
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
    try:
        docker = run(["docker", "info"], capture_output=True, text=True, timeout=20).returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        docker = False
    if not docker:
        raise TrainError("Docker не найден или не запущен — экспорт в ONNX идёт в Docker. "
                         "Запусти Docker Desktop или экспортируй в Colab")
    _ensure_image(run)
    try:
        cpath, extra = _container(p, ckpt), None
    except ValueError:
        cpath, extra = "/ckptin/" + Path(ckpt).name, Path(ckpt).resolve().parent
    if run(export_command(p, cpath, extra)).returncode != 0:
        raise TrainError("Экспорт в ONNX не удался")
    return p.export_dir / "model.onnx"
