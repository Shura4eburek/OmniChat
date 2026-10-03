# omnivoice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Python tool `omnivoice` (CLI + Gradio UI) in `tools/omnivoice/` that turns raw audio, a ready dataset, or a ready piper model into a voice folder the OmniChat mod loads safely.

**Architecture:** Pure, unit-tested core modules (project state, dataset records, text normalization, segment planning, ONNX metadata, mod rules, packaging) under a Typer CLI. Heavy work is isolated: audio prep behind the `[prep]` extra, training/export in a CUDA Docker image (or Colab), sherpa-onnx verification in a subprocess. The Gradio UI only calls the same core functions.

**Tech Stack:** Python ≥ 3.11, uv, Typer, onnx, sherpa-onnx, Pillow, numpy, soundfile, soxr, num2words, tomli-w, pytest; `[prep]` faster-whisper, silero-vad, demucs, pyloudnorm; `[ui]` gradio, tensorboard; Docker image `pytorch/pytorch:2.14.1-cuda12.6-cudnn9-devel` + piper1-gpl.

**Spec:** `docs/superpowers/specs/2026-10-04-omnivoice-design.md`. Verified external facts (commands, URLs, APIs): `.superpowers/omnivoice-facts.md` — executors must read the relevant section before touching piper/sherpa/whisper/vad/demucs code.

## Global Constraints

