import io
import subprocess
import zipfile
from pathlib import Path

import pytest

from omnivoice import deps, slicer, wslenv


@pytest.fixture(autouse=True)
def cache(tmp_path, monkeypatch):
    monkeypatch.setenv("OMNIVOICE_CACHE", str(tmp_path / "cache"))
    monkeypatch.setattr(deps.shutil, "which", lambda n: None)


def make_zip(path: Path, with_probe=True):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("ffmpeg-9.0.2-essentials_build/bin/ffmpeg.exe", b"FF")
        if with_probe:
            z.writestr("ffmpeg-9.0.2-essentials_build/bin/ffprobe.exe", b"PR")
        z.writestr("ffmpeg-9.0.2-essentials_build/bin/ffplay.exe", b"PL")
        z.writestr("ffmpeg-9.0.2-essentials_build/doc/readme.html", b"x")


def test_ffmpeg_path_prefers_path_then_cache(tmp_path, monkeypatch):
    assert deps.ffmpeg_path() is None
    (deps.ffmpeg_dir()).mkdir(parents=True)
    (deps.ffmpeg_dir() / "ffmpeg.exe").write_bytes(b"x")
    assert deps.ffmpeg_path() == str(deps.ffmpeg_dir() / "ffmpeg.exe")
    monkeypatch.setattr(deps.shutil, "which", lambda n: "C:/bin/ffmpeg.exe")
    assert deps.ffmpeg_path() == "C:/bin/ffmpeg.exe"


def test_extract_only_two_exes_atomically(tmp_path):
    z = tmp_path / "f.zip"
    make_zip(z)
    dest = deps.extract_ffmpeg(z)
    assert sorted(p.name for p in dest.iterdir()) == ["ffmpeg.exe", "ffprobe.exe"]
    assert (dest / "ffmpeg.exe").read_bytes() == b"FF"
    assert [p.name for p in dest.parent.iterdir()] == ["bin"]  # no temp leftovers
    deps.extract_ffmpeg(z)  # re-extract over existing


def test_extract_missing_exe_keeps_old_and_cleans(tmp_path):
    z = tmp_path / "f.zip"
    make_zip(z)
    deps.extract_ffmpeg(z)
    make_zip(z, with_probe=False)
    with pytest.raises(deps.DepsError, match="ffprobe.exe"):
        deps.extract_ffmpeg(z)
    assert (deps.ffmpeg_dir() / "ffprobe.exe").is_file()
    assert [p.name for p in deps.ffmpeg_dir().parent.iterdir()] == ["bin"]


def test_extract_bad_zip(tmp_path):
    z = tmp_path / "f.zip"
    z.write_bytes(b"nope")
    with pytest.raises(deps.DepsError, match="повреждён"):
        deps.extract_ffmpeg(z)


def test_install_ffmpeg_downloads_verifies_and_extracts(tmp_path, monkeypatch):
    seen = {}

    def fake_fetch(urls, target, **kw):
        seen.update(urls=urls, kw=kw)
        target.parent.mkdir(parents=True, exist_ok=True)
        make_zip(target)
        return target

    monkeypatch.setattr(deps.download, "fetch", fake_fetch)
    out = deps.install_ffmpeg()
    assert out.endswith("ffmpeg.exe") and Path(out).read_bytes() == b"FF"
    assert seen["kw"]["sha256"] == deps.FFMPEG_SHA256 and seen["kw"]["error"] is deps.DepsError
    assert not (deps.ffmpeg_dir().parent / deps.FFMPEG_ZIP).exists()


def test_install_ffmpeg_skips_when_present(monkeypatch):
    monkeypatch.setattr(deps.shutil, "which", lambda n: "ffmpeg")
    monkeypatch.setattr(deps.download, "fetch", lambda *a, **k: pytest.fail("download"))
    assert deps.install_ffmpeg() == "ffmpeg"


class FakePopen:
    def __init__(self, cmd, **kw):
        self.cmd = cmd
        self.stdout = io.StringIO("line1\n\nline2\n")
        self.returncode = 0

    def wait(self):
        return self.returncode


def test_install_prep_repo_checkout(monkeypatch):
    monkeypatch.setattr(deps.shutil, "which", lambda n: "C:/uv.exe")
    got = []
    cmds = []
    monkeypatch.setattr(deps, "repo_root", lambda: Path("R"))

    def pop(cmd, **kw):
        cmds.append(cmd)
        return FakePopen(cmd)

    deps.install_prep(got.append, popen=pop)
    assert cmds[0] == ["C:/uv.exe", "sync", "--all-extras", "--project", "R"]
    assert got == ["line1", "line2"]


def test_install_prep_installed_package(monkeypatch):
    monkeypatch.setattr(deps.shutil, "which", lambda n: "uv")
    monkeypatch.setattr(deps, "repo_root", lambda: None)
    cmds = []
    deps.install_prep(lambda l: None, popen=lambda c, **k: cmds.append(c) or FakePopen(c))
    assert cmds[0][:4] == ["uv", "pip", "install", "--python"] and cmds[0][-1] == "omnivoice[prep,ui]"


