"""synth/: the synthetic phrases of a project (spec «Данные проекта»). synth.json holds the plan, the
generation status and the check verdicts; wavs/ the audio; lines.txt the user's own lines."""
from __future__ import annotations
import json
import statistics
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

from omnivoice import audio, corpus, dataset, synth_check
from omnivoice.project import atomic_write_text

REF_RANGE = (3.0, 12.0)   # s
REF_TOTAL = 30.0          # s
REF_MAX = 5
DEFAULT_RATE = 14.0       # characters per second when there is nothing to measure
DEFAULT_MINUTES = 15
DEFAULT_WEIGHT = 3


@dataclass
class SynthItem:
    id: str
    text: str
    source: str                      # "user" | "corpus"
    status: str = "pending"          # pending | done | failed
    duration: float = 0.0
    heard: str | None = None
    cer: float | None = None
    verdict: str = "unchecked"       # accepted | suspect | rejected | unchecked
    reasons: list[str] = field(default_factory=list)
    dropped: bool = True             # not in training until checked and accepted
    manual: str | None = None        # "accept" | "drop": the user's word beats the check
    error: str | None = None


@dataclass
class SynthState:
    refs: list[str] = field(default_factory=list)
    items: list[SynthItem] = field(default_factory=list)
    use: bool = True                 # use the accepted phrases when training
    weight: int = DEFAULT_WEIGHT     # how many times each original phrase repeats


def _file(p) -> Path:
    return p.synth_dir / "synth.json"


def wav(p, item_id: str) -> Path:
    return p.synth_dir / "wavs" / f"{item_id}.wav"


