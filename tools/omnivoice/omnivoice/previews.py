"""Training previews (TensorBoard audio) and checkpoint listing."""
import json
import re
import struct
import threading
from dataclasses import dataclass
from pathlib import Path

_CKPT_RE = re.compile(r"epoch=(\d+)-(val_mel|val_mos)=(\d+(?:\.\d+)?)\.ckpt$")
from omnivoice.hints import NEED_UI as _NEED_UI


@dataclass
class Checkpoint:
    path: Path
    epoch: int
    step: int | None
    metric: str | None
    value: float | None


def cut_short(f: Path) -> bool:
    """A torch checkpoint is a zip archive. One whose save was killed half-way (e.g. a hard stop while the
    file was being copied to the Windows disk) starts like a zip but has no central directory at its end,
    and torch cannot load it. Anything that does not start like a zip is left to torch to judge."""
    import zipfile
    try:
        with open(f, "rb") as fh:
            if fh.read(4) != b"PK\x03\x04":
                return False
        return not zipfile.is_zipfile(f)
    except OSError:
        return False


def cut_short_checkpoints(p) -> list[Path]:
    return [f for f in p.train_dir.glob("lightning_logs/*/checkpoints/*.ckpt") if cut_short(f)]


def list_checkpoints(p) -> list[Checkpoint]:
    """Checkpoints under train/lightning_logs/*/checkpoints/, newest epoch first.

    Files matching no known pattern, and files cut short by a killed save, are skipped. ``last.ckpt`` has no epoch in
    its name: it takes the highest epoch among its sibling checkpoints (-1 if
    there are none) and is sorted before every other checkpoint.
    """
    out: list[Checkpoint] = []
    for d in sorted(p.train_dir.glob("lightning_logs/*/checkpoints")):
        found: list[Checkpoint] = []
        last: Path | None = None
        for f in sorted(d.glob("*.ckpt")):
            if cut_short(f):
                continue
            if f.name == "last.ckpt":
                last = f; continue
            m = _CKPT_RE.match(f.name)
            if m:
                found.append(Checkpoint(f, int(m.group(1)), None, m.group(2), float(m.group(3))))
        out += found
        if last is not None:
            out.append(Checkpoint(last, max((c.epoch for c in found), default=-1), None, None, None))
    out.sort(key=lambda c: (c.metric is not None, -c.epoch))
    return out


def _accumulator(logdir: Path, size_guidance: dict):
    try:
        from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
    except ImportError as e:
        raise RuntimeError(_NEED_UI) from e
    acc = EventAccumulator(str(logdir), size_guidance=size_guidance)
    acc.Reload()
    return acc


def _version_key(d: Path, root: Path):
    """Order event dirs by the numeric suffix of their version_N dir (version_10 after version_9)."""
    top = d.relative_to(root).parts[0] if d != root else ""
    m = re.fullmatch(r"version_(\d+)", top)
    return (0, int(m.group(1)), str(d)) if m else (1, 0, str(d))


def _event_dirs(root: Path) -> list[Path]:
    return sorted({f.parent for f in root.rglob("events.out.tfevents*")}, key=lambda d: _version_key(d, root))


def extract_previews(p, out_dir: Path | None = None) -> dict[int, list[Path]]:
    """Write TensorBoard audio to ``<out_dir>/<step>/<n>.wav`` (default train/previews).

    Idempotent: existing wav files are kept as they are.
    """
    logs = p.train_dir / "lightning_logs"
    if not logs.is_dir():
        return {}
    out_dir = out_dir or (p.train_dir / "previews")
    result: dict[int, list[Path]] = {}
    for d in _event_dirs(logs):
        acc = _accumulator(d, {"audio": 0})
        for tag in sorted(acc.Tags().get("audio", [])):
            for ev in acc.Audio(tag):
                paths = result.setdefault(ev.step, [])
                target = out_dir / str(ev.step) / f"{len(paths)}.wav"
                if not target.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(ev.encoded_audio_string)
                paths.append(target)
    return dict(sorted(result.items()))


