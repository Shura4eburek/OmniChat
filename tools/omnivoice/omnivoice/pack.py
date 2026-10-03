from __future__ import annotations
import json, re, shutil
from pathlib import Path
from omnivoice import __version__, modrules, onnxmeta
from omnivoice.espeak import ensure_espeak_data
from omnivoice.fsutil import TargetBusy, swap_dir
from omnivoice.portrait import make_portrait
from omnivoice.translit import translit

class PackError(Exception):
    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems)); self.problems = problems

def folder_name(name: str) -> str:
    return re.sub(r"[^a-z0-9_-]", "_", translit(name).lower()).strip("_") or "voice"

def iso_name_for_voice(voice: str | None, default: str = "Russian") -> str:
    """English ISO 639 language name for an espeak voice code: ru → Russian, en-us → English."""
    if not voice:
        return default
    try:
        from iso639 import Lang
        return Lang(voice.split("-")[0].strip().lower()).name
    except Exception:
        return default

def config_voice(config_path: Path | None) -> str | None:
    """espeak voice from a piper .onnx.json, or None if it can't be read."""
    if config_path is None:
        return None
    try:
        return json.loads(Path(config_path).read_text(encoding="utf-8"))["espeak"]["voice"]
    except Exception:
        return None

def _voice_json(display: dict, language: str) -> dict:
    out = {"language": language[: modrules.LIMITS["language"]]}
    for key in ("name", "description", "gender", "sample"):
        if display.get(key):
            out[key] = str(display[key])[: modrules.LIMITS[key]]
    if display.get("license"):
        out["license"] = str(display["license"])
    return out

def pack_voice(onnx_path: Path, config_path: Path | None, out_dir: Path, display: dict, iso_name: str,
               voice_override: str | None = None, portrait_bytes: bytes | None = None,
               espeak_dir: Path | None = None) -> Path:
    onnx_path = Path(onnx_path)
    if not onnx_path.is_file():
        raise PackError([f"Файл модели не найден: {onnx_path}"])
    name = folder_name(display.get("name") or onnx_path.stem)
    try:
        loaded_meta = modrules.read_onnx_metadata(onnx_path)
    except Exception:
        raise PackError([f"Не удалось прочитать модель {onnx_path.name}: это не ONNX или файл повреждён"])
    folder = Path(out_dir) / name
    inputs = [onnx_path, onnx_path.with_name("tokens.txt")]
    if config_path is not None:
        inputs.append(Path(config_path))
    if espeak_dir is not None:
        inputs.append(Path(espeak_dir))
    target = folder.resolve()
    for src in inputs:
        r = src.resolve()
        if r == target or target in r.parents:
            raise PackError(["Входные файлы лежат в папке назначения — укажи другую папку вывода (--out)"])
    if config_path is None:
        tokens_src = onnx_path.with_name("tokens.txt")
        if not voice_override or not tokens_src.is_file():
            raise PackError(["Нет .onnx.json рядом с моделью — укажи язык через --voice и положи tokens.txt"])
        existing = loaded_meta
        meta = {"model_type": "vits", "version": "1", "language": iso_name,
                "sample_rate": "22050"} | existing | {
                    "comment": existing.get("comment", "piper"), "voice": voice_override,
                    "has_espeak": "1", "n_speakers": existing.get("n_speakers", "1"),
                    "omnivoice_version": __version__}
        tokens = tokens_src.read_text(encoding="utf-8"); voice = voice_override; config = None
    else:
        try:
            config = json.loads(Path(config_path).read_text(encoding="utf-8"))
            meta = onnxmeta.piper_metadata(config, iso_name, __version__)
            tokens = onnxmeta.tokens_from_config(config)
        except (OSError, ValueError, KeyError, TypeError) as e:
            raise PackError([f"Не удалось прочитать конфиг {config_path}: {e}"])
        if voice_override:
            meta["voice"] = voice_override
        voice = meta["voice"]
    portrait_png = None
    if portrait_bytes:
        try:
            portrait_png = make_portrait(portrait_bytes)
        except Exception as e:
            raise PackError([f"Не удалось обработать портрет: {e}"])
    espeak_src = Path(espeak_dir) if espeak_dir else ensure_espeak_data()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    # Build in a sibling temp dir; the old folder is swapped out only after a successful, validated build.
    tmp = out_dir / f".{name}.packing"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir()
    try:
        onnxmeta.write_metadata(onnx_path, tmp / f"{name}.onnx", meta)
        if config is not None:
            (tmp / f"{name}.onnx.json").write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
        (tmp / "tokens.txt").write_text(tokens, encoding="utf-8")
        shutil.copytree(espeak_src, tmp / "espeak-ng-data")
        (tmp / "voice.json").write_text(json.dumps(_voice_json(display, voice.split("-")[0]), ensure_ascii=False, indent=2),
                                        encoding="utf-8")
        if portrait_png:
            (tmp / "portrait.png").write_bytes(portrait_png)
        problems = modrules.validate_voice_folder(tmp)
        if problems:
            raise PackError(["Папка не прошла проверку мода:", *problems])
        try:
            swap_dir(tmp, folder)
        except TargetBusy as e:
            raise PackError([str(e)])
    except OSError as e:
        raise PackError([f"Ошибка записи: {e}"])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return folder

def pack_project(p, onnx_path: Path | None = None, portrait: Path | None = None) -> Path:
    from omnivoice import languages
    folder = pack_voice(onnx_path or p.export_dir / "model.onnx", p.train_dir / "config.json", p.export_dir,
                        p.display, languages.PRESETS[p.language].iso_name,
                        portrait_bytes=Path(portrait).read_bytes() if portrait else None)
    p.mark_fresh("pack")
    return folder
