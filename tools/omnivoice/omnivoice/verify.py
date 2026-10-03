from __future__ import annotations
import json, shutil, subprocess, sys, tempfile
from dataclasses import dataclass
from pathlib import Path
from omnivoice import modrules, languages

@dataclass
class VerifyResult:
    ok: bool
    message: str
    # Points to sample.wav in a fresh temp dir (the voice folder is never modified);
    # the caller may copy or keep it, and is responsible for cleaning it up.
    sample: Path | None = None

_NATIVE_CRASH = {0xC0000005, 0xC0000409, 0xC000001D, 0xC0000094, 0xC00000FD}  # access violation, stack, etc.

def _worker_cmd(folder: Path, text: str, out: Path) -> list[str]:
    return [sys.executable, "-m", "omnivoice._verify_worker", str(folder), text, str(out)]

def _default_text(folder: Path) -> str:
    try:
        vj = folder / "voice.json"
        data = json.loads(vj.read_text(encoding="utf-8")) if vj.is_file() else {}
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    sample = data.get("sample")
    if isinstance(sample, str):
        sample = sample.replace("\0", "").strip()
        if sample:
            return sample
    code = data.get("language")
    lang = languages.PRESETS.get(code) if isinstance(code, str) else None
    return (lang or languages.PRESETS["ru"]).test_phrase

def verify_voice(folder: Path, text: str | None = None, timeout: int = 120,
                 python: str = sys.executable) -> VerifyResult:
    """Never raises. On success `sample` is a file in a fresh temp dir that the caller owns
    (and should delete); on any failure that temp dir is already removed."""
    folder = Path(folder)
    problems = modrules.validate_voice_folder(folder)
    if problems:
        return VerifyResult(False, "Папка не прошла проверку мода: " + "; ".join(problems))
    work = Path(tempfile.mkdtemp(prefix="omnivoice-verify-"))
    try:
        res = _run(folder, text, timeout, python, work / "sample.wav")
    except Exception as e:  # last resort: verify must not raise
        res = VerifyResult(False, f"Не удалось выполнить проверку: {e}")
    if not res.ok:
        shutil.rmtree(work, ignore_errors=True)
    return res

def _run(folder: Path, text: str | None, timeout: int, python: str, out: Path) -> VerifyResult:
    try:
        phrase = (text or "").replace("\0", "").strip() or _default_text(folder)
        cmd = _worker_cmd(folder, phrase, out)
        cmd[0] = python
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=timeout)
    except subprocess.TimeoutExpired:
        return VerifyResult(False, f"sherpa-onnx не ответил за {timeout} с — процесс остановлен")
    except (OSError, ValueError, TypeError) as e:
        return VerifyResult(False, f"Не удалось запустить проверку: {e}")
    tail = "\n".join((r.stderr or "").strip().splitlines()[-15:])
    code = r.returncode
    if code == 4:
        return VerifyResult(False, f"Не установлен sherpa-onnx или soundfile (код {code}).\n{tail}")
    if code != 0 or not out.is_file():
        crash = " (аварийное завершение процесса)" if (code & 0xFFFFFFFF) in _NATIVE_CRASH else ""
        return VerifyResult(False, f"Синтез упал (код {code}){crash}. Такая модель уронила бы игру.\n{tail}")
    return VerifyResult(True, "Модель загрузилась и озвучила фразу", out)
