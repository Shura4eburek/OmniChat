"""Configurable dependency location (paths.cache_dir / config.json) and moving it (datadir.move_data).
Never touches WSL: every wsl.exe call goes through a fake `run`."""
import json
import os
import shutil
import subprocess
from collections import namedtuple
from pathlib import Path

import pytest

from omnivoice import datadir, paths, wslenv
from omnivoice.datadir import DataDirError

Usage = namedtuple("Usage", "total used free")
BIG = Usage(10**13, 0, 10**12)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.delenv("OMNIVOICE_CACHE", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setattr(paths.sys, "platform", "win32")
    return tmp_path


# ---------- paths: resolution order ----------

def test_default_when_nothing_configured(env):
    assert paths.cache_source() == (env / "local" / "omnivoice", "default")
    assert paths.cache_dir() == env / "local" / "omnivoice" and paths.cache_dir().is_dir()


def test_config_path_is_in_appdata(env):
    assert paths.config_path() == env / "roaming" / "omnivoice" / "config.json"


def test_config_beats_default_and_env_beats_config(env, monkeypatch):
    paths.set_data_dir(env / "g" / "omnivoice")
    assert paths.cache_source() == (env / "g" / "omnivoice", "config")
    assert paths.cache_dir() == env / "g" / "omnivoice"
    monkeypatch.setenv("OMNIVOICE_CACHE", str(env / "envdir"))
    assert paths.cache_source() == (env / "envdir", "env")


def test_broken_config_falls_back_to_default(env):
    paths.config_path().parent.mkdir(parents=True)
    paths.config_path().write_text("{не json", encoding="utf-8")
    assert paths.cache_source()[1] == "default"
    paths.config_path().write_text('{"data_dir": ""}', encoding="utf-8")
    assert paths.cache_source()[1] == "default"


def test_set_data_dir_keeps_other_keys(env):
    paths.config_path().parent.mkdir(parents=True)
    paths.config_path().write_text('{"other": 1}', encoding="utf-8")
    paths.set_data_dir(env / "x")
    assert json.loads(paths.config_path().read_text(encoding="utf-8")) == {"other": 1, "data_dir": str(env / "x")}


def test_set_data_dir_is_atomic(env, monkeypatch):
    paths.set_data_dir(env / "old")
    def boom(src, dst):
        raise OSError("диск отвалился")
    monkeypatch.setattr(paths.os, "replace", boom)
    with pytest.raises(OSError):
        paths.set_data_dir(env / "new")
    assert paths.cache_source() == (env / "old", "config")  # the old config is intact
    assert [p.name for p in paths.config_path().parent.iterdir()] == ["config.json"]  # no temp file left


def test_unavailable_data_dir_is_a_russian_oserror(env, monkeypatch):
    paths.set_data_dir(env / "g")
    def boom(*a, **k):
        raise OSError("нет диска")
    monkeypatch.setattr(Path, "mkdir", boom)
    with pytest.raises(OSError, match="недоступна"):
        paths.cache_dir()


def test_import_distro_lands_in_configured_dir(env):
    paths.set_data_dir(env / "g" / "omnivoice")
    seen = []
    def run(cmd, **kw):
        seen.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "Ubuntu\n" if cmd[:3] == ["wsl", "-l", "-q"] else "", "")
    wslenv.import_distro(env / "rootfs.tar.gz", run=run)
    imp = next(c for c in seen if "--import" in c)
    assert imp[3] == str(env / "g" / "omnivoice" / "wsl" / "omnivoice")


# ---------- move_data ----------

def _install(root: Path, vhdx=True):
    (root / "checkpoints" / "ru").mkdir(parents=True)
    (root / "checkpoints" / "ru" / "base.ckpt").write_bytes(b"c" * 100)
    (root / "ffmpeg" / "bin").mkdir(parents=True)
    (root / "ffmpeg" / "bin" / "ffmpeg.exe").write_bytes(b"f" * 50)
    (root / "wsl").mkdir(parents=True)
    (root / "wsl" / "install-attempted").write_text("1", encoding="utf-8")
    (root / "espeak.txt").write_text("e", encoding="utf-8")
    if vhdx:
        (root / "wsl" / "omnivoice").mkdir()
        (root / "wsl" / "omnivoice" / "ext4.vhdx").write_bytes(b"v" * 1000)


class FakeWsl:
    def __init__(self, old: Path, registered=True, move_rc=0, move_out="", listing_rc=0, on_move=None):
        self.old, self.registered, self.move_rc, self.move_out = old, registered, move_rc, move_out
        self.listing_rc, self.on_move = listing_rc, on_move
        self.cmds = []

    def __call__(self, cmd, **kw):
        self.cmds.append(cmd)
        if cmd[:3] == ["wsl", "-l", "-q"]:
            if self.listing_rc:
                return subprocess.CompletedProcess(cmd, self.listing_rc, "", "wsl сломан")
            return subprocess.CompletedProcess(cmd, 0, "omnivoice\n" if self.registered else "Ubuntu\n", "")
        if "--move" in cmd:
            if self.on_move:
                self.on_move()
            if self.move_rc == 0:
                dest = Path(cmd[-1])
                dest.mkdir(parents=True, exist_ok=True)
                shutil.move(str(self.old / "wsl" / "omnivoice" / "ext4.vhdx"), str(dest / "ext4.vhdx"))
            return subprocess.CompletedProcess(cmd, self.move_rc, self.move_out, "")
        return subprocess.CompletedProcess(cmd, 0, "", "")


