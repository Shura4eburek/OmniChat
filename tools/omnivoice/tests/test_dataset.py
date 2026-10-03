import numpy as np, soundfile as sf
from pathlib import Path
from omnivoice.project import Project
from omnivoice import dataset
from omnivoice.dataset import Segment

def tone(path: Path, sr=44100, sec=2.0):
    t = np.arange(int(sr * sec)) / sr
    sf.write(path, 0.3 * np.sin(2 * np.pi * 220 * t), sr)

def proj(tmp_path): return Project.create(tmp_path / "p", name="p", language="ru")

def test_import_ljspeech(tmp_path):
    src = tmp_path / "lj"; (src / "wavs").mkdir(parents=True)
    tone(src / "wavs" / "a1.wav"); tone(src / "wavs" / "a2.wav", sec=3)
    (src / "metadata.csv").write_text("a1|Привет 2|Привет два\na2|Пока\n", encoding="utf-8")
    p = proj(tmp_path)
    assert dataset.import_dataset(p, src).added == 2
    segs = {s.id: s for s in dataset.load(p)}
    assert segs["a1"].text == "Привет два"          # 3rd column preferred when present
    info = sf.info(p.segments_dir / "a1.wav")
    assert info.samplerate == 22050 and info.channels == 1 and info.subtype == "PCM_16"
    assert abs(segs["a2"].duration - 3.3) < 0.05     # +150 ms padding each side

def test_import_pairs_and_rerun_is_idempotent(tmp_path):
    src = tmp_path / "pairs"; src.mkdir()
    tone(src / "x y.wav"); (src / "x y.txt").write_text("Текст", encoding="utf-8")
    p = proj(tmp_path)
    assert dataset.import_dataset(p, src).added == 1
    assert dataset.import_dataset(p, src).added == 0
    assert [s.id for s in dataset.load(p)] == ["x_y"]

def test_piper_csv_skips_dropped_and_empty(tmp_path):
    p = proj(tmp_path)
    dataset.save(p, [Segment("a", "Один", 2.0), Segment("b", "Два", 2.0, dropped=True), Segment("c", "", 1.5)])
    n = dataset.piper_csv(p, tmp_path / "train.csv")
    assert n == 1 and (tmp_path / "train.csv").read_text(encoding="utf-8") == "a.wav|Один\n"

def test_save_load_roundtrip_keeps_review_state(tmp_path):
    p = proj(tmp_path)
    dataset.save(p, [Segment("a", "x|y", 2.0, confidence=0.4, flags=["check"], edited=True)])
    s = dataset.load(p)[0]
    assert s.text == "x y" and s.flags == ["check"] and s.edited and s.confidence == 0.4

import pytest
from omnivoice.project import ProjectError

def test_cyrillic_names_get_distinct_ids(tmp_path):
    src = tmp_path / "c"; src.mkdir()
    for n in ("привет", "ответы"):
        tone(src / f"{n}.wav"); (src / f"{n}.txt").write_text(n, encoding="utf-8")
    tone(src / "aб.wav"); (src / "aб.txt").write_text("1", encoding="utf-8")
    tone(src / "аб.wav"); (src / "аб.txt").write_text("2", encoding="utf-8")
    p = proj(tmp_path)
    assert dataset.import_dataset(p, src).added == 4
    ids = [s.id for s in dataset.load(p)]
    assert len(set(ids)) == 4 and "privet" in ids
    assert dataset.import_dataset(p, src).added == 0

def test_bom_metadata_first_row(tmp_path):
    src = tmp_path / "b"; src.mkdir(); tone(src / "a1.wav")
    (src / "metadata.csv").write_bytes(("a1|Текст" + chr(10)).encode("utf-8-sig"))
    p = proj(tmp_path)
    assert dataset.import_dataset(p, src).added == 1
    assert dataset.load(p)[0].id == "a1"

def test_missing_and_corrupt_reported(tmp_path):
    src = tmp_path / "m"; src.mkdir(); tone(src / "ok.wav")
    (src / "bad.wav").write_bytes(b"not a wav")
    (src / "metadata.csv").write_text(chr(10).join(["ok|a", "bad|b", "gone|c"]), encoding="utf-8")
    r = dataset.import_dataset(proj(tmp_path), src)
    assert r.added == 1 and r.missing_audio == ["gone"] and r.failed == ["bad"]