def load(p) -> SynthState:
    try:
        data = json.loads(_file(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return SynthState()
    items = [SynthItem(**{k: v for k, v in it.items() if k in SynthItem.__dataclass_fields__})
             for it in data.get("items", [])]
    return SynthState(list(data.get("refs", [])), items, bool(data.get("use", True)),
                      int(data.get("weight", DEFAULT_WEIGHT)))


def save(p, state: SynthState) -> None:
    p.synth_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(_file(p), json.dumps(asdict(state), ensure_ascii=False, indent=1))


def lines(p) -> list[str]:
    try:
        text = (p.synth_dir / "lines.txt").read_text(encoding="utf-8")
    except OSError:
        return []
    return [s.strip() for s in text.splitlines() if s.strip()]


def save_lines(p, text: str) -> None:
    p.synth_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(p.synth_dir / "lines.txt", "\n".join(s.strip() for s in text.splitlines() if s.strip()) + "\n")


def choose_refs(segments) -> list[str]:
    """3–12 s phrases without flags, longest first, up to REF_MAX and REF_TOTAL seconds in all."""
    fit = sorted((s for s in segments if not s.dropped and not s.flags and REF_RANGE[0] <= s.duration <= REF_RANGE[1]),
                 key=lambda s: -s.duration)
    out, total = [], 0.0
    for s in fit:
        if len(out) >= REF_MAX or total + s.duration > REF_TOTAL:
            break
        out.append(s.id)
        total += s.duration
    return out


def speech_rate(segments) -> float:
    rates = [len(s.text) / s.duration for s in segments if not s.dropped and s.text.strip() and s.duration > 0.3]
    return statistics.median(rates) if rates else DEFAULT_RATE


def _id_number(item_id: str) -> int:
    tail = item_id.rsplit("_", 1)[-1]
    return int(tail) if tail.isdigit() else 0


def make_plan(p, minutes: float, refs: list[str]) -> SynthState:
    """A fresh plan; phrases already generated with the same references keep their id, audio and verdict.
    Everything else gets a NEW id (never one an old phrase had: its wav would pass for the new text) and is
    (re)generated; of the user's decisions only «drop» carries over to new audio — an «accept» was for a take
    that no longer exists."""
    old = load(p)
    same_refs = old.refs == refs
    by_text = {it.text: it for it in old.items}
    segs = dataset.load(p)
    picked = corpus.pick(corpus.load(p.language), lines(p), minutes, speech_rate(segs))
    next_n = max((_id_number(it.id) for it in old.items), default=0) + 1
    items = []
    for text, source in picked:
        prev = by_text.get(text)
        if prev is not None and same_refs and prev.status == "done":
            items.append(prev)
            continue
        item = SynthItem(f"synth_{next_n:04d}", text, source,
                         manual="drop" if prev is not None and prev.manual == "drop" else None)
        next_n += 1
        for f in (wav(p, item.id), wav(p, item.id).with_suffix(".wav.part")):
            f.unlink(missing_ok=True)
        items.append(item)
    used = {it.id for it in items}
    for it in old.items:                       # files of phrases that left the plan or got a new id
        if it.id not in used:
            wav(p, it.id).unlink(missing_ok=True)
    return SynthState(refs, items, old.use, old.weight)


def merge_user_changes(p, state: SynthState) -> SynthState:
    """Before a runner saves its in-memory state: take the decisions and training settings the user changed
    on disk meanwhile (same id and text), so a ✓ / ✕ or a weight set during a run is not reverted."""
    cur = load(p)
    state.use, state.weight = cur.use, cur.weight
    on_disk = {(it.id, it.text): it for it in cur.items}
    for it in state.items:
        mine = on_disk.get((it.id, it.text))
        if mine is not None and mine.manual != it.manual:
            it.manual = mine.manual
            if it.status == "done" and it.verdict is not None:
                _apply_decision(it)
    return state


def valid_refs(p, refs: list[str]) -> list[str]:
    """References that still are usable: the phrase exists, is not dropped and has its wav."""
    ok = {s.id for s in dataset.load(p) if not s.dropped and (p.segments_dir / f"{s.id}.wav").is_file()}
    return [r for r in refs if r in ok]


def sync_generated(p, state: SynthState) -> SynthState:
    for it in state.items:
        f = wav(p, it.id)
        if it.status != "failed" and f.is_file():
            it.status, it.duration = "done", round(audio.duration(f), 3)
    return state


def _apply_decision(it: SynthItem) -> None:
    if it.manual == "accept":
        it.dropped = False
    elif it.manual == "drop":
        it.dropped = True
    else:
        it.dropped = it.verdict != "accepted"


def apply_check(p, state: SynthState, recognize: Callable[[Path], str] | None) -> SynthState:
    """Verdict for every generated phrase; `recognize` None (no Whisper) leaves them «unchecked»."""
    rate = speech_rate(dataset.load(p))
    for it in state.items:
        if it.status != "done":
            continue
        x, sr = audio.load_mono(wav(p, it.id))
        it.heard = recognize(wav(p, it.id)) if recognize else None
        it.cer = None if it.heard is None else round(synth_check.cer(it.text, it.heard), 3)
        it.verdict, it.reasons = synth_check.verdict(it.text, it.heard, x, sr, len(it.text) / rate)
        _apply_decision(it)
    return state


def set_manual(p, item_id: str, decision: str | None) -> SynthState:
    state = load(p)
    for it in state.items:
        if it.id == item_id:
            it.manual = decision
            _apply_decision(it)
    save(p, state)
    return state


def summary(state: SynthState) -> dict:
    done = [i for i in state.items if i.status == "done"]
    taken = [i for i in done if not i.dropped]
    return {"accepted": len(taken), "accepted_min": round(sum(i.duration for i in taken) / 60, 1),
            "suspect": sum(i.verdict == "suspect" and i.manual is None for i in done),
            "rejected": sum(i.dropped and (i.verdict == "rejected" or i.manual == "drop") for i in done),
            "failed": sum(i.status == "failed" for i in state.items),
            "pending": sum(i.status == "pending" for i in state.items)}


def training_items(p) -> list[SynthItem]:
    state = load(p)
    if not state.use:
        return []
    return [i for i in state.items if i.status == "done" and not i.dropped and wav(p, i.id).is_file()]
