"""The Windows installer: CRLF, UTF-8 without BOM, Russian messages, and the key commands (never executed here)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BAT = ROOT / "install-omnivoice.bat"


def test_bat_is_crlf_utf8_without_bom():
    data = BAT.read_bytes()
    data.decode("utf-8")  # strict: raises on invalid UTF-8
    assert not data.isascii()  # Russian messages
    assert b"\r\n" in data
    assert data.count(b"\n") == data.count(b"\r\n"), "every line must end with CRLF"
    assert not data.startswith(b"\xef\xbb\xbf")


def test_bat_has_key_commands():
    text = BAT.read_text(encoding="utf-8")
    for needle in ("where uv", "irm https://astral.sh/uv/install.ps1 | iex", "-ExecutionPolicy Bypass",
                   r"%USERPROFILE%\.local\bin", "sync --all-extras --inexact", "%~dp0",
                   r"%USERPROFILE%\omnivoice-projects", "WScript.Shell", "OmniVoice.lnk",
                   "run omnivoice ui --projects", "OMNIVOICE_DRYRUN", "pause", "exit /b 1"):
        assert needle in text, needle


def test_bat_uses_pushd_for_its_folder():
    text = BAT.read_text(encoding="utf-8")
    assert 'pushd "%~dp0"' in text  # works for UNC paths too, unlike cd /d
    assert "cd /d" not in text


def test_gitattributes_keeps_bat_crlf():
    attrs = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "*.bat text eol=crlf" in attrs


def test_bat_switches_console_to_utf8_first():
    lines = BAT.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "@echo off" and lines[1] == "chcp 65001 >nul"
    assert all(l.isascii() for l in lines[:2])  # read before the codepage switch


def test_bat_messages_are_russian_and_paths_quoted():
    text = BAT.read_text(encoding="utf-8")
    for needle in ("Установка OmniVoice", "Проверяю uv", "ОШИБКА", "«Установить зависимости»",
                   'echo Папка: "%TOOL_DIR%"', 'echo ОШИБКА: не удалось открыть папку "%~dp0" или создать папку "%PROJECTS%".'):
        assert needle in text, needle
    echoes = [l for l in text.splitlines() if l.startswith("echo ") and l != "echo."]
    assert not any(w in l for l in echoes for w in ("ERROR", "Checking", "Installing", "Folder:"))
