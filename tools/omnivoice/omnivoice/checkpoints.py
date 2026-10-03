from pathlib import Path
from omnivoice import download
from omnivoice.paths import cache_dir

BASE = "https://huggingface.co/datasets/rhasspy/piper-checkpoints/resolve/main/"

class CheckpointError(RuntimeError):
    pass

def url(path: str) -> str:
    return BASE + path.replace("=", "%3D")

LABEL = "Скачиваю базовую модель Piper (~850 МБ)…"

def local(path: str) -> Path:
    return cache_dir() / "checkpoints" / path

def ensure(path: str, progress=None) -> Path:
    return download.fetch(url(path), local(path), progress=progress,
                          what="базовую модель", error=CheckpointError)
