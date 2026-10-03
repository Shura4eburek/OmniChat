import hashlib
import re
import shutil
import subprocess
import pytest
from omnivoice import download, wslenv
from omnivoice.piper_compat import HERE as COMPAT


def u16(text: str) -> bytes:
    """wsl.exe writes its own messages as UTF-16LE with CRLF."""
    return text.replace("\n", "\r\n").encode("utf-16-le")


STATUS_EN = u16("Default Distribution: Ubuntu-24.04\nDefault Version: 2\n"
                "WSL1 is not supported with your current machine configuration.\n")
STATUS_RU = u16("Дистрибутив по умолчанию: Ubuntu-24.04\nВерсия по умолчанию: 2\n")
VERSION_EN = u16("WSL version: 2.6.3.0\nKernel version: 6.6.87.2-1\nWSLg version: 1.0.71\n")
VERSION_RU = u16("Версия WSL: 2.6.3.0\nВерсия ядра: 6.6.87.2-1\n")
LIST_NO_OMNI = u16("Ubuntu-24.04\ndocker-desktop\n")
LIST_OMNI = u16("Ubuntu-24.04\ndocker-desktop\nomnivoice\n")
NOT_INSTALLED_RU = u16('Подсистема Windows для Linux не установлена. Ее можно установить, '
                       'выполнив команду "wsl.exe --install".\n')
OLD_INBOX_HELP = u16("Copyright (c) Microsoft Corporation. All rights reserved.\n\n"
                     "Usage: wsl.exe [Argument] [Options...] [CommandLine]\n")


class Fake:
    """subprocess.run stand-in: first matching key (substring of the joined command) wins."""
    def __init__(self, table):
        self.table, self.calls = table, []

    def __call__(self, cmd, **kw):
        self.calls.append((cmd, kw))
        j = " ".join(map(str, cmd))
        for key, res in self.table.items():
            if key in j:
                if isinstance(res, BaseException):
                    raise res
                rc, out = res
                return subprocess.CompletedProcess(cmd, rc, out, b"")
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    def joined(self):
        return [" ".join(map(str, c)) for c, _ in self.calls]


def healthy(ready=True, distro=True, gpu=True):
    t = {"--status": (0, STATUS_EN), "--version": (0, VERSION_EN),
         "-l -q": (0, LIST_OMNI if distro else LIST_NO_OMNI),
         "cat /opt/omnivoice/READY": (0, (wslenv.ENV_VERSION + "\n").encode() if ready else b"")}
    t["nvidia-smi"] = (0, b"GPU 0: RTX") if gpu else (1, b"")
    return t


# --- decoding -------------------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    (STATUS_EN, "Default Distribution: Ubuntu-24.04"),
    (STATUS_RU, "Дистрибутив по умолчанию: Ubuntu-24.04"),
    (b"\xff\xfe" + u16("omnivoice\n"), "omnivoice"),
    ("Версия: 1".encode("utf-8"), "Версия: 1"),
    (b"", ""),
])
def test_decode_utf16_and_utf8(raw, expected):
    assert wslenv.decode(raw).splitlines()[0:1] == ([expected] if expected else [])


def test_decode_utf16_split_on_newline_byte():
    # a pipe reader splits UTF-16 output at b"\n", leaving a stray NUL on either side
    raw = u16("A\nБ\n")
    first, rest = raw.split(b"\n", 1)
    assert wslenv.decode(first + b"\n").strip() == "A"
    assert wslenv.decode(rest.split(b"\n", 1)[0]).strip() == "Б"


def test_distros_parses_utf16_list():
    fake = Fake({"-l -q": (0, LIST_OMNI)})
    assert wslenv.distros(run=fake) == ["Ubuntu-24.04", "docker-desktop", "omnivoice"]


# --- status ---------------------------------------------------------------------------------------

def test_status_ready():
    st = wslenv.status(run=Fake(healthy()))
    assert (st.wsl, st.wsl_version_ok, st.distro, st.ready, st.gpu) == (True, True, True, True, True)
    assert "готова" in st.message


def test_status_russian_windows_distro_missing():
    fake = Fake({"--status": (0, STATUS_RU), "--version": (0, VERSION_RU), "-l -q": (0, LIST_NO_OMNI)})
    st = wslenv.status(run=fake)
    assert (st.wsl, st.wsl_version_ok, st.distro, st.ready, st.gpu) == (True, True, False, False, None)
    assert "omnivoice" in st.message
    assert not any("-d omnivoice" in c for c in fake.joined())  # never touches a missing distro