# ---------- piper events, read incrementally ----------
# piper logs per validation: 5 audio clips (tag = phrase text, step = global_step), then val_* scalars
# and "epoch" at Lightning's own step. The audio step doesn't match the scalar step, so a clip belongs
# to the next "epoch" scalar that follows it in the file. Events are read with a small TFRecord
# reader that remembers its byte offset: the chart refreshes every few seconds while the file grows,
# and tensorboard's pure-python reader needs ~4 s for a 30 MB file (mostly audio).

_INDEX: dict[str, "_EventFile"] = {}
_INDEX_LOCK = threading.Lock()
METRIC_TAGS = ("val_mos", "val_mel")


class _EventFile:
    def __init__(self, path: Path):
        self.path = path
        self.offset = 0
        self.lock = threading.Lock()
        self.epoch_of_step: dict[int, int] = {}
        self.scalars: dict[str, dict[int, float]] = {t: {} for t in METRIC_TAGS}
        self.audio: dict[int, list[tuple[str, int]]] = {}  # epoch → [(phrase, record offset)]
        self._pending: list[tuple[str, int]] = []

    def update(self) -> "_EventFile":
        with self.lock:
            try:
                size = self.path.stat().st_size
            except OSError:
                return self
            if size < self.offset:  # rewritten: start over
                self.__init__(self.path)
            if size > self.offset:
                self._read_new()
        return self

    def _read_new(self) -> None:
        event_pb2, masked_crc32c = _proto()
        with open(self.path, "rb") as f:
            f.seek(self.offset)
            while True:
                start = f.tell()
                head = f.read(12)
                if len(head) < 12:
                    break
                length, crc = struct.unpack("<QI", head)
                if masked_crc32c(head[:8]) != crc:
                    break  # a half-written header: retry on the next update
                data = f.read(length)
                if len(data) < length or len(f.read(4)) < 4:
                    break
                self.offset = f.tell()
                self._record(event_pb2.Event.FromString(data), start)

    def _record(self, ev, start: int) -> None:
        for v in ev.summary.value:
            kind = v.WhichOneof("value")
            if kind == "audio":
                self._pending.append((v.tag, start))
            elif kind == "simple_value":
                if v.tag == "epoch":
                    e = int(round(v.simple_value))
                    self.epoch_of_step[ev.step] = e
                    if self._pending:
                        self.audio.setdefault(e, []).extend(self._pending)
                        self._pending = []
                elif v.tag in self.scalars:
                    self.scalars[v.tag][ev.step] = v.simple_value

    def metrics(self) -> dict[int, dict[str, float]]:
        out: dict[int, dict[str, float]] = {}
        for tag, series in self.scalars.items():
            for step, value in series.items():
                e = self.epoch_of_step.get(step)
                if e is not None:
                    out.setdefault(e, {})[tag] = value
        return out

    def audio_bytes(self, record_offset: int) -> bytes:
        event_pb2, _ = _proto()
        with open(self.path, "rb") as f:
            f.seek(record_offset)
            length, _crc = struct.unpack("<QI", f.read(12))
            ev = event_pb2.Event.FromString(f.read(length))
        return ev.summary.value[0].audio.encoded_audio_string


def _proto():
    try:
        from tensorboard.compat.proto import event_pb2
        from tensorboard.compat.tensorflow_stub.pywrap_tensorflow import masked_crc32c
    except ImportError as e:
        raise RuntimeError(_NEED_UI) from e
    return event_pb2, masked_crc32c


def _event_files(p) -> list[_EventFile]:
    """Every events file under train/lightning_logs, oldest version first, read up to date."""
    logs = p.train_dir / "lightning_logs"
    if not logs.is_dir():
        return []
    files = sorted(logs.rglob("events.out.tfevents*"), key=lambda f: _version_key(f.parent, logs) + (f.name,))
    out = []
    for f in files:
        key = str(f.resolve())
        with _INDEX_LOCK:
            ef = _INDEX.setdefault(key, _EventFile(f))
        out.append(ef.update())
    return out


def epoch_metrics(p) -> dict[int, dict[str, float]]:
    """{absolute epoch: {"val_mos": .., "val_mel": ..}} merged over every version (later wins)."""
    merged: dict[int, dict[str, float]] = {}
    for ef in _event_files(p):
        for e, m in ef.metrics().items():
            merged.setdefault(e, {}).update(m)
    return dict(sorted(merged.items()))


