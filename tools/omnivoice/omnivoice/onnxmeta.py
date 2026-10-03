from __future__ import annotations
from pathlib import Path
import onnx

def piper_metadata(config: dict, iso_name: str, version: str) -> dict[str, str]:
    voice = config.get("lang_code") or config["espeak"]["voice"]
    if voice == "pt-PT":
        voice = "pt"
    sr = int(config.get("audio", {}).get("sample_rate", 22050))
    if sr == 22500:
        sr = 22050
    return {"model_type": "vits", "comment": "piper", "language": iso_name, "voice": voice, "version": "1",
            "has_espeak": "1", "n_speakers": str(config.get("num_speakers", 1)), "sample_rate": str(sr),
            "omnivoice_version": version}

def tokens_from_config(config: dict) -> str:
    lines = []
    for s, i in config["phoneme_id_map"].items():
        if s == "\n":
            continue
        if isinstance(i, list):
            i = i[0]
        lines.append(f"{s} {i}\n")
    return "".join(lines)

def write_metadata(onnx_in: Path, onnx_out: Path, meta: dict[str, str]) -> None:
    model = onnx.load(str(onnx_in))
    del model.metadata_props[:]
    for k, v in meta.items():
        p = model.metadata_props.add(); p.key = k; p.value = str(v)
    onnx.save(model, str(onnx_out))