def test_status_outdated_version_marker():
    t = healthy(); t["cat /opt/omnivoice/READY"] = (0, b"0-old\n")
    st = wslenv.status(run=Fake(t))
    assert st.distro and not st.ready and "не настроена" in st.message


def test_status_wsl_not_installed_stub():
    fake = Fake({"--status": (1, NOT_INSTALLED_RU), "--version": (1, NOT_INSTALLED_RU),
                 "-l -q": (1, NOT_INSTALLED_RU)})
    st = wslenv.status(run=fake)
    assert not st.wsl and not st.distro and not st.ready
    assert "WSL не установлен" in st.message and "Установить зависимости" in st.message


def test_status_wsl_exe_missing():
    st = wslenv.status(run=Fake({"wsl": FileNotFoundError()}))
    assert not st.wsl and "WSL не установлен" in st.message


def test_status_old_inbox_wsl_needs_update():
    fake = Fake({"--status": (0, STATUS_EN), "--version": (1, OLD_INBOX_HELP), "-l -q": (0, LIST_NO_OMNI)})
    st = wslenv.status(run=fake)
    assert st.wsl and not st.wsl_version_ok and "обнов" in st.message


def test_gpu_ok():
    assert wslenv.gpu_ok(run=Fake({"nvidia-smi": (0, b"GPU 0")})) is True
    assert wslenv.gpu_ok(run=Fake({"nvidia-smi": (127, b"")})) is False
    assert wslenv.gpu_ok(run=Fake({"nvidia-smi": subprocess.TimeoutExpired("wsl", 1)})) is False


def test_commands_inside_distro_run_as_root():
    assert wslenv.wsl_cmd("true") == ["wsl", "-d", "omnivoice", "-u", "root", "--", "true"]


# --- ensure_wsl / elevation -----------------------------------------------------------------------

def test_elevated_command_construction():
    cmd = wslenv.elevated_command(["--install", "--no-distribution"])
    assert cmd[:3] == ["powershell", "-NoProfile", "-Command"]
    script = cmd[3]
    assert "Start-Process wsl -ArgumentList '--install','--no-distribution' -Verb RunAs -Wait -PassThru" in script
    assert "exit $p.ExitCode" in script and "1223" in script


def test_ensure_wsl_noop_when_ok():
    fake = Fake(healthy())
    assert wslenv.ensure_wsl(run=fake) is None
    assert not any("powershell" in c for c in fake.joined())


class Seq(Fake):
    """WSL appears only after the elevated install ran."""
    def __init__(self, before, after, install_rc):
        super().__init__(before)
        self.after, self.install_rc = after, install_rc

    def __call__(self, cmd, **kw):
        if cmd[0] == "powershell":
            self.calls.append((cmd, kw)); self.table = self.after
            return subprocess.CompletedProcess(cmd, self.install_rc, b"", b"")
        return super().__call__(cmd, **kw)


MISSING = {"--status": (1, NOT_INSTALLED_RU), "--version": (1, NOT_INSTALLED_RU), "-l -q": (1, NOT_INSTALLED_RU)}


def test_ensure_wsl_installs_and_asks_for_reboot():
    fake = Seq(MISSING, MISSING, 0)
    assert "перезагруз" in wslenv.ensure_wsl(run=fake)
    ps = [c for c in fake.joined() if c.startswith("powershell")]
    assert len(ps) == 1 and "'--install','--no-distribution'" in ps[0]


def test_ensure_wsl_installs_without_reboot():
    assert wslenv.ensure_wsl(run=Seq(MISSING, healthy(distro=False), 0)) is None


def test_ensure_wsl_updates_old_inbox_wsl():
    before = {"--status": (0, STATUS_EN), "--version": (1, OLD_INBOX_HELP), "-l -q": (0, LIST_NO_OMNI)}
    fake = Seq(before, healthy(distro=False), 0)
    assert wslenv.ensure_wsl(run=fake) is None
    assert any("'--update'" in c for c in fake.joined())


def test_ensure_wsl_uac_cancelled_is_russian():
    with pytest.raises(wslenv.WslError, match="отменена"):
        wslenv.ensure_wsl(run=Seq(MISSING, MISSING, 1223))


