import json, pytest
from pathlib import Path
from typer.testing import CliRunner
from omnivoice import pack, espeak
from omnivoice.cli import app
from omnivoice.modrules import read_onnx_metadata, validate_voice_folder
from tests.helpers import make_onnx, png

def espeak_dir(tmp_path):
    d = tmp_path / "espeak-ng-data"; d.mkdir(exist_ok=True); (d / "phontab").write_bytes(b"x"); return d

CFG = {"audio": {"sample_rate": 22050}, "espeak": {"voice": "ru"}, "num_speakers": 1, "phoneme_id_map": {"_": [0]}}

def test_pack_own_export(tmp_path):
    onnx = make_onnx(tmp_path / "model.onnx", {})
    before = onnx.read_bytes()
    cfg = tmp_path / "config.json"; cfg.write_text(json.dumps(CFG), encoding="utf-8")
    out = pack.pack_voice(onnx, cfg, tmp_path / "out", {"name": "GLaDOS" * 10, "description": "Злой ИИ", "license": "CC0"},
                          "Russian", portrait_bytes=png(64, 64), espeak_dir=espeak_dir(tmp_path))
    assert out.is_dir()
    assert validate_voice_folder(out) == []
    assert (out / "portrait.png").is_file()
    assert read_onnx_metadata(next(out.glob("*.onnx")))["voice"] == "ru"
    vj = json.loads((out / "voice.json").read_text(encoding="utf-8"))
    assert len(vj["name"]) == 32 and vj["license"] == "CC0"
    assert onnx.read_bytes() == before

def test_pack_replaces_existing_but_keeps_unrelated(tmp_path):
    onnx = make_onnx(tmp_path / "model.onnx", {})
    cfg = tmp_path / "config.json"; cfg.write_text(json.dumps(CFG), encoding="utf-8")
    out_dir = tmp_path / "out"; (out_dir / "v").mkdir(parents=True)
    (out_dir / "v" / "stale.txt").write_text("x"); (out_dir / "other.txt").write_text("keep")
    out = pack.pack_voice(onnx, cfg, out_dir, {"name": "v"}, "Russian", espeak_dir=espeak_dir(tmp_path))
    assert not (out / "stale.txt").exists() and (out_dir / "other.txt").read_text() == "keep"

def test_pack_foreign_model_without_json_needs_voice(tmp_path):
    onnx = make_onnx(tmp_path / "m.onnx", {"n_speakers": "1", "comment": "piper"})
    with pytest.raises(pack.PackError, match="--voice"):
        pack.pack_voice(onnx, None, tmp_path / "out", {"name": "x"}, "Russian", espeak_dir=espeak_dir(tmp_path))
    (tmp_path / "tokens.txt").write_text("_ 0\n", encoding="utf-8")
    out = pack.pack_voice(onnx, None, tmp_path / "out", {"name": "x"}, "Russian", voice_override="ru",
                          espeak_dir=espeak_dir(tmp_path))
    assert read_onnx_metadata(next(out.glob("*.onnx")))["voice"] == "ru"

def test_ensure_espeak_failure_leaves_no_half_data(tmp_path, monkeypatch):
    monkeypatch.setenv("OMNIVOICE_CACHE", str(tmp_path / "cache"))
    def boom(url, timeout=None):
        raise OSError("offline")
    monkeypatch.setattr(espeak.urllib.request, "urlopen", boom)
    with pytest.raises(RuntimeError, match="espeak"):
        espeak.ensure_espeak_data()
    cache = tmp_path / "cache"
    assert not (cache / "espeak-ng-data").exists()
    assert not list(cache.glob("*.part"))

def test_cli_pack_bad_onnx_is_clean_error(tmp_path):
    r = CliRunner().invoke(app, ["pack", "--onnx", str(tmp_path / "nope.onnx"), "--name", "x"])
    assert r.exit_code == 1 and "Traceback" not in r.output

def _cfg(tmp_path):
    cfg = tmp_path / "config.json"; cfg.write_text(json.dumps(CFG), encoding="utf-8"); return cfg

def test_locked_old_folder_stays_intact(tmp_path, monkeypatch):
    onnx = make_onnx(tmp_path / "model.onnx", {})
    out_dir = tmp_path / "out"; (out_dir / "v").mkdir(parents=True); (out_dir / "v" / "keep.txt").write_text("k")
    real = Path.rename
    def fake(self, target):
        if self.name == "v":
            raise PermissionError("locked")
        return real(self, target)
    monkeypatch.setattr(Path, "rename", fake)
    with pytest.raises(pack.PackError, match="занята"):
        pack.pack_voice(onnx, _cfg(tmp_path), out_dir, {"name": "v"}, "Russian", espeak_dir=espeak_dir(tmp_path))
    assert (out_dir / "v" / "keep.txt").read_text() == "k"

