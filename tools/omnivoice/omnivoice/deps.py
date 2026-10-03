"""Windows-side dependencies: prep/ui extras, ffmpeg, and the WSL training environment (via wslenv)."""
from __future__ import annotations
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from omnivoice import download, wslenv
from omnivoice.paths import cache_dir

# gyan.dev "release essentials" 9.0.2 (GPL build); the sha256 is the one published next to the zip
# (https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-9.0.2-essentials_build.zip.sha256). The GitHub mirror holds the same file.
FFMPEG_URLS = (
    "https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-9.0.2-essentials_build.zip",
    "https://github.com/GyanD/codexffmpeg/releases/download/9.0.2/ffmpeg-9.0.2-essentials_build.zip",
)
FFMPEG_SHA256 = "60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba"
FFMPEG_ZIP = "ffmpeg-9.0.2-essentials_build.zip"
FFMPEG_EXES = ("ffmpeg.exe", "ffprobe.exe")
PREP_MODULES = ("faster_whisper", "silero_vad", "demucs", "pyloudnorm", "gradio", "tensorboard")
HINT = "нажми «Установить зависимости» (omnivoice setup)"
PREP, FFMPEG, WSL, ENV = "Пакеты (prep, ui)", "ffmpeg", "WSL", "Среда обучения"


class DepsError(RuntimeError):
    pass


@dataclass
class Item:
    name: str
    ok: bool
    detail: str
    optional: bool = False


def ffmpeg_dir() -> Path:
    return cache_dir() / "ffmpeg" / "bin"


def ffmpeg_path() -> str | None:
    """ffmpeg from PATH, else the copy installed by install_ffmpeg, else None."""
    if found := shutil.which("ffmpeg"):
        return found
    local = ffmpeg_dir() / "ffmpeg.exe"
    return str(local) if local.is_file() else None


def extract_ffmpeg(zip_path: Path, dest: Path | None = None) -> Path:
    """Extract only ffmpeg.exe and ffprobe.exe (from any `.../bin/`) into dest atomically."""
    dest = Path(dest) if dest else ffmpeg_dir()
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="bin-", dir=dest.parent))
    try:
        with zipfile.ZipFile(zip_path) as z:
            names = {Path(n).name.lower(): n for n in z.namelist() if "/bin/" in "/" + n.lower()}
            for exe in FFMPEG_EXES:
                if exe not in names:
                    raise DepsError(f"В архиве ffmpeg нет {exe}. Удали {zip_path} и повтори установку")
                with z.open(names[exe]) as src, (tmp / exe).open("wb") as out:
                    shutil.copyfileobj(src, out)
        if dest.exists():
            shutil.rmtree(dest)
        os.replace(tmp, dest)
    except zipfile.BadZipFile as e:
        raise DepsError(f"Архив ffmpeg повреждён ({zip_path}). Удали файл и повтори установку") from e
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return dest


def install_ffmpeg(progress: Callable[[int, int], None] | None = None) -> str:
    if p := ffmpeg_path():
        return p
    z = download.fetch(FFMPEG_URLS, cache_dir() / "ffmpeg" / FFMPEG_ZIP, progress=progress,
                       sha256=FFMPEG_SHA256, what="ffmpeg", error=DepsError)
    extract_ffmpeg(z)
    z.unlink(missing_ok=True)
    return str(ffmpeg_dir() / "ffmpeg.exe")


def prep_ok() -> bool:
    try:
        return all(importlib.util.find_spec(m) is not None for m in PREP_MODULES)
    except (ImportError, ValueError):
        return False


def repo_root() -> Path | None:
    root = Path(__file__).resolve().parents[1]
    py = root / "pyproject.toml"
    try:
        if py.is_file() and 'name = "omnivoice"' in py.read_text(encoding="utf-8"):
            return root
    except OSError:
        pass
    return None


def find_uv() -> str | None:
    if u := shutil.which("uv"):
        return u
    for n in ("uv.exe", "uv"):
        c = Path(sys.executable).parent / n
        if c.is_file():
            return str(c)
    return None


def install_prep(on_line: Callable[[str], None], popen=subprocess.Popen) -> None:
    uv = find_uv()
    if not uv:
        raise DepsError("Не найден uv. Установи его (в PowerShell: irm https://astral.sh/uv/install.ps1 | iex; "
                        "подробнее https://docs.astral.sh/uv/getting-started/installation/) и повтори установку")
    root = repo_root()
    cmd = ([uv, "sync", "--all-extras", "--project", str(root)] if root
           else [uv, "pip", "install", "--python", sys.executable, "omnivoice[prep,ui]"])
    try:
        p = popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    except OSError as e:
        raise DepsError(f"Не удалось запустить uv ({uv}): {e}") from e
    for line in p.stdout or ():
        if line := line.rstrip():
            on_line(line)
    if p.wait() != 0:
        raise DepsError(f"Установка пакетов (uv) завершилась с ошибкой (код {p.returncode}). Лог выше; "
                        f"повтори или выполни вручную: {' '.join(cmd)}")


def check_all(run=subprocess.run) -> list[Item]:
    """Fast checklist; never starts Docker containers."""
    st = wslenv.status(run)
    prep = prep_ok()
    ff = ffmpeg_path()
    docker = shutil.which("docker")
    wsl_ok = st.wsl and st.wsl_version_ok
    return [
        Item(PREP, prep, "установлены" if prep else "не установлены — " + HINT),
        Item(FFMPEG, bool(ff), ff or "не найден — " + HINT),
        Item(WSL, wsl_ok, "готов" if wsl_ok else ("устарел" if st.wsl else "не установлен") + " — " + HINT),
        Item(ENV, st.ready, st.message),
        Item("GPU в WSL", bool(st.gpu), "доступен" if st.gpu else "не обнаружен (проверяется после установки среды; "
             "нужен драйвер NVIDIA для Windows)", optional=True),
        Item("Docker", bool(docker), docker or "не найден (необязательно — запасной вариант обучения)", optional=True),
    ]


def _missing(items: list[Item], name: str) -> bool:
    return any(i.name == name and not i.ok for i in items)


def install_all(on_line: Callable[[str], None], progress: Callable[[int, int], None] | None = None,
                run=subprocess.run) -> str | None:
    """prep → ffmpeg → WSL environment, skipping what is OK. Returns the reboot message if one is needed, else None."""
    items = check_all(run)
    if _missing(items, PREP):
        on_line("Устанавливаю пакеты (prep, ui)…")
        install_prep(on_line)
    if _missing(items, FFMPEG):
        on_line("Скачиваю ffmpeg…")
        install_ffmpeg(progress)
    if _missing(items, WSL) or _missing(items, ENV):
        on_line("Настраиваю среду обучения WSL…")
        try:
            wslenv.ensure_ready(on_line, progress)
        except wslenv.RebootRequired as e:
            msg = str(e) or wslenv.REBOOT_MSG
            on_line(msg)
            return msg
    on_line("Готово.")
    return None