def test_bad_sources(tmp_path):
    p = proj(tmp_path)
    with pytest.raises(ProjectError): dataset.import_dataset(p, tmp_path / "nope")
    (tmp_path / "e").mkdir()
    with pytest.raises(ProjectError): dataset.import_dataset(p, tmp_path / "e")

from typer.testing import CliRunner
from omnivoice.cli import app

def test_truncated_review_json_is_project_error(tmp_path):
    p = proj(tmp_path)
    dataset.save(p, [Segment("a", "Один", 2.0)])
    p.review_json.write_text('{"a": {"duration": 2.0, "fla', encoding="utf-8")
    with pytest.raises(ProjectError, match="Файл review.json повреждён"):
        dataset.load(p)
    r = CliRunner().invoke(app, ["check", "-p", str(p.root)])
    assert r.exit_code == 1 and "review.json" in r.output and "Traceback" not in r.output
    assert r.exception is None or isinstance(r.exception, SystemExit)

def test_review_json_wrong_shape_is_project_error(tmp_path):
    p = proj(tmp_path)
    dataset.save(p, [Segment("a", "Один", 2.0)])
    p.review_json.write_text('["a"]', encoding="utf-8")
    with pytest.raises(ProjectError, match="review.json"):
        dataset.load(p)

def test_bad_metadata_csv_is_project_error(tmp_path):
    p = proj(tmp_path)
    p.metadata_csv.write_bytes(b"a|\xff\xfe\n")
    with pytest.raises(ProjectError, match="Файл metadata.csv повреждён"):
        dataset.load(p)

def test_save_leaves_no_tmp_files(tmp_path):
    p = proj(tmp_path)
    dataset.save(p, [Segment("a", "Один", 2.0)])
    dataset.save(p, [Segment("a", "Два", 2.0)])
    assert not [f for f in p.root.iterdir() if f.name.endswith(".tmp")]
    assert dataset.load(p)[0].text == "Два"

def test_line_breaks_become_spaces(tmp_path):
    p = proj(tmp_path)
    dataset.save(p, [Segment("a", "один\rдва\r\nтри\nчетыре", 2.0), Segment("b", "x", 1.0)])
    assert [(s.id, s.text) for s in dataset.load(p)] == [("a", "один два три четыре"), ("b", "x")]
    assert dataset.clean_text("a\r\nb") == "a b"

def test_import_normalises_and_flags_text(tmp_path):
    src = tmp_path / "lj"; (src / "wavs").mkdir(parents=True)
    for n in ("a", "b", "c", "d"):
        tone(src / "wavs" / f"{n}.wav")
    (src / "metadata.csv").write_text(
        "a|Привет hello\nb|Ура 🎉\nc|*смеётся* Ну да\nd|Мне 5 лет\n", encoding="utf-8")
    p = proj(tmp_path)
    assert dataset.import_dataset(p, src).added == 4
    s = {x.id: x for x in dataset.load(p)}
    assert "foreign_letters" in s["a"].flags
    assert "emoji" in s["b"].flags and "🎉" not in s["b"].text
    assert "stage_direction" in s["c"].flags and "смеётся" not in s["c"].text
    assert "пять" in s["d"].text

def test_import_lone_cr_does_not_split_rows(tmp_path):
    src = tmp_path / "pairs"; src.mkdir()
    tone(src / "a.wav"); (src / "a.txt").write_bytes("Первая\rвторая".encode("utf-8"))
    p = proj(tmp_path)
    dataset.import_dataset(p, src)
    segs = dataset.load(p)
    assert len(segs) == 1 and segs[0].text == "Первая вторая"

def test_import_ids_case_insensitive(tmp_path):
    p = proj(tmp_path)
    p.segments_dir.mkdir(exist_ok=True)
    dataset.save(p, [Segment("Abc", "x", 1.0, source="old")])
    src = tmp_path / "pairs"; src.mkdir()
    tone(src / "abc.wav"); (src / "abc.txt").write_text("y", encoding="utf-8")
    dataset.import_dataset(p, src)
    ids = [s.id for s in dataset.load(p)]
    assert ids == ["Abc", "abc_2"]

def test_import_marks_without_clobbering_display(tmp_path):
    p = proj(tmp_path)
    other = Project.load(p.root); other.display["description"] = "d"; other.save()
    src = tmp_path / "pairs"; src.mkdir()
    tone(src / "a.wav"); (src / "a.txt").write_text("y", encoding="utf-8")
    dataset.import_dataset(p, src)
    q = Project.load(p.root)
    assert q.steps["slice"] and q.display["description"] == "d"
