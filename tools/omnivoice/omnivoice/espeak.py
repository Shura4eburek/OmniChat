from __future__ import annotations
import shutil, tarfile, tempfile, urllib.request
from pathlib import Path
from omnivoice.paths import cache_dir

URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/espeak-ng-data.tar.bz2"

def ensure_espeak_data() -> Path:
    cache = cache_dir()
    target = cache / "espeak-ng-data"
    if (target / "phontab").is_file():
        return target
    archive = cache / "espeak-ng-data.tar.bz2.part"
    tmp = Path(tempfile.mkdtemp(prefix="espeak-", dir=cache))
    try:
        try:
            with urllib.request.urlopen(URL, timeout=60) as resp, open(archive, "wb") as f:
                shutil.copyfileobj(resp, f)
        except Exception as e:
            raise RuntimeError(f"Не удалось скачать espeak-ng-data: {e}") from e
        try:
            with tarfile.open(archive, "r:bz2") as t:
                t.extractall(tmp, filter="data")
        except Exception as e:
            raise RuntimeError(f"Не удалось распаковать espeak-ng-data: {e}") from e
        if not (tmp / "espeak-ng-data" / "phontab").is_file():
            raise RuntimeError("Архив espeak-ng-data не содержит phontab")
        if target.exists():
            shutil.rmtree(target)
        (tmp / "espeak-ng-data").rename(target)
    finally:
        archive.unlink(missing_ok=True)
        shutil.rmtree(tmp, ignore_errors=True)
    return target