- Package root `tools/omnivoice/`, import package `omnivoice`, console script `omnivoice`. Python `>=3.11`. Managed with `uv`; tests: `cd tools/omnivoice && uv run pytest`.
- Base deps only: `typer`, `onnx`, `sherpa-onnx`, `pillow`, `numpy`, `soundfile`, `soxr`, `num2words`, `tomli-w`, `iso639-lang`. Extras: `prep` = `faster-whisper`, `silero-vad`, `demucs`, `pyloudnorm`; `ui` = `gradio`, `tensorboard`. torch / piper-train are NEVER local deps (Docker/Colab only).
- Segments: WAV, 22050 Hz, mono, PCM 16-bit; length 1–15 s; 150 ms silence padding at both ends.
- Dataset file `metadata.csv`: `id|text` (no header, `|` delimiter, UTF-8); review state in `review.json`. Piper training csv: `id.wav|text`.
- Mod rules (must equal the mod's Java): `name` ≤ 32, `description` ≤ 200, `sample` ≤ 120, `language` ≤ 8, `gender` ≤ 16; portrait PNG exactly 16×16 or 32×32, ≤ 8192 bytes; ONNX metadata must contain `n_speakers`; piper (`comment=piper`) must contain non-blank `voice`.
- ONNX metadata written by omnivoice (exact keys): `model_type=vits`, `comment=piper`, `language=<ISO 639 English name, e.g. Russian>`, `voice=<espeak voice>`, `version=1`, `has_espeak=1`, `n_speakers=1`, `sample_rate=22050`, `omnivoice_version=<package version>`.
- `tokens.txt` line format: `<symbol> <id>` (first id if list), skip `"\n"`.
- espeak-ng-data source: `https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/espeak-ng-data.tar.bz2`, cached under the omnivoice cache dir.
- Base checkpoints: `https://huggingface.co/datasets/rhasspy/piper-checkpoints/resolve/main/<path>` with paths from facts §3; defaults: `ru` → irina medium, `en` → lessac medium.
- User-facing CLI/UI text is Russian; log lines and internal exception details are English. Every UI string lives in `omnivoice/ui/strings.py`.
- Git: commit after every task, Conventional Commits, trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Never modify the user's real models in `run/config/omnichat/models/` — tests copy.
- Windows-first: paths via `pathlib`, no shell-specific tricks; Docker invoked via `subprocess` list args.

## Review Focus

1. **Audio with music/noise and long monologues** — a 10-minute game clip without `--isolate` must still slice into 1–15 s phrases (long speech split at the quietest point), never a 10-minute segment. Test: `test_segments.py::test_long_speech_is_split_at_quietest_point` (Task 5).
2. **Text the phonemizer can't speak** (Latin in a Russian voice, emoji, `*sound*` stage directions, digits) — normalized or flagged, never silently fed to training. Test: `test_textnorm.py::test_stage_directions_and_emoji_are_removed_and_flagged` (Task 3).
3. **Re-running a step after a crash or edit** — `slice`/`transcribe`/`import` must not duplicate rows or lose manual text edits. Test: `test_dataset.py::test_transcribe_keeps_manual_edits_on_rerun` (Task 6).
4. **Foreign piper model with list-valued ids, `\n` symbol, `pt-PT` voice, missing `.onnx.json`** — `pack` handles or fails with a clear message. Tests: `test_onnxmeta.py::test_tokens_from_config_edge_cases`, `test_pack.py::test_pack_foreign_model_without_json_needs_voice` (Task 8).
5. **Docker present but no NVIDIA GPU / WSL GPU passthrough missing** — `train` stops before a long build with a Colab hint. Test: `test_train.py::test_no_gpu_suggests_colab` (Task 11).

---

## File Structure

```
tools/omnivoice/
  pyproject.toml
  README.md
  omnivoice/
    __init__.py            # __version__
    cli.py                 # Typer app, one sub-command per stage (thin)
    paths.py               # cache dir, find minecraft dirs
    modrules.py            # mod limits + validate_voice_folder()
    project.py             # Project, project.toml load/save, steps
    languages.py           # language presets (espeak voice, iso name, base ckpt path)
    dataset.py             # Segment record, metadata.csv/review.json io, import_dataset()
    textnorm.py            # normalize_text() -> (text, flags)
    audio.py               # load/resample/write wav, loudness, clipping
    segments.py            # plan_segments() pure timestamp logic
    slicer.py              # slice_project() (prep extra: ffmpeg, demucs, silero)
    transcriber.py         # transcribe_project() (prep extra: faster-whisper)
    checker.py             # check_project() -> Report
    onnxmeta.py            # write_piper_metadata(), tokens_from_config()
    espeak.py              # ensure_espeak_data() download+cache
    portrait.py            # make_portrait()
    pack.py                # pack_voice()
    verify.py              # verify_voice() (subprocess) + _verify_worker.py
    install.py             # install_voice()
    checkpoints.py         # base ckpt download/cache
    train.py               # docker detection, build, fit/export command builders, run
    previews.py            # TensorBoard audio extraction, checkpoint listing
    colab.py               # dataset.zip for Colab
    ui/
      app.py               # Gradio Blocks
      theme.py             # HUD theme + CSS
      strings.py           # all UI strings (ru)
  docker/Dockerfile
  notebooks/omnivoice_colab.ipynb
  tests/ ... (one test module per core module)
```

---

### Task 1: Package scaffold, CLI skeleton, mod rules

**Files:**
- Create: `tools/omnivoice/pyproject.toml`, `tools/omnivoice/omnivoice/__init__.py`, `tools/omnivoice/omnivoice/cli.py`, `tools/omnivoice/omnivoice/modrules.py`
- Test: `tools/omnivoice/tests/test_modrules.py`, `tools/omnivoice/tests/test_cli.py`
- Modify: root `.gitignore` (add `tools/omnivoice/.venv/`, `**/__pycache__/`, `tools/omnivoice/.pytest_cache/`)

**Interfaces:**
- Produces: `omnivoice.__version__ == "0.1.0"`; `modrules.LIMITS = {"name":32,"description":200,"sample":120,"language":8,"gender":16}`; `modrules.MAX_PORTRAIT_BYTES = 8192`; `modrules.PORTRAIT_SIZES = (16, 32)`; `modrules.onnx_problem(meta: dict[str,str]) -> str | None`; `modrules.validate_voice_folder(folder: Path) -> list[str]` (problems, empty = OK); Typer `app` in `cli.py` with `--version`.

- [ ] **Step 1: pyproject**

```toml
[project]
name = "omnivoice"
version = "0.1.0"
description = "Train and package TTS voices for the OmniChat Minecraft mod"
requires-python = ">=3.11"
dependencies = [
  "typer>=0.12", "onnx>=1.16", "sherpa-onnx>=1.12", "pillow>=10", "numpy>=1.26",
  "soundfile>=0.12", "soxr>=0.3", "num2words>=0.5.13", "tomli-w>=1.0", "iso639-lang>=2.2",
]
[project.optional-dependencies]
prep = ["faster-whisper>=1.0", "silero-vad>=5.1", "demucs>=4.0", "pyloudnorm>=0.1.1"]
ui = ["gradio>=4.44", "tensorboard>=2.16"]
[project.scripts]
omnivoice = "omnivoice.cli:app"
[dependency-groups]
dev = ["pytest>=8"]
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Failing tests**

`tests/test_modrules.py`:
```python
import json
from pathlib import Path
from omnivoice import modrules
from tests.helpers import make_onnx, png

def test_onnx_problem_matches_mod():
    assert modrules.onnx_problem({"comment": "piper", "voice": "ru"}) == "missing 'n_speakers' metadata"
    assert modrules.onnx_problem({"n_speakers": "1", "comment": "piper"}) == "missing 'voice' metadata (espeak voice)"
    assert modrules.onnx_problem({"n_speakers": "1", "comment": "piper", "voice": " "}) == "missing 'voice' metadata (espeak voice)"
    assert modrules.onnx_problem({"n_speakers": "1", "comment": "piper", "voice": "ru"}) is None
    assert modrules.onnx_problem({"n_speakers": "4", "comment": "coqui"}) is None

def test_validate_voice_folder(tmp_path: Path):
    folder = tmp_path / "glados"; folder.mkdir()
    make_onnx(folder / "glados.onnx", {"n_speakers": "1", "comment": "piper", "voice": "ru"})
    (folder / "tokens.txt").write_text("_ 0\n", encoding="utf-8")
    (folder / "espeak-ng-data").mkdir(); (folder / "espeak-ng-data" / "phontab").write_bytes(b"x")
    (folder / "voice.json").write_text(json.dumps({"name": "GLaDOS"}), encoding="utf-8")
    (folder / "portrait.png").write_bytes(png(32, 32))
    assert modrules.validate_voice_folder(folder) == []

def test_validate_voice_folder_reports_each_problem(tmp_path: Path):
    folder = tmp_path / "bad"; folder.mkdir()
    make_onnx(folder / "bad.onnx", {"comment": "piper"})
    (folder / "voice.json").write_text(json.dumps({"name": "N" * 40}), encoding="utf-8")
    (folder / "portrait.png").write_bytes(png(64, 64))
    problems = modrules.validate_voice_folder(folder)
    assert any("n_speakers" in p for p in problems)
    assert any("tokens.txt" in p for p in problems)
    assert any("name" in p and "32" in p for p in problems)
    assert any("portrait" in p for p in problems)
```

`tests/helpers.py` (shared test helpers):
```python
import io
from pathlib import Path
import onnx
from onnx import helper, TensorProto
from PIL import Image

def make_onnx(path: Path, meta: dict[str, str]) -> Path:
    node = helper.make_node("Identity", ["x"], ["y"])
    graph = helper.make_graph([node], "g",
        [helper.make_tensor_value_info("x", TensorProto.FLOAT, [1])],
        [helper.make_tensor_value_info("y", TensorProto.FLOAT, [1])])
    model = helper.make_model(graph)
    for k, v in meta.items():
        p = model.metadata_props.add(); p.key = k; p.value = v
    onnx.save(model, path)
    return path

def png(w: int, h: int) -> bytes:
    buf = io.BytesIO(); Image.new("RGBA", (w, h), (53, 224, 200, 255)).save(buf, "PNG")
    return buf.getvalue()
```
Also create empty `tests/__init__.py`.

`tests/test_cli.py`:
```python
from typer.testing import CliRunner
from omnivoice.cli import app
from omnivoice import __version__

def test_version():
    r = CliRunner().invoke(app, ["--version"])
    assert r.exit_code == 0 and __version__ in r.output
```

- [ ] **Step 3: Run** — `cd tools/omnivoice && uv sync && uv run pytest` → FAIL (modules missing).

- [ ] **Step 4: Implement**

`omnivoice/__init__.py`: `__version__ = "0.1.0"`

`omnivoice/modrules.py`:
```python
"""Limits the OmniChat mod enforces. Keep in sync with:
src/main/java/org/mamoru/omnichat/voice/VoiceMetaReader.java and
src/client/java/org/mamoru/omnichat/client/tts/OnnxMetadata.java."""
from __future__ import annotations
import json
from pathlib import Path
import onnx

LIMITS = {"name": 32, "description": 200, "sample": 120, "language": 8, "gender": 16}
MAX_PORTRAIT_BYTES = 8192
PORTRAIT_SIZES = (16, 32)
_PNG_SIG = b"\x89PNG\r\n\x1a\n"

def read_onnx_metadata(path: Path) -> dict[str, str]:
    model = onnx.load(str(path), load_external_data=False)
    return {p.key: p.value for p in model.metadata_props}

def onnx_problem(meta: dict[str, str]) -> str | None:
    if "n_speakers" not in meta:
        return "missing 'n_speakers' metadata"
    if meta.get("comment", "").lower() == "piper" and not meta.get("voice", "").strip():
        return "missing 'voice' metadata (espeak voice)"
    return None

def portrait_problem(data: bytes) -> str | None:
    if len(data) > MAX_PORTRAIT_BYTES:
        return f"portrait.png is {len(data)} bytes, limit {MAX_PORTRAIT_BYTES}"
    if len(data) < 24 or not data.startswith(_PNG_SIG) or data[12:16] != b"IHDR":
        return "portrait.png is not a PNG"
    w, h = int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    if w != h or w not in PORTRAIT_SIZES:
        return f"portrait.png must be 16x16 or 32x32, got {w}x{h}"
    return None

def validate_voice_folder(folder: Path) -> list[str]:
    problems: list[str] = []
    models = sorted(folder.glob("*.onnx"))
    if len(models) != 1:
        problems.append(f"expected exactly one .onnx in {folder.name}, found {len(models)}")
    else:
        p = onnx_problem(read_onnx_metadata(models[0]))
        if p: problems.append(p)
    if not (folder / "tokens.txt").is_file():
        problems.append("tokens.txt is missing")
    if not (folder / "espeak-ng-data" / "phontab").is_file():
        problems.append("espeak-ng-data is missing or incomplete (no phontab)")
    vj = folder / "voice.json"
    if vj.is_file():
        try:
            data = json.loads(vj.read_text(encoding="utf-8"))
            for key, limit in LIMITS.items():
                if len(str(data.get(key, ""))) > limit:
                    problems.append(f"voice.json {key} longer than {limit}")
        except json.JSONDecodeError as e:
            problems.append(f"voice.json is not valid JSON: {e}")
    pp = folder / "portrait.png"
    if pp.is_file():
        p = portrait_problem(pp.read_bytes())
        if p: problems.append(p)
    return problems
```

`omnivoice/cli.py`:
```python
import typer
from omnivoice import __version__

app = typer.Typer(help="omnivoice — обучение и упаковка голосов для OmniChat", no_args_is_help=True)

def _version(value: bool):
    if value:
        typer.echo(f"omnivoice {__version__}"); raise typer.Exit()

@app.callback()
def main(version: bool = typer.Option(False, "--version", callback=_version, is_eager=True, help="Показать версию")):
    pass
```

- [ ] **Step 5: Run** — `uv run pytest` → all pass.
- [ ] **Step 6: Commit** — `git add tools/omnivoice .gitignore && git commit -m "feat(omnivoice): scaffold package with cli and mod rules"`

---

### Task 2: Language presets, project file, `init`

**Files:**
- Create: `omnivoice/languages.py`, `omnivoice/project.py`, `omnivoice/paths.py`
- Modify: `omnivoice/cli.py` (add `init`)
- Test: `tests/test_project.py`

**Interfaces:**
- Produces:
  - `languages.Language(code: str, espeak_voice: str, iso_name: str, base_checkpoint: str, test_phrase: str)`; `languages.PRESETS: dict[str, Language]` with `ru` (espeak `ru`, `Russian`, `ru/ru_RU/irina/medium/epoch=4139-step=929464.ckpt`, `"Привет! Вот так я звучу."`) and `en` (espeak `en-us`, `English`, `en/en_US/lessac/medium/epoch=2164-step=1355540.ckpt`, `"Hello! This is how I sound."`); `languages.BASE_CHECKPOINTS: dict[str,str]` mapping `denis|dmitri|irina|ruslan|lessac` → paths from facts §3.
  - `project.Project` dataclass: `root: Path`, `name: str`, `language: str`, `espeak_voice: str`, `base_checkpoint: str`, `sample_rate: int = 22050`, `display: dict` (`name`, `description`, `gender`, `sample`, `license`), `steps: dict[str, bool]`; `Project.create(root, name, language, base=None) -> Project`; `Project.load(root) -> Project`; `save()`; `mark(step)`; properties `raw_dir`, `segments_dir`, `metadata_csv`, `review_json`, `train_dir`, `export_dir`.
  - `STEPS = ("audio", "slice", "phrases", "check", "train", "pack")`.
  - `paths.cache_dir() -> Path` (`%LOCALAPPDATA%/omnivoice` on Windows, `~/.cache/omnivoice` elsewhere; env `OMNIVOICE_CACHE` overrides).
- CLI: `omnivoice init DIR --name N --language ru [--base irina]`.

- [ ] **Step 1: Failing tests** (`tests/test_project.py`):

```python
from pathlib import Path
import pytest
from typer.testing import CliRunner
from omnivoice.project import Project, STEPS
from omnivoice import languages
from omnivoice.cli import app

def test_create_load_roundtrip(tmp_path: Path):
    p = Project.create(tmp_path / "glados", name="glados", language="ru")
    assert p.espeak_voice == "ru" and p.base_checkpoint == languages.PRESETS["ru"].base_checkpoint
    assert p.raw_dir.is_dir() and p.segments_dir.is_dir()
    p.mark("audio"); p.display["description"] = "Злой ИИ"; p.save()
    q = Project.load(tmp_path / "glados")
    assert q.steps["audio"] is True and q.display["description"] == "Злой ИИ"
    assert set(q.steps) == set(STEPS)

def test_create_with_named_base(tmp_path: Path):
    p = Project.create(tmp_path / "x", name="x", language="ru", base="denis")
    assert "denis" in p.base_checkpoint

def test_unknown_language_is_rejected(tmp_path: Path):
    with pytest.raises(ValueError, match="language"):
        Project.create(tmp_path / "x", name="x", language="xx")

def test_init_command(tmp_path: Path):
    r = CliRunner().invoke(app, ["init", str(tmp_path / "v"), "--name", "v", "--language", "en"])
    assert r.exit_code == 0, r.output
    assert Project.load(tmp_path / "v").espeak_voice == "en-us"
```

- [ ] **Step 2: Run** — `uv run pytest tests/test_project.py` → FAIL.

- [ ] **Step 3: Implement**

`omnivoice/languages.py`:
```python
from dataclasses import dataclass

BASE_CHECKPOINTS = {
    "denis": "ru/ru_RU/denis/medium/epoch=4474-step=1521860.ckpt",
    "dmitri": "ru/ru_RU/dmitri/medium/epoch=5589-step=1478840.ckpt",
    "irina": "ru/ru_RU/irina/medium/epoch=4139-step=929464.ckpt",
    "ruslan": "ru/ru_RU/ruslan/medium/epoch=2436-step=1724372.ckpt",
    "lessac": "en/en_US/lessac/medium/epoch=2164-step=1355540.ckpt",
}

@dataclass(frozen=True)
class Language:
    code: str
    espeak_voice: str
    iso_name: str
    base_checkpoint: str
    test_phrase: str

PRESETS = {
    "ru": Language("ru", "ru", "Russian", BASE_CHECKPOINTS["irina"], "Привет! Вот так я звучу."),
    "en": Language("en", "en-us", "English", BASE_CHECKPOINTS["lessac"], "Hello! This is how I sound."),
}
```

`omnivoice/paths.py`:
```python
import os, sys
from pathlib import Path

def cache_dir() -> Path:
    if env := os.environ.get("OMNIVOICE_CACHE"):
        d = Path(env)
    elif sys.platform == "win32":
        d = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "omnivoice"
    else:
        d = Path.home() / ".cache" / "omnivoice"
    d.mkdir(parents=True, exist_ok=True)
    return d
```

`omnivoice/project.py`:
```python
from __future__ import annotations
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
import tomli_w
from omnivoice import languages

STEPS = ("audio", "slice", "phrases", "check", "train", "pack")
FILE = "project.toml"

@dataclass
class Project:
    root: Path
    name: str
    language: str
    espeak_voice: str
    base_checkpoint: str
    sample_rate: int = 22050
    display: dict = field(default_factory=dict)
    steps: dict = field(default_factory=lambda: {s: False for s in STEPS})

    raw_dir = property(lambda self: self.root / "raw")
    segments_dir = property(lambda self: self.root / "segments")
    metadata_csv = property(lambda self: self.root / "metadata.csv")
    review_json = property(lambda self: self.root / "review.json")
    train_dir = property(lambda self: self.root / "train")
    export_dir = property(lambda self: self.root / "export")

    @classmethod
    def create(cls, root: Path, name: str, language: str, base: str | None = None) -> "Project":
        if language not in languages.PRESETS:
            raise ValueError(f"unknown language '{language}', supported: {', '.join(languages.PRESETS)}")
        lang = languages.PRESETS[language]
        ckpt = languages.BASE_CHECKPOINTS[base] if base else lang.base_checkpoint
        p = cls(Path(root), name, language, lang.espeak_voice, ckpt,
                display={"name": name, "description": "", "gender": "", "sample": lang.test_phrase, "license": ""})
        for d in (p.raw_dir, p.segments_dir, p.train_dir, p.export_dir):
            d.mkdir(parents=True, exist_ok=True)
        p.save()
        return p

    @classmethod
    def load(cls, root: Path) -> "Project":
        data = tomllib.loads((Path(root) / FILE).read_text(encoding="utf-8"))
        steps = {s: False for s in STEPS} | data.get("steps", {})
        return cls(Path(root), data["name"], data["language"], data["espeak_voice"], data["base_checkpoint"],
                   data.get("sample_rate", 22050), data.get("display", {}), steps)

    def save(self) -> None:
        data = {"name": self.name, "language": self.language, "espeak_voice": self.espeak_voice,
                "base_checkpoint": self.base_checkpoint, "sample_rate": self.sample_rate,
                "display": self.display, "steps": self.steps}
        (self.root / FILE).write_text(tomli_w.dumps(data), encoding="utf-8")

    def mark(self, step: str, done: bool = True) -> None:
        if step not in STEPS:
            raise ValueError(step)
        self.steps[step] = done
```

`cli.py` add:
```python
from pathlib import Path
from omnivoice.project import Project

@app.command()
def init(directory: Path, name: str = typer.Option(..., help="Имя голоса"),
         language: str = typer.Option("ru", help="Язык: ru или en"),
         base: str = typer.Option(None, help="Базовая модель: denis, dmitri, irina, ruslan, lessac")):
    """Создать проект голоса."""
    try:
        p = Project.create(directory, name=name, language=language, base=base)
    except (ValueError, KeyError) as e:
        typer.secho(f"Ошибка: {e}", fg="red"); raise typer.Exit(1)
    typer.secho(f"Проект «{p.name}» создан в {p.root}", fg="green")
```

- [ ] **Step 4: Run** — `uv run pytest` → pass.
- [ ] **Step 5: Commit** — `feat(omnivoice): add language presets, project file and init`

---

### Task 3: Text normalization

**Files:** Create `omnivoice/textnorm.py`; Test `tests/test_textnorm.py`

**Interfaces:**
- Produces: `textnorm.normalize_text(text: str, language: str) -> tuple[str, list[str]]` — returns cleaned text and flags from `{"digits", "stage_direction", "foreign_letters", "emoji", "empty"}`.

Rules: strip `*...*`, `[...]`, `(...)` stage directions (flag `stage_direction`); remove emoji/symbols outside letters, digits and `.,!?;:-—«»"' ` (flag `emoji` if any removed); digits → words via `num2words(n, lang=language)` (flag `digits`); for `ru`, Latin letters remaining → flag `foreign_letters` (keep text); collapse whitespace; empty result → flag `empty`.

- [ ] **Step 1: Failing tests**

```python
from omnivoice.textnorm import normalize_text

def test_digits_become_words():
    t, f = normalize_text("Тест номер 3.", "ru")
    assert t == "Тест номер три." and "digits" in f

def test_stage_directions_and_emoji_are_removed_and_flagged():
    t, f = normalize_text("*звук двери* Ты здесь? 😀 [неразборчиво]", "ru")
    assert t == "Ты здесь?" and {"stage_direction", "emoji"} <= set(f)

def test_latin_in_russian_is_flagged_not_removed():
    t, f = normalize_text("Запусти Aperture Science.", "ru")
    assert "Aperture" in t and "foreign_letters" in f

def test_empty():
    t, f = normalize_text("*тишина*", "ru")
    assert t == "" and "empty" in f

def test_english():
    t, f = normalize_text("I have 2 cakes!", "en")
    assert t == "I have two cakes!" and f == ["digits"]
```

- [ ] **Step 2: Run** → FAIL. 

- [ ] **Step 3: Implement**

```python
import re
from num2words import num2words

_STAGE = re.compile(r"\*[^*]*\*|\[[^\]]*\]|\([^)]*\)")
_ALLOWED = re.compile(r"[^\w\s.,!?;:\-—«»\"']", re.UNICODE)
_DIGITS = re.compile(r"\d+")
_LATIN = re.compile(r"[A-Za-z]")

def normalize_text(text: str, language: str) -> tuple[str, list[str]]:
    flags: list[str] = []
    stripped = _STAGE.sub(" ", text)
    if stripped != text:
        flags.append("stage_direction")
    cleaned = _ALLOWED.sub(" ", stripped)
    if cleaned != stripped:
        flags.append("emoji")
    if _DIGITS.search(cleaned):
        cleaned = _DIGITS.sub(lambda m: num2words(int(m.group()), lang=language), cleaned)
        flags.append("digits")
    cleaned = re.sub(r"\s+([.,!?;:])", r"\1", re.sub(r"\s+", " ", cleaned)).strip()
    if language == "ru" and _LATIN.search(cleaned):
        flags.append("foreign_letters")
    if not cleaned:
        flags.append("empty")
    return cleaned, flags
```

- [ ] **Step 4: Run** → pass. **Step 5: Commit** — `feat(omnivoice): normalize transcript text`

---

### Task 4: Audio helpers and dataset records, `import`

**Files:** Create `omnivoice/audio.py`, `omnivoice/dataset.py`; Modify `cli.py` (`import`); Test `tests/test_dataset.py`, `tests/test_audio.py`

**Interfaces:**
- Produces:
  - `audio.load_mono(path) -> tuple[np.ndarray, int]` (float32, any input soundfile reads); `audio.resample(x, sr_in, sr_out=22050)` (soxr); `audio.pad(x, sr, ms=150)`; `audio.write_wav(path, x, sr=22050)` (PCM_16); `audio.clipping_ratio(x) -> float` (share of |x| ≥ 0.999); `audio.duration(path) -> float`.
  - `dataset.Segment(id: str, text: str, duration: float, confidence: float | None = None, flags: list[str] = [], dropped: bool = False, edited: bool = False)`.
  - `dataset.load(project) -> list[Segment]` (merge metadata.csv + review.json); `dataset.save(project, segments)` (writes both; metadata.csv excludes nothing — dropped kept in review only; training export filters).
  - `dataset.import_dataset(project, source: Path) -> int` — accepts LJSpeech (`metadata.csv` with `id|text` or `id|text|normalized` + `wavs/`) or pairs `x.wav` + `x.txt`; resamples to 22050 mono, pads, writes `segments/<id>.wav`; ids sanitized to `[A-Za-z0-9_-]`; skips ids already present.
  - `dataset.piper_csv(project, out: Path) -> int` — writes `id.wav|text` for non-dropped, non-empty rows.

- [ ] **Step 1: Failing tests** (`tests/test_dataset.py`):

```python
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
    assert dataset.import_dataset(p, src) == 2
    segs = {s.id: s for s in dataset.load(p)}
    assert segs["a1"].text == "Привет два"          # 3rd column preferred when present
    info = sf.info(p.segments_dir / "a1.wav")
    assert info.samplerate == 22050 and info.channels == 1 and info.subtype == "PCM_16"
    assert abs(segs["a2"].duration - 3.3) < 0.05     # +150 ms padding each side

def test_import_pairs_and_rerun_is_idempotent(tmp_path):
    src = tmp_path / "pairs"; src.mkdir()
    tone(src / "x y.wav"); (src / "x y.txt").write_text("Текст", encoding="utf-8")
    p = proj(tmp_path)
    assert dataset.import_dataset(p, src) == 1
    assert dataset.import_dataset(p, src) == 0
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
```
(`|` inside text is replaced by a space on save — it is the csv delimiter.)

`tests/test_audio.py`:
```python
import numpy as np
from omnivoice import audio

def test_clipping_ratio():
    x = np.zeros(1000, np.float32); x[:10] = 1.0
    assert abs(audio.clipping_ratio(x) - 0.01) < 1e-9

def test_resample_and_pad_lengths():
    x = np.zeros(44100, np.float32)
    y = audio.resample(x, 44100, 22050)
    assert abs(len(y) - 22050) <= 2
    assert len(audio.pad(y, 22050)) == len(y) + 2 * int(0.15 * 22050)
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Implement** `omnivoice/audio.py`:

```python
from pathlib import Path
import numpy as np, soundfile as sf, soxr

SR = 22050

def load_mono(path) -> tuple[np.ndarray, int]:
    x, sr = sf.read(str(path), dtype="float32", always_2d=True)
    return x.mean(axis=1), sr

def resample(x: np.ndarray, sr_in: int, sr_out: int = SR) -> np.ndarray:
    return x if sr_in == sr_out else soxr.resample(x, sr_in, sr_out).astype(np.float32)

def pad(x: np.ndarray, sr: int, ms: int = 150) -> np.ndarray:
    z = np.zeros(int(sr * ms / 1000), np.float32)
    return np.concatenate([z, x.astype(np.float32), z])

def write_wav(path, x: np.ndarray, sr: int = SR) -> None:
    sf.write(str(path), np.clip(x, -1, 1), sr, subtype="PCM_16")

def clipping_ratio(x: np.ndarray) -> float:
    return float(np.mean(np.abs(x) >= 0.999)) if len(x) else 0.0

def duration(path) -> float:
    i = sf.info(str(path)); return i.frames / i.samplerate
```

`omnivoice/dataset.py`:
```python
from __future__ import annotations
import csv, json, re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from omnivoice import audio
from omnivoice.project import Project

@dataclass
class Segment:
    id: str
    text: str
    duration: float
    confidence: float | None = None
    flags: list[str] = field(default_factory=list)
    dropped: bool = False
    edited: bool = False

def _clean(text: str) -> str:
    return text.replace("|", " ").replace("\n", " ").strip()

def load(p: Project) -> list[Segment]:
    if not p.metadata_csv.is_file():
        return []
    review = json.loads(p.review_json.read_text(encoding="utf-8")) if p.review_json.is_file() else {}
    out = []
    for row in csv.reader(p.metadata_csv.open(encoding="utf-8"), delimiter="|", quoting=csv.QUOTE_NONE):
        if not row: continue
        r = review.get(row[0], {})
        out.append(Segment(row[0], row[1] if len(row) > 1 else "", r.get("duration", 0.0), r.get("confidence"),
                           r.get("flags", []), r.get("dropped", False), r.get("edited", False)))
    return out

def save(p: Project, segments: list[Segment]) -> None:
    with p.metadata_csv.open("w", encoding="utf-8", newline="") as f:
        for s in segments:
            f.write(f"{s.id}|{_clean(s.text)}\n")
    review = {s.id: {k: v for k, v in asdict(s).items() if k not in ("id", "text")} for s in segments}
    p.review_json.write_text(json.dumps(review, ensure_ascii=False, indent=1), encoding="utf-8")

def sanitize_id(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", name)

def add_wav(p: Project, seg_id: str, source_audio) -> float:
    x, sr = audio.load_mono(source_audio)
    y = audio.pad(audio.resample(x, sr), audio.SR)
    audio.write_wav(p.segments_dir / f"{seg_id}.wav", y)
    return len(y) / audio.SR

def import_dataset(p: Project, source: Path) -> int:
    source = Path(source)
    segments = load(p); known = {s.id for s in segments}; added = 0
    pairs: list[tuple[str, Path, str]] = []
    meta = source / "metadata.csv"
    if meta.is_file():
        wav_dir = source / "wavs" if (source / "wavs").is_dir() else source
        for row in csv.reader(meta.open(encoding="utf-8"), delimiter="|", quoting=csv.QUOTE_NONE):
            if len(row) < 2: continue
            name = row[0].removesuffix(".wav")
            pairs.append((name, wav_dir / f"{name}.wav", row[2] if len(row) > 2 and row[2] else row[1]))
    else:
        for wav in sorted(source.glob("*.wav")):
            txt = wav.with_suffix(".txt")
            if txt.is_file():
                pairs.append((wav.stem, wav, txt.read_text(encoding="utf-8").strip()))
    for name, wav, text in pairs:
        sid = sanitize_id(name)
        if sid in known or not wav.is_file(): continue
        segments.append(Segment(sid, _clean(text), add_wav(p, sid, wav)))
        known.add(sid); added += 1
    save(p, segments)
    if added: p.mark("audio"); p.mark("slice"); p.save()
    return added

def piper_csv(p: Project, out: Path) -> int:
    rows = [s for s in load(p) if not s.dropped and s.text.strip()]
    with Path(out).open("w", encoding="utf-8", newline="") as f:
        for s in rows:
            f.write(f"{s.id}.wav|{_clean(s.text)}\n")
    return len(rows)
```

`cli.py` add:
```python
from omnivoice import dataset as ds

@app.command("import")
def import_cmd(source: Path, project: Path = typer.Option(Path("."), "--project", "-p")):
    """Импортировать готовый датасет (LJSpeech или пары .wav + .txt)."""
    n = ds.import_dataset(Project.load(project), source)
    typer.secho(f"Добавлено фраз: {n}", fg="green")
```

- [ ] **Step 4: Run** → pass. **Step 5: Commit** — `feat(omnivoice): dataset records, audio helpers and import`

---

### Task 5: Segment planning (pure) and `slice`

**Files:** Create `omnivoice/segments.py`, `omnivoice/slicer.py`; Modify `cli.py` (`slice`); Test `tests/test_segments.py`, `tests/test_slicer.py`

**Interfaces:**
- Produces:
  - `segments.plan_segments(speech: list[tuple[float,float]], energy: Callable[[float,float], float] | None, min_s=1.0, max_s=15.0, merge_gap=0.35) -> list[tuple[float,float]]` — merges neighbouring speech regions closer than `merge_gap` while total ≤ `max_s`; regions shorter than `min_s` are merged into a neighbour or dropped; regions longer than `max_s` are split recursively at the point of minimum `energy(t-0.1,t+0.1)` within the middle 60 % (if `energy` is None, split at the midpoint).
  - `slicer.slice_project(p, isolate: bool = False, progress: Callable[[str,float],None] | None = None) -> int` — for every file in `raw/` not yet sliced (tracked in `raw/.sliced.json` by name+size+mtime): decode with ffmpeg to 22050 mono float (`ffmpeg -v error -i IN -ac 1 -ar 22050 -f f32le -`), optional demucs (`python -m demucs --two-stems=vocals -n htdemucs -o TMP IN`, use `TMP/htdemucs/<stem>/vocals.wav`), silero `get_speech_timestamps(..., sampling_rate=16000, return_seconds=True)` on a 16 kHz copy, `plan_segments`, loudness-normalize each segment to −20 LUFS (pyloudnorm; skip if shorter than 0.4 s for the meter), pad 150 ms, write `segments/<rawstem>_<nnnn>.wav`, append `Segment(id, "", duration)`; marks steps `audio`, `slice`.
  - Raises `RuntimeError("ffmpeg не найден…")` if ffmpeg missing; `RuntimeError("Нужен пакет omnivoice[prep]…")` if silero/pyloudnorm import fails.

- [ ] **Step 1: Failing tests** (`tests/test_segments.py`):

```python
from omnivoice.segments import plan_segments

def test_merges_close_regions_and_drops_tiny():
    out = plan_segments([(0.0, 0.8), (0.9, 2.5), (5.0, 5.2)], None)
    assert out == [(0.0, 2.5)]

def test_keeps_separate_when_gap_large():
    out = plan_segments([(0.0, 2.0), (3.0, 6.0)], None)
    assert out == [(0.0, 2.0), (3.0, 6.0)]

def test_long_speech_is_split_at_quietest_point():
    quiet_at = 22.0
    energy = lambda a, b: 0.0 if a <= quiet_at <= b else 1.0
    out = plan_segments([(0.0, 40.0)], energy)
    assert all(1.0 <= e - s <= 15.0 for s, e in out)
    assert any(abs(e - quiet_at) < 0.2 for s, e in out)
    assert out[0][0] == 0.0 and out[-1][1] == 40.0
```

`tests/test_slicer.py` (no heavy deps: monkeypatch the decoder/VAD):
```python
import numpy as np
from omnivoice import slicer, dataset
from omnivoice.project import Project

def test_slice_writes_segments_and_is_idempotent(tmp_path, monkeypatch):
    p = Project.create(tmp_path / "p", name="p", language="ru")
    (p.raw_dir / "clip.mp4").write_bytes(b"fake")
    sr = 22050
    x = np.concatenate([np.zeros(sr), 0.2 * np.sin(np.arange(3 * sr) / 10), np.zeros(sr)]).astype(np.float32)
    monkeypatch.setattr(slicer, "_decode", lambda path: x)
    monkeypatch.setattr(slicer, "_speech", lambda y: [(1.0, 4.0)])
    monkeypatch.setattr(slicer, "_normalize", lambda y: y)
    assert slicer.slice_project(p) == 1
    assert slicer.slice_project(p) == 0
    segs = dataset.load(p)
    assert [s.id for s in segs] == ["clip_0000"] and abs(segs[0].duration - 3.3) < 0.05
    assert p.steps["slice"]
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Implement** `omnivoice/segments.py`:

```python
from typing import Callable

Span = tuple[float, float]

def _split(span: Span, energy, max_s: float) -> list[Span]:
    s, e = span
    if e - s <= max_s:
        return [span]
    lo, hi = s + 0.2 * (e - s), s + 0.8 * (e - s)
    if energy is None:
        cut = (s + e) / 2
    else:
        steps = [lo + i * (hi - lo) / 200 for i in range(201)]
        cut = min(steps, key=lambda t: energy(t - 0.1, t + 0.1))
    return _split((s, cut), energy, max_s) + _split((cut, e), energy, max_s)

def plan_segments(speech: list[Span], energy: Callable[[float, float], float] | None,
                  min_s: float = 1.0, max_s: float = 15.0, merge_gap: float = 0.35) -> list[Span]:
    merged: list[Span] = []
    for s, e in sorted(speech):
        if merged and s - merged[-1][1] <= merge_gap and e - merged[-1][0] <= max_s:
            merged[-1] = (merged[-1][0], e)
        else:
            merged.append((s, e))
    out: list[Span] = []
    for span in merged:
        out.extend(_split(span, energy, max_s))
    return [(round(s, 3), round(e, 3)) for s, e in out if e - s >= min_s]
```
Note: the first test expects `(0.0,0.8)` + `(0.9,2.5)` merged (gap 0.1) and `(5.0,5.2)` dropped (< 1 s).

`omnivoice/slicer.py`:
```python
from __future__ import annotations
import json, shutil, subprocess, sys, tempfile
from pathlib import Path
import numpy as np
from omnivoice import audio, dataset
from omnivoice.dataset import Segment
from omnivoice.segments import plan_segments

SR = audio.SR

def _decode(path: Path) -> np.ndarray:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg не найден. Установи ffmpeg и добавь в PATH (winget install ffmpeg).")
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).copy()

def _isolate(path: Path) -> Path:
    out = Path(tempfile.mkdtemp(prefix="omnivoice-demucs-"))
    subprocess.run([sys.executable, "-m", "demucs", "--two-stems=vocals", "-n", "htdemucs", "-o", str(out), str(path)], check=True)
    vocals = next(out.rglob("vocals.wav"), None)
    if vocals is None:
        raise RuntimeError("demucs не создал vocals.wav")
    return vocals

def _speech(x: np.ndarray) -> list[tuple[float, float]]:
    try:
        from silero_vad import load_silero_vad, get_speech_timestamps
        import torch
    except ImportError as e:
        raise RuntimeError("Нужен пакет omnivoice[prep] (uv sync --extra prep)") from e
    x16 = audio.resample(x, SR, 16000)
    ts = get_speech_timestamps(torch.from_numpy(x16), load_silero_vad(), sampling_rate=16000, return_seconds=True)
    return [(t["start"], t["end"]) for t in ts]

def _normalize(y: np.ndarray) -> np.ndarray:
    import pyloudnorm as pyln
    if len(y) < 0.4 * SR:
        return y
    loud = pyln.Meter(SR).integrated_loudness(y)
    return pyln.normalize.loudness(y, loud, -20.0) if np.isfinite(loud) else y

def _energy(x: np.ndarray):
    def f(a: float, b: float) -> float:
        seg = x[max(0, int(a * SR)): int(b * SR)]
        return float(np.sqrt(np.mean(seg ** 2))) if len(seg) else 0.0
    return f

def slice_project(p, isolate: bool = False, progress=None) -> int:
    done_file = p.raw_dir / ".sliced.json"
    done = json.loads(done_file.read_text(encoding="utf-8")) if done_file.is_file() else {}
    segments = dataset.load(p); added = 0
    files = [f for f in sorted(p.raw_dir.iterdir()) if f.is_file() and not f.name.startswith(".")]
    for i, f in enumerate(files):
        key = f"{f.stat().st_size}:{int(f.stat().st_mtime)}"
        if done.get(f.name) == key:
            continue
        if progress: progress(f.name, i / max(1, len(files)))
        x = _decode(_isolate(f) if isolate else f)
        stem = dataset.sanitize_id(f.stem)
        for n, (s, e) in enumerate(plan_segments(_speech(x), _energy(x))):
            y = audio.pad(_normalize(x[int(s * SR): int(e * SR)]), SR)
            sid = f"{stem}_{n:04d}"
            audio.write_wav(p.segments_dir / f"{sid}.wav", y)
            segments.append(Segment(sid, "", round(len(y) / SR, 3)))
            added += 1
        done[f.name] = key
    dataset.save(p, segments)
    done_file.write_text(json.dumps(done), encoding="utf-8")
    if added:
        p.mark("audio"); p.mark("slice"); p.save()
    return added
```

`cli.py` add:
```python
from omnivoice import slicer

@app.command("slice")
def slice_cmd(project: Path = typer.Option(Path("."), "--project", "-p"),
              isolate: bool = typer.Option(False, "--isolate", help="Отделить голос от музыки (demucs)")):
    """Нарезать сырое аудио из raw/ на фразы."""
    try:
        n = slicer.slice_project(Project.load(project), isolate=isolate)
    except RuntimeError as e:
        typer.secho(str(e), fg="red"); raise typer.Exit(1)
    typer.secho(f"Новых фраз: {n}", fg="green")
```

- [ ] **Step 4: Run** → pass. **Step 5: Commit** — `feat(omnivoice): plan segments and slice raw audio`

---

### Task 6: `transcribe`

**Files:** Create `omnivoice/transcriber.py`; Modify `cli.py`; Test `tests/test_transcriber.py`

**Interfaces:**
- Consumes: `dataset.load/save`, `textnorm.normalize_text`.
- Produces: `transcriber.transcribe_project(p, model: str | None = None, recognizer=None, progress=None) -> int` — for every segment with empty text and not `edited`: run recognizer, normalize, set `confidence = exp(mean avg_logprob)` (0..1), flags = textnorm flags + `"check"` if confidence < 0.6 or any no_speech_prob > 0.5; never touches `edited` rows; marks `phrases` only after review in UI (not here). `recognizer` is a callable `(wav_path) -> list[tuple[text, avg_logprob, no_speech_prob]]`; default builds faster-whisper (`WhisperModel("large-v3" if cuda else "medium", device="cuda"|"cpu", compute_type="float16"|"int8")`, `transcribe(path, language=p.language, beam_size=5, vad_filter=False)`).

- [ ] **Step 1: Failing tests**

```python
from omnivoice import transcriber, dataset
from omnivoice.dataset import Segment
from omnivoice.project import Project

def fake(results):
    return lambda wav: results[wav.stem]

def test_fills_text_confidence_and_flags(tmp_path):
    p = Project.create(tmp_path / "p", name="p", language="ru")
    dataset.save(p, [Segment("a", "", 2.0), Segment("b", "", 2.0)])
    n = transcriber.transcribe_project(p, recognizer=fake({
        "a": [("Тест 1.", -0.1, 0.01)], "b": [("[шум] хм", -1.5, 0.7)]}))
    s = {x.id: x for x in dataset.load(p)}
    assert n == 2
    assert s["a"].text == "Тест один." and "check" not in s["a"].flags and s["a"].confidence > 0.9
    assert "check" in s["b"].flags and "stage_direction" in s["b"].flags

def test_transcribe_keeps_manual_edits_on_rerun(tmp_path):
    p = Project.create(tmp_path / "p", name="p", language="ru")
    dataset.save(p, [Segment("a", "Моя правка", 2.0, edited=True), Segment("b", "", 2.0)])
    transcriber.transcribe_project(p, recognizer=fake({"b": [("Второй", -0.2, 0.0)]}))
    assert transcriber.transcribe_project(p, recognizer=fake({})) == 0
    s = {x.id: x for x in dataset.load(p)}
    assert s["a"].text == "Моя правка" and s["b"].text == "Второй" and len(s) == 2
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Implement**

```python
from __future__ import annotations
import math
from omnivoice import dataset
from omnivoice.textnorm import normalize_text

def _default_recognizer(language: str, model: str | None):
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise RuntimeError("Нужен пакет omnivoice[prep] (uv sync --extra prep)") from e
    try:
        import ctranslate2
        cuda = ctranslate2.get_cuda_device_count() > 0
    except Exception:
        cuda = False
    wm = WhisperModel(model or ("large-v3" if cuda else "medium"),
                      device="cuda" if cuda else "cpu", compute_type="float16" if cuda else "int8")
    def run(wav):
        segs, _ = wm.transcribe(str(wav), language=language, beam_size=5, vad_filter=False)
        return [(s.text, s.avg_logprob, s.no_speech_prob) for s in segs]
    return run

def transcribe_project(p, model: str | None = None, recognizer=None, progress=None) -> int:
    segments = dataset.load(p)
    todo = [s for s in segments if not s.edited and not s.text.strip() and not s.dropped]
    if not todo:
        return 0
    rec = recognizer or _default_recognizer(p.language, model)
    for i, s in enumerate(todo):
        if progress: progress(s.id, i / len(todo))
        parts = rec(p.segments_dir / f"{s.id}.wav")
        raw = " ".join(t.strip() for t, _, _ in parts)
        text, flags = normalize_text(raw, p.language)
        conf = math.exp(sum(lp for _, lp, _ in parts) / len(parts)) if parts else 0.0
        if conf < 0.6 or any(ns > 0.5 for _, _, ns in parts) or not parts:
            flags.append("check")
        s.text, s.confidence, s.flags = text, round(conf, 3), flags
    dataset.save(p, segments)
    return len(todo)
```

`cli.py`: command `transcribe` (`--project`, `--model`), same error handling pattern as `slice`.

- [ ] **Step 4: Run** → pass. **Step 5: Commit** — `feat(omnivoice): transcribe segments with whisper`

---

### Task 7: `check`

**Files:** Create `omnivoice/checker.py`; Modify `cli.py`; Test `tests/test_checker.py`

**Interfaces:**
- Produces: `checker.Report(total_minutes: float, phrases: int, errors: list[str], warnings: list[str], per_segment: dict[str, list[str]])`; `checker.check_project(p, phonemize=None) -> Report` — ignores dropped; per-segment issues: `too_short` (< 1.0 s incl. padding), `too_long` (> 15.3 s), `clipping` (ratio > 0.001), `empty_text`, `unspeakable` (phonemize returns empty / raises), plus any textnorm flags still present (`check`, `foreign_letters`); warnings: total < 10 min → «Мало данных: X мин (минимум 10, лучше 30+)»; errors: 0 phrases, any `empty_text`. `phonemize` is a callable `(text) -> list[str]`; default tries `piper.phonemize_espeak` from the `piper-tts` package if installed, otherwise phonemization is skipped with a warning «Фонемизатор не установлен — проверка произносимости пропущена». On success with no errors marks `check`.

- [ ] **Step 1: Failing tests**

```python
import numpy as np
from omnivoice import checker, dataset, audio
from omnivoice.dataset import Segment
from omnivoice.project import Project

def wav(p, sid, sec, amp=0.2):
    audio.write_wav(p.segments_dir / f"{sid}.wav", (amp * np.sin(np.arange(int(sec * 22050)) / 5)).astype(np.float32))

def test_report(tmp_path):
    p = Project.create(tmp_path / "p", name="p", language="ru")
    wav(p, "ok", 3); wav(p, "short", 0.5); wav(p, "loud", 2, amp=1.5); wav(p, "drop", 3)
    dataset.save(p, [Segment("ok", "Хорошо", 3), Segment("short", "Да", 0.5), Segment("loud", "", 2),
                     Segment("drop", "x", 3, dropped=True)])
    r = checker.check_project(p, phonemize=lambda t: list(t))
    assert r.phrases == 3
    assert "too_short" in r.per_segment["short"]
    assert {"clipping", "empty_text"} <= set(r.per_segment["loud"])
    assert any("Мало данных" in w for w in r.warnings) and r.errors
    assert not p.steps["check"]

def test_unspeakable(tmp_path):
    p = Project.create(tmp_path / "p", name="p", language="ru")
    wav(p, "a", 3); dataset.save(p, [Segment("a", "☃", 3)])
    r = checker.check_project(p, phonemize=lambda t: [])
    assert "unspeakable" in r.per_segment["a"]
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Implement**

```python
from __future__ import annotations
from dataclasses import dataclass, field
from omnivoice import audio, dataset

@dataclass
class Report:
    total_minutes: float = 0.0
    phrases: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    per_segment: dict[str, list[str]] = field(default_factory=dict)

def _default_phonemizer(p):
    try:
        from piper import phonemize_espeak  # piper-tts
    except ImportError:
        return None
    return lambda text: [ph for sent in phonemize_espeak(text, p.espeak_voice) for ph in sent]

def check_project(p, phonemize=None) -> Report:
    r = Report()
    ph = phonemize or _default_phonemizer(p)
    if ph is None:
        r.warnings.append("Фонемизатор не установлен — проверка произносимости пропущена")
    segs = [s for s in dataset.load(p) if not s.dropped]
    r.phrases = len(segs)
    for s in segs:
        issues = [f for f in s.flags if f in ("check", "foreign_letters")]
        path = p.segments_dir / f"{s.id}.wav"
        x, _ = audio.load_mono(path)
        dur = len(x) / audio.SR
        r.total_minutes += dur / 60
        if dur < 1.0: issues.append("too_short")
        if dur > 15.3: issues.append("too_long")
        if audio.clipping_ratio(x) > 0.001: issues.append("clipping")
        if not s.text.strip(): issues.append("empty_text")
        elif ph is not None:
            try:
                if not ph(s.text): issues.append("unspeakable")
            except Exception:
                issues.append("unspeakable")
        if issues: r.per_segment[s.id] = issues
    r.total_minutes = round(r.total_minutes, 1)
    if r.phrases == 0: r.errors.append("Нет ни одной фразы")
    if any("empty_text" in v for v in r.per_segment.values()): r.errors.append("Есть фразы без текста")
    if r.total_minutes < 10: r.warnings.append(f"Мало данных: {r.total_minutes} мин (минимум 10, лучше 30+)")
    if not r.errors:
        p.mark("check"); p.save()
    return r
```

`cli.py`: `check` command prints totals, warnings (yellow), errors (red), and per-segment issues table; exit code 1 when errors.

- [ ] **Step 4: Run** → pass. **Step 5: Commit** — `feat(omnivoice): dataset quality check`

---

### Task 8: ONNX metadata, tokens, espeak data, portrait, `pack`

**Files:** Create `omnivoice/onnxmeta.py`, `omnivoice/espeak.py`, `omnivoice/portrait.py`, `omnivoice/pack.py`; Modify `cli.py`; Test `tests/test_onnxmeta.py`, `tests/test_pack.py`, `tests/test_portrait.py`

**Interfaces:**
- Consumes: `modrules`, `languages.PRESETS`, `paths.cache_dir`, `Project`.
- Produces:
  - `onnxmeta.piper_metadata(config: dict, iso_name: str, version: str) -> dict[str,str]` (exact keys from Global Constraints; `voice` = `config.get("lang_code") or config["espeak"]["voice"]`, `pt-PT`→`pt`; `sample_rate` 22500→22050; `n_speakers` = `config.get("num_speakers", 1)`).
  - `onnxmeta.write_metadata(onnx_in: Path, onnx_out: Path, meta: dict[str,str]) -> None` (clears existing props, writes new; uses `onnx.load`/`onnx.save`; keeps external data inline).
  - `onnxmeta.tokens_from_config(config: dict) -> str`.
  - `espeak.ensure_espeak_data() -> Path` (downloads tarball once to `cache_dir()/espeak-ng-data`, extracts; checks `phontab`).
  - `portrait.make_portrait(image_bytes: bytes) -> bytes` (RGBA, center-crop square, resize 32×32 NEAREST, quantize to ≤ 64 colours if > 8192 bytes, then 16×16 fallback; result passes `modrules.portrait_problem`).
  - `pack.pack_voice(onnx_path: Path, config_path: Path | None, out_dir: Path, display: dict, iso_name: str, voice_override: str | None = None, portrait_bytes: bytes | None = None, espeak_dir: Path | None = None) -> Path` — creates `out_dir/<name>/` with `<name>.onnx` (metadata written), `<name>.onnx.json` (copied if given), `tokens.txt`, `espeak-ng-data/` (copied from `espeak_dir or ensure_espeak_data()`), `voice.json` (fields truncated to limits, `license` included), `portrait.png` (optional); runs `modrules.validate_voice_folder`; raises `PackError(problems)` if any. Without `config_path`: requires `voice_override` and an existing `tokens.txt` next to the onnx, else `PackError(["Нет .onnx.json рядом с моделью — укажи язык через --voice и положи tokens.txt"])`.
  - `pack.pack_project(p, onnx_path=None, portrait=None) -> Path` — uses `p.export_dir/model.onnx` + `p.train_dir/config.json` by default, marks `pack`.
- CLI: `omnivoice pack [--project P] [--onnx X --config Y --voice ru --name N] [--portrait img]`.

- [ ] **Step 1: Failing tests**

`tests/test_onnxmeta.py`:
```python
from omnivoice import onnxmeta
from tests.helpers import make_onnx
from omnivoice.modrules import read_onnx_metadata

CFG = {"audio": {"sample_rate": 22050}, "espeak": {"voice": "ru"}, "num_speakers": 1,
       "phoneme_id_map": {"_": [0], "^": [1], " ": [3], "\n": [9], "a": 5}}

def test_piper_metadata_exact_keys():
    m = onnxmeta.piper_metadata(CFG, "Russian", "0.1.0")
    assert m == {"model_type": "vits", "comment": "piper", "language": "Russian", "voice": "ru", "version": "1",
                 "has_espeak": "1", "n_speakers": "1", "sample_rate": "22050", "omnivoice_version": "0.1.0"}

def test_tokens_from_config_edge_cases():
    assert onnxmeta.tokens_from_config(CFG) == "_ 0\n^ 1\n  3\na 5\n"
    pt = dict(CFG, espeak={"voice": "pt-PT"}, audio={"sample_rate": 22500})
    m = onnxmeta.piper_metadata(pt, "Portuguese", "0.1.0")
    assert m["voice"] == "pt" and m["sample_rate"] == "22050"

def test_write_metadata_replaces_existing(tmp_path):
    src = make_onnx(tmp_path / "a.onnx", {"comment": "old", "junk": "1"})
    onnxmeta.write_metadata(src, tmp_path / "b.onnx", {"n_speakers": "1", "comment": "piper", "voice": "ru"})
    assert read_onnx_metadata(tmp_path / "b.onnx") == {"n_speakers": "1", "comment": "piper", "voice": "ru"}
```

`tests/test_portrait.py`:
```python
import io
from PIL import Image
from omnivoice.portrait import make_portrait
from omnivoice.modrules import portrait_problem

def test_any_image_becomes_valid_portrait():
    buf = io.BytesIO(); Image.effect_noise((300, 200), 80).convert("RGB").save(buf, "PNG")
    out = make_portrait(buf.getvalue())
    assert portrait_problem(out) is None
```

`tests/test_pack.py`:
```python
import json, pytest
from pathlib import Path
from omnivoice import pack
from omnivoice.modrules import read_onnx_metadata, validate_voice_folder
from tests.helpers import make_onnx

def espeak(tmp_path):
    d = tmp_path / "espeak-ng-data"; d.mkdir(); (d / "phontab").write_bytes(b"x"); return d

CFG = {"audio": {"sample_rate": 22050}, "espeak": {"voice": "ru"}, "num_speakers": 1, "phoneme_id_map": {"_": [0]}}

def test_pack_own_export(tmp_path):
    onnx = make_onnx(tmp_path / "model.onnx", {})
    cfg = tmp_path / "config.json"; cfg.write_text(json.dumps(CFG), encoding="utf-8")
    out = pack.pack_voice(onnx, cfg, tmp_path / "out", {"name": "GLaDOS" * 10, "description": "Злой ИИ", "license": "CC0"},
                          "Russian", espeak_dir=espeak(tmp_path))
    assert out.is_dir()
    assert validate_voice_folder(out) == []
    assert read_onnx_metadata(next(out.glob("*.onnx")))["voice"] == "ru"
    vj = json.loads((out / "voice.json").read_text(encoding="utf-8"))
    assert len(vj["name"]) == 32 and vj["license"] == "CC0"

def test_pack_foreign_model_without_json_needs_voice(tmp_path):
    onnx = make_onnx(tmp_path / "m.onnx", {"n_speakers": "1", "comment": "piper"})
    with pytest.raises(pack.PackError, match="--voice"):
        pack.pack_voice(onnx, None, tmp_path / "out", {"name": "x"}, "Russian", espeak_dir=espeak(tmp_path))
    (tmp_path / "tokens.txt").write_text("_ 0\n", encoding="utf-8")
    out = pack.pack_voice(onnx, None, tmp_path / "out", {"name": "x"}, "Russian", voice_override="ru",
                          espeak_dir=espeak(tmp_path))
    assert read_onnx_metadata(next(out.glob("*.onnx")))["voice"] == "ru"
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Implement**

`omnivoice/onnxmeta.py`:
```python
from __future__ import annotations
from pathlib import Path
import onnx

def piper_metadata(config: dict, iso_name: str, version: str) -> dict[str, str]:
    voice = config.get("lang_code") or config["espeak"]["voice"]
    if voice == "pt-PT":
        voice = "pt"
    sr = int(config.get("audio", {}).get("sample_rate", 22050))
    if sr == 22500:
        sr = 22050
    return {"model_type": "vits", "comment": "piper", "language": iso_name, "voice": voice, "version": "1",
            "has_espeak": "1", "n_speakers": str(config.get("num_speakers", 1)), "sample_rate": str(sr),
            "omnivoice_version": version}

def tokens_from_config(config: dict) -> str:
    lines = []
    for s, i in config["phoneme_id_map"].items():
        if s == "\n":
            continue
        if isinstance(i, list):
            i = i[0]
        lines.append(f"{s} {i}\n")
    return "".join(lines)

def write_metadata(onnx_in: Path, onnx_out: Path, meta: dict[str, str]) -> None:
    model = onnx.load(str(onnx_in))
    del model.metadata_props[:]
    for k, v in meta.items():
        p = model.metadata_props.add(); p.key = k; p.value = str(v)
    onnx.save(model, str(onnx_out))
```

`omnivoice/espeak.py`:
```python
import tarfile, urllib.request
from pathlib import Path
from omnivoice.paths import cache_dir

URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/espeak-ng-data.tar.bz2"

def ensure_espeak_data() -> Path:
    target = cache_dir() / "espeak-ng-data"
    if (target / "phontab").is_file():
        return target
    archive = cache_dir() / "espeak-ng-data.tar.bz2"
    urllib.request.urlretrieve(URL, archive)
    with tarfile.open(archive, "r:bz2") as t:
        t.extractall(cache_dir(), filter="data")
    archive.unlink(missing_ok=True)
    if not (target / "phontab").is_file():
        raise RuntimeError("Архив espeak-ng-data не содержит phontab")
    return target
```

`omnivoice/portrait.py`:
```python
import io
from PIL import Image
from omnivoice.modrules import MAX_PORTRAIT_BYTES

def _png(img: Image.Image) -> bytes:
    buf = io.BytesIO(); img.save(buf, "PNG", optimize=True); return buf.getvalue()

def make_portrait(image_bytes: bytes) -> bytes:
    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    side = min(img.size)
    left, top = (img.width - side) // 2, (img.height - side) // 2
    img = img.crop((left, top, left + side, top + side))
    for size in (32, 16):
        small = img.resize((size, size), Image.NEAREST)
        for candidate in (small, small.quantize(64).convert("RGBA")):
            data = _png(candidate)
            if len(data) <= MAX_PORTRAIT_BYTES:
                return data
    raise ValueError("Не удалось ужать портрет до 8 КБ")
```

`omnivoice/pack.py`:
```python
from __future__ import annotations
import json, re, shutil
from pathlib import Path
from omnivoice import __version__, modrules, onnxmeta
from omnivoice.espeak import ensure_espeak_data
from omnivoice.portrait import make_portrait

class PackError(Exception):
    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems)); self.problems = problems

