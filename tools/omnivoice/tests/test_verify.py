import json, shutil, sys, pytest
from pathlib import Path
from omnivoice import verify

DENIS = Path(__file__).resolve().parents[3] / "run/config/omnichat/models/denis"

def test_verify_real_model(tmp_path):
    if not (DENIS / "ru_RU-denis-medium.onnx").is_file():
        pytest.skip("local denis model not present")
    pytest.importorskip("sherpa_onnx")
    folder = tmp_path / "denis"; shutil.copytree(DENIS, folder)
    before = sorted(p.name for p in folder.iterdir())
    r = verify.verify_voice(folder, "Проверка.")
    assert r.ok, r.message
    assert r.sample and r.sample.stat().st_size > 1000
    assert folder not in r.sample.parents and sorted(p.name for p in folder.iterdir()) == before
    shutil.rmtree(r.sample.parent, ignore_errors=True)

def _fake(tmp_path, monkeypatch, body):
    (tmp_path / "v").mkdir(exist_ok=True)
    monkeypatch.setattr(verify.modrules, "validate_voice_folder", lambda f: [])
    script = tmp_path / "w.py"; script.write_text(body)
    monkeypatch.setattr(verify, "_worker_cmd", lambda folder, text, out: [sys.executable, str(script)])
    return tmp_path / "v"

def test_crash_is_reported_not_raised(tmp_path, monkeypatch):
    v = _fake(tmp_path, monkeypatch, "import sys; sys.stderr.write('boom\\n'); sys.exit(-1073740791)")
    r = verify.verify_voice(v, "x")
    assert not r.ok and "boom" in r.message

def test_native_crash_code_unsigned(tmp_path, monkeypatch):
    v = _fake(tmp_path, monkeypatch, "import sys; sys.exit(3221226505)")
    r = verify.verify_voice(v, "x")
    assert not r.ok and "аварийное" in r.message

def test_timeout_is_reported(tmp_path, monkeypatch):
    v = _fake(tmp_path, monkeypatch, "import time; time.sleep(30)")
    r = verify.verify_voice(v, "x", timeout=1)
    assert not r.ok and "не ответил" in r.message

def test_missing_sherpa_in_worker(tmp_path, monkeypatch):
    v = _fake(tmp_path, monkeypatch, "import sys; sys.stderr.write('No module named sherpa_onnx'); sys.exit(4)")
    r = verify.verify_voice(v, "x")
    assert not r.ok and "sherpa-onnx" in r.message and "sherpa_onnx" in r.message

def test_exit_zero_without_wav_fails(tmp_path, monkeypatch):
    v = _fake(tmp_path, monkeypatch, "pass")
    assert not verify.verify_voice(v, "x").ok

def test_invalid_folder_fails_fast(tmp_path):
    (tmp_path / "v").mkdir()
    r = verify.verify_voice(tmp_path / "v", "x")
    assert not r.ok and "tokens.txt" in r.message

def test_default_text_from_voice_json(tmp_path):
    (tmp_path / "voice.json").write_text('{"language":"en"}', encoding="utf-8")
    assert verify._default_text(tmp_path).startswith("Hello")
    (tmp_path / "voice.json").write_text('{"sample":"Мой текст"}', encoding="utf-8")
    assert verify._default_text(tmp_path) == "Мой текст"

def test_weird_voice_json_does_not_raise(tmp_path, monkeypatch):
    v = _fake(tmp_path, monkeypatch, "pass")
    for body in ('{"language": [], "sample": 123}', '{"language": {}, "sample": "a\u0000b"}', "not json", "[]"):
        (v / "voice.json").write_text(body, encoding="utf-8")
        r = verify.verify_voice(v)
        assert isinstance(r, verify.VerifyResult)
    assert verify._default_text(v) == verify.languages.PRESETS["ru"].test_phrase
    (v / "voice.json").write_text(json.dumps({"sample": "a\0b"}), encoding="utf-8")
    assert verify._default_text(v) == "ab"

def test_failure_removes_temp_dir(tmp_path, monkeypatch):
    v = _fake(tmp_path, monkeypatch, "import sys; sys.exit(3)")
    made = []
    real = verify.tempfile.mkdtemp
    monkeypatch.setattr(verify.tempfile, "mkdtemp", lambda **k: made.append(real(**k)) or made[-1])
    assert not verify.verify_voice(v, "x").ok
    assert made and not Path(made[0]).exists()
