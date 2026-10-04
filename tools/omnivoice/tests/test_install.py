import pytest
from pathlib import Path
from typer.testing import CliRunner
from omnivoice import install
from omnivoice.cli import app

def test_install_and_overwrite(tmp_path):
    src = tmp_path / "glados"; src.mkdir(); (src / "a.txt").write_text("1")
    target = tmp_path / "models"; target.mkdir()
    dest = install.install_voice(src, target)
    assert (dest / "a.txt").read_text() == "1"
    with pytest.raises(FileExistsError):
        install.install_voice(src, target)
    (src / "a.txt").write_text("2")
    install.install_voice(src, target, overwrite=True)
    assert (dest / "a.txt").read_text() == "2"
    assert sorted(p.name for p in target.iterdir()) == ["glados"]

def test_locked_target_keeps_old_and_says_busy(tmp_path, monkeypatch):
    src = tmp_path / "v"; src.mkdir(); (src / "a.txt").write_text("new")
    target = tmp_path / "models"; (target / "v").mkdir(parents=True); (target / "v" / "a.txt").write_text("old")
    real = Path.rename
    def fake(self, to):
        if self.name == "v":
            raise PermissionError("locked")
        return real(self, to)
    monkeypatch.setattr(Path, "rename", fake)
    with pytest.raises(install.TargetBusy, match="занята"):
        install.install_voice(src, target, overwrite=True)
    assert (target / "v" / "a.txt").read_text() == "old"
    assert [p.name for p in target.iterdir()] == ["v"]

def test_default_targets(tmp_path, monkeypatch):
    appdata = tmp_path / "AppData"
    mc = appdata / ".minecraft/config/omnichat/models"; mc.mkdir(parents=True)
    pr = appdata / "PrismLauncher/instances/I1/minecraft/config/omnichat/models"; pr.mkdir(parents=True)
    repo = tmp_path / "repo"; (repo / "run/config/omnichat/models").mkdir(parents=True)
    (repo / "sub").mkdir()
    monkeypatch.setenv("APPDATA", str(appdata)); monkeypatch.chdir(repo / "sub")
    assert install.default_targets() == [mc, pr, repo / "run/config/omnichat/models"]

def test_default_targets_missing_appdata_dirs(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "none")); monkeypatch.chdir(tmp_path)
    assert install.default_targets() == []

def test_cli_install_target_and_exists(tmp_path):
    src = tmp_path / "v"; src.mkdir(); (src / "a.txt").write_text("1")
    t = tmp_path / "m"
    r = CliRunner().invoke(app, ["install", str(src), "--target", str(t)])
    assert r.exit_code == 0 and (t / "v" / "a.txt").is_file()
    r = CliRunner().invoke(app, ["install", str(src), "--target", str(t)])
    assert r.exit_code == 1 and "Traceback" not in r.output

def test_cli_install_picks_from_prompt(tmp_path, monkeypatch):
    src = tmp_path / "v"; src.mkdir()
    a, b = tmp_path / "a", tmp_path / "b"; a.mkdir(); b.mkdir()
    monkeypatch.setattr(install, "default_targets", lambda: [a, b])
    r = CliRunner().invoke(app, ["install", str(src)], input="2\n")
    assert r.exit_code == 0 and (b / "v").is_dir() and not (a / "v").exists()

def test_cli_verify_invalid_folder(tmp_path):
    (tmp_path / "v").mkdir()
    r = CliRunner().invoke(app, ["verify", str(tmp_path / "v")])
    assert r.exit_code == 1 and "Traceback" not in r.output

def test_install_dot_from_inside_voice_folder_is_refused(tmp_path, monkeypatch):
    models = tmp_path / "models"
    for n in ("v", "other"):
        (models / n).mkdir(parents=True); (models / n / "a.txt").write_text(n)
    monkeypatch.chdir(models / "v")
    with pytest.raises(ValueError):
        install.install_voice(Path("."), models, overwrite=True)
    assert (models / "v" / "a.txt").read_text() == "v" and (models / "other" / "a.txt").read_text() == "other"
    r = CliRunner().invoke(app, [ "install", ".", "--target", str(models), "--overwrite"])
    assert r.exit_code == 1 and "Traceback" not in r.output and (models / "other" / "a.txt").is_file()

def test_source_containing_target_is_refused(tmp_path):
    src = tmp_path / "v"; (src / "models").mkdir(parents=True); (src / "a.txt").write_text("1")
    with pytest.raises(ValueError):
        install.install_voice(src, src / "models")
    with pytest.raises(ValueError):
        install.install_voice(src, src)
    assert sorted(p.name for p in src.iterdir()) == ["a.txt", "models"]

def test_swap_dir_refuses_ancestor_target(tmp_path):
    from omnivoice.fsutil import swap_dir
    models = tmp_path / "models"; (models / ".t").mkdir(parents=True); (models / "keep").mkdir()
    with pytest.raises(ValueError):
        swap_dir(models / ".t", models)
    assert (models / "keep").is_dir() and (models / ".t").is_dir()


def test_find_targets_in_launchers_with_the_mod(tmp_path, monkeypatch):
    appdata, home = tmp_path / "AppData", tmp_path / "home"
    mr = appdata / "ModrinthApp/profiles/123123"; (mr / "mods").mkdir(parents=True)
    (mr / "mods/omnichat-0.1.jar").write_bytes(b"jar")                          # the mod, no models yet
    (appdata / "ModrinthApp/profiles/Vanilla/mods").mkdir(parents=True)        # no OmniChat: skipped
    cf = home / "curseforge/minecraft/Instances/Pack"; (cf / "config/omnichat").mkdir(parents=True)
    pr = appdata / "PrismLauncher/instances/Inst/minecraft"; (pr / "config/omnichat/models").mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata)); monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.chdir(tmp_path)
    found = [(t.launcher, t.name, t.path) for t in install.find_targets()]
    assert found == [("Prism", "Inst", pr / "config/omnichat/models"),
                     ("Modrinth", "123123", mr / "config/omnichat/models"),
                     ("CurseForge", "Pack", cf / "config/omnichat/models")]


def test_models_dir_for_a_picked_folder(tmp_path):
    game = tmp_path / "profile"; (game / "mods").mkdir(parents=True)
    assert install.models_dir_for(game) == game / "config/omnichat/models"
    assert install.models_dir_for(game / "config/omnichat") == game / "config/omnichat/models"
    models = tmp_path / "anything/models"; models.mkdir(parents=True)
    assert install.models_dir_for(models) == models