def folder_name(name: str) -> str:
    return re.sub(r"[^a-z0-9_-]", "_", name.lower()).strip("_") or "voice"

def _voice_json(display: dict, language: str) -> dict:
    out = {"language": language[: modrules.LIMITS["language"]]}
    for key in ("name", "description", "gender", "sample"):
        if display.get(key):
            out[key] = str(display[key])[: modrules.LIMITS[key]]
    if display.get("license"):
        out["license"] = str(display["license"])
    return out

def pack_voice(onnx_path: Path, config_path: Path | None, out_dir: Path, display: dict, iso_name: str,
               voice_override: str | None = None, portrait_bytes: bytes | None = None,
               espeak_dir: Path | None = None) -> Path:
    name = folder_name(display.get("name") or onnx_path.stem)
    if config_path is None:
        tokens_src = onnx_path.with_name("tokens.txt")
        if not voice_override or not tokens_src.is_file():
            raise PackError(["Нет .onnx.json рядом с моделью — укажи язык через --voice и положи tokens.txt"])
        existing = modrules.read_onnx_metadata(onnx_path)
        meta = existing | {"comment": existing.get("comment", "piper"), "voice": voice_override,
                           "has_espeak": "1", "n_speakers": existing.get("n_speakers", "1"),
                           "omnivoice_version": __version__}
        tokens = tokens_src.read_text(encoding="utf-8"); voice = voice_override; config = None
    else:
        config = json.loads(Path(config_path).read_text(encoding="utf-8"))
        meta = onnxmeta.piper_metadata(config, iso_name, __version__)
        if voice_override:
            meta["voice"] = voice_override
        tokens = onnxmeta.tokens_from_config(config); voice = meta["voice"]
    folder = Path(out_dir) / name
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    onnxmeta.write_metadata(onnx_path, folder / f"{name}.onnx", meta)
    if config is not None:
        (folder / f"{name}.onnx.json").write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    (folder / "tokens.txt").write_text(tokens, encoding="utf-8")
    shutil.copytree(espeak_dir or ensure_espeak_data(), folder / "espeak-ng-data")
    (folder / "voice.json").write_text(json.dumps(_voice_json(display, voice.split("-")[0]), ensure_ascii=False, indent=2),
                                       encoding="utf-8")
    if portrait_bytes:
        (folder / "portrait.png").write_bytes(make_portrait(portrait_bytes))
    problems = modrules.validate_voice_folder(folder)
    if problems:
        raise PackError(problems)
    return folder

