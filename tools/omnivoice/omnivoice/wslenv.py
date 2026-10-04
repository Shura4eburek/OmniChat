"""Training environment in an own WSL2 distro «omnivoice»: official Ubuntu 24.04 rootfs + pinned pip packages.

omnivoice owns only the distro named DISTRO; other distros are never touched.
wsl.exe writes its own messages as UTF-16LE; commands run inside the distro write UTF-8 (see decode()).
"""
from __future__ import annotations
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path, PureWindowsPath
from typing import Callable

from omnivoice import download
from omnivoice.paths import cache_dir
from omnivoice.piper_compat import HERE as COMPAT_DIR

DISTRO = "omnivoice"
# Bump when wsl_setup.sh, constraints.txt or the shim change: a different READY marker re-runs provisioning.
ENV_VERSION = "1 ubuntu-24.04.5 torch-2.14.1+cu126 piper1-gpl-v1.8.0"

# Official Canonical WSL image (a gzip'd rootfs tar), listed in https://releases.ubuntu.com/24.04.5/SHA256SUMS.
# Point releases move to old-releases.ubuntu.com once superseded, hence the fallbacks (same file, same sha256).
ROOTFS_URLS = (
    "https://releases.ubuntu.com/24.04.5/ubuntu-24.04.5-wsl-amd64.wsl",
    "https://releases.ubuntu.com/noble/ubuntu-24.04.5-wsl-amd64.wsl",
    "https://old-releases.ubuntu.com/releases/24.04.5/ubuntu-24.04.5-wsl-amd64.wsl",
)
ROOTFS_SHA256 = "bb415d824822c4b878125729af451a5d18fb13d1cf5cbed9a7393ad64ac6039e"
ROOTFS_NAME = "ubuntu-24.04.5-wsl-amd64.tar.gz"  # .tar.gz is accepted by every `wsl --import`

ROOT = "/opt/omnivoice"
SETUP_DIR = f"{ROOT}/setup"
READY_FILE = f"{ROOT}/READY"
SETUP_FILES = ("wsl_setup.sh", "constraints.txt", "torch_shim.py", "clean_ckpt.py")
TIMEOUT = 60
ERROR_CANCELLED = 1223  # UAC prompt declined
START_FAILED = 9009  # Start-Process failed for another reason (elevated_command)
REBOOT_MSG = ("WSL установлен — нужна перезагрузка Windows. Перезагрузи компьютер и снова нажми "
              "«Установить зависимости»: после перезагрузки открой OmniVoice ярлыком на рабочем столе и нажми "
              "«Установить зависимости» ещё раз")
VMP_HINT = ("Включи виртуализацию в BIOS/UEFI (Intel VT-x / AMD SVM) и компонент Windows «Платформа виртуальной "
            "машины», затем перезагрузи компьютер")
# wsl.exe / Windows wording for «the VM can't start» (virtualization off, VMP feature missing), any UI language
VMP_MARKERS = ("virtualization", "virtual machine platform", "virtualmachineplatform", "виртуализац",
               "платформа виртуальной машины", "0x80370102", "hcs_e_hyperv_not_installed")
ROOTFS_LABEL = "Скачиваю образ Ubuntu (~390 МБ)…"

Run = Callable[..., subprocess.CompletedProcess]


class WslError(RuntimeError):
    pass


class RebootRequired(WslError):
    pass


@dataclass
class EnvStatus:
    wsl: bool
    wsl_version_ok: bool
    distro: bool
    ready: bool
    gpu: bool | None
    message: str
    raw: str = field(default="", repr=False)  # `wsl --status` output, for the virtualization hint


def decode(data: bytes | str | None) -> str:
    """wsl.exe output: UTF-16LE (optionally with BOM, possibly split at a b"\\n" byte) or UTF-8."""
    if data is None:
        return ""
    if isinstance(data, str):
        return data.replace("\x00", "")
    if data.startswith(b"\xff\xfe"):
        data = data[2:]
    if b"\x00" in data:
        if len(data) % 2:
            data = data[1:] if data[0] == 0 else data[:-1] if data[-1:] == b"\n" else data + b"\x00"
        return data.decode("utf-16-le", errors="replace").replace("\x00", "")
    return data.decode("utf-8", errors="replace")


