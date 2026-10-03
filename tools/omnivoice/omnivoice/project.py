from __future__ import annotations
import os
import threading, tomllib
from dataclasses import dataclass, field
from pathlib import Path
import tomli_w
from omnivoice import languages

STEPS = ("audio", "slice", "phrases", "check", "train", "pack")
FILE = "project.toml"

class ProjectError(ValueError):
    """Project-related error with user-facing Russian message."""
    pass

def atomic_write_text(path: Path, text: str) -> None:
    """Write via a sibling tmp file + os.replace, so a crash never leaves a half-written file."""
    path = Path(path)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        with tmp.open("w", encoding="utf-8", newline="") as f:
            f.write(text)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()

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
            raise ProjectError(f"Неизвестный язык «{language}». Доступны: {', '.join(languages.PRESETS)}")
        lang = languages.PRESETS[language]
        if base and base not in languages.BASE_CHECKPOINTS:
            raise ProjectError(f"Неизвестная базовая модель «{base}». Доступны: {', '.join(languages.BASE_CHECKPOINTS)}")
        ckpt = languages.BASE_CHECKPOINTS[base] if base else lang.base_checkpoint
        if (Path(root) / FILE).exists():
            raise ProjectError(f"В {root} уже есть проект (project.toml) — выбери другую папку")
        p = cls(Path(root), name, language, lang.espeak_voice, ckpt,
                display={"name": name, "description": "", "gender": "", "sample": lang.test_phrase, "license": ""})
        for d in (p.raw_dir, p.segments_dir, p.train_dir, p.export_dir):
            d.mkdir(parents=True, exist_ok=True)
        p.save()
        return p

    @classmethod
    def load(cls, root: Path) -> "Project":
        root = Path(root)
        project_file = root / FILE
        if not project_file.exists():
            raise ProjectError(f"В {root} нет project.toml — создай проект: omnivoice init")
        try:
            data = tomllib.loads(project_file.read_text(encoding="utf-8"))
            steps = {s: False for s in STEPS} | data.get("steps", {})
            return cls(root, data["name"], data["language"], data["espeak_voice"], data["base_checkpoint"],
                       data.get("sample_rate", 22050), data.get("display", {}), steps)
        except (KeyError, TypeError, ValueError, UnicodeDecodeError, tomllib.TOMLDecodeError) as e:
            raise ProjectError(f"Файл project.toml повреждён: {e}")

    def save(self) -> None:
        data = {"name": self.name, "language": self.language, "espeak_voice": self.espeak_voice,
                "base_checkpoint": self.base_checkpoint, "sample_rate": self.sample_rate,
                "display": self.display, "steps": self.steps}
        atomic_write_text(self.root / FILE, tomli_w.dumps(data))

    def mark(self, step: str, done: bool = True) -> None:
        if step not in STEPS:
            raise ValueError(step)
        self.steps[step] = done

    @classmethod
    def mark_saved(cls, root: Path, step, value: bool = True) -> "Project":
        """Read-modify-write: reload project.toml, set step(s), save. Use after long operations so
        edits made meanwhile (e.g. display fields in the UI) are not overwritten by a stale copy."""
        fresh = cls.load(root)
        for s in ((step,) if isinstance(step, str) else step):
            fresh.mark(s, value)
        fresh.save()
        return fresh

    def mark_fresh(self, step, value: bool = True) -> None:
        """mark_saved() on disk, then mirror the saved steps into this (possibly stale) instance."""
        self.steps = dict(Project.mark_saved(self.root, step, value).steps)