def pack_project(p, onnx_path: Path | None = None, portrait: Path | None = None) -> Path:
    from omnivoice import languages
    folder = pack_voice(onnx_path or p.export_dir / "model.onnx", p.train_dir / "config.json", p.export_dir,
                        p.display, languages.PRESETS[p.language].iso_name,
                        portrait_bytes=portrait.read_bytes() if portrait else None)
    p.mark("pack"); p.save()
    return folder
```
Note the test `test_pack_own_export` expects `name` truncated to 32 in voice.json; folder name from the full name is fine.

`cli.py`: `pack` command — with `--onnx` uses `pack_voice` (needs `--name`, optional `--config`, `--voice`, `--language` for iso name, default `Russian`); otherwise `pack_project`; prints folder; on `PackError` prints each problem in red, exit 1.

- [ ] **Step 4: Run** → pass. **Step 5: Commit** — `feat(omnivoice): write piper metadata and pack mod voice folders`

---

### Task 9: `verify` and `install`

**Files:** Create `omnivoice/verify.py`, `omnivoice/_verify_worker.py`, `omnivoice/install.py`; Modify `cli.py`; Test `tests/test_verify.py`, `tests/test_install.py`

**Interfaces:**
- Produces:
  - `verify.VerifyResult(ok: bool, message: str, sample: Path | None)`.
  - `verify.verify_voice(folder: Path, text: str | None = None, timeout: int = 120, python: str = sys.executable) -> VerifyResult` — runs `python -m omnivoice._verify_worker <folder> <text> <out.wav>` in a subprocess; worker builds `sherpa_onnx.OfflineTtsConfig` exactly as facts §6 (vits model, tokens, data_dir=espeak-ng-data, num_threads=2, provider cpu), `tts.generate(text, 0, 1.0)` positional, writes `sample.wav` with soundfile; text default = voice.json `sample` or language test phrase. Non-zero exit / native crash → `ok=False` with exit code + last 15 lines of stderr; first runs `modrules.validate_voice_folder` and fails fast with those problems.
  - `install.default_targets() -> list[Path]` — existing among: `%APPDATA%/.minecraft/config/omnichat/models`, repo `run/config/omnichat/models` (if cwd inside OmniChat repo), Prism/MultiMC instance dirs `%APPDATA%/PrismLauncher/instances/*/minecraft/config/omnichat/models`.
  - `install.install_voice(folder: Path, target_models_dir: Path, overwrite: bool = False) -> Path` — copies folder to `target/<folder.name>`; refuses to overwrite unless `overwrite`; if overwriting, keeps old copy as `<name>.old` until copy succeeds.

- [ ] **Step 1: Failing tests**

`tests/test_verify.py`:
```python
import shutil, sys, pytest
from pathlib import Path
from omnivoice import verify

DENIS = Path(__file__).resolve().parents[3] / "run/config/omnichat/models/denis"

@pytest.mark.skipif(not (DENIS / "ru_RU-denis-medium.onnx").is_file(), reason="local denis model not present")
def test_verify_real_model(tmp_path):
    folder = tmp_path / "denis"; shutil.copytree(DENIS, folder)
    r = verify.verify_voice(folder, "Проверка.")
    assert r.ok, r.message
    assert r.sample and r.sample.stat().st_size > 1000

def test_crash_is_reported_not_raised(tmp_path, monkeypatch):
    (tmp_path / "v").mkdir()
    monkeypatch.setattr(verify.modrules, "validate_voice_folder", lambda f: [])
    crash = tmp_path / "crash.py"; crash.write_text("import sys; sys.stderr.write('boom\\n'); sys.exit(-1073740791)")
    monkeypatch.setattr(verify, "_worker_cmd", lambda folder, text, out: [sys.executable, str(crash)])
    r = verify.verify_voice(tmp_path / "v", "x")
    assert not r.ok and "boom" in r.message

def test_invalid_folder_fails_fast(tmp_path):
    (tmp_path / "v").mkdir()
    r = verify.verify_voice(tmp_path / "v", "x")
    assert not r.ok and "tokens.txt" in r.message
```

`tests/test_install.py`:
```python
import pytest
from omnivoice import install

def test_install_and_overwrite(tmp_path):
    src = tmp_path / "glados"; src.mkdir(); (src / "a.txt").write_text("1")
    target = tmp_path / "models"; target.mkdir()
    dest = install.install_voice(src, target)
    assert (dest / "a.txt").read_text() == "1"
    with pytest.raises(FileExistsError):
        install.install_voice(src, target)
    (src / "a.txt").write_text("2")
    install.install_voice(src, target, overwrite=True)
    assert (dest / "a.txt").read_text() == "2" and not (target / "glados.old").exists()
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Implement**

`omnivoice/_verify_worker.py`:
```python
import sys
from pathlib import Path

def main(folder: str, text: str, out: str) -> None:
    import sherpa_onnx, soundfile as sf
    f = Path(folder)
    model = next(f.glob("*.onnx"))
    cfg = sherpa_onnx.OfflineTtsConfig(
        model=sherpa_onnx.OfflineTtsModelConfig(
            vits=sherpa_onnx.OfflineTtsVitsModelConfig(model=str(model), lexicon="",
                 data_dir=str(f / "espeak-ng-data"), tokens=str(f / "tokens.txt")),
            provider="cpu", debug=False, num_threads=2),
        rule_fsts="", max_num_sentences=1)
    if not cfg.validate():
        sys.stderr.write("sherpa-onnx config validation failed\n"); sys.exit(2)
    tts = sherpa_onnx.OfflineTts(cfg)
    audio = tts.generate(text, 0, 1.0)
    if len(audio.samples) == 0:
        sys.stderr.write("sherpa-onnx produced no audio\n"); sys.exit(3)
    sf.write(out, audio.samples, samplerate=audio.sample_rate, subtype="PCM_16")

if __name__ == "__main__":
    main(*sys.argv[1:4])
```

`omnivoice/verify.py`:
```python
from __future__ import annotations
import json, subprocess, sys
from dataclasses import dataclass
from pathlib import Path
from omnivoice import modrules, languages

@dataclass
class VerifyResult:
    ok: bool
    message: str
    sample: Path | None = None

def _worker_cmd(folder: Path, text: str, out: Path) -> list[str]:
    return [sys.executable, "-m", "omnivoice._verify_worker", str(folder), text, str(out)]

def _default_text(folder: Path) -> str:
    vj = folder / "voice.json"
    data = json.loads(vj.read_text(encoding="utf-8")) if vj.is_file() else {}
    lang = languages.PRESETS.get(data.get("language", "ru"), languages.PRESETS["ru"])
    return data.get("sample") or lang.test_phrase

def verify_voice(folder: Path, text: str | None = None, timeout: int = 120) -> VerifyResult:
    folder = Path(folder)
    problems = modrules.validate_voice_folder(folder)
    if problems:
        return VerifyResult(False, "Папка не прошла проверку мода: " + "; ".join(problems))
    out = folder / "sample.wav"
    try:
        r = subprocess.run(_worker_cmd(folder, text or _default_text(folder), out),
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return VerifyResult(False, f"sherpa-onnx не ответил за {timeout} с")
    if r.returncode != 0 or not out.is_file():
        tail = "\n".join(r.stderr.strip().splitlines()[-15:])
        return VerifyResult(False, f"Синтез упал (код {r.returncode}). Такая модель уронила бы игру.\n{tail}")
    return VerifyResult(True, "Модель загрузилась и озвучила фразу", out)
```

`omnivoice/install.py`:
```python
from __future__ import annotations
import os, shutil
from pathlib import Path

def default_targets() -> list[Path]:
    cands: list[Path] = []
    appdata = os.environ.get("APPDATA")
    if appdata:
        cands.append(Path(appdata) / ".minecraft/config/omnichat/models")
        cands += sorted(Path(appdata).glob("PrismLauncher/instances/*/minecraft/config/omnichat/models"))
    for parent in [Path.cwd(), *Path.cwd().parents]:
        if (parent / "run/config/omnichat/models").is_dir():
            cands.append(parent / "run/config/omnichat/models"); break
    return [c for c in cands if c.is_dir()]

