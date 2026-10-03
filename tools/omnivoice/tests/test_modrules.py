import json
from pathlib import Path
from omnivoice import modrules
from tests.helpers import make_onnx, png

def test_onnx_problem_matches_mod():
    assert modrules.onnx_problem({"comment": "piper", "voice": "ru"}) == "в метаданных модели нет n_speakers"
    assert modrules.onnx_problem({"n_speakers": "1", "comment": "piper"}) == "в метаданных модели нет voice (голос espeak)"
    assert modrules.onnx_problem({"n_speakers": "1", "comment": "piper", "voice": " "}) == "в метаданных модели нет voice (голос espeak)"
    assert modrules.onnx_problem({"n_speakers": "1", "comment": "piper", "voice": "ru"}) is None
    assert modrules.onnx_problem({"n_speakers": "4", "comment": "coqui"}) is None

def test_validate_voice_folder(tmp_path: Path):
    folder = tmp_path / "glados"; folder.mkdir()
    make_onnx(folder / "glados.onnx", {"n_speakers": "1", "comment": "piper", "voice": "ru"})
    (folder / "tokens.txt").write_text("_ 0\n", encoding="utf-8")
    (folder / "espeak-ng-data").mkdir(); (folder / "espeak-ng-data" / "phontab").write_bytes(b"x")
    (folder / "voice.json").write_text(json.dumps({"name": "GLaDOS"}), encoding="utf-8")
    (folder / "portrait.png").write_bytes(png(32, 32))
    assert modrules.validate_voice_folder(folder) == []

def test_validate_voice_folder_reports_each_problem(tmp_path: Path):
    folder = tmp_path / "bad"; folder.mkdir()
    make_onnx(folder / "bad.onnx", {"comment": "piper"})
    (folder / "voice.json").write_text(json.dumps({"name": "N" * 40}), encoding="utf-8")
    (folder / "portrait.png").write_bytes(png(64, 64))
    problems = modrules.validate_voice_folder(folder)
    assert any("n_speakers" in p for p in problems)
    assert any("tokens.txt" in p for p in problems)
    assert any("name" in p and "32" in p for p in problems)
    assert any("portrait" in p for p in problems)

def test_validate_voice_folder_corrupt_onnx(tmp_path: Path):
    folder = tmp_path / "corrupt"; folder.mkdir()
    (folder / "corrupt.onnx").write_bytes(b"not a valid onnx file")
    problems = modrules.validate_voice_folder(folder)
    assert any("не удалось прочитать файл модели" in p for p in problems)

def test_validate_voice_folder_voice_json_not_dict(tmp_path: Path):
    folder = tmp_path / "listjson"; folder.mkdir()
    make_onnx(folder / "listjson.onnx", {"n_speakers": "1", "comment": "piper", "voice": "ru"})
    (folder / "voice.json").write_text(json.dumps(["not", "a", "dict"]), encoding="utf-8")
    problems = modrules.validate_voice_folder(folder)
    assert any("voice.json должен быть JSON-объектом" in p for p in problems)

def test_validate_voice_folder_voice_json_invalid_utf8(tmp_path: Path):
    folder = tmp_path / "badjson"; folder.mkdir()
    make_onnx(folder / "badjson.onnx", {"n_speakers": "1", "comment": "piper", "voice": "ru"})
    (folder / "voice.json").write_bytes(b"\xff\xfe invalid utf-8")
    problems = modrules.validate_voice_folder(folder)
    assert any("voice.json — некорректный JSON" in p for p in problems)