def test_install_prep_uv_missing_and_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(deps.sys, "executable", str(tmp_path / "python.exe"))
    with pytest.raises(deps.DepsError, match="Не найден uv"):
        deps.install_prep(lambda l: None)
    (tmp_path / "uv.exe").write_bytes(b"")
    assert deps.find_uv() == str(tmp_path / "uv.exe")

    class Bad(FakePopen):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self.returncode = 2

    with pytest.raises(deps.DepsError, match="код 2"):
        deps.install_prep(lambda l: None, popen=Bad)


def test_repo_root_is_this_checkout():
    assert (deps.repo_root() / "pyproject.toml").is_file()


def status(**kw):
    base = dict(wsl=True, wsl_version_ok=True, distro=True, ready=True, gpu=True, message="готова")
    base.update(kw)
    return wslenv.EnvStatus(**base)


def items(monkeypatch, st, prep=True, ff=True, docker=True):
    monkeypatch.setattr(deps.wslenv, "status", lambda run=None: st)
    monkeypatch.setattr(deps, "prep_ok", lambda: prep)
    monkeypatch.setattr(deps, "ffmpeg_path", lambda: "ffmpeg.exe" if ff else None)
    monkeypatch.setattr(deps.shutil, "which", lambda n: "docker.exe" if docker else None)
    return {i.name: i for i in deps.check_all()}


def test_check_all_everything_ok(monkeypatch):
    it = items(monkeypatch, status())
    assert all(i.ok for i in it.values())
    assert [i.name for i in it.values()] == [deps.PREP, deps.FFMPEG, deps.WSL, deps.ENV, "GPU в WSL", "Docker"]


def test_check_all_each_item_fails_separately(monkeypatch):
    assert not items(monkeypatch, status(), prep=False)[deps.PREP].ok
    assert not items(monkeypatch, status(), ff=False)[deps.FFMPEG].ok
    it = items(monkeypatch, status(wsl=False, wsl_version_ok=False, distro=False, ready=False, gpu=None, message="нет"))
    assert not it[deps.WSL].ok and "не установлен" in it[deps.WSL].detail and not it[deps.ENV].ok
    assert not items(monkeypatch, status(wsl_version_ok=False))[deps.WSL].ok
    assert not items(monkeypatch, status(ready=False, gpu=None))[deps.ENV].ok
    gpu = items(monkeypatch, status(gpu=False))["GPU в WSL"]
    assert not gpu.ok and gpu.optional
    dk = items(monkeypatch, status(), docker=False)["Docker"]
    assert not dk.ok and dk.optional


def test_check_all_never_runs_docker(monkeypatch):
    monkeypatch.setattr(deps.wslenv, "status", lambda run=None: status())
    ran = []
    monkeypatch.setattr(deps.subprocess, "run", lambda *a, **k: ran.append(a))
    deps.check_all()
    assert ran == []


def fake_install(monkeypatch, st, calls, reboot=False, **flags):
    items(monkeypatch, st, **flags)
    monkeypatch.setattr(deps, "install_prep", lambda on_line: calls.append("prep"))
    monkeypatch.setattr(deps, "install_ffmpeg", lambda progress=None: calls.append("ffmpeg"))

    def ready(on_line, progress=None):
        calls.append("wsl")
        if reboot:
            raise wslenv.RebootRequired(wslenv.REBOOT_MSG)

    monkeypatch.setattr(deps.wslenv, "ensure_ready", ready)


def test_install_all_order(monkeypatch):
    calls = []
    fake_install(monkeypatch, status(ready=False, distro=False, gpu=None), calls, prep=False, ff=False)
    assert deps.install_all(lambda l: None) is None
    assert calls == ["prep", "ffmpeg", "wsl"]


def test_install_all_skips_ok_items(monkeypatch):
    calls = []
    fake_install(monkeypatch, status(), calls)
    deps.install_all(lambda l: None)
    assert calls == []
    calls.clear()
    fake_install(monkeypatch, status(), calls, ff=False)
    deps.install_all(lambda l: None)
    assert calls == ["ffmpeg"]


def test_install_all_stops_on_reboot(monkeypatch):
    calls, lines = [], []
    fake_install(monkeypatch, status(wsl=False, wsl_version_ok=False, distro=False, ready=False, gpu=None), calls,
                 reboot=True, prep=False)
    msg = deps.install_all(lines.append)
    assert "перезагрузк" in msg and calls == ["prep", "wsl"]
    assert lines[-1] == msg


def test_slicer_uses_ffmpeg_path(monkeypatch):
    monkeypatch.setattr(slicer.deps, "ffmpeg_path", lambda: "C:/cache/ffmpeg.exe")
    seen = []

    def run(cmd, **kw):
        seen.append(cmd[0])
        return subprocess.CompletedProcess(cmd, 0, stdout=b"")

    monkeypatch.setattr(slicer.subprocess, "run", run)
    slicer._decode(Path("a.mp4"))
    assert seen == ["C:/cache/ffmpeg.exe"]


def test_slicer_missing_ffmpeg_points_to_setup(monkeypatch):
    monkeypatch.setattr(slicer.deps, "ffmpeg_path", lambda: None)
    with pytest.raises(RuntimeError, match="Установить зависимости.*omnivoice setup"):
        slicer._decode(Path("a.mp4"))