def install_voice(folder: Path, target_models_dir: Path, overwrite: bool = False) -> Path:
    dest = Path(target_models_dir) / Path(folder).name
    if dest.exists() and not overwrite:
        raise FileExistsError(f"{dest} уже существует (используй --overwrite)")
    old = dest.with_name(dest.name + ".old")
    if dest.exists():
        if old.exists(): shutil.rmtree(old)
        dest.rename(old)
    try:
        shutil.copytree(folder, dest)
    except Exception:
        if old.exists(): old.rename(dest)
        raise
    if old.exists(): shutil.rmtree(old)
    return dest
```

`cli.py`: `verify FOLDER [--text]` (green ok + sample path, red message + exit 1) and `install FOLDER [--target DIR] [--overwrite]` (no `--target` → list `default_targets()`, pick the only one or ask with `typer.prompt` index).

- [ ] **Step 4: Run** → pass (denis test runs locally if the model exists). **Step 5: Commit** — `feat(omnivoice): verify voices in a sandbox process and install them`

---

### Task 10: Base checkpoints and Docker training/export

**Files:** Create `omnivoice/checkpoints.py`, `omnivoice/train.py`, `tools/omnivoice/docker/Dockerfile`; Modify `cli.py` (`train`, `export`); Test `tests/test_train.py`

**Interfaces:**
- Consumes: `Project`, `dataset.piper_csv`, `languages.BASE_CHECKPOINTS`, `paths.cache_dir`.
- Produces:
  - `checkpoints.url(path: str) -> str` (`https://huggingface.co/datasets/rhasspy/piper-checkpoints/resolve/main/` + path with `=` → `%3D`); `checkpoints.ensure(path: str, progress=None) -> Path` (cache `cache_dir()/checkpoints/<path>`, download with `.part` then rename; resumable via HTTP Range if `.part` exists).
  - `train.Env(docker: bool, gpu: bool, gpu_name: str | None, vram_mib: int | None)`; `train.detect_env(run=subprocess.run) -> Env` (`docker info` exit code; `docker run --rm --gpus all <image or nvidia/cuda:12.6.0-base-ubuntu22.04> nvidia-smi --query-gpu=name,memory.total --format=csv,noheader`; falls back to host `nvidia-smi` for VRAM).
  - `train.batch_size_for(vram_mib: int | None) -> int` — `None`→16, `<8000`→8, `<12000`→16, `<20000`→24, else 32.
  - `train.IMAGE = "omnivoice-train:0.1"`; `train.build_image(run=subprocess.run)` (`docker build -t IMAGE tools/omnivoice/docker`).
  - `train.fit_command(p, ckpt_in_container: str, batch: int, max_epochs: int, resume: bool) -> list[str]` — the `docker run --rm --gpus all --shm-size=8g -v <project>:/work -v <cache>/checkpoints:/ckpt IMAGE python3 -m piper.train fit ...` list with args exactly per facts §1: `--data.voice_name <name> --data.csv_path /work/train/train.csv --data.audio_dir /work/segments/ --model.sample_rate 22050 --data.espeak_voice <espeak> --data.cache_dir /work/train/cache/ --data.config_path /work/train/config.json --data.batch_size <b> --trainer.max_epochs <n> --trainer.default_root_dir /work/train/ --ckpt_path <ckpt>`; when `resume` and `train/lightning_logs/**/checkpoints/last.ckpt` exists, `--ckpt_path` points at that last.ckpt (container path) instead of the base.
  - `train.export_command(p, ckpt_container_path: str) -> list[str]` — `docker run --rm -v <project>:/work IMAGE python3 -m piper.train.export_onnx --checkpoint <ckpt> --output-file /work/export/model.onnx`.
  - `train.train_project(p, max_epochs=3000, resume=True, run=subprocess.run, env=None, on_line=None) -> int` — checks env (no docker → `TrainError("Docker не найден… Используй Colab: omnivoice train --colab")`, no gpu → same Colab hint), writes `train/train.csv` via `dataset.piper_csv` (error if 0 rows), ensures base checkpoint, builds image if `docker image inspect IMAGE` fails, streams the fit command output lines to `on_line`; marks `train` on exit 0.
  - `train.export_project(p, ckpt: str | None = None, run=...) -> Path` — default ckpt = newest `last.ckpt`; returns `p.export_dir/model.onnx`.