def loss_series(p, tag: str = "val_mel", offset: int = 0, metrics: dict | None = None) -> list[tuple[int, float]]:
    """(epoch − offset, value) of a validation metric, merged across every version_* run."""
    metrics = epoch_metrics(p) if metrics is None else metrics
    return [(e - offset, m[tag]) for e, m in sorted(metrics.items()) if tag in m]


def _preview_dir(p, epoch: int) -> Path:
    return p.train_dir / "previews" / f"epoch_{epoch}"


def _cached(p, epoch: int) -> list[tuple[str, Path]] | None:
    d = _preview_dir(p, epoch)
    try:
        items = json.loads((d / "phrases.json").read_text(encoding="utf-8"))
        out = [(it["text"], d / it["file"]) for it in items]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return out if out and all(f.is_file() for _, f in out) else None


def listen(p, epoch: int) -> tuple[int | None, list[tuple[str, Path]]]:
    """The validation phrases synthesised at `epoch` (or the nearest epoch that has them) as wav files
    under train/previews/epoch_<n>/, with their texts. Cached on disk: a second call reads nothing."""
    hit = _cached(p, epoch)
    if hit:
        return epoch, hit
    where: dict[int, _EventFile] = {}
    for ef in _event_files(p):
        for e in ef.audio:
            where[e] = ef  # a later version wins
    if not where:
        return None, []
    near = min(where, key=lambda e: (abs(e - epoch), -e))
    hit = _cached(p, near)
    if hit:
        return near, hit
    ef, d = where[near], _preview_dir(p, near)
    d.mkdir(parents=True, exist_ok=True)
    items, out = [], []
    for i, (text, off) in enumerate(ef.audio[near]):
        f = d / f"{i}.wav"
        if not f.is_file():
            f.write_bytes(ef.audio_bytes(off))
        items.append({"text": text, "file": f.name})
        out.append((text, f))
    (d / "phrases.json").write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
    return near, out


# ---------- checkpoints: ranking, pruning, disk ----------

WARMUP_MIN = 20       # epochs after the base checkpoint that are never «best» nor listed
WARMUP_SHARE = 0.05   # ... or this share of the epochs trained so far, if larger


@dataclass
class Ranked:
    path: Path
    epoch: int
    mos: float | None
    mel: float | None
    best_mos: bool = False
    best_mel: bool = False
    last: bool = False      # the newest last.ckpt (what «Продолжить» resumes from)
    old_last: bool = False  # last.ckpt of an earlier run


def _last_epochs(p) -> dict[Path, int]:
    """version dir → the highest epoch its events reached (= the epoch of its last.ckpt)."""
    out: dict[Path, int] = {}
    try:
        files = _event_files(p)
    except RuntimeError:
        return out
    for ef in files:
        if ef.epoch_of_step:
            d = ef.path.parent
            out[d] = max(out.get(d, -1), max(ef.epoch_of_step.values()))
    return out


