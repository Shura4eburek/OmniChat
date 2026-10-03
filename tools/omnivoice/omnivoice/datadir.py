"""Move the dependency folder (paths.cache_dir()) to another drive. Projects are not affected.

Order, so the setting always points to a folder where everything works:
1. the WSL distro disk via `wsl --manage omnivoice --move` (atomic on WSL's side; a registered distro is
   found by name wherever its disk lies, so the old folder keeps working without it);
2. everything else is copied to the new folder and checked by size;
3. the setting is switched (paths.set_data_dir);
4. the old copies are deleted (a failure here is only a warning).
A failed step 1-2 leaves the setting on the old folder; partial copies are removed.
"""
from __future__ import annotations
import os
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path, PureWindowsPath
from typing import Callable

from omnivoice import paths, wslenv

DISTRO = wslenv.DISTRO
VHDX = "ext4.vhdx"
HEADROOM = 1.1  # free space needed: current size + 10 %
DRIVE_NO_ROOT_DIR, DRIVE_FIXED = 1, 3  # GetDriveTypeW
SHARING_MARKERS = ("error_sharing_violation", "используется другим процессом", "used by another process",
                   "0x80070020")
SHARING_MSG = ("Диск среды WSL «omnivoice» занят: его держит открытым другая виртуальная машина WSL "
               "(например, Docker Desktop). Закрой Docker Desktop или выполни в PowerShell «wsl --shutdown», "
               "затем повтори перенос. Ничего не перенесено, всё осталось на старом месте")
EXAMPLE = "G:\\omnivoice"


class DataDirError(RuntimeError):
    pass


def human_size(n: int) -> str:
    for unit, div in (("ГБ", 1 << 30), ("МБ", 1 << 20), ("КБ", 1 << 10)):
        if n >= div:
            return f"{n / div:.1f} {unit}".replace(".", ",")
    return f"{n} Б"


def size_of(path: Path) -> int:
    """Bytes in a file or a folder tree (links are not followed); 0 when it is missing."""
    try:
        if path.is_file():
            return path.stat().st_size
    except OSError:
        return 0
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.lstat(os.path.join(root, f)).st_size
            except OSError:
                pass
    return total


def describe() -> tuple[Path, str, int]:
    """(current folder, source "env" | "config" | "default", bytes used). Read-only."""
    d, source = paths.cache_source()
    return d, source, size_of(d) if d.is_dir() else 0


def volume_info(path: Path) -> tuple[int | None, str | None]:
    """(GetDriveTypeW, file system name) of the path's drive; (None, None) when unknown (not Windows)."""
    if sys.platform != "win32":
        return None, None
    try:
        import ctypes
        root = PureWindowsPath(path).anchor
        k = ctypes.windll.kernel32
        dtype = k.GetDriveTypeW(root)
        fs = ctypes.create_unicode_buffer(64)
        ok = k.GetVolumeInformationW(root, None, 0, None, None, None, fs, len(fs))
        return dtype, (fs.value if ok else None)
    except Exception:
        return None, None


def _norm(p) -> str:
    return os.path.normcase(os.path.normpath(str(p)))


def _inside(child: Path, parent: Path) -> bool:
    return _norm(child).startswith(_norm(parent).rstrip("\\/") + os.sep)


def _absolute(raw: str) -> bool:
    if sys.platform == "win32":
        w = PureWindowsPath(raw)
        return bool(re.fullmatch(r"[A-Za-z]:", w.drive)) and w.root == "\\"
    return Path(raw).is_absolute()


def _drive(p: Path) -> str:
    return PureWindowsPath(p).drive or p.anchor or str(p)


def _registered(old: Path, run) -> bool:
    try:
        return DISTRO in wslenv.distros(run)
    except wslenv.WslError as e:
        if (old / "wsl" / DISTRO / VHDX).exists():
            raise DataDirError(f"{e}. Диск среды WSL лежит в {old}, но WSL не отвечает — перенос сейчас "
                               f"невозможен") from e
        return False  # no WSL yet (fresh machine): nothing to move there


