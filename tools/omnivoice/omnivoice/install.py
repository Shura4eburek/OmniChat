from __future__ import annotations
import os, shutil
from pathlib import Path
from omnivoice.fsutil import TargetBusy, swap_dir

def default_targets() -> list[Path]:
    cands: list[Path] = []
    appdata = os.environ.get("APPDATA")
    if appdata:
        cands.append(Path(appdata) / ".minecraft/config/omnichat/models")
        cands += sorted(Path(appdata).glob("PrismLauncher/instances/*/minecraft/config/omnichat/models"))
    for parent in [Path.cwd(), *Path.cwd().parents]:
        if (parent / "run/config/omnichat/models").is_dir():
            cands.append(parent / "run/config/omnichat/models"); break
    return [c for c in cands if c.is_dir()]

def install_voice(folder: Path, target_models_dir: Path, overwrite: bool = False) -> Path:
    """Copy a voice folder into a models dir. Raises FileExistsError (no overwrite) or
    TargetBusy (existing folder locked by the game)."""
    folder = Path(folder).resolve()
    target_models_dir = Path(target_models_dir).resolve()
    if folder.name in ("", ".", ".."):
        raise ValueError("Не удалось определить имя голоса — укажи путь к папке голоса явно")
    if folder == target_models_dir or folder in target_models_dir.parents:
        raise ValueError("Папка models лежит внутри папки голоса — выбери другую папку назначения")
    dest = target_models_dir / folder.name
    if dest == target_models_dir or dest in target_models_dir.parents:
        raise ValueError("Недопустимое имя папки голоса")
    if dest.resolve() == folder:
        raise ValueError(f"Источник и назначение совпадают: {dest}")
    if dest.exists() and not overwrite:
        raise FileExistsError(f"{dest} уже существует (используй --overwrite)")
    tmp = target_models_dir / f".{folder.name}.installing"
    shutil.rmtree(tmp, ignore_errors=True)
    try:
        shutil.copytree(folder, tmp)
        swap_dir(tmp, dest)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return dest
