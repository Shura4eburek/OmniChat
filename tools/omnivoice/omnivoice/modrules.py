"""Limits the OmniChat mod enforces. Keep in sync with:
src/main/java/org/mamoru/omnichat/voice/VoiceMetaReader.java and
src/client/java/org/mamoru/omnichat/client/tts/OnnxMetadata.java."""
from __future__ import annotations
import json
from pathlib import Path
import onnx

LIMITS = {"name": 32, "description": 200, "sample": 120, "language": 8, "gender": 16}
MAX_PORTRAIT_BYTES = 8192
PORTRAIT_SIZES = (16, 32)
_PNG_SIG = b"\x89PNG\r\n\x1a\n"

def read_onnx_metadata(path: Path) -> dict[str, str]:
    model = onnx.load(str(path), load_external_data=False)
    return {p.key: p.value for p in model.metadata_props}

def onnx_problem(meta: dict[str, str]) -> str | None:
    if "n_speakers" not in meta:
        return "в метаданных модели нет n_speakers"
    if meta.get("comment", "").lower() == "piper" and not meta.get("voice", "").strip():
        return "в метаданных модели нет voice (голос espeak)"
    return None

def portrait_problem(data: bytes) -> str | None:
    if len(data) > MAX_PORTRAIT_BYTES:
        return f"portrait.png весит {len(data)} байт, максимум {MAX_PORTRAIT_BYTES}"
    if len(data) < 24 or not data.startswith(_PNG_SIG) or data[12:16] != b"IHDR":
        return "portrait.png — не PNG"
    w, h = int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    if w != h or w not in PORTRAIT_SIZES:
        return f"portrait.png должен быть 16x16 или 32x32, а он {w}x{h}"
    return None

def validate_voice_folder(folder: Path) -> list[str]:
    problems: list[str] = []
    models = sorted(folder.glob("*.onnx"))
    if len(models) != 1:
        problems.append(f"в папке {folder.name} должен быть ровно один .onnx, найдено {len(models)}")
    else:
        try:
            meta = read_onnx_metadata(models[0])
            p = onnx_problem(meta)
            if p: problems.append(p)
        except Exception as e:
            problems.append(f"не удалось прочитать файл модели: {e}")
    if not (folder / "tokens.txt").is_file():
        problems.append("нет tokens.txt")
    if not (folder / "espeak-ng-data" / "phontab").is_file():
        problems.append("нет espeak-ng-data или она неполная (нет phontab)")
    vj = folder / "voice.json"
    if vj.is_file():
        try:
            data = json.loads(vj.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                problems.append("voice.json должен быть JSON-объектом")
            else:
                for key, limit in LIMITS.items():
                    if len(str(data.get(key, ""))) > limit:
                        problems.append(f"voice.json: поле {key} длиннее {limit} символов")
        except (json.JSONDecodeError, ValueError, OSError, UnicodeDecodeError) as e:
            problems.append(f"voice.json — некорректный JSON: {e}")
    pp = folder / "portrait.png"
    if pp.is_file():
        p = portrait_problem(pp.read_bytes())
        if p: problems.append(p)
    return problems
