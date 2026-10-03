import io
import subprocess
import zipfile
from pathlib import Path

import pytest

from omnivoice import deps, slicer, wslenv


@pytest.fixture(autouse=True)
def cache(tmp_path, monkeypatch):
    monkeypatch.setattr(deps, "prep_ok", lambda: False)
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
    assert cmds[0] == ["C:/uv.exe", "sync", "--all-extras", "--inexact", "--project", "R"]
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


def test_install_prep_skips_when_already_installed(monkeypatch):
    monkeypatch.setattr(deps, "prep_ok", lambda: True)
    got = []
    deps.install_prep(got.append, popen=lambda *a, **k: pytest.fail("uv"))
    assert got == ["Пакеты уже установлены"]


def test_install_prep_invalidates_import_caches(monkeypatch):
    monkeypatch.setattr(deps.shutil, "which", lambda n: "uv")
    called = []
    monkeypatch.setattr(deps.importlib, "invalidate_caches", lambda: called.append(1))
    deps.install_prep(lambda l: None, popen=FakePopen)
    assert called == [1]


@pytest.mark.parametrize("text", ["error: Access is denied. (os error 5)", "failed (OS error 5)"])
def test_install_prep_locked_files_hint(monkeypatch, text):
    monkeypatch.setattr(deps.shutil, "which", lambda n: "uv")

    class Locked(FakePopen):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self.stdout = io.StringIO(text + " ")
            self.returncode = 2

    with pytest.raises(deps.DepsError, match="Файлы заняты запущенной программой.*install-omnivoice.bat"):
        deps.install_prep(lambda l: None, popen=Locked)


def test_install_prep_popen_oserror(monkeypatch):
    monkeypatch.setattr(deps.shutil, "which", lambda n: "uv")

    def boom(*a, **k):
        raise OSError("nope")

    with pytest.raises(deps.DepsError, match="Не удалось запустить uv"):
        deps.install_prep(lambda l: None, popen=boom)


def test_ffmpeg_env_prepends_local_dir_only_when_used(monkeypatch):
    monkeypatch.setenv("PATH", "P")
    assert deps.ffmpeg_env()["PATH"] == "P"
    deps.ffmpeg_dir().mkdir(parents=True)
    (deps.ffmpeg_dir() / "ffmpeg.exe").write_bytes(b"x")
    assert deps.ffmpeg_env()["PATH"] == str(deps.ffmpeg_dir()) + deps.os.pathsep + "P"
    monkeypatch.setattr(deps.shutil, "which", lambda n: "C:/sys/ffmpeg.exe")  # system ffmpeg wins
    assert deps.ffmpeg_env()["PATH"] == "P"


def test_demucs_gets_ffmpeg_env(monkeypatch, tmp_path):
    monkeypatch.setattr(slicer.deps, "ffmpeg_env", lambda: {"PATH": "X"})
    seen = {}
    monkeypatch.setattr(slicer.subprocess, "run", lambda cmd, **kw: seen.update(kw) or subprocess.CompletedProcess(cmd, 0))
    with pytest.raises(RuntimeError, match="vocals"):  # fake demucs wrote nothing; only the call matters
        slicer._isolate(Path("a.mp4"), tmp_path)
    assert seen["env"] == {"PATH": "X"}


def test_extract_swap_oserror_is_russian(tmp_path, monkeypatch):
    z = tmp_path / "f.zip"
    make_zip(z)

    def boom(*a):
        raise PermissionError("busy")

    monkeypatch.setattr(deps.os, "replace", boom)
    with pytest.raises(deps.DepsError, match="Не удалось обновить папку ffmpeg"):
        deps.extract_ffmpeg(z)


class _Resp:
    def __init__(self, data):
        self.data, self.headers, self.status = data, {"Content-Length": str(len(data))}, 200

    def __enter__(self): return self
    def __exit__(self, *a): return False

    def read(self, n=-1):
        d, self.data = self.data, b""
        return d


@pytest.mark.parametrize("fail", ["http500", "urlerror", "timeout"])
def test_download_falls_through_on_5xx_and_network_errors(tmp_path, monkeypatch, fail):
    import urllib.error
    from omnivoice import download

    def urlopen(req, timeout=None):
        if "first" in req.full_url:
            raise {"http500": urllib.error.HTTPError(req.full_url, 503, "x", {}, None),
                   "urlerror": urllib.error.URLError("dns"), "timeout": TimeoutError()}[fail]
        return _Resp(b"ok")

    monkeypatch.setattr(download.urllib.request, "urlopen", urlopen)
    out = download.fetch(["https://x/first", "https://x/second"], tmp_path / "f")
    assert out.read_bytes() == b"ok"


def test_download_last_mirror_failure_still_raises(tmp_path, monkeypatch):
    import urllib.error
    from omnivoice import download
    monkeypatch.setattr(download.urllib.request, "urlopen",
                        lambda req, timeout=None: (_ for _ in ()).throw(urllib.error.HTTPError(req.full_url, 503, "x", {}, None)))
    with pytest.raises(download.DownloadError, match="HTTP 503"):
        download.fetch(["https://x/a", "https://x/b"], tmp_path / "f")