def test_ensure_wsl_failure_is_russian():
    with pytest.raises(wslenv.WslError, match="Не удалось установить WSL"):
        wslenv.ensure_wsl(run=Seq(MISSING, MISSING, 5))


# --- path mapping ---------------------------------------------------------------------------------

@pytest.mark.parametrize("win,lin", [
    (r"C:\Users\Мамору\voices\p", "/mnt/c/Users/Мамору/voices/p"),
    (r"d:\a b\c.wav", "/mnt/d/a b/c.wav"),
    ("C:/x/y/", "/mnt/c/x/y"),
    ("C:\\", "/mnt/c"),
    (r"\\?\C:\long\path", "/mnt/c/long/path"),
    (r"\\wsl$\omnivoice\opt\omnivoice", "/opt/omnivoice"),
    (r"\\wsl.localhost\omnivoice\root", "/root"),
])
def test_wsl_path(win, lin):
    assert wslenv.wsl_path(win) == lin


@pytest.mark.parametrize("bad", [r"\\server\share\x", r"\\wsl$\Ubuntu-24.04\home"])
def test_wsl_path_rejects_unreachable(bad):
    with pytest.raises(wslenv.WslError):
        wslenv.wsl_path(bad)


# --- STEP lines -----------------------------------------------------------------------------------

def test_parse_step():
    assert wslenv.parse_step("STEP 3/7 PyTorch (CUDA 12.6)") == (3, 7, "PyTorch (CUDA 12.6)")
    assert wslenv.parse_step("STEP 3/7 PyTorch\r\n") == (3, 7, "PyTorch")
    assert wslenv.parse_step("Collecting torch==2.14.1") is None
    assert wslenv.parse_step("  STEP 1/7 x") is None