def wsl_cmd(*args: str) -> list[str]:
    """A command inside the omnivoice distro, as root (the imported rootfs has no other user).
    --exec passes argv verbatim; `--` would re-parse it with the shell (quotes, spaces, «(» or «&» in paths
    break it). Shell features need an explicit `sh -c`."""
    return ["wsl", "-d", DISTRO, "-u", "root", "--exec", *args]


def _run(run: Run, cmd: list[str], timeout: float | None = TIMEOUT, input: bytes | None = None
         ) -> tuple[int | None, str]:
    """(returncode, decoded stdout+stderr); returncode None when the program is missing or hangs."""
    try:
        r = run(cmd, capture_output=True, timeout=timeout, input=input)
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None, ""
    return r.returncode, decode(r.stdout) + decode(r.stderr)


def _wsl_installed(rc: int | None, out: str) -> bool:
    # without WSL, the inbox wsl.exe stub only says «run wsl.exe --install» (any UI language)
    return rc == 0 and "--install" not in out


def _wsl_version(rc: int | None, out: str) -> tuple[int, ...] | None:
    if rc != 0:
        return None  # the old inbox WSL has no --version
    lines = out.strip().splitlines()
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", lines[0]) if lines else None
    return tuple(int(x) for x in m.groups()) if m else None


def distros(run: Run = subprocess.run) -> list[str]:
    """Registered distros. Raises WslError when the list can't be read (never guesses an empty list)."""
    rc, out = _run(run, ["wsl", "-l", "-q"])
    if rc != 0 and "WSL_E_DEFAULT_DISTRO_NOT_FOUND" in out:
        return []  # WSL works, there are simply no distros yet
    if rc != 0:
        detail = out.strip() or ("wsl.exe не отвечает" if rc is None else f"код {rc}")
        raise WslError(f"Не удалось получить список дистрибутивов WSL: {detail}")
    return [l.strip() for l in out.splitlines() if l.strip()]


def gpu_ok(run: Run = subprocess.run) -> bool:
    rc, _ = _run(run, wsl_cmd("sh", "-c", "PATH=$PATH:/usr/lib/wsl/lib nvidia-smi -L"))
    return rc == 0


def status(run: Run = subprocess.run) -> EnvStatus:
    status_rc, status_out = _run(run, ["wsl", "--status"])
    wsl = _wsl_installed(status_rc, status_out)
    ver = _wsl_version(*_run(run, ["wsl", "--version"])) if wsl else None
    version_ok = ver is not None and ver >= (2, 0, 0)
    try:
        distro = wsl and DISTRO in distros(run)
    except WslError:
        distro = False  # read-only report; import_distro re-checks and refuses to act on a failed listing
    ready, gpu = False, None
    if distro:
        rc, out = _run(run, wsl_cmd("cat", READY_FILE))
        ready = rc == 0 and out.strip() == ENV_VERSION
        gpu = gpu_ok(run)
    if not wsl:
        msg = "WSL не установлен — нажми «Установить зависимости» (omnivoice setup)"
    elif not version_ok:
        msg = "WSL устарел — нужно обновить его: нажми «Установить зависимости» (omnivoice setup)"
    elif not distro:
        msg = f"Среда обучения WSL «{DISTRO}» не создана — нажми «Установить зависимости» (omnivoice setup)"
    elif not ready:
        msg = f"Среда обучения WSL «{DISTRO}» не настроена или устарела — нажми «Установить зависимости»"
    else:
        msg = f"Среда обучения WSL «{DISTRO}» готова, GPU: {'есть' if gpu else 'нет — обнови драйвер NVIDIA или обучайте в Colab'}"
    return EnvStatus(wsl, version_ok, distro, ready, gpu, msg, status_out)


