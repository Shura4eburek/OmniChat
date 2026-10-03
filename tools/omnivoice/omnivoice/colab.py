from __future__ import annotations
import os
import zipfile
from pathlib import Path
from omnivoice import dataset

NOTEBOOK_URL = ("https://colab.research.google.com/github/Shura4eburek/OmniChat/blob/main/"
                "tools/omnivoice/notebooks/omnivoice_colab.ipynb")

def make_dataset_zip(p, out: Path | None = None) -> Path:
    out = Path(out) if out else p.root / f"{p.name}-dataset.zip"
    p.train_dir.mkdir(parents=True, exist_ok=True)
    csv = p.train_dir / "train.csv"
    if dataset.piper_csv(p, csv) == 0:
        raise RuntimeError("Нет ни одной фразы с текстом для обучения")
    ids = [line.split("|", 1)[0] for line in csv.read_text(encoding="utf-8").splitlines() if line]
    missing = [n for n in ids if not (p.segments_dir / n).is_file()]
    if missing:
        raise RuntimeError(f"Нет аудиофайлов для фраз ({len(missing)}): " + ", ".join(missing[:10])
                           + (" …" if len(missing) > 10 else ""))
    tmp = out.with_name(out.name + ".part")
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(p.root / "project.toml", "project.toml")
            for extra in ("metadata.csv", "review.json"):
                if (p.root / extra).is_file():
                    z.write(p.root / extra, extra)
            z.write(csv, "train/train.csv")
            for name in ids:
                z.write(p.segments_dir / name, f"segments/{name}", compress_type=zipfile.ZIP_STORED)
        os.replace(tmp, out)
    finally:
        tmp.unlink(missing_ok=True)
    return out