def _entries(old: Path) -> list[Path]:
    """What is copied (relative paths): everything under old except the distro disk folder wsl/omnivoice."""
    if not old.is_dir():
        return []
    out = []
    for p in sorted(old.iterdir()):
        if p.name.lower() == "wsl" and p.is_dir():
            out += [Path("wsl") / c.name for c in sorted(p.iterdir()) if c.name.lower() != DISTRO]
        else:
            out.append(Path(p.name))
    return out


def _check_target(new: Path, entries: list[Path], need: int, disk_usage, volume) -> None:
    drive = _drive(new)
    try:
        dtype, fs = volume(new)
    except Exception:
        dtype, fs = None, None
    if dtype == DRIVE_NO_ROOT_DIR:
        raise DataDirError(f"Диск {drive} не найден — проверь букву диска")
    if dtype is not None and dtype != DRIVE_FIXED:
        raise DataDirError(f"{drive} — не локальный жёсткий диск (сетевой, съёмный или виртуальный). "
                           f"Выбери папку на внутреннем диске NTFS")
    if fs is not None and fs.upper() != "NTFS":
        raise DataDirError(f"Диск {drive} отформатирован в {fs}, а среде WSL нужен NTFS — выбери другой диск")
    if new.exists() and not new.is_dir():
        raise DataDirError(f"{new} — это файл, а нужна папка")
    if clash := [str(e) for e in entries if (new / e).exists()]:
        raise DataDirError(f"В папке {new} уже есть {', '.join(clash)} — выбери пустую папку или удали их")
    try:
        free = disk_usage(new.anchor or str(new)).free
    except OSError as e:
        raise DataDirError(f"Не удалось узнать свободное место на диске {drive}: {e}") from e
    if free < need * HEADROOM:
        raise DataDirError(f"Мало места на диске {drive}: нужно ~{human_size(int(need * HEADROOM))}, "
                           f"свободно {human_size(free)}")
    created = not new.exists()
    probe = new / f".omnivoice-write-test-{uuid.uuid4().hex}"
    try:
        new.mkdir(parents=True, exist_ok=True)
        probe.write_bytes(b"ok")
        probe.unlink()
    except OSError as e:
        if created:
            shutil.rmtree(new, ignore_errors=True)
        raise DataDirError(f"Не удалось записать в {new}: {e}. Выбери папку, куда есть доступ") from e


def _move_distro(new: Path, on_line, run) -> None:
    dest = new / "wsl" / DISTRO
    dest.mkdir(parents=True, exist_ok=True)
    on_line(f"Останавливаю среду WSL «{DISTRO}»…")
    wslenv._run(run, ["wsl", "--terminate", DISTRO])
    on_line(f"Переношу диск среды WSL в {dest}… (несколько минут, не закрывай окно)")
    rc, out = wslenv._run(run, ["wsl", "--manage", DISTRO, "--move", str(dest)], timeout=None)
    if rc != 0:
        if any(m in out.lower() for m in SHARING_MARKERS):
            raise DataDirError(SHARING_MSG)
        detail = out.strip() or ("wsl.exe не отвечает" if rc is None else "нет вывода")
        raise DataDirError(f"Не удалось перенести среду WSL «{DISTRO}» (код {rc}): {detail}. Обнови WSL "
                           f"(wsl --update) и повтори. Ничего не перенесено, всё осталось на старом месте")
    if not (dest / VHDX).exists():
        raise DataDirError(f"WSL сообщил об успехе, но диска {dest / VHDX} нет — проверь «wsl -l -v» и повтори")
    on_line("Среда WSL перенесена")


