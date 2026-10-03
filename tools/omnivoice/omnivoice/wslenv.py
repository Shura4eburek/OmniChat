"""Training environment in an own WSL2 distro «omnivoice»: official Ubuntu 24.04 rootfs + pinned pip packages.

omnivoice owns only the distro named DISTRO; other distros are never touched.
wsl.exe writes its own messages as UTF-16LE; commands run inside the distro write UTF-8 (see decode()).
"""
from __future__ import annotations
import os
import re
import subprocess
from dataclasses import dataclass
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
              "«Установить зависимости»")

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
    wsl = _wsl_installed(*_run(run, ["wsl", "--status"]))
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
        msg = f"Среда обучения WSL «{DISTRO}» готова, GPU: {'есть' if gpu else 'нет (обучение на CPU будет очень долгим)'}"
    return EnvStatus(wsl, version_ok, distro, ready, gpu, msg)


def elevated_command(wsl_args: list[str]) -> list[str]:
    """Run `wsl <args>` as administrator (one UAC prompt); exit code 1223 if the prompt was declined."""
    arglist = ",".join("'" + a.replace("'", "''") + "'" for a in wsl_args)
    script = (f"try {{ $p = Start-Process wsl -ArgumentList {arglist} -Verb RunAs -Wait -PassThru; "
              f"exit $p.ExitCode }} catch {{ $e = $_.Exception; while ($e) {{ "
              f"if ($e.NativeErrorCode -eq {ERROR_CANCELLED}) {{ exit {ERROR_CANCELLED} }}; $e = $e.InnerException }}; "
              f"[Console]::Error.WriteLine($_.Exception.Message); exit {START_FAILED} }}")
    return ["powershell", "-NoProfile", "-Command", script]


def ensure_wsl(run: Run = subprocess.run) -> str | None:
    """Install (or update) WSL. None when WSL is usable, REBOOT_MSG when Windows needs a restart first."""
    st = status(run)
    if st.wsl and st.wsl_version_ok:
        return None
    args = ["--update"] if st.wsl else ["--install", "--no-distribution"]
    rc, out = _run(run, elevated_command(args), timeout=None)
    if rc == ERROR_CANCELLED:
        raise WslError("Установка WSL отменена: подтверди запрос администратора (UAC) и повтори")
    if rc is None or rc == START_FAILED:
        raise WslError("Не удалось запустить установку WSL от имени администратора"
                       + (f": {out.strip()}" if out.strip() else "")
                       + f". Открой PowerShell от администратора и выполни «wsl {' '.join(args)}»")
    after = status(run)
    if after.wsl and after.wsl_version_ok:
        return None
    if rc in (0, 3010):  # 3010 = ERROR_SUCCESS_REBOOT_REQUIRED
        return REBOOT_MSG
    raise WslError(f"Не удалось установить WSL (код {rc}). Открой PowerShell от администратора и выполни "
                   f"«wsl {' '.join(args)}», затем повтори")


def download_rootfs(progress: Callable[[int, int], None] | None = None) -> Path:
    return download.fetch(ROOTFS_URLS, cache_dir() / "wsl" / ROOTFS_NAME, progress=progress,
                          sha256=ROOTFS_SHA256, what="образ Ubuntu 24.04 для WSL", error=WslError)


def _hint(out: str) -> str:
    text = out.strip() or "нет вывода"
    if any(k in out for k in ("HCS_E_HYPERV_NOT_INSTALLED", "VirtualMachinePlatform", "virtualization",
                              "виртуализац", "0x80370102")):
        text += ("\nВключи виртуализацию в BIOS/UEFI и компонент Windows «Платформа виртуальной машины», "
                 "затем перезагрузи компьютер")
    return text


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
        import_distro(download_rootfs(progress=progress), run=run)
    if not st.ready:
        provision(on_line, run=run, popen=popen)
    st = status(run)
    if not st.ready:
        raise WslError(f"Среда WSL «{DISTRO}» настроена, но метка готовности не найдена — повтори «Установить зависимости»")
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
