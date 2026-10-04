from pathlib import Path
from omnivoice import download
from omnivoice.paths import cache_dir

BASE = "https://huggingface.co/datasets/rhasspy/piper-checkpoints/resolve/main/"

class CheckpointError(RuntimeError):
    pass

def url(path: str) -> str:
    return BASE + path.replace("=", "%3D")

LABEL = "Скачиваю базовую модель Piper (~850 МБ)…"
SAMPLES = "https://huggingface.co/rhasspy/piper-voices/resolve/main/"


def sample_url(path: str) -> str:
    """The published voice sample of a base checkpoint (piper-voices keeps one per voice / quality)."""
    return SAMPLES + path.rsplit("/", 1)[0] + "/samples/speaker_0.mp3"


def sample(path: str) -> Path:
    """The base voice's sample, downloaded once (~80 КБ) into the cache."""
    return download.fetch(sample_url(path), cache_dir() / "samples" / (path.rsplit("/", 1)[0] + ".mp3"),
                          what="пример голоса", error=CheckpointError)

def local(path: str) -> Path:
    return cache_dir() / "checkpoints" / path

def ensure(path: str, progress=None) -> Path:
    return download.fetch(url(path), local(path), progress=progress,
                          what="базовую модель", error=CheckpointError)