def _move(new, run, lines=None, usage=BIG, volume=lambda p: (3, "NTFS")):
    return datadir.move_data(new, (lines if lines is not None else []).append, run=run,
                             disk_usage=lambda p: usage, volume=volume)


def test_move_order_wsl_then_copy_then_config_then_delete(env, monkeypatch):
    old, new = env / "local" / "omnivoice", env / "g" / "omnivoice"
    _install(old)
    events = []

    def on_move():
        events.append("wsl")
        assert not (new / "checkpoints").exists() and paths.cache_source()[1] == "default"
    real_set = paths.set_data_dir

    def set_data_dir(p):
        events.append("config")
        assert (new / "checkpoints" / "ru" / "base.ckpt").read_bytes() == b"c" * 100  # copied first
        assert (new / "wsl" / "omnivoice" / "ext4.vhdx").exists()
        assert (old / "checkpoints").exists()  # old copies are deleted only after the switch
        real_set(p)
    monkeypatch.setattr(paths, "set_data_dir", set_data_dir)
    run = FakeWsl(old, on_move=on_move)
    lines = []
    assert _move(str(new), run, lines) is True
    assert events == ["wsl", "config"]
    assert ["wsl", "--terminate", "omnivoice"] in run.cmds
    assert ["wsl", "--manage", "omnivoice", "--move", str(new / "wsl" / "omnivoice")] in run.cmds
    assert run.cmds.index(["wsl", "--terminate", "omnivoice"]) < next(i for i, c in enumerate(run.cmds) if "--move" in c)
    assert paths.cache_source() == (new, "config")
    assert (new / "ffmpeg" / "bin" / "ffmpeg.exe").exists() and (new / "espeak.txt").exists()
    assert (new / "wsl" / "install-attempted").exists()
    assert not old.exists()  # everything copied away, empty dirs removed
    assert any("Готово" in l for l in lines)


def test_move_without_distro_copies_files_only(env):
    old, new = env / "local" / "omnivoice", env / "g" / "omnivoice"
    _install(old, vhdx=False)
    run = FakeWsl(old, registered=False)
    assert _move(new, run) is True
    assert not any("--move" in c for c in run.cmds) and not any("--terminate" in c for c in run.cmds)
    assert (new / "checkpoints" / "ru" / "base.ckpt").exists() and paths.cache_source() == (new, "config")


def test_fresh_machine_only_sets_config(env):
    run = FakeWsl(env, registered=False, listing_rc=1)  # no WSL at all yet
    assert _move(env / "g" / "omnivoice", run) is True
    assert paths.cache_source() == (env / "g" / "omnivoice", "config")


def test_same_location_is_a_noop(env):
    old = env / "local" / "omnivoice"
    _install(old)
    run, lines = FakeWsl(old), []
    assert _move(str(old).upper() + "\\", run, lines) is False
    assert run.cmds == [] and paths.cache_source()[1] == "default"
    assert "переносить нечего" in lines[0]


def test_sharing_violation_explains_docker(env):
    old = env / "local" / "omnivoice"
    _install(old)
    run = FakeWsl(old, move_rc=1, move_out="Процесс не может получить доступ к файлу, так как этот файл "
                                           "используется другим процессом.\nКод ошибки: Wsl/ERROR_SHARING_VIOLATION")
    with pytest.raises(DataDirError) as e:
        _move(env / "g" / "omnivoice", run)
    msg = str(e.value)
    assert "Docker Desktop" in msg and "wsl --shutdown" in msg
    assert not any(c == ["wsl", "--shutdown"] for c in run.cmds)  # never runs it itself
    assert paths.cache_source()[1] == "default" and (old / "checkpoints").exists()


def test_other_wsl_move_failure(env):
    old = env / "local" / "omnivoice"
    _install(old)
    with pytest.raises(DataDirError, match="Не удалось перенести среду WSL"):
        _move(env / "g" / "omnivoice", FakeWsl(old, move_rc=5, move_out="Unknown option --manage"))
    assert paths.cache_source()[1] == "default"