def elevated_command(wsl_args: list[str]) -> list[str]:
    """Run `wsl <args>` as administrator (one UAC prompt); exit code 1223 if the prompt was declined."""
    arglist = ",".join("'" + a.replace("'", "''") + "'" for a in wsl_args)
    script = (f"try {{ $p = Start-Process wsl -ArgumentList {arglist} -Verb RunAs -Wait -PassThru; "
              f"exit $p.ExitCode }} catch {{ $e = $_.Exception; while ($e) {{ "
              f"if ($e.NativeErrorCode -eq {ERROR_CANCELLED}) {{ exit {ERROR_CANCELLED} }}; $e = $e.InnerException }}; "
              f"[Console]::Error.WriteLine($_.Exception.Message); exit {START_FAILED} }}")
    return ["powershell", "-NoProfile", "-Command", script]


def install_marker() -> Path:
    """Written after an elevated `wsl --install` (its timestamp): a second failure after a reboot is not
    another reboot but virtualization / «Платформа виртуальной машины» being off."""
    return cache_dir() / "wsl" / "install-attempted"


def _boot_time() -> float | None:
    """Unix time of the last Windows boot (None when unknown)."""
    try:
        import ctypes
        ticks = ctypes.windll.kernel32.GetTickCount64
        ticks.restype = ctypes.c_ulonglong
        return time.time() - ticks() / 1000
    except Exception:
        return None


def _marker_time() -> float | None:
    try:
        text = install_marker().read_text(encoding="utf-8").strip()
    except OSError:
        return None
    try:
        return float(text)
    except ValueError:
        return 0.0  # unreadable stamp: the attempt happened, the time is unknown


def _forget_marker() -> None:
    try:
        install_marker().unlink(missing_ok=True)
    except OSError:
        pass


def _remember_install() -> None:
    try:
        m = install_marker()
        m.parent.mkdir(parents=True, exist_ok=True)
        m.write_text(f"{time.time():.0f}", encoding="utf-8")
    except OSError:
        pass  # only loses the BIOS hint on a later failure


def needs_vmp(*outputs: str) -> bool:
    text = " ".join(outputs).lower()
    return any(k in text for k in VMP_MARKERS)


def _with_vmp(msg: str, *outputs: str) -> str:
    return f"{msg}\n{VMP_HINT}" if needs_vmp(*outputs) else msg


def ensure_wsl(run: Run = subprocess.run, boot_time: Callable[[], float | None] = _boot_time) -> str | None:
    """Install (or update) WSL. None when WSL is usable, REBOOT_MSG when Windows needs a restart first."""
    st = status(run)
    if st.wsl and st.wsl_version_ok:
        _forget_marker()
        return None
    install = not st.wsl
    if install and (since := _marker_time()) is not None:
        booted = boot_time()
        if booted is not None and booted < since:
            return _with_vmp(REBOOT_MSG, st.raw)  # the reboot asked for last time hasn't happened yet
        _forget_marker()  # the next press installs again (e.g. after fixing BIOS)
        detail = f"\nВывод wsl --status: {st.raw.strip()}" if st.raw.strip() else ""
        raise WslError("WSL установлен, но не запускается и после перезагрузки — скорее всего, выключена "
                       f"виртуализация. {VMP_HINT}, и снова нажми «Установить зависимости»{detail}")
    args = ["--update"] if st.wsl else ["--install", "--no-distribution"]
    rc, out = _run(run, elevated_command(args), timeout=None)
    if rc == ERROR_CANCELLED:
        raise WslError("Установка WSL отменена: подтверди запрос администратора (UAC) и повтори")
    if rc is None or rc == START_FAILED:
        raise WslError(_with_vmp("Не удалось запустить установку WSL от имени администратора"
                                 + (f": {out.strip()}" if out.strip() else "")
                                 + f". Открой PowerShell от администратора и выполни «wsl {' '.join(args)}»",
                                 st.raw, out))
    if install and rc in (0, 3010):
        _remember_install()
    # 3010 = ERROR_SUCCESS_REBOOT_REQUIRED. After --install the reboot is pending even if wsl --status answers.
    if rc == 3010 or (install and rc == 0):
        return _with_vmp(REBOOT_MSG, st.raw, out)
    after = status(run)
    if after.wsl and after.wsl_version_ok:
        return None
    if rc == 0:
        return _with_vmp(REBOOT_MSG, st.raw, out, after.raw)
    raise WslError(_with_vmp(f"Не удалось установить WSL (код {rc}). Открой PowerShell от администратора и "
                             f"выполни «wsl {' '.join(args)}», затем повтори", st.raw, out, after.raw))


