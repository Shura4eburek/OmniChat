from __future__ import annotations
import os, shutil
from dataclasses import dataclass
from pathlib import Path
from omnivoice.fsutil import TargetBusy, swap_dir

MODELS = Path("config/omnichat/models")  # inside a game folder (an instance / profile)
DEV = "run"  # the mod repo's own game folder (gradle runClient)


@dataclass(frozen=True)
class Target:
    path: Path      # <game folder>/config/omnichat/models — may not exist before the first voice
    launcher: str   # "Modrinth", "CurseForge", … ; "" for the mod repo's run folder
    name: str       # instance / profile name


def _game_dirs() -> list[tuple[str, Path]]:
    """(launcher, game folder) of every instance the usual launchers keep in their default places."""
    out: list[tuple[str, Path]] = []
    appdata, home = os.environ.get("APPDATA"), Path.home()
    if appdata:
        a = Path(appdata)
        out.append(("Minecraft", a / ".minecraft"))
        for pattern, launcher in (("PrismLauncher/instances/*/minecraft", "Prism"),
                                  ("PrismLauncher/instances/*/.minecraft", "Prism"),
                                  ("MultiMC/instances/*/.minecraft", "MultiMC"),
                                  ("ModrinthApp/profiles/*", "Modrinth"),
                                  ("com.modrinth.theseus/profiles/*", "Modrinth"),
                                  ("ATLauncher/instances/*", "ATLauncher"),
                                  ("gdlauncher_next/instances/*", "GDLauncher")):
            out += [(launcher, d) for d in sorted(a.glob(pattern)) if d.is_dir()]
    out += [("CurseForge", d) for d in sorted((home / "curseforge/minecraft/Instances").glob("*")) if d.is_dir()]
    return out


def _has_omnichat(game: Path) -> bool:
    """The mod is installed in this game folder (its config folder or its jar)."""
    return (game / "config/omnichat").is_dir() or any((game / "mods").glob("omnichat*.jar"))


def find_targets() -> list[Target]:
    """Every game folder with OmniChat in it, launchers first, then the mod repo's run folder."""
    found: list[Target] = []
    for launcher, game in _game_dirs():
        if _has_omnichat(game):
            name = game.parent.name if game.name in ("minecraft", ".minecraft") and launcher != "Minecraft" else game.name
            found.append(Target(game / MODELS, launcher, name))
    for parent in [Path.cwd(), *Path.cwd().parents]:
        if (parent / DEV / MODELS).is_dir():
            found.append(Target(parent / DEV / MODELS, "", DEV)); break
    return found


def default_targets() -> list[Path]:
    return [t.path for t in find_targets()]


def models_dir_for(folder: Path) -> Path:
    """A folder the user picked → the models folder to install into: a game folder (it has mods/ or
    config/) means its config/omnichat/models, the mod's config folder means its models/, else as is."""
    folder = Path(folder)
    if folder.name.lower() == "omnichat" and folder.parent.name.lower() == "config":
        return folder / "models"
    if (folder / "mods").is_dir() or (folder / "config").is_dir():
        return folder / MODELS
    return folder

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
