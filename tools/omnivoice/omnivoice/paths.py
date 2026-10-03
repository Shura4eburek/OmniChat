"""Where omnivoice keeps its heavy dependencies (WSL disk, base checkpoints, ffmpeg). Projects live elsewhere.

cache_dir() resolves: the OMNIVOICE_CACHE env var → "data_dir" in config_path() → the platform default.
The setting is changed by set_data_dir() (datadir.move_data moves an existing install first)."""
import json
import os
import sys
import tempfile
from pathlib import Path

ENV = "OMNIVOICE_CACHE"


def default_dir() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "omnivoice"
    return Path.home() / ".cache" / "omnivoice"


def config_path() -> Path:
    """%APPDATA%\\omnivoice\\config.json (a roaming-safe, tiny settings file)."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "omnivoice" / "config.json"


def read_config() -> dict:
    """The settings, {} when the file is missing or unreadable (never raises)."""
    try:
        data = json.loads(config_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def cache_source() -> tuple[Path, str]:
    """(dependency folder, where it comes from: "env" | "config" | "default"). Doesn't create the folder."""
    if env := os.environ.get(ENV):
        return Path(env), "env"
    d = read_config().get("data_dir")
    if isinstance(d, str) and d.strip():
        return Path(d.strip()), "config"
    return default_dir(), "default"


def cache_dir() -> Path:
    d = cache_source()[0]
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise OSError(f"Папка для зависимостей {d} недоступна ({e}). Подключи диск или смени папку: "
                      f"omnivoice data-dir <путь>") from e
    return d


def set_data_dir(path) -> None:
    """Store the dependency folder in config_path() atomically (temp file + os.replace); other keys stay."""
    cfg = config_path()
    cfg.parent.mkdir(parents=True, exist_ok=True)
    data = read_config()
    data["data_dir"] = str(path)
    fd, tmp = tempfile.mkstemp(prefix=".config-", suffix=".tmp", dir=cfg.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, cfg)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
