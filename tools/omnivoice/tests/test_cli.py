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


# ---------- omnivoice setup ----------
import pytest
from omnivoice import deps, wslenv


def _items(*, env_ok=True, docker=False):
    return [deps.Item(deps.PREP, True, "установлены"), deps.Item(deps.FFMPEG, True, "C:/ff/ffmpeg.exe"),
            deps.Item(deps.WSL, True, "готов"), deps.Item(deps.ENV, env_ok, "готова" if env_ok else "не создана"),
            deps.Item("GPU в WSL", env_ok, "доступен", optional=True),
            deps.Item("Docker", docker, "не найден", optional=True)]


def test_setup_check_all_ok_exits_0(monkeypatch):
    monkeypatch.setattr(deps, "check_all", lambda: _items())
    monkeypatch.setattr(deps, "install_all", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no install")))
    r = CliRunner().invoke(app, ["setup", "--check"])
    assert r.exit_code == 0, r.output
    assert "✓ Пакеты (prep, ui) — установлены" in r.output
    assert "✗ Docker (необязательно) — не найден" in r.output


def test_setup_check_missing_required_exits_1(monkeypatch):
    monkeypatch.setattr(deps, "check_all", lambda: _items(env_ok=False))
    r = CliRunner().invoke(app, ["setup", "--check"])
    assert r.exit_code == 1
    assert "✗ Среда обучения — не создана" in r.output
    assert "omnivoice setup" in r.output


def test_setup_runs_install_and_streams(monkeypatch):
    state = {"done": False}
    monkeypatch.setattr(deps, "check_all", lambda: _items(env_ok=state["done"]))

    def fake_install(on_line, progress=None):
        on_line("Скачиваю ffmpeg…")
        for done in (0, 50, 100):
            progress(done, 100)
        on_line("STEP 2/7 Ставлю torch")
        on_line("обычная строка")
        state["done"] = True
        return None
    monkeypatch.setattr(deps, "install_all", fake_install)
    r = CliRunner().invoke(app, ["setup"])
    assert r.exit_code == 0, r.output
    assert "✗ Среда обучения" in r.output and "✓ Среда обучения" in r.output  # before and after
    assert "[2/7] Ставлю torch" in r.output and "обычная строка" in r.output
    assert "Скачиваю: 50%" in r.output and "Скачиваю: 100%" in r.output


def test_setup_reboot_exits_2(monkeypatch):
    monkeypatch.setattr(deps, "check_all", lambda: _items(env_ok=False))
    monkeypatch.setattr(deps, "install_all", lambda on_line, progress=None: "Перезагрузи компьютер")
    r = CliRunner().invoke(app, ["setup"])
    assert r.exit_code == 2
    assert "Перезагрузи компьютер" in r.output


@pytest.mark.parametrize("exc", [deps.DepsError("нет uv"), wslenv.WslError("нет uv"),
                                 __import__("omnivoice.train", fromlist=["TrainError"]).TrainError("нет uv")])
def test_setup_errors_exit_1_without_traceback(monkeypatch, exc):
    monkeypatch.setattr(deps, "check_all", lambda: _items(env_ok=False))
    def boom(on_line, progress=None):
        raise exc
    monkeypatch.setattr(deps, "install_all", boom)
    r = CliRunner().invoke(app, ["setup"])
    assert r.exit_code == 1
    assert "нет uv" in r.output and "Traceback" not in r.output
    assert r.exception is None or isinstance(r.exception, SystemExit)


def test_setup_check_failure_is_friendly(monkeypatch):
    def boom():
        raise OSError("wsl.exe недоступен")
    monkeypatch.setattr(deps, "check_all", boom)
    r = CliRunner().invoke(app, ["setup", "--check"])
    assert r.exit_code == 1 and "wsl.exe недоступен" in r.output


def test_setup_check_without_gpu_exits_0_and_points_to_colab(monkeypatch):
    st = wslenv.EnvStatus(False, False, False, False, None, "WSL не установлен")
    monkeypatch.setattr(deps.wslenv, "status", lambda run=None: st)
    monkeypatch.setattr(deps, "host_gpu", lambda run=None: False)
    monkeypatch.setattr(deps, "prep_ok", lambda: True)
    monkeypatch.setattr(deps, "ffmpeg_path", lambda: "C:/ff/ffmpeg.exe")
    r = CliRunner().invoke(app, ["setup", "--check"])
    assert r.exit_code == 0, r.output
    assert f"✗ Среда обучения (необязательно) — {deps.NO_GPU_DETAIL}" in r.output


# ---------- omnivoice data-dir ----------
from omnivoice import datadir


def test_data_dir_without_argument_prints_location(monkeypatch, tmp_path):
    monkeypatch.setattr(datadir, "describe", lambda: (tmp_path / "omnivoice", "config", 3 * 2**30))
    monkeypatch.setattr(datadir, "move_data", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no move")))
    r = CliRunner().invoke(app, ["data-dir"])
    assert r.exit_code == 0, r.output
    assert str(tmp_path / "omnivoice") in r.output and "3,0 ГБ" in r.output and "config.json" in r.output


def test_data_dir_with_argument_moves_and_streams(monkeypatch, tmp_path):
    seen = {}
    def move(new_root, on_line, **kw):
        seen["to"] = new_root
        on_line("Копирую checkpoints…")
        return True
    monkeypatch.setattr(datadir, "move_data", move)
    r = CliRunner().invoke(app, ["data-dir", str(tmp_path / "g")])
    assert r.exit_code == 0, r.output
    assert seen["to"] == str(tmp_path / "g") and "Копирую checkpoints…" in r.output


def test_data_dir_error_exits_1_without_traceback(monkeypatch, tmp_path):
    def move(new_root, on_line, **kw):
        raise datadir.DataDirError("Мало места на диске G:")
    monkeypatch.setattr(datadir, "move_data", move)
    r = CliRunner().invoke(app, ["data-dir", str(tmp_path / "g")])
    assert r.exit_code == 1 and "Мало места на диске G:" in r.output
    assert r.exception is None or isinstance(r.exception, SystemExit)
    assert "Traceback" not in r.output


def test_setup_data_dir_sets_location_before_install(monkeypatch, tmp_path):
    order = []
    monkeypatch.setattr(datadir, "move_data", lambda new_root, on_line, **kw: order.append(("move", new_root)) or True)
    monkeypatch.setattr(deps, "check_all", lambda: order.append("check") or _items())
    monkeypatch.setattr(deps, "install_all", lambda on_line, progress=None: order.append("install"))
    r = CliRunner().invoke(app, ["setup", "--data-dir", str(tmp_path / "g")])
    assert r.exit_code == 0, r.output
    assert order[0] == ("move", str(tmp_path / "g")) and "install" in order


def test_setup_data_dir_error_stops_before_install(monkeypatch, tmp_path):
    def move(new_root, on_line, **kw):
        raise datadir.DataDirError("Диск G: не найден")
    monkeypatch.setattr(datadir, "move_data", move)
    monkeypatch.setattr(deps, "install_all", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no install")))
    r = CliRunner().invoke(app, ["setup", "--data-dir", r"G:\x"])
    assert r.exit_code == 1 and "Диск G: не найден" in r.output
