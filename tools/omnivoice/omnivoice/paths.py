import os, sys
from pathlib import Path

def cache_dir() -> Path:
    if env := os.environ.get("OMNIVOICE_CACHE"):
        d = Path(env)
    elif sys.platform == "win32":
        d = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "omnivoice"
    else:
        d = Path.home() / ".cache" / "omnivoice"
    d.mkdir(parents=True, exist_ok=True)
    return d
