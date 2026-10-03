"""Compatibility layer for training with piper1-gpl v1.8.0 on current PyTorch/Lightning.

Shared by the Docker image (this folder is its build context) and the Colab notebook.
"""
import site
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PTH_NAME = "omnivoice_torch_shim.pth"


def install_shim(site_dir: Path | None = None) -> Path:
    """Make every new Python process load torch_shim.py at start (for piper subprocesses)."""
    target = Path(site_dir or site.getsitepackages()[0])
    (target / "omnivoice_torch_shim.py").write_text((HERE / "torch_shim.py").read_text(encoding="utf-8"),
                                                   encoding="utf-8")
    pth = target / PTH_NAME
    pth.write_text("import omnivoice_torch_shim\n", encoding="utf-8")
    return pth


def clean_command(src: str, dst: str) -> list[str]:
    """Command that writes a cleaned copy of an old rhasspy base checkpoint."""
    return [sys.executable, str(HERE / "clean_ckpt.py"), src, dst]


def clean_base_local(ckpt: Path) -> Path:
    """Cleaned sibling of a base checkpoint, made with the local Python (Colab). Needs piper installed."""
    import subprocess
    ckpt = Path(ckpt)
    clean = ckpt.with_name(ckpt.stem + ".clean.ckpt")
    if not clean.is_file():
        subprocess.run(clean_command(str(ckpt), str(clean)), check=True)
    return clean
