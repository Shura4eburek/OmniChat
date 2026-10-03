import pytest
gr = pytest.importorskip("gradio")
from omnivoice.ui.app import build
from omnivoice.project import Project


def test_build_lists_projects(tmp_path):
    Project.create(tmp_path / "glados", name="glados", language="ru")
    demo = build(tmp_path)
    assert isinstance(demo, gr.Blocks)


def test_strings_have_no_empty_values():
    from omnivoice.ui import strings
    assert all(isinstance(v, str) and v for k, v in vars(strings).items() if k.isupper())


def test_build_does_not_probe_env(tmp_path, monkeypatch):
    from omnivoice import train
    def boom(*a, **k):
        raise AssertionError("detect_env must not run inside build()")
    monkeypatch.setattr(train, "detect_env", boom)
    assert isinstance(build(tmp_path), gr.Blocks)


def test_theme_and_css_present():
    from omnivoice.ui import theme
    assert isinstance(theme.THEME, gr.themes.Base)
    assert ".hud-panel" in theme.CSS and "::before" in theme.CSS and ".st.done" in theme.CSS


def test_upload_and_export_hold_project_lock():
    import inspect, re
    from omnivoice.ui import app as ui_app
    src = inspect.getsource(ui_app.build)
    for fn, op in (("on_upload", "OP_UPLOAD"), ("on_export", "OP_EXPORT")):
        body = re.search(rf"def {fn}\(.*?(?=\n        @|\n        def |\n        [a-z_]+\.(click|upload)\()", src, re.S).group(0)
        assert f"with locked(name, S.{op})" in body, fn


def test_build_survives_corrupt_review_json(tmp_path):
    from omnivoice import dataset
    from omnivoice.dataset import Segment
    p = Project.create(tmp_path / "glados", name="glados", language="ru")
    dataset.save(p, [Segment("a", "x", 1.0)])
    p.review_json.write_text("{broken", encoding="utf-8")
    assert isinstance(build(tmp_path), gr.Blocks)
