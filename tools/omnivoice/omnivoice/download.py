"""Resumable downloads: a .part file, HTTP Range resume, one retry, optional pinned sha256, Russian errors."""
from __future__ import annotations
import hashlib
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Iterable

TIMEOUT = 60
CHUNK = 1 << 20


class DownloadError(RuntimeError):
    pass


class _Missing(Exception):
    """This mirror has no such file; try the next one."""


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        while chunk := f.read(CHUNK):
            h.update(chunk)
    return h.hexdigest()


def fetch(urls: str | Iterable[str], target: Path, *, progress: Callable[[int, int], None] | None = None,
          sha256: str | None = None, what: str = "файл", error: type[Exception] = DownloadError) -> Path:
    """Download the first available URL to target. Existing valid target → no network."""
    urls = [urls] if isinstance(urls, str) else list(urls)
    target = Path(target)
    if target.is_file():
        if sha256 is None or sha256_of(target) == sha256:
            return target
        target.unlink()
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_name(target.name + ".part")
    for i, u in enumerate(urls):
        try:
            _get(u, part, progress, what, error, last=i == len(urls) - 1)
            break
        except _Missing:
            continue
    if sha256 is not None and (got := sha256_of(part)) != sha256:
        part.unlink()
        raise error(f"Не удалось скачать {what} {u}: контрольная сумма не совпала (ожидалась {sha256}, "
                    f"получена {got}). Файл удалён — повтори команду")
    os.replace(part, target)
    return target


def _get(u: str, part: Path, progress, what: str, error, last: bool) -> None:
    for attempt in (0, 1):
        done = part.stat().st_size if part.exists() else 0
        req = urllib.request.Request(u, headers={"Range": f"bytes={done}-"} if done else {})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                if done and getattr(r, "status", 206) != 206:
                    done = 0  # server ignored Range: restart from scratch
                length = int(r.headers.get("Content-Length", 0))
                total = done + length
                with part.open("ab" if done else "wb") as f:
                    while chunk := r.read(CHUNK):
                        f.write(chunk); done += len(chunk)
                        if progress: progress(done, total)
        except urllib.error.HTTPError as e:
            if e.code == 416 and done:
                return  # .part is already complete
            if e.code in (404, 410) and not last:
                raise _Missing() from e
            raise error(f"Не удалось скачать {what} {u}: HTTP {e.code}. Повтори команду") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            if attempt == 0:
                continue
            raise error(f"Не удалось скачать {what} {u}: {e}. Проверь интернет и повтори команду "
                        f"(загрузка продолжится с места остановки)") from e
        if not length or done == total:
            return
    raise error(f"Не удалось скачать {what} {u}: загрузка оборвалась — запусти снова, докачается")