def rootfs_path() -> Path:
    return cache_dir() / "wsl" / ROOTFS_NAME


def download_rootfs(progress: Callable[[int, int], None] | None = None) -> Path:
    return download.fetch(ROOTFS_URLS, rootfs_path(), progress=progress,
                          sha256=ROOTFS_SHA256, what="образ Ubuntu 24.04 для WSL", error=WslError)


def _hint(out: str) -> str:
    return _with_vmp(out.strip() or "нет вывода", out)


def import_distro(tar: Path, run: Run = subprocess.run) -> None:
    if DISTRO in distros(run):
        return
    location = cache_dir() / "wsl" / DISTRO
    location.mkdir(parents=True, exist_ok=True)
    # distros() above succeeded without «omnivoice», so a vhdx here is left by an interrupted import
    stale = location / "ext4.vhdx"
    if stale.exists():
        try:
            stale.unlink()
        except OSError as e:
            raise WslError(f"Не удалось удалить старый диск omnivoice: {stale} ({e}). "
                           f"Выполни «wsl --shutdown» и повтори") from e
    rc, out = _run(run, ["wsl", "--import", DISTRO, str(location), str(tar), "--version", "2"], timeout=None)
    if rc != 0:
        raise WslError(f"Не удалось создать среду WSL «{DISTRO}»: {_hint(out)}")


def parse_step(line: str) -> tuple[int, int, str] | None:
    m = re.match(r"STEP (\d+)/(\d+) (.+)$", line.strip("\r\n"))
    return (int(m.group(1)), int(m.group(2)), m.group(3).strip()) if m else None


XTTS_VERSION = "1 coqui-tts-0.27.5 torch-2.8.0+cu126"  # bump with xtts_setup.sh / xtts_constraints.txt
XTTS_READY = f"{ROOT}/xtts/READY"
XTTS_FILES = ("xtts_setup.sh", "xtts_constraints.txt")


def xtts_ready(run: Run = subprocess.run) -> bool:
    """The optional XTTS v2 venv (synthetic phrases) is built for this XTTS_VERSION."""
    rc, out = _run(run, wsl_cmd("cat", XTTS_READY))
    return rc == 0 and out.strip() == XTTS_VERSION


def provision_xtts(on_line: Callable[[str], None], run: Run = subprocess.run, popen=subprocess.Popen) -> None:
    """Copy xtts_setup.sh + its constraints into the distro and run it (≈ 3–4 GB the first time)."""
    for name in XTTS_FILES:
        data = (COMPAT_DIR / name).read_bytes().replace(b"\r\n", b"\n")  # a CRLF checkout breaks bash
        rc, out = _run(run, wsl_cmd("sh", "-c", f"mkdir -p {SETUP_DIR} && cat > {SETUP_DIR}/{name}"), input=data)
        if rc != 0:
            raise WslError(f"Не удалось скопировать {name} в среду WSL «{DISTRO}»: {_hint(out)}")
    try:
        proc = popen(wsl_cmd("bash", f"{SETUP_DIR}/xtts_setup.sh", XTTS_VERSION), stdout=subprocess.PIPE,
                     stderr=subprocess.STDOUT, env={**os.environ, "WSL_UTF8": "1"})
    except OSError as e:
        raise WslError(f"Не удалось запустить установку XTTS v2: {e}") from e
    tail: list[str] = []
    for raw in proc.stdout:
        line = decode(raw).rstrip("\r\n")
        tail = (tail + [line])[-8:]
        on_line(line)
    if proc.wait() != 0:
        raise WslError("Установка XTTS v2 не удалась. Повтори «Установить зависимости» с галочкой XTTS — готовые "
                       "шаги не повторятся. Последние строки:\n" + "\n".join(tail))


