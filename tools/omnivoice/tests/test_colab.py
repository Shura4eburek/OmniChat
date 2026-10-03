import json
import pytest
import zipfile
from pathlib import Path
import numpy as np
from typer.testing import CliRunner
from omnivoice import colab, dataset, audio
from omnivoice.cli import app
from omnivoice.dataset import Segment
from omnivoice.project import Project

NB = Path(colab.__file__).resolve().parents[1] / "notebooks" / "omnivoice_colab.ipynb"

def _project(tmp_path, segs):
    p = Project.create(tmp_path / "g", name="g", language="ru")
    for s in segs:
        audio.write_wav(p.segments_dir / f"{s.id}.wav", np.zeros(22050, np.float32))
    dataset.save(p, segs)
    return p

def test_dataset_zip_contains_only_kept(tmp_path):
    p = _project(tmp_path, [Segment("a", "Да", 1.0), Segment("b", "Нет", 1.0, dropped=True)])
    z = colab.make_dataset_zip(p)
    names = zipfile.ZipFile(z).namelist()
    assert "segments/a.wav" in names and "segments/b.wav" not in names
    assert "project.toml" in names and "train/train.csv" in names
    assert not list(tmp_path.rglob("*.part"))

def test_dataset_zip_empty_raises(tmp_path):
    p = _project(tmp_path, [Segment("a", "  ", 1.0)])
    with pytest.raises(RuntimeError, match="фраз"):
        colab.make_dataset_zip(p)

def test_dataset_zip_missing_wav_raises(tmp_path):
    p = _project(tmp_path, [Segment("a", "Да", 1.0), Segment("b", "Нет", 1.0)])
    (p.segments_dir / "b.wav").unlink()
    with pytest.raises(RuntimeError, match="b.wav"):
        colab.make_dataset_zip(p)

def test_notebook_valid_and_in_sync():
    text = NB.read_text(encoding="utf-8")
    nb = json.loads(text)
    assert nb["cells"] and nb["nbformat"] == 4
    assert nb["metadata"]["accelerator"] == "GPU"
    assert "fit_args" in text and "base_epoch" in text and "Сколько эпох дообучать" in text and "rm -rf" not in text
    assert all(c.get("outputs", []) == [] for c in nb["cells"] if c["cell_type"] == "code")

def test_cli_train_colab_prints_zip_and_url(tmp_path):
    p = _project(tmp_path, [Segment("a", "Да", 1.0)])
    r = CliRunner().invoke(app, ["train", "--colab", "-p", str(p.root)])
    assert r.exit_code == 0
    assert "g-dataset.zip" in r.output and colab.NOTEBOOK_URL in r.output

def test_cli_train_colab_empty_exits_1(tmp_path):
    p = _project(tmp_path, [Segment("a", "", 1.0)])
    r = CliRunner().invoke(app, ["train", "--colab", "-p", str(p.root)])
    assert r.exit_code == 1
    assert "фраз" in r.output