- Dockerfile:

```dockerfile
FROM pytorch/pytorch:2.14.1-cuda12.6-cudnn9-devel
RUN apt-get update && apt-get install -y --no-install-recommends build-essential cmake ninja-build git \
    && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 --branch v1.8.0 https://github.com/OHF-voice/piper1-gpl.git /opt/piper1-gpl
WORKDIR /opt/piper1-gpl
RUN python3 -m pip install --no-cache-dir -e '.[train]' && ./build_monotonic_align.sh && python3 setup.py build_ext --inplace
WORKDIR /work
```

- [ ] **Step 1: Failing tests** (`tests/test_train.py`, no Docker needed — `run` is injected):

```python
import subprocess, pytest
from pathlib import Path
from omnivoice import train, checkpoints, dataset
from omnivoice.dataset import Segment
from omnivoice.project import Project

class Fake:
    def __init__(self, codes): self.codes, self.calls = codes, []
    def __call__(self, cmd, **kw):
        self.calls.append(cmd)
        key = next((k for k in self.codes if k in " ".join(cmd)), None)
        code, out = self.codes.get(key, (0, ""))
        return subprocess.CompletedProcess(cmd, code, stdout=out, stderr="")

def test_checkpoint_url_encodes_equals():
    assert checkpoints.url("ru/ru_RU/irina/medium/epoch=4139-step=929464.ckpt").endswith(
        "ru/ru_RU/irina/medium/epoch%3D4139-step%3D929464.ckpt")

def test_batch_size():
    assert [train.batch_size_for(v) for v in (None, 6000, 12282, 24000)] == [16, 8, 24, 32]

def test_no_gpu_suggests_colab(tmp_path):
    p = Project.create(tmp_path / "p", name="p", language="ru")
    env = train.Env(docker=True, gpu=False, gpu_name=None, vram_mib=None)
    with pytest.raises(train.TrainError, match="Colab"):
        train.train_project(p, env=env, run=Fake({}))

def test_fit_command_args(tmp_path):
    p = Project.create(tmp_path / "glados", name="glados", language="ru")
    cmd = train.fit_command(p, "/ckpt/base.ckpt", batch=24, max_epochs=3000, resume=False)
    joined = " ".join(cmd)
    for part in ["--gpus all", "python3 -m piper.train fit", "--data.voice_name glados", "--data.espeak_voice ru",
                 "--data.csv_path /work/train/train.csv", "--data.audio_dir /work/segments/",
                 "--model.sample_rate 22050", "--data.batch_size 24", "--trainer.max_epochs 3000",
                 "--ckpt_path /ckpt/base.ckpt"]:
        assert part in joined, part

def test_resume_uses_last_ckpt(tmp_path):
    p = Project.create(tmp_path / "g", name="g", language="ru")
    last = p.train_dir / "lightning_logs/version_0/checkpoints/last.ckpt"; last.parent.mkdir(parents=True); last.write_bytes(b"x")
    cmd = train.fit_command(p, "/ckpt/base.ckpt", batch=16, max_epochs=10, resume=True)
    assert "/work/train/lightning_logs/version_0/checkpoints/last.ckpt" in cmd

def test_empty_dataset_is_an_error(tmp_path):
    p = Project.create(tmp_path / "p", name="p", language="ru")
    env = train.Env(docker=True, gpu=True, gpu_name="RTX", vram_mib=12000)
    with pytest.raises(train.TrainError, match="фраз"):
        train.train_project(p, env=env, run=Fake({}))
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Implement**

`omnivoice/checkpoints.py`:
```python
import urllib.request
from pathlib import Path
from omnivoice.paths import cache_dir