def provision(on_line: Callable[[str], None], run: Run = subprocess.run, popen=subprocess.Popen) -> None:
    """Copy the setup files into the distro and run wsl_setup.sh, streaming its output to on_line."""
    for name in SETUP_FILES:
        data = (COMPAT_DIR / name).read_bytes().replace(b"\r\n", b"\n")  # a CRLF checkout breaks bash
        rc, out = _run(run, wsl_cmd("sh", "-c", f"mkdir -p {SETUP_DIR} && cat > {SETUP_DIR}/{name}"), input=data)
        if rc != 0:
            raise WslError(f"Не удалось скопировать {name} в среду WSL «{DISTRO}»: {_hint(out)}")
    try:
        proc = popen(wsl_cmd("bash", f"{SETUP_DIR}/wsl_setup.sh", ENV_VERSION), stdout=subprocess.PIPE,
                     stderr=subprocess.STDOUT, env={**os.environ, "WSL_UTF8": "1"})
    except OSError as e:
        raise WslError(f"Не удалось запустить настройку среды WSL: {e}") from e
    step, tail = None, []
    for raw in proc.stdout:
        line = decode(raw).rstrip("\r\n")
        step = parse_step(line) or step
        tail = (tail + [line])[-8:]
        on_line(line)
    rc = proc.wait()
    if rc != 0:
        where = f"шаг {step[0]}/{step[1]} «{step[2]}»" if step else "начало"
        raise WslError(f"Настройка среды WSL не удалась ({where}, код {rc}). Повтори «Установить зависимости» — "
                       f"готовые шаги не повторятся. Последние строки:\n" + "\n".join(tail))


def ensure_ready(on_line: Callable[[str], None], progress: Callable[[int, int], None] | None = None,
                 run: Run = subprocess.run, popen=subprocess.Popen) -> EnvStatus:
    """WSL → rootfs → import → provision, skipping whatever is already done."""
    st = status(run)
    if not (st.wsl and st.wsl_version_ok):
        if msg := ensure_wsl(run=run):
            raise RebootRequired(msg)
        st = status(run)
    if not st.distro:
        on_line(ROOTFS_LABEL)
        import_distro(download_rootfs(progress=progress), run=run)
    if not st.ready:
        provision(on_line, run=run, popen=popen)
    st = status(run)
    if not st.ready:
        raise WslError(f"Среда WSL «{DISTRO}» настроена, но метка готовности не найдена — повтори «Установить зависимости»")
    try:  # the distro has its own disk now; the tar only spares a rare re-download (download_rootfs refetches)
        rootfs_path().unlink(missing_ok=True)
    except OSError:
        pass
    return st


def wsl_path(win_path: str | os.PathLike) -> str:
    """Windows path → path inside the distro: C:\\a\\b → /mnt/c/a/b, \\\\wsl$\\omnivoice\\x → /x."""
    p = str(win_path).replace("/", "\\")
    if p.startswith("\\\\?\\"):
        p = p[4:]
    if not PureWindowsPath(p).anchor:
        p = os.path.abspath(p).replace("/", "\\")
    m = re.match(r"^\\\\(?:wsl\$|wsl\.localhost)\\([^\\]+)(\\.*)?$", p, re.I)
    if m:
        if m.group(1).lower() != DISTRO:
            raise WslError(f"Путь {win_path} лежит в другом дистрибутиве WSL — перенеси файлы на диск Windows")
        return (m.group(2) or "\\").replace("\\", "/").rstrip("/") or "/"
    m = re.match(r"^([A-Za-z]):(\\.*)?$", p)
    if not m:
        raise WslError(f"Путь {win_path} недоступен из WSL — перенеси проект на локальный диск (C:, D: …)")
    rest = (m.group(2) or "").replace("\\", "/").rstrip("/")
    return f"/mnt/{m.group(1).lower()}{rest}"
