from __future__ import annotations
import shutil, uuid
from pathlib import Path

class TargetBusy(Exception):
    """The existing target folder cannot be renamed (usually held open by the running game)."""

def swap_dir(new_tmp: Path, target: Path) -> None:
    """Move new_tmp into place as target. An existing target is renamed to a backup first and
    restored on failure; the backup is removed only after success. Raises TargetBusy if the
    existing target is locked, OSError if the final rename fails (old target restored)."""
    new_tmp, target = Path(new_tmp), Path(target)
    nt, tg = new_tmp.resolve(), target.resolve()
    if tg == nt or tg == nt.parent or tg in nt.parent.parents:
        raise ValueError(f"unsafe swap target: {target}")
    had_old = target.exists()
    backup = target.with_name(f".{target.name}.old-{uuid.uuid4().hex[:8]}")
    if had_old:
        try:
            target.rename(backup)
        except OSError:
            raise TargetBusy("Папка голоса занята (игра запущена?) — закрой Minecraft и повтори")
    try:
        new_tmp.rename(target)
    except OSError:
        if had_old:
            backup.rename(target)
        raise
    if had_old:
        shutil.rmtree(backup, ignore_errors=True)
