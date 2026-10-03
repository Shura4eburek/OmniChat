"""The Windows installer: CRLF, ASCII, and the key commands (never executed here)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BAT = ROOT / "install-omnivoice.bat"


def test_bat_is_crlf_and_ascii():
    data = BAT.read_bytes()
    assert data.isascii()
    assert b"\r\n" in data
    assert data.count(b"\n") == data.count(b"\r\n"), "every line must end with CRLF"
    assert not data.startswith(b"\xef\xbb\xbf")


def test_bat_has_key_commands():
    text = BAT.read_text(encoding="ascii")
    for needle in ("where uv", "irm https://astral.sh/uv/install.ps1 | iex", "-ExecutionPolicy Bypass",
                   r"%USERPROFILE%\.local\bin", "sync --all-extras --inexact", "%~dp0",
                   r"%USERPROFILE%\omnivoice-projects", "WScript.Shell", "OmniVoice.lnk",
                   "run omnivoice ui --projects", "OMNIVOICE_DRYRUN", "pause", "exit /b 1"):
        assert needle in text, needle


def test_gitattributes_keeps_bat_crlf():
    attrs = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "*.bat text eol=crlf" in attrs
