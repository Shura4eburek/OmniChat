import os
import urllib.error
import urllib.request
from pathlib import Path
from omnivoice.paths import cache_dir

BASE = "https://huggingface.co/datasets/rhasspy/piper-checkpoints/resolve/main/"

class CheckpointError(RuntimeError):
    pass

def url(path: str) -> str:
    return BASE + path.replace("=", "%3D")

def ensure(path: str, progress=None) -> Path:
    target = cache_dir() / "checkpoints" / path
    if target.is_file():
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_name(target.name + ".part")
    u = url(path)
    for attempt in (0, 1):
        done = part.stat().st_size if part.exists() else 0
        req = urllib.request.Request(u, headers={"Range": f"bytes={done}-"} if done else {})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                if done and getattr(r, "status", 206) != 206:
                    done = 0  # server ignored Range: restart from scratch
                length = int(r.headers.get("Content-Length", 0))
                total = done + length
                with part.open("ab" if done else "wb") as f:
                    while chunk := r.read(1 << 20):
                        f.write(chunk); done += len(chunk)
                        if progress: progress(done, total)
            break
        except urllib.error.HTTPError as e:
            if e.code == 416 and done:
                os.replace(part, target)  # .part is already complete
                return target
            raise CheckpointError(f"Не удалось скачать базовую модель {u}: HTTP {e.code}. Повтори команду") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise CheckpointError(f"Не удалось скачать базовую модель {u}: {e}. Проверь интернет и повтори команду "
                                  f"(загрузка продолжится с места остановки)") from e
    if length and done != total:
        raise CheckpointError(f"Базовая модель {u}: загрузка оборвалась, запусти снова — докачается")
    os.replace(part, target)
    return target