BASE = "https://huggingface.co/datasets/rhasspy/piper-checkpoints/resolve/main/"

def url(path: str) -> str:
    return BASE + path.replace("=", "%3D")

def ensure(path: str, progress=None) -> Path:
    target = cache_dir() / "checkpoints" / path
    if target.is_file():
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_name(target.name + ".part")
    done = part.stat().st_size if part.exists() else 0
    req = urllib.request.Request(url(path), headers={"Range": f"bytes={done}-"} if done else {})
    with urllib.request.urlopen(req) as r, part.open("ab" if done else "wb") as f:
        total = done + int(r.headers.get("Content-Length", 0))
        while chunk := r.read(1 << 20):
            f.write(chunk); done += len(chunk)
            if progress: progress(done, total)
    part.rename(target)
    return target
```

`omnivoice/train.py`:
```python
from __future__ import annotations
import subprocess
from dataclasses import dataclass
from pathlib import Path
from omnivoice import checkpoints, dataset
from omnivoice.paths import cache_dir

IMAGE = "omnivoice-train:0.1"
DOCKER_DIR = Path(__file__).resolve().parents[1] / "docker"

class TrainError(Exception):
    pass

@dataclass
class Env:
    docker: bool
    gpu: bool
    gpu_name: str | None
    vram_mib: int | None

def detect_env(run=subprocess.run) -> Env:
    try:
        docker = run(["docker", "info"], capture_output=True, text=True).returncode == 0
    except FileNotFoundError:
        docker = False
    name = vram = None
    try:
        r = run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            n, v = r.stdout.strip().splitlines()[0].rsplit(",", 1)
            name, vram = n.strip(), int(float(v))
    except FileNotFoundError:
        pass
    gpu = False
    if docker and name:
        gpu = run(["docker", "run", "--rm", "--gpus", "all", "nvidia/cuda:12.6.0-base-ubuntu22.04", "nvidia-smi"],
                  capture_output=True, text=True).returncode == 0
    return Env(docker, gpu, name, vram)

def batch_size_for(vram_mib: int | None) -> int:
    if vram_mib is None: return 16
    if vram_mib < 8000: return 8
    if vram_mib < 12000: return 16
    if vram_mib < 20000: return 24
    return 32

def build_image(run=subprocess.run) -> None:
    if run(["docker", "build", "-t", IMAGE, str(DOCKER_DIR)]).returncode != 0:
        raise TrainError("Сборка Docker-образа не удалась (см. вывод выше)")

def _container(p, host: Path) -> str:
    return "/work/" + host.resolve().relative_to(p.root.resolve()).as_posix()

def last_checkpoint(p) -> Path | None:
    found = sorted(p.train_dir.glob("lightning_logs/*/checkpoints/last.ckpt"), key=lambda f: f.stat().st_mtime)
    return found[-1] if found else None

def fit_args(p, ckpt: str, batch: int, max_epochs: int, root: str) -> list[str]:
    return ["python3", "-m", "piper.train", "fit",
            "--data.voice_name", p.name,
            "--data.csv_path", f"{root}/train/train.csv",
            "--data.audio_dir", f"{root}/segments/",
            "--model.sample_rate", str(p.sample_rate),
            "--data.espeak_voice", p.espeak_voice,
            "--data.cache_dir", f"{root}/train/cache/",
            "--data.config_path", f"{root}/train/config.json",
            "--data.batch_size", str(batch),
            "--trainer.max_epochs", str(max_epochs),
            "--trainer.default_root_dir", f"{root}/train/",
            "--ckpt_path", ckpt]

def fit_command(p, ckpt_in_container: str, batch: int, max_epochs: int, resume: bool) -> list[str]:
    last = last_checkpoint(p) if resume else None
    ckpt = _container(p, last) if last else ckpt_in_container
    return ["docker", "run", "--rm", "--gpus", "all", "--shm-size=8g",
            "-v", f"{p.root.resolve()}:/work", "-v", f"{cache_dir() / 'checkpoints'}:/ckpt",
            IMAGE, *fit_args(p, ckpt, batch, max_epochs, "/work")]

def export_command(p, ckpt_container_path: str) -> list[str]:
    return ["docker", "run", "--rm", "-v", f"{p.root.resolve()}:/work", IMAGE,
            "python3", "-m", "piper.train.export_onnx", "--checkpoint", ckpt_container_path,
            "--output-file", "/work/export/model.onnx"]

def _stream(cmd: list[str], on_line) -> int:
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            encoding="utf-8", errors="replace")
    for line in proc.stdout:
        if on_line: on_line(line.rstrip())
    return proc.wait()

def _ensure_image(run) -> None:
    if run(["docker", "image", "inspect", IMAGE], capture_output=True).returncode != 0:
        build_image(run)

def train_project(p, max_epochs: int = 3000, resume: bool = True, run=subprocess.run, env: Env | None = None,
                  on_line=None, batch: int | None = None) -> int:
    env = env or detect_env(run)
    if not env.docker:
        raise TrainError("Docker не найден. Установи Docker Desktop или используй Colab: omnivoice train --colab")
    if not env.gpu:
        raise TrainError("Docker не видит видеокарту NVIDIA. Используй Colab: omnivoice train --colab")
    if dataset.piper_csv(p, p.train_dir / "train.csv") == 0:
        raise TrainError("Нет ни одной фразы с текстом для обучения")
    ckpt = checkpoints.ensure(p.base_checkpoint)
    _ensure_image(run)
    cmd = fit_command(p, "/ckpt/" + ckpt.relative_to(cache_dir() / "checkpoints").as_posix(),
                      batch or batch_size_for(env.vram_mib), max_epochs, resume)
    code = _stream(cmd, on_line) if run is subprocess.run else run(cmd).returncode
    if code == 0:
        p.mark("train"); p.save()
    return code

def export_project(p, ckpt: Path | None = None, run=subprocess.run) -> Path:
    ckpt = ckpt or last_checkpoint(p)
    if ckpt is None:
        raise TrainError("Нет чекпойнтов — сначала обучи модель")
    if run(export_command(p, _container(p, ckpt))).returncode != 0:
        raise TrainError("Экспорт в ONNX не удался")
    return p.export_dir / "model.onnx"
```
Note: `test_empty_dataset_is_an_error` passes before any download because `piper_csv` is checked before `checkpoints.ensure`.

`cli.py` additions:
```python
from omnivoice import train as tr, pack as pk, verify as vf

@app.command("train")
def train_cmd(project: Path = typer.Option(Path("."), "--project", "-p"), epochs: int = 3000,
              no_resume: bool = typer.Option(False, "--no-resume"), build: bool = False,
              colab_: bool = typer.Option(False, "--colab")):
    """Дообучить голос (Docker с GPU) или подготовить zip для Colab."""
    p = Project.load(project)
    try:
        if build:
            tr.build_image(); return
        if colab_:
            from omnivoice import colab
            z = colab.make_dataset_zip(p)
            typer.echo(f"Датасет: {z}")
            typer.echo(f"Открой ноутбук: {colab.NOTEBOOK_URL}"); return
        code = tr.train_project(p, max_epochs=epochs, resume=not no_resume, on_line=typer.echo)
    except tr.TrainError as e:
        typer.secho(str(e), fg="red"); raise typer.Exit(1)
    raise typer.Exit(code)

@app.command("export")
def export_cmd(project: Path = typer.Option(Path("."), "--project", "-p"), ckpt: Path = typer.Option(None)):
    """Экспортировать чекпойнт в ONNX, упаковать и проверить."""
    p = Project.load(project)
    try:
        onnx_path = tr.export_project(p, ckpt)
        folder = pk.pack_project(p, onnx_path)
    except (tr.TrainError, pk.PackError) as e:
        typer.secho(str(e), fg="red"); raise typer.Exit(1)
    r = vf.verify_voice(folder)
    typer.secho(r.message, fg="green" if r.ok else "red")
    raise typer.Exit(0 if r.ok else 1)
