from __future__ import annotations
import csv, json, re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from omnivoice import audio
from omnivoice.project import Project, ProjectError, atomic_write_text
from omnivoice.textnorm import normalize_text
from omnivoice.translit import translit as _translit

@dataclass
class Segment:
    id: str
    text: str
    duration: float
    confidence: float | None = None
    flags: list[str] = field(default_factory=list)
    dropped: bool = False
    edited: bool = False
    source: str | None = None

def clean_text(text: str) -> str:
    """One csv-safe line: `|` and every line break (CRLF, lone CR, LF) become a space."""
    return re.sub(r"\r\n|[\r\n]", " ", text.replace("|", " ")).strip()

_clean = clean_text

def load(p: Project) -> list[Segment]:
    if not p.metadata_csv.is_file():
        return []
    try:
        review = json.loads(p.review_json.read_text(encoding="utf-8")) if p.review_json.is_file() else {}
        if not isinstance(review, dict) or not all(isinstance(v, dict) for v in review.values()):
            raise ValueError("expected an object of objects")
    except (ValueError, UnicodeDecodeError) as e:
        raise ProjectError(f"Файл review.json повреждён: {e}") from e
    out = []
    try:
        with p.metadata_csv.open(encoding="utf-8", newline="") as f:
            for row in csv.reader(f, delimiter="|", quoting=csv.QUOTE_NONE):
                if not row: continue
                r = review.get(row[0], {})
                out.append(Segment(row[0], row[1] if len(row) > 1 else "", r.get("duration", 0.0), r.get("confidence"),
                                   r.get("flags", []), r.get("dropped", False), r.get("edited", False), r.get("source")))
    except (csv.Error, UnicodeDecodeError) as e:
        raise ProjectError(f"Файл metadata.csv повреждён: {e}") from e
    return out

def save(p: Project, segments: list[Segment]) -> None:
    atomic_write_text(p.metadata_csv, "".join(f"{s.id}|{clean_text(s.text)}\n" for s in segments))
    review = {s.id: {k: v for k, v in asdict(s).items() if k not in ("id", "text")} for s in segments}
    atomic_write_text(p.review_json, json.dumps(review, ensure_ascii=False, indent=1))

def sanitize_id(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", _translit(name))

def add_wav(p: Project, seg_id: str, source_audio) -> float:
    x, sr = audio.load_mono(source_audio)
    y = audio.pad(audio.resample(x, sr), audio.SR)
    audio.write_wav(p.segments_dir / f"{seg_id}.wav", y)
    return len(y) / audio.SR

@dataclass
class ImportResult:
    added: int = 0
    skipped_existing: int = 0
    missing_audio: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)

def import_dataset(p: Project, source: Path) -> ImportResult:
    source = Path(source)
    if not source.is_dir():
        raise ProjectError(f"Папка {source} не найдена")
    pairs: list[tuple[str, Path, str]] = []
    meta = source / "metadata.csv"
    if meta.is_file():
        wav_dir = source / "wavs" if (source / "wavs").is_dir() else source
        with meta.open(encoding="utf-8-sig", newline="") as f:
            for row in csv.reader(f, delimiter="|", quoting=csv.QUOTE_NONE):
                if len(row) < 2: continue
                name = row[0].removesuffix(".wav")
                pairs.append((name, wav_dir / f"{name}.wav", row[2] if len(row) > 2 and row[2] else row[1]))
    else:
        for wav in sorted(source.glob("*.wav")):
            txt = wav.with_suffix(".txt")
            if txt.is_file():
                pairs.append((wav.stem, wav, txt.read_text(encoding="utf-8-sig").strip()))
    if not pairs:
        raise ProjectError("Не найден ни metadata.csv, ни пар .wav + .txt")
    segments = load(p)
    known = {s.id.casefold() for s in segments}  # case-insensitive: a.wav and A.wav collide on Windows
    sources = {s.source for s in segments if s.source}
    res = ImportResult()
    p.segments_dir.mkdir(parents=True, exist_ok=True)
    for name, wav, text in pairs:
        if name in sources:
            res.skipped_existing += 1; continue
        if not wav.is_file():
            res.missing_audio.append(name); continue
        base = sanitize_id(name) or "seg"
        sid, n = base, 1
        while sid.casefold() in known:
            n += 1; sid = f"{base}_{n}"
        try:
            dur = add_wav(p, sid, wav)
        except Exception:
            res.failed.append(name); continue
        norm, flags = normalize_text(clean_text(text), p.language)
        segments.append(Segment(sid, clean_text(norm), dur, flags=list(flags), source=name))
        known.add(sid.casefold()); sources.add(name); res.added += 1
    save(p, segments)
    if res.added: p.mark_fresh(("audio", "slice"))
    return res

def piper_csv(p: Project, out: Path) -> int:
    rows = [s for s in load(p) if not s.dropped and s.text.strip()]
    with Path(out).open("w", encoding="utf-8", newline="") as f:
        for s in rows:
            f.write(f"{s.id}.wav|{clean_text(s.text)}\n")
    return len(rows)