def _remove(root: Path, rels: list[Path]) -> list[Path]:
    """Delete root/rel for each rel; returns what could not be deleted."""
    left = []
    for rel in rels:
        p = root / rel
        try:
            if p.is_dir() and not p.is_symlink():
                shutil.rmtree(p)
            elif p.exists() or p.is_symlink():
                p.unlink()
        except OSError:
            left.append(p)
    return left


def _copy(old: Path, new: Path, entries: list[Path], on_line) -> None:
    done: list[Path] = []
    try:
        for rel in entries:
            src, dst = old / rel, new / rel
            on_line(f"Копирую {rel}…")
            dst.parent.mkdir(parents=True, exist_ok=True)
            done.append(rel)
            try:
                if src.is_dir():
                    shutil.copytree(src, dst)
                else:
                    shutil.copy2(src, dst)
            except OSError as e:
                raise DataDirError(f"Не удалось скопировать {rel} в {new}: {e}") from e
            if size_of(src) != size_of(dst):
                raise DataDirError(f"Копия {rel} не совпадает по размеру с оригиналом — проверь диск "
                                   f"{_drive(new)} и повтори")
    except DataDirError:
        _remove(new, done)
        raise


def move_data(new_root, on_line: Callable[[str], None], run=subprocess.run, disk_usage=shutil.disk_usage,
              volume=volume_info) -> bool:
    """Move the dependency folder to new_root (see the module doc). False when it is already there.
    On a fresh machine there is nothing to move: it only switches the setting. Raises DataDirError."""
    old, source = paths.cache_source()
    raw = str(new_root or "").strip().strip('"').strip()
    if not raw:
        raise DataDirError(f"Укажи папку для зависимостей, например {EXAMPLE}")
    if not _absolute(raw):
        raise DataDirError(f"Укажи полный путь с буквой диска, например {EXAMPLE} (сейчас: {raw})")
    new = Path(os.path.normpath(raw))
    if _norm(new) == _norm(old):
        on_line(f"Зависимости уже лежат в {old} — переносить нечего")
        return False
    if new.parent == new:
        raise DataDirError(f"Укажи папку, а не корень диска: например {_drive(new)}\\omnivoice")
    if source == "env":
        raise DataDirError(f"Папка задана переменной окружения {paths.ENV}={old} — убери переменную "
                           f"или поменяй её значение")
    if _inside(new, old):
        raise DataDirError(f"Новая папка {new} лежит внутри текущей {old} — выбери другую")
    from omnivoice import train
    if train._ACTIVE:
        raise DataDirError("Идёт обучение — дождись конца или останови его, потом переноси")

    registered = _registered(old, run)
    wsl_done = registered and (new / "wsl" / DISTRO / VHDX).exists()  # a previous attempt moved it already
    entries = _entries(old)
    need = sum(size_of(old / e) for e in entries)
    if registered and not wsl_done:
        need += size_of(old / "wsl" / DISTRO)
    _check_target(new, entries, need, disk_usage, volume)
    on_line(f"Переношу зависимости: {old} → {new} (~{human_size(need)})")

    if wsl_done:
        on_line(f"Среда WSL уже лежит в {new / 'wsl' / DISTRO}")
    elif registered:
        _move_distro(new, on_line, run)
    try:
        _copy(old, new, entries, on_line)
        paths.set_data_dir(new)
    except (DataDirError, OSError) as e:
        note = (f"\nСреда WSL уже перенесена в {new / 'wsl' / DISTRO} и работает; остальное осталось в {old}. "
                f"Повтори перенос" if registered else "")
        raise DataDirError(f"{e}{note}") from e
    on_line(f"Настройка обновлена: зависимости теперь в {new}")

    left = _remove(old, entries)
    for d in (old / "wsl" / DISTRO, old / "wsl", old):
        try:
            d.rmdir()  # only when empty
        except OSError:
            pass
    if left:
        on_line("Не удалось удалить старые файлы (закрой программы, которые их используют, и удали вручную): "
                + ", ".join(str(p) for p in left))
    on_line(f"Готово — зависимости в {new}")
    return True
