from pathlib import Path
from omnivoice import download
from omnivoice.paths import cache_dir

BASE = "https://huggingface.co/datasets/rhasspy/piper-checkpoints/resolve/main/"

class CheckpointError(RuntimeError):
    pass

def url(path: str) -> str:
    return BASE + path.replace("=", "%3D")

def ensure(path: str, progress=None) -> Path:
    return download.fetch(url(path), cache_dir() / "checkpoints" / path, progress=progress,
                          what="базовую модель", error=CheckpointError)