```

- [ ] **Step 4: Run** → pass.
- [ ] **Step 5: Manual smoke (record in report):** `uv run omnivoice train --build` (image builds), then on a 20-phrase test project `uv run omnivoice train --epochs 2` reaches "Epoch 1" and writes `train/lightning_logs/version_*/checkpoints/last.ckpt`; `uv run omnivoice export` produces a folder that passes `verify`. If the base image's Python can't build piper1-gpl, switch the `FROM` to the cuda13.0 tag listed in facts §5 and record which works.
- [ ] **Step 6: Commit** — `feat(omnivoice): train and export piper voices in docker`

---

### Task 11: Training previews and checkpoint list

**Files:** Create `omnivoice/previews.py`; Modify `cli.py` (`previews`); Test `tests/test_previews.py`

**Interfaces:**
- Produces:
  - `previews.Checkpoint(path: Path, epoch: int, step: int | None, metric: str | None, value: float | None)`; `previews.list_checkpoints(p) -> list[Checkpoint]` — parses `epoch=N-val_mel=X.ckpt`, `epoch=N-val_mos=X.ckpt`, `last.ckpt` under `train/lightning_logs/*/checkpoints/`, sorted by epoch desc.
  - `previews.extract_previews(p, out_dir: Path | None = None) -> dict[int, list[Path]]` — reads TensorBoard event files under `train/lightning_logs/` with `tensorboard.backend.event_processing.event_accumulator.EventAccumulator(dir, size_guidance={"audio": 0})`, for each audio tag writes `train/previews/<step>/<n>.wav` from `encoded_audio_string`, returns `{step: [paths]}`; requires the `[ui]` extra (tensorboard), clear RuntimeError otherwise.
  - `previews.loss_series(p, tag="loss_disc_all") -> list[tuple[int, float]]` — scalar series for the UI chart (first existing of `loss_disc_all`, `loss_gen_all`, `val_mel`).

- [ ] **Step 1: Failing test** (writes a real event file without torch):

```python
import io, wave, struct
from pathlib import Path
import pytest
pytest.importorskip("tensorboard")
from tensorboard.summary.writer.event_file_writer import EventFileWriter
from tensorboard.compat.proto.summary_pb2 import Summary
from tensorboard.compat.proto.event_pb2 import Event
from omnivoice import previews
from omnivoice.project import Project

def wav_bytes():
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(22050); w.writeframes(struct.pack("<100h", *range(100)))
    return buf.getvalue()

def test_extract_previews_and_checkpoints(tmp_path):
    p = Project.create(tmp_path / "p", name="p", language="ru")
    logdir = p.train_dir / "lightning_logs/version_0"; (logdir / "checkpoints").mkdir(parents=True)
    for name in ["epoch=10-val_mel=0.5000.ckpt", "epoch=20-val_mel=0.4000.ckpt", "last.ckpt"]:
        (logdir / "checkpoints" / name).write_bytes(b"x")
    w = EventFileWriter(str(logdir))
    audio = Summary.Audio(sample_rate=22050, num_channels=1, length_frames=100, encoded_audio_string=wav_bytes(),
                          content_type="audio/wav")
    w.add_event(Event(step=500, summary=Summary(value=[Summary.Value(tag="Привет", audio=audio)])))
    w.close()
    out = previews.extract_previews(p)
    assert list(out) == [500] and out[500][0].read_bytes()[:4] == b"RIFF"
    cps = previews.list_checkpoints(p)
    assert [c.epoch for c in cps if c.metric] == [20, 10] and any(c.path.name == "last.ckpt" for c in cps)
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** per interfaces (regex `epoch=(\d+)-(val_mel|val_mos)=([\d.]+)\.ckpt`; `last.ckpt` → epoch from its mtime order, metric None, epoch = max known epoch). **Step 4: Run** → pass. **Step 5: Commit** — `feat(omnivoice): extract training previews from tensorboard logs`

---

### Task 12: Colab notebook and `train --colab`

**Files:** Create `omnivoice/colab.py`, `tools/omnivoice/notebooks/omnivoice_colab.ipynb`; Modify `cli.py`; Test `tests/test_colab.py`

**Interfaces:**
- Produces: `colab.make_dataset_zip(p, out: Path | None = None) -> Path` — zip with `project.toml`, `metadata.csv` (filtered via `piper_csv` into `train.csv`), `segments/*.wav` of kept rows only; default `p.root / f"{p.name}-dataset.zip"`. `colab.NOTEBOOK_URL = "https://colab.research.google.com/github/Shura4eburek/OmniChat/blob/main/tools/omnivoice/notebooks/omnivoice_colab.ipynb"`.
- Notebook cells (markdown in Russian):
  1. Check GPU (`!nvidia-smi`).
  2. Install: `!git clone --depth 1 --branch v1.8.0 https://github.com/OHF-voice/piper1-gpl.git && cd piper1-gpl && pip install -e '.[train]' && ./build_monotonic_align.sh && python3 setup.py build_ext --inplace`; `!pip install "git+https://github.com/Shura4eburek/OmniChat.git#subdirectory=tools/omnivoice"`.
  3. Upload `*-dataset.zip` (`google.colab.files.upload()`), unzip to `/content/project`.
  4. Download base checkpoint via `omnivoice.checkpoints.ensure` with `OMNIVOICE_CACHE=/content/cache`.
  5. Train: same args as `train.fit_command` but without docker (`python3 -m piper.train fit ... --trainer.default_root_dir /content/project/train/`), max_epochs form field; checkpoints saved to Google Drive if mounted (optional cell).
  6. Export: `python3 -m piper.train.export_onnx --checkpoint <last.ckpt> --output-file /content/project/export/model.onnx`; then `omnivoice pack --project /content/project` and `omnivoice verify`.
  7. Zip `export/<voice>` and `files.download`.
  - Known issue note: if `torch.load` complains about `weights_only`, set `TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1` before training (facts §7).
- To keep the notebook and Docker in sync, add `train.fit_args(p, ckpt, batch, max_epochs, root) -> list[str]` (the `python3 -m piper.train fit ...` part) used by both `fit_command` and the notebook (the notebook imports it from the installed omnivoice).

- [ ] **Step 1: Failing test**

```python
import zipfile
from omnivoice import colab, dataset, audio
from omnivoice.dataset import Segment
from omnivoice.project import Project
import numpy as np

def test_dataset_zip_contains_only_kept(tmp_path):
    p = Project.create(tmp_path / "g", name="g", language="ru")
    for sid in ("a", "b"):
        audio.write_wav(p.segments_dir / f"{sid}.wav", np.zeros(22050, np.float32))
    dataset.save(p, [Segment("a", "Да", 1.0), Segment("b", "Нет", 1.0, dropped=True)])
    z = colab.make_dataset_zip(p)
    names = zipfile.ZipFile(z).namelist()
    assert "segments/a.wav" in names and "segments/b.wav" not in names
    assert "project.toml" in names and "train/train.csv" in names
```

- [ ] **Step 2–4:** fail → implement → pass (validate the notebook JSON loads with `json.loads` in the test too: `assert json.loads(Path(...).read_text())["cells"]`).
- [ ] **Step 5: Commit** — `feat(omnivoice): colab notebook and dataset zip`

---

### Task 13: Gradio UI with HUD theme

**Files:** Create `omnivoice/ui/__init__.py`, `omnivoice/ui/strings.py`, `omnivoice/ui/theme.py`, `omnivoice/ui/app.py`; Modify `cli.py` (`ui`); Test `tests/test_ui.py`

**Interfaces:**
- Consumes: every core function above (`Project`, `dataset`, `slicer`, `transcriber`, `checker`, `train`, `previews`, `pack`, `verify`, `install`).
- Produces: `ui.app.build(projects_root: Path) -> gradio.Blocks`; `cli ui [--projects DIR] [--port 7860]` launches `build(...).queue().launch(server_port=port, inbrowser=True)`.

Layout (approved mockup `.superpowers/brainstorm/*/content/omnivoice-layout.html`, variant B + steps bar):
- Header row: `OMNIVOICE` title (spaced, teal) + environment badge (`train.detect_env()` once at start: GPU name / «нет GPU», Docker ✓/✗).
- Left column (scale 1): project dropdown (dirs with `project.toml` under `projects_root`), «+ новый проект» (name + language → `Project.create`), section radio: Аудио, Нарезка, Фразы, Проверка, Обучение, Упаковка.
- Right column (scale 4): steps bar (6 HTML chips from `project.steps`: done ✓ green / current teal / pending grey; clicking a chip sets the radio), then one `gr.Group` per section, only the selected one visible.
  - Аудио: file upload (multiple) → copies into `raw/`; list of raw files; button «Нарезать» (+ checkbox «Отделить голос от музыки») → `slice_project` with `gr.Progress`.
  - Нарезка/Фразы: stats line (фраз, минут, к проверке, выкинуто); filter «только ⚑»; `gr.Dataframe` (id, текст editable, длительность, флаги, выкинута) + `gr.Audio` player for the selected row; buttons «Расшифровать» (transcribe), «Сохранить правки» (writes edited texts → `edited=True`, removes `check` flag), «Выкинуть/Вернуть», «Готово» (marks `phrases`).
  - Проверка: «Проверить» → render `Report` (warnings yellow, errors red, table of segment issues).
  - Обучение: epochs number, batch (auto from env, editable), buttons Старт/Стоп/Продолжить (background thread running `train_project` with `on_line` appending to a log textbox; Stop terminates the Popen), live epoch/step parsed from log lines (`Epoch N`), loss chart (`gr.LinePlot` from `previews.loss_series`, refreshed every 15 s via `gr.Timer`), checkpoints dropdown (`list_checkpoints`) + previews audio list (`extract_previews`), «Экспортировать этот чекпойнт». If env has no GPU: show the Colab hint with `colab.NOTEBOOK_URL` and a «Скачать датасет для Colab» button (`make_dataset_zip`).
  - Упаковка: fields name/description/gender/sample/license (from `project.display`, char counters with mod limits), portrait upload with 32×32 nearest preview, «Упаковать» → `pack_project` → `verify_voice` → result text + `gr.Audio(sample.wav)`; install target dropdown (`default_targets()` + custom path) + «Установить в Minecraft».
- All strings come from `strings.py` (Russian). Errors from core functions (RuntimeError, PackError, TrainError) are shown as `gr.Warning` toasts and in the section, never as tracebacks.

`ui/theme.py`: `THEME = gr.themes.Base(primary_hue=..., font=[gr.themes.GoogleFont("JetBrains Mono"), "monospace"]).set(body_background_fill="#0B0A0E", block_background_fill="#0F0D13", block_border_color="rgba(53,224,200,.4)", button_primary_background_fill="transparent", button_primary_border_color="#35E0C8", button_primary_text_color="#35E0C8", ...)` and `CSS` with the HUD frame (1 px teal border, 2 px corner brackets via `::before/::after` on `.hud-panel`), spaced title, step chips (`.st.done/.on`), flag colours (⚑ `#FFCF4A`, dropped strike-through).

- [ ] **Step 1: Failing test** (`tests/test_ui.py`, smoke only):

```python
import pytest
gr = pytest.importorskip("gradio")
from omnivoice.ui.app import build
from omnivoice.project import Project

def test_build_lists_projects(tmp_path):
    Project.create(tmp_path / "glados", name="glados", language="ru")
    demo = build(tmp_path)
    assert isinstance(demo, gr.Blocks)

def test_strings_have_no_empty_values():
    from omnivoice.ui import strings
    assert all(isinstance(v, str) and v for k, v in vars(strings).items() if k.isupper())
```

- [ ] **Step 2–4:** fail → implement → pass.
- [ ] **Step 5: Visual check:** `uv run --extra ui omnivoice ui --projects <tmp>` with a project that has ~5 imported phrases; open http://127.0.0.1:7860, take screenshots (any available browser automation, or ask the controller to look) of: Фразы, Обучение (no-GPU state is fine), Упаковка; verify the HUD look matches the approved mockup (dark, teal frame with corner brackets, steps bar, sidebar). Record screenshot paths in the report.
- [ ] **Step 6: Commit** — `feat(omnivoice): gradio ui in omnichat hud style`

---

### Task 14: README, mod README link, end-to-end check

**Files:** Create `tools/omnivoice/README.md`; Modify root `README.md` (section «Свои голоса» linking to the tool)

- [ ] **Step 1:** `tools/omnivoice/README.md` (Russian): what it does (3 entry points diagram), install (`uv sync`, extras `--extra prep`, `--extra ui`), ffmpeg + Docker Desktop (WSL2, NVIDIA driver) prerequisites, quick starts for A/B/C with exact commands, Colab section with `NOTEBOOK_URL`, what's inside a voice folder (matches the mod's «Оформление голосов»), troubleshooting (no GPU → Colab; `verify` failed; low VRAM), **rights warning** (game/recorded voices are copyrighted; publish only with permission; `license` field).
- [ ] **Step 2:** root `README.md`: short «Свои голоса» section → link to `tools/omnivoice/README.md`.
- [ ] **Step 3: End-to-end (C path, no GPU needed):** `uv run omnivoice pack --onnx <copy of run/config/omnichat/models/glados.onnx.bak> --config <its .onnx.json> --name "GLaDOS test" --language Russian --portrait <any png>` → `uv run omnivoice verify <folder>` OK → `uv run omnivoice install <folder> --target <tmp models dir>`. Record output. (Use the `.bak`/a copy — never the user's live model.)
- [ ] **Step 4:** full test suite `uv run pytest` green; commit — `docs(omnivoice): readme and mod link`

---

## Self-review notes

- Spec coverage: entry points A/B/C → Tasks 4, 5–6, 8; project/steps → 2; check → 7; train/export Docker → 10; previews → 11; Colab → 12; pack/verify/install → 8–9; UI → 13; errors/messages → each task + 10 (no docker/gpu), 9 (verify crash); rights/license → 8 (`license` in voice.json) + 14; tests → every task; out-of-scope respected (no from-scratch, no multi-speaker, no GLaDOS format).
- Review Focus items have tests in Tasks 5, 3, 6, 8, 10.
- External facts with UNVERIFIED status (Docker base image Python, demucs output names, sherpa generate overload) are handled defensively: Task 10 Step 5 manual smoke with fallback tag, slicer finds `vocals.wav` by `rglob`, verify worker passes args positionally.