def test_input_inside_target_rejected(tmp_path):
    out_dir = tmp_path / "out"; (out_dir / "v").mkdir(parents=True)
    onnx = make_onnx(out_dir / "v" / "m.onnx", {})
    with pytest.raises(pack.PackError, match="--out"):
        pack.pack_voice(onnx, _cfg(tmp_path), out_dir, {"name": "v"}, "Russian", espeak_dir=espeak_dir(tmp_path))
    assert onnx.is_file()

def test_foreign_model_gets_all_keys(tmp_path):
    onnx = make_onnx(tmp_path / "m.onnx", {})
    (tmp_path / "tokens.txt").write_text("_ 0\n", encoding="utf-8")
    out = pack.pack_voice(onnx, None, tmp_path / "out", {"name": "x"}, "Russian", voice_override="ru",
                          espeak_dir=espeak_dir(tmp_path))
    m = read_onnx_metadata(next(out.glob("*.onnx")))
    assert m == {"model_type": "vits", "comment": "piper", "language": "Russian", "voice": "ru", "version": "1",
                 "has_espeak": "1", "n_speakers": "1", "sample_rate": "22050", "omnivoice_version": m["omnivoice_version"]}

def test_cli_pack_garbage_onnx(tmp_path):
    bad = tmp_path / "bad.onnx"; bad.write_bytes(b"\x00garbage\xff" * 50)
    r = CliRunner().invoke(app, ["pack", "--onnx", str(bad), "--name", "x", "--out", str(tmp_path / "o")])
    assert r.exit_code == 1 and "Traceback" not in r.output and "не ONNX" in r.output

def test_folder_name_transliterates_cyrillic():
    assert pack.folder_name("Мой голос") == "moy_golos"
    assert pack.folder_name("Тест ГЛаДОС") == "test_glados"
    assert pack.folder_name("Денис") != pack.folder_name("Ирина")
    assert pack.folder_name("GLaDOS v2") == "glados_v2"
    assert pack.folder_name("!!!") == "voice"

def test_iso_name_for_voice():
    assert pack.iso_name_for_voice("ru") == "Russian"
    assert pack.iso_name_for_voice("en-us") == "English"
    assert pack.iso_name_for_voice("zz-qq") == "Russian"
    assert pack.iso_name_for_voice(None) == "Russian"

def _cli_pack(tmp_path, *extra):
    onnx = make_onnx(tmp_path / "m.onnx", {})
    (tmp_path / "tokens.txt").write_text("_ 0\n", encoding="utf-8")
    out = tmp_path / "o"
    r = CliRunner().invoke(app, ["pack", "--onnx", str(onnx), "--name", "Мой голос", "--out", str(out), *extra])
    return r, out

def test_cli_pack_language_from_voice(tmp_path, monkeypatch):
    monkeypatch.setattr(pack, "ensure_espeak_data", lambda: espeak_dir(tmp_path))
    r, out = _cli_pack(tmp_path, "--voice", "en-us")
    assert r.exit_code == 0, r.output
    assert read_onnx_metadata(out / "moy_golos" / "moy_golos.onnx")["language"] == "English"

def test_cli_pack_explicit_language_wins(tmp_path, monkeypatch):
    monkeypatch.setattr(pack, "ensure_espeak_data", lambda: espeak_dir(tmp_path))
    r, out = _cli_pack(tmp_path, "--voice", "en-us", "--language", "German")
    assert r.exit_code == 0, r.output
    assert read_onnx_metadata(out / "moy_golos" / "moy_golos.onnx")["language"] == "German"

def test_pack_project_keeps_concurrent_display(tmp_path):
    from omnivoice.project import Project
    p = Project.create(tmp_path / "p", name="Голос", language="ru")
    make_onnx(p.export_dir / "model.onnx", {})
    (p.train_dir / "config.json").write_text(json.dumps(CFG), encoding="utf-8")
    other = Project.load(p.root); other.display["description"] = "свежее"; other.save()
    import omnivoice.pack as pk
    orig = pk.ensure_espeak_data
    pk.ensure_espeak_data = lambda: espeak_dir(tmp_path)
    try:
        folder = pack.pack_project(p)
    finally:
        pk.ensure_espeak_data = orig
    assert folder.name == "golos"
    q = Project.load(p.root)
    assert q.steps["pack"] and q.display["description"] == "свежее"

def test_cli_pack_language_from_config_voice(tmp_path, monkeypatch):
    monkeypatch.setattr(pack, "ensure_espeak_data", lambda: espeak_dir(tmp_path))
    onnx = make_onnx(tmp_path / "m.onnx", {})
    cfg = tmp_path / "m.onnx.json"; cfg.write_text(json.dumps(CFG | {"espeak": {"voice": "en-us"}}), encoding="utf-8")
    r = CliRunner().invoke(app, ["pack", "--onnx", str(onnx), "--config", str(cfg), "--name", "x", "--out", str(tmp_path / "o")])
    assert r.exit_code == 0, r.output
    assert read_onnx_metadata(tmp_path / "o" / "x" / "x.onnx")["language"] == "English"
