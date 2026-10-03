from typer.testing import CliRunner
from omnivoice.cli import app
from omnivoice import __version__

def test_version():
    r = CliRunner().invoke(app, ["--version"])
    assert r.exit_code == 0 and __version__ in r.output

def test_cli_cyrillic_output_does_not_raise():
    from typer.testing import CliRunner
    from omnivoice.cli import app
    r = CliRunner().invoke(app, ["init", "/nonexistent/да/x", "--name", "Тест", "--language", "zz"])
    assert r.exception is None or isinstance(r.exception, SystemExit)

def test_force_utf8_reconfigures_streams(monkeypatch):
    import io, sys
    from omnivoice import cli
    raw = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(raw, encoding="cp1251"))
    monkeypatch.setattr(sys, "stderr", io.TextIOWrapper(io.BytesIO(), encoding="cp1251"))
    cli._force_utf8()
    print("Привет → ✓")
    sys.stdout.flush()
    assert raw.getvalue().decode("utf-8").strip() == "Привет → ✓"

def test_ui_command_launches(monkeypatch, tmp_path):
    import pytest
    pytest.importorskip("gradio")
    from omnivoice.ui import app as ui_app
    seen = {}
    monkeypatch.setattr(ui_app, "launch", lambda root, port, inbrowser: seen.update(root=root, port=port, inb=inbrowser))
    r = CliRunner().invoke(app, ["ui", "--projects", str(tmp_path), "--port", "7999", "--no-browser"])
    assert r.exit_code == 0, r.output
    assert seen == {"root": tmp_path, "port": 7999, "inb": False}