def test_setup_script_steps_match_total():
    text = (COMPAT / "wsl_setup.sh").read_text(encoding="utf-8")
    steps = [int(n) for n in re.findall(r'^step (\d+) "', text, flags=re.M)]
    total = int(re.search(r"^TOTAL=(\d+)$", text, flags=re.M).group(1))
    assert steps == list(range(1, total + 1))


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")
def test_setup_script_bash_syntax():
    r = subprocess.run(["bash", "-n", str(COMPAT / "wsl_setup.sh")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_setup_files_shipped():
    for name in wslenv.SETUP_FILES:
        assert (COMPAT / name).is_file(), name


# --- constraints / Dockerfile ---------------------------------------------------------------------

def test_constraints_pin_cuda_torch():
    lines = (COMPAT / "constraints.txt").read_text(encoding="utf-8").splitlines()
    pins = dict(l.split("==", 1) for l in lines if "==" in l and not l.startswith("#"))
    assert pins["torch"] == "2.14.1+cu126" and pins["torchaudio"] == "2.11.0+cu126"
    for name, ver in {"lightning": "2.6.6", "pytorch-lightning": "2.6.6", "lightning-utilities": "0.15.3",
                      "torchmetrics": "1.9.0", "jsonargparse": "4.52.0", "numpy": "2.5.3", "librosa": "0.11.0",
                      "onnx": "1.23.1", "onnxscript": "0.7.2", "onnxruntime": "1.30.0", "tensorboard": "2.21.0",
                      "Cython": "3.3.0", "scikit-build": "0.19.1"}.items():
        assert pins[name] == ver, name


def test_dockerfile_and_setup_use_constraints():
    docker = (COMPAT / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY constraints.txt" in docker and docker.count("-c /opt/omnivoice/constraints.txt") >= 2
    assert "download.pytorch.org/whl/cu126" in docker
    sh = (COMPAT / "wsl_setup.sh").read_text(encoding="utf-8")
    assert '-c "$C"' in sh and "download.pytorch.org/whl/cu126" in sh and "v1.8.0" in sh


# --- download / import / provision / ensure_ready -------------------------------------------------

class Resp:
    def __init__(self, data, status=200):
        self.status, self.data = status, [data, b""]
        self.headers = {"Content-Length": str(len(data))}
    def read(self, n): return self.data.pop(0)
    def __enter__(self): return self
    def __exit__(self, *a): pass


def test_rootfs_pin_is_official_canonical():
    assert all(u.startswith(("https://releases.ubuntu.com/", "https://old-releases.ubuntu.com/"))
               for u in wslenv.ROOTFS_URLS)
    assert len(wslenv.ROOTFS_SHA256) == 64


def test_download_rootfs_checks_sha(tmp_path, monkeypatch):
    monkeypatch.setenv("OMNIVOICE_CACHE", str(tmp_path))
    monkeypatch.setattr(wslenv, "ROOTFS_SHA256", hashlib.sha256(b"tar").hexdigest())
    monkeypatch.setattr(download.urllib.request, "urlopen", lambda req, timeout=None: Resp(b"tar"))
    seen = []
    p = wslenv.download_rootfs(lambda d, t: seen.append((d, t)))
    assert p.parent == tmp_path / "wsl" and p.read_bytes() == b"tar" and seen[-1] == (3, 3)


def test_download_sha_mismatch_is_russian_and_deletes_part(tmp_path, monkeypatch):
    monkeypatch.setenv("OMNIVOICE_CACHE", str(tmp_path))
    monkeypatch.setattr(download.urllib.request, "urlopen", lambda req, timeout=None: Resp(b"evil"))
    with pytest.raises(wslenv.WslError, match="контрольная сумма") as e:
        wslenv.download_rootfs()
    assert wslenv.ROOTFS_URLS[0] in str(e.value)
    assert not list((tmp_path / "wsl").iterdir())


def test_download_falls_back_to_next_mirror(tmp_path, monkeypatch):
    import urllib.error
    def urlopen(req, timeout=None):
        if "first" in req.full_url:
            raise urllib.error.HTTPError(req.full_url, 404, "nf", {}, None)
        return Resp(b"ok")
    monkeypatch.setattr(download.urllib.request, "urlopen", urlopen)
    out = download.fetch(["https://x/first", "https://x/second"], tmp_path / "f",
                         sha256=hashlib.sha256(b"ok").hexdigest())
    assert out.read_bytes() == b"ok"


def test_download_existing_valid_file_skips_network(tmp_path, monkeypatch):
    f = tmp_path / "f"; f.write_bytes(b"ok")
    monkeypatch.setattr(download.urllib.request, "urlopen", lambda *a, **k: pytest.fail("network"))
    assert download.fetch("https://x/f", f, sha256=hashlib.sha256(b"ok").hexdigest()) == f


def test_download_retries_once_after_network_error(tmp_path, monkeypatch):
    import urllib.error
    calls = []
    def urlopen(req, timeout=None):
        calls.append(req)
        if len(calls) == 1:
            raise urllib.error.URLError("reset")
        return Resp(b"ok")
    monkeypatch.setattr(download.urllib.request, "urlopen", urlopen)
    assert download.fetch("https://x/f", tmp_path / "f").read_bytes() == b"ok" and len(calls) == 2


def test_import_distro_command(tmp_path, monkeypatch):
    monkeypatch.setenv("OMNIVOICE_CACHE", str(tmp_path))
    fake = Fake({"-l -q": (0, LIST_NO_OMNI)})
    wslenv.import_distro(tmp_path / "u.tar.gz", run=fake)
    imp = [c for c, _ in fake.calls if "--import" in c][0]
    assert imp == ["wsl", "--import", "omnivoice", str(tmp_path / "wsl" / "omnivoice"),
                   str(tmp_path / "u.tar.gz"), "--version", "2"]


def test_import_distro_skips_existing(tmp_path, monkeypatch):
    monkeypatch.setenv("OMNIVOICE_CACHE", str(tmp_path))
    fake = Fake({"-l -q": (0, LIST_OMNI)})
    wslenv.import_distro(tmp_path / "u.tar.gz", run=fake)
    assert not any("--import" in c for c in fake.joined())


def test_import_failure_is_russian_with_hint(tmp_path, monkeypatch):
    monkeypatch.setenv("OMNIVOICE_CACHE", str(tmp_path))
    fake = Fake({"-l -q": (0, LIST_NO_OMNI),
                 "--import": (1, u16("Error code: Wsl/Service/RegisterDistro/HCS_E_HYPERV_NOT_INSTALLED\n"))})
    with pytest.raises(wslenv.WslError, match="виртуализац"):
        wslenv.import_distro(tmp_path / "u.tar.gz", run=fake)


class FakePopen:
    def __init__(self, lines, rc=0):
        self.lines, self.rc, self.cmds = lines, rc, []

    def __call__(self, cmd, **kw):
        self.cmds.append(cmd)
        self.stdout = iter(l.encode() + b"\n" for l in self.lines)
        return self

    def wait(self, timeout=None): return self.rc


def test_provision_copies_files_and_streams_lines():
    fake = Fake({})
    pop = FakePopen(["STEP 1/7 Системные пакеты", "Reading package lists...", "STEP 7/7 Проверка"])
    got = []
    wslenv.provision(got.append, run=fake, popen=pop)
    copied = [(c, kw["input"]) for c, kw in fake.calls if "cat >" in " ".join(c)]
    assert sorted(c[-1].rsplit("/", 1)[1] for c, _ in copied) == sorted(wslenv.SETUP_FILES)
    assert all(b"\r\n" not in data for _, data in copied)
    assert pop.cmds[0] == wslenv.wsl_cmd("bash", "/opt/omnivoice/setup/wsl_setup.sh", wslenv.ENV_VERSION)
    assert got == ["STEP 1/7 Системные пакеты", "Reading package lists...", "STEP 7/7 Проверка"]


def test_provision_failure_names_step():
    pop = FakePopen(["STEP 1/7 Системные пакеты", "STEP 3/7 PyTorch", "ERROR: No matching distribution"], rc=1)
    with pytest.raises(wslenv.WslError, match=r"шаг 3/7.*PyTorch") as e:
        wslenv.provision(lambda l: None, run=Fake({}), popen=pop)
    assert "No matching distribution" in str(e.value)


def test_ensure_ready_skips_everything_when_ready(monkeypatch):
    monkeypatch.setattr(wslenv, "download_rootfs", lambda *a, **k: pytest.fail("download"))
    monkeypatch.setattr(wslenv, "import_distro", lambda *a, **k: pytest.fail("import"))
    monkeypatch.setattr(wslenv, "provision", lambda *a, **k: pytest.fail("provision"))
    st = wslenv.ensure_ready(lambda l: None, run=Fake(healthy()))
    assert st.ready


def test_ensure_ready_only_reprovisions_on_version_change(monkeypatch):
    t = healthy(); t["cat /opt/omnivoice/READY"] = (0, b"0-old\n")
    fake = Fake(t)
    monkeypatch.setattr(wslenv, "download_rootfs", lambda *a, **k: pytest.fail("download"))
    monkeypatch.setattr(wslenv, "import_distro", lambda *a, **k: pytest.fail("import"))
    def provision(on_line, run=None, popen=None):
        fake.table["cat /opt/omnivoice/READY"] = (0, wslenv.ENV_VERSION.encode())
    monkeypatch.setattr(wslenv, "provision", provision)
    assert wslenv.ensure_ready(lambda l: None, run=fake).ready


def test_ensure_ready_full_path(monkeypatch, tmp_path):
    fake = Fake(healthy(ready=False, distro=False))
    order = []
    monkeypatch.setattr(wslenv, "download_rootfs", lambda progress=None: order.append("dl") or tmp_path / "t")
    def imp(tar, run=None):
        order.append("import"); fake.table["-l -q"] = (0, LIST_OMNI)
    def prov(on_line, run=None, popen=None):
        order.append("prov"); fake.table["cat /opt/omnivoice/READY"] = (0, wslenv.ENV_VERSION.encode())
    monkeypatch.setattr(wslenv, "import_distro", imp)
    monkeypatch.setattr(wslenv, "provision", prov)
    assert wslenv.ensure_ready(lambda l: None, run=fake).ready and order == ["dl", "import", "prov"]


def test_ensure_ready_reboot_needed(monkeypatch):
    monkeypatch.setattr(wslenv, "ensure_wsl", lambda run=None: "Нужна перезагрузка")
    with pytest.raises(wslenv.RebootRequired, match="перезагрузка"):
        wslenv.ensure_ready(lambda l: None, run=Fake(MISSING))


# --- fix round 1 ----------------------------------------------------------------------------------

NO_DISTROS = u16("Windows Subsystem for Linux has no installed distributions.\n"
                 "Error code: Wsl/WSL_E_DEFAULT_DISTRO_NOT_FOUND\n")


def test_distros_empty_when_none_installed():
    assert wslenv.distros(run=Fake({"-l -q": (0xFFFFFFFF, NO_DISTROS)})) == []


@pytest.mark.parametrize("res", [(1, u16("Error code: Wsl/Service/E_UNEXPECTED\n")),
                                 subprocess.TimeoutExpired("wsl", 60)])
def test_distros_failure_raises(res):
    with pytest.raises(wslenv.WslError, match="список дистрибутивов"):
        wslenv.distros(run=Fake({"-l -q": res}))


def test_status_survives_listing_failure():
    t = healthy(); t["-l -q"] = subprocess.TimeoutExpired("wsl", 60)
    st = wslenv.status(run=Fake(t))
    assert st.wsl and not st.distro and not st.ready


def test_import_listing_failure_keeps_vhdx(tmp_path, monkeypatch):
    monkeypatch.setenv("OMNIVOICE_CACHE", str(tmp_path))
    vhdx = tmp_path / "wsl" / "omnivoice" / "ext4.vhdx"; vhdx.parent.mkdir(parents=True); vhdx.write_bytes(b"disk")
    fake = Fake({"-l -q": subprocess.TimeoutExpired("wsl", 60)})
    with pytest.raises(wslenv.WslError):
        wslenv.import_distro(tmp_path / "u.tar.gz", run=fake)
    assert vhdx.read_bytes() == b"disk" and not any("--import" in c for c in fake.joined())


def test_import_removes_stale_vhdx_when_not_registered(tmp_path, monkeypatch):
    monkeypatch.setenv("OMNIVOICE_CACHE", str(tmp_path))
    vhdx = tmp_path / "wsl" / "omnivoice" / "ext4.vhdx"; vhdx.parent.mkdir(parents=True); vhdx.write_bytes(b"old")
    wslenv.import_distro(tmp_path / "u.tar.gz", run=Fake({"-l -q": (0, LIST_NO_OMNI)}))
    assert not vhdx.exists()


def test_import_locked_vhdx_is_russian(tmp_path, monkeypatch):
    monkeypatch.setenv("OMNIVOICE_CACHE", str(tmp_path))
    vhdx = tmp_path / "wsl" / "omnivoice" / "ext4.vhdx"; vhdx.parent.mkdir(parents=True); vhdx.write_bytes(b"x")
    real_unlink = type(vhdx).unlink
    def locked(self, *a, **k):
        if self.name == "ext4.vhdx":
            raise PermissionError(32, "used by another process")
        return real_unlink(self, *a, **k)
    monkeypatch.setattr(type(vhdx), "unlink", locked)
    fake = Fake({"-l -q": (0, LIST_NO_OMNI)})
    with pytest.raises(wslenv.WslError, match="Не удалось удалить старый диск omnivoice"):
        wslenv.import_distro(tmp_path / "u.tar.gz", run=fake)
    assert not any("--import" in c for c in fake.joined())


def test_elevated_command_distinguishes_uac_cancel():
    script = wslenv.elevated_command(["--install"])[3]
    assert "NativeErrorCode -eq 1223" in script and f"exit {wslenv.START_FAILED}" in script


def test_ensure_wsl_start_failure_is_not_uac_message():
    with pytest.raises(wslenv.WslError) as e:
        wslenv.ensure_wsl(run=Seq(MISSING, MISSING, wslenv.START_FAILED))
    assert "отменена" not in str(e.value) and "администратора" in str(e.value)


def test_setup_script_stamps_and_venv_check():
    sh = (COMPAT / "wsl_setup.sh").read_text(encoding="utf-8")
    assert '"$VENV/bin/pip"' in sh and "python3 -m venv --clear" in sh
    assert "piper.train.vits.monotonic_align" in sh and "уже собрано" in sh
    assert sh.count("sha256sum") >= 1 and "DEPS_STAMP" in sh and "PIPER_STAMP" in sh


def test_download_unknown_length_truncated_fails_sha(tmp_path, monkeypatch):
    class NoLen(Resp):
        def __init__(self):
            super().__init__(b"trunc"); self.headers = {}
    monkeypatch.setattr(download.urllib.request, "urlopen", lambda req, timeout=None: NoLen())
    with pytest.raises(download.DownloadError, match="контрольная сумма"):
        download.fetch("https://x/f", tmp_path / "f", sha256=hashlib.sha256(b"truncated-full").hexdigest())
    assert not (tmp_path / "f").exists() and not (tmp_path / "f.part").exists()


def test_download_unknown_length_without_sha_is_accepted(tmp_path, monkeypatch):
    class NoLen(Resp):
        def __init__(self):
            super().__init__(b"data"); self.headers = {}
    monkeypatch.setattr(download.urllib.request, "urlopen", lambda req, timeout=None: NoLen())
    assert download.fetch("https://x/f", tmp_path / "f").read_bytes() == b"data"