def _last_ckpt_epoch(last: Path) -> int | None:
    """The epoch fit.py wrote last.ckpt at (it saves every few epochs, so the events may run further);
    None for a run without the note (piper's own fit rewrote last.ckpt every time)."""
    from omnivoice.piper_compat.fit import LAST_EPOCH
    try:
        return int(last.with_name(LAST_EPOCH).read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _metrics_or_empty(p) -> dict:
    try:
        return epoch_metrics(p)
    except RuntimeError:  # no tensorboard: names still carry one metric each
        return {}


def rank_checkpoints(p, metrics: dict | None = None) -> list[Ranked]:
    """One row per epoch (the val_mel and val_mos files of an epoch hold the same weights), with MOS / mel
    from the events (or the file name). The first warm-up epochs (WARMUP_*) still sound like the base
    voice and score a high MOS, so they are hidden and never «best», unless nothing else exists yet.
    Order: best MOS, the newest last.ckpt, best mel, the rest by epoch (newest first), older runs'
    last.ckpt at the bottom (minus those repeating a listed epoch)."""
    metrics = _metrics_or_empty(p) if metrics is None else metrics
    cps = list_checkpoints(p)
    if not cps:
        return []
    last_epochs = _last_epochs(p)
    lasts = [c for c in cps if c.metric is None]
    newest = max(lasts, key=lambda c: c.path.stat().st_mtime).path if lasts else None
    named: dict[int, Ranked] = {}
    last, old = None, []
    for c in cps:
        if c.metric is None:
            e = _last_ckpt_epoch(c.path)
            e = last_epochs.get(c.path.parent.parent, c.epoch) if e is None else e
            m = metrics.get(e, {})
            r = Ranked(c.path, e, m.get("val_mos"), m.get("val_mel"), last=c.path == newest,
                       old_last=c.path != newest)
            if r.last:
                last = r
            else:
                old.append(r)
            continue
        m = metrics.get(c.epoch, {})
        mos = m.get("val_mos", c.value if c.metric == "val_mos" else None)
        mel = m.get("val_mel", c.value if c.metric == "val_mel" else None)
        prev = named.get(c.epoch)
        if prev is None:
            named[c.epoch] = Ranked(c.path, c.epoch, mos, mel)
        else:  # the second file of the same epoch: prefer showing the val_mos one, merge the values
            if c.metric == "val_mos":
                prev.path = c.path
            prev.mos = prev.mos if prev.mos is not None else mos
            prev.mel = prev.mel if prev.mel is not None else mel
    rows = list(named.values())
    from omnivoice.train import base_epoch
    base = base_epoch(p)
    top = max([r.epoch for r in rows + old] + ([last.epoch] if last else []))
    warmup = max(WARMUP_MIN, round((top - base) * WARMUP_SHARE))
    trained = [r for r in rows if r.epoch - base > warmup]
    rows = trained or rows
    if any(r.mos is not None for r in rows):
        max((r for r in rows if r.mos is not None), key=lambda r: (r.mos, r.epoch)).best_mos = True
    if any(r.mel is not None for r in rows):
        min((r for r in rows if r.mel is not None), key=lambda r: (r.mel, -r.epoch)).best_mel = True
    pinned = [r for r in rows if r.best_mos] + ([last] if last else []) + [r for r in rows if r.best_mel and not r.best_mos]
    rest = sorted((r for r in rows if not (r.best_mos or r.best_mel)), key=lambda r: -r.epoch)
    shown = {r.epoch for r in pinned + rest}
    old = [r for r in old if r.epoch not in shown and (not trained or r.epoch - base > warmup)]
    return pinned + rest + sorted(old, key=lambda r: -r.epoch)


def prune_plan(p) -> tuple[list[Path], list[Path]]:
    """(keep, delete): the best-by-MOS checkpoint, the best-by-mel one and the newest last.ckpt stay;
    every other .ckpt (older runs' last.ckpt included) goes."""
    rows = rank_checkpoints(p)
    cps = list_checkpoints(p)
    keep: list[Path] = [r.path for r in rows if r.last]
    for flag, metric in (("best_mos", "val_mos"), ("best_mel", "val_mel")):
        r = next((x for x in rows if getattr(x, flag)), None)
        if r is None:
            continue
        # an epoch may have both files: keep the one named after this metric
        own = [c.path for c in cps if c.epoch == r.epoch and c.metric == metric and c.path.parent == r.path.parent]
        path = own[0] if own else r.path
        if path not in keep:
            keep.append(path)
    return keep, [c.path for c in cps if c.path not in keep] + cut_short_checkpoints(p)


def recently_written(p, seconds: float = 180, now: float | None = None) -> bool:
    """A checkpoint or events file changed in the last `seconds`: a training (maybe in another
    omnivoice window or the CLI) is probably still writing here."""
    import time
    now = time.time() if now is None else now
    logs = p.train_dir / "lightning_logs"
    for f in list(logs.glob("*/checkpoints/*.ckpt")) + list(logs.rglob("events.out.tfevents*")):
        try:
            if now - f.stat().st_mtime < seconds:
                return True
        except OSError:
            pass
    return False


def delete_checkpoints(files) -> tuple[int, int]:
    """Delete files; (how many, bytes freed). Already-missing files are skipped."""
    n = freed = 0
    for f in files:
        try:
            size = f.stat().st_size
            f.unlink()
        except FileNotFoundError:
            continue
        n += 1
        freed += size
    return n, freed

