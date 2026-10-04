from pathlib import Path
import pytest
from typer.testing import CliRunner
from omnivoice.project import Project, STEPS, ProjectError
from omnivoice import languages
from omnivoice.cli import app

def test_create_load_roundtrip(tmp_path: Path):
    p = Project.create(tmp_path / "glados", name="glados", language="ru")
    assert p.espeak_voice == "ru" and p.base_checkpoint == languages.PRESETS["ru"].base_checkpoint
    assert p.raw_dir.is_dir() and p.segments_dir.is_dir()
    p.mark("audio"); p.display["description"] = "Злой ИИ"; p.save()
    q = Project.load(tmp_path / "glados")
    assert q.steps["audio"] is True and q.display["description"] == "Злой ИИ"
    assert set(q.steps) == set(STEPS)

def test_create_with_named_base(tmp_path: Path):
    p = Project.create(tmp_path / "x", name="x", language="ru", base="denis")
    assert "denis" in p.base_checkpoint

def test_unknown_language_is_rejected(tmp_path: Path):
    with pytest.raises(ProjectError, match="Неизвестный язык"):
        Project.create(tmp_path / "x", name="x", language="xx")

def test_unknown_base_is_rejected(tmp_path: Path):
    with pytest.raises(ProjectError, match="Неизвестная базовая модель"):
        Project.create(tmp_path / "x", name="x", language="ru", base="unknown")

def test_load_missing_project_toml(tmp_path: Path):
    with pytest.raises(ProjectError, match="нет project.toml"):
        Project.load(tmp_path / "x")

def test_load_corrupt_toml(tmp_path: Path):
    root = tmp_path / "x"
    root.mkdir()
    (root / "project.toml").write_text("invalid toml [[[")
    with pytest.raises(ProjectError, match="повреждён"):
        Project.load(root)

def test_init_command_bad_base(tmp_path: Path):
    r = CliRunner().invoke(app, ["init", str(tmp_path / "x"), "--name", "x", "--language", "ru", "--base", "unknown"])
    assert r.exit_code == 1
    assert "Неизвестная базовая модель" in r.output

def test_init_command(tmp_path: Path):
    r = CliRunner().invoke(app, ["init", str(tmp_path / "v"), "--name", "v", "--language", "en"])
    assert r.exit_code == 0, r.output
    assert Project.load(tmp_path / "v").espeak_voice == "en-us"

def test_init_refuses_existing_project(tmp_path: Path):
    Project.create(tmp_path / "v", name="v", language="ru")
    with pytest.raises(ProjectError, match="уже есть проект"):
        Project.create(tmp_path / "v", name="other", language="en")
    assert Project.load(tmp_path / "v").name == "v"
    r = CliRunner().invoke(app, ["init", str(tmp_path / "v"), "--name", "x"])
    assert r.exit_code == 1 and "уже есть проект" in r.output and "Traceback" not in r.output

def test_save_is_atomic_and_leaves_no_tmp(tmp_path: Path):
    p = Project.create(tmp_path / "v", name="v", language="ru")
    p.display["name"] = "Новое"; p.save()
    assert not list(p.root.glob("*.tmp")) and not list(p.root.glob(".*tmp"))
    assert Project.load(p.root).display["name"] == "Новое"

def test_mark_saved_keeps_concurrent_edits(tmp_path: Path):
    stale = Project.create(tmp_path / "v", name="v", language="ru")
    other = Project.load(stale.root); other.display["description"] = "из UI"; other.save()
    stale.mark_fresh("train")
    q = Project.load(stale.root)
    assert q.display["description"] == "из UI" and q.steps["train"] is True and stale.steps["train"] is True
    Project.mark_saved(stale.root, ("audio", "slice"))
    assert Project.load(stale.root).steps["slice"] is True
    Project.mark_saved(stale.root, "slice", False)
    assert Project.load(stale.root).steps["slice"] is False

def test_load_corrupt_toml_names_file(tmp_path: Path):
    root = tmp_path / "x"; root.mkdir()
    (root / "project.toml").write_text('name = "x"\nlanguage = ', encoding="utf-8")
    with pytest.raises(ProjectError, match="Файл project.toml повреждён"):
        Project.load(root)


def test_delete_project_removes_folder_and_reports_size(tmp_path):
    from omnivoice.project import delete_project
    p = Project.create(tmp_path / "Arthas", name="Arthas", language="ru")
    (p.train_dir / "big.ckpt").write_bytes(b"x" * 1000)
    other = Project.create(tmp_path / "Jaina", name="Jaina", language="ru")
    assert delete_project(p, tmp_path) >= 1000
    assert not (tmp_path / "Arthas").exists() and (other.root / "project.toml").is_file()


def test_delete_project_refuses_anything_but_a_project_folder(tmp_path):
    from omnivoice.project import delete_project
    nested = Project.create(tmp_path / "a" / "b", name="b", language="ru")
    with pytest.raises(ProjectError):
        delete_project(nested, tmp_path)  # not a direct child of the projects folder
    assert nested.root.is_dir()
    (nested.root / "project.toml").unlink()
    with pytest.raises(ProjectError):
        delete_project(nested, tmp_path / "a")  # no project.toml: not a project
    assert nested.root.is_dir()