def test_copy_failure_keeps_setting_and_old_files(env, monkeypatch):
    old, new = env / "local" / "omnivoice", env / "g" / "omnivoice"
    _install(old)
    real = shutil.copytree

    def copytree(src, dst, *a, **k):
        if Path(src).name == "ffmpeg":
            raise OSError("нет места")
        return real(src, dst, *a, **k)
    monkeypatch.setattr(datadir.shutil, "copytree", copytree)
    with pytest.raises(DataDirError) as e:
        _move(new, FakeWsl(old))
    assert "нет места" in str(e.value) and "WSL уже перенесена" in str(e.value)
    assert paths.cache_source()[1] == "default"
    assert (old / "checkpoints" / "ru" / "base.ckpt").exists() and (old / "ffmpeg").exists()
    assert not (new / "checkpoints").exists()  # partial copies cleaned up
    # retry: the distro already lives in the new place → no second wsl --move
    run = FakeWsl(old)
    monkeypatch.setattr(datadir.shutil, "copytree", real)
    assert _move(new, run) is True
    assert not any("--move" in c for c in run.cmds) and paths.cache_source() == (new, "config")


def test_copy_size_mismatch_is_detected(env, monkeypatch):
    old, new = env / "local" / "omnivoice", env / "g" / "omnivoice"
    _install(old, vhdx=False)
    def bad_copy(src, dst, *a, **k):
        Path(dst).mkdir(parents=True)
        (Path(dst) / "half").write_bytes(b"x")
    monkeypatch.setattr(datadir.shutil, "copytree", bad_copy)
    with pytest.raises(DataDirError, match="не совпадает"):
        _move(new, FakeWsl(old, registered=False))
    assert paths.cache_source()[1] == "default" and (old / "checkpoints").exists()


def test_delete_failure_is_only_a_warning(env, monkeypatch):
    old, new = env / "local" / "omnivoice", env / "g" / "omnivoice"
    _install(old, vhdx=False)
    def rmtree(p, *a, **k):
        raise OSError("занято")
    monkeypatch.setattr(datadir.shutil, "rmtree", rmtree)
    lines = []
    assert _move(new, FakeWsl(old, registered=False), lines) is True
    assert paths.cache_source() == (new, "config")
    assert any("Не удалось удалить" in l for l in lines)


# ---------- move_data: validation ----------

@pytest.fixture
def installed(env):
    _install(env / "local" / "omnivoice")
    return env


def _err(new, **kw):
    with pytest.raises(DataDirError) as e:
        _move(new, FakeWsl(Path("nowhere")), **kw)
    assert paths.cache_source()[1] == "default"
    return str(e.value)


def test_relative_path_rejected(installed):
    assert "полный путь" in _err("omnivoice-data")


def test_empty_path_rejected(installed):
    assert "Укажи папку" in _err("  ")


def test_drive_root_rejected(installed):
    assert "корень диска" in _err("G:\\")


def test_inside_current_rejected(installed):
    assert "внутри текущей" in _err(installed / "local" / "omnivoice" / "sub")


def test_missing_drive_rejected(installed):
    assert "не найден" in _err(installed / "g", volume=lambda p: (1, None))


def test_network_or_removable_drive_rejected(installed):
    assert "не локальный" in _err(installed / "g", volume=lambda p: (4, "NTFS"))
    assert "не локальный" in _err(installed / "g", volume=lambda p: (2, "NTFS"))


def test_non_ntfs_rejected(installed):
    assert "exFAT" in _err(installed / "g", volume=lambda p: (3, "exFAT"))


def test_not_enough_space_rejected(installed):
    # 1152 bytes of data + 10 % headroom = 1267 > 1200 free
    msg = _err(installed / "g", usage=Usage(10**6, 0, 1200))
    assert "Мало места" in msg


def test_write_test_failure_rejected(installed, monkeypatch):
    real = Path.write_bytes

    def write_bytes(self, data):
        if self.name.startswith(".omnivoice-write-test"):
            raise PermissionError("доступ запрещён")
        return real(self, data)
    monkeypatch.setattr(Path, "write_bytes", write_bytes)
    assert "Не удалось записать" in _err(installed / "g")


def test_existing_entries_in_target_rejected(installed):
    (installed / "g" / "checkpoints").mkdir(parents=True)
    assert "уже есть" in _err(installed / "g")


def test_env_var_location_cannot_be_moved(installed, monkeypatch):
    monkeypatch.setenv("OMNIVOICE_CACHE", str(installed / "local" / "omnivoice"))
    with pytest.raises(DataDirError, match="OMNIVOICE_CACHE"):
        _move(installed / "g", FakeWsl(installed))


def test_refused_while_training(installed, monkeypatch):
    from omnivoice import train
    monkeypatch.setitem(train._ACTIVE, "omnivoice-x", "wsl")
    assert "обучение" in _err(installed / "g").lower()


def test_human_size():
    assert datadir.human_size(int(12.5 * 2**30)) == "12,5 ГБ"
    assert datadir.human_size(3 * 2**20) == "3,0 МБ"
    assert datadir.human_size(10) == "10 Б"


def test_describe(env):
    _install(env / "local" / "omnivoice", vhdx=False)
    path, source, size = datadir.describe()
    assert path == env / "local" / "omnivoice" and source == "default" and size == 100 + 50 + 1 + 1
