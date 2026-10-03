"""Training previews (TensorBoard audio) and checkpoint listing."""
import re
from dataclasses import dataclass
from pathlib import Path

_CKPT_RE = re.compile(r"epoch=(\d+)-(val_mel|val_mos)=(\d+(?:\.\d+)?)\.ckpt$")
_LOSS_TAGS = ("loss_disc_all", "loss_gen_all", "val_mel")
from omnivoice.hints import NEED_UI as _NEED_UI


@dataclass
class Checkpoint:
    path: Path
    epoch: int
    step: int | None
    metric: str | None
    value: float | None


def list_checkpoints(p) -> list[Checkpoint]:
    """Checkpoints under train/lightning_logs/*/checkpoints/, newest epoch first.

    Files matching no known pattern are skipped. ``last.ckpt`` has no epoch in
    its name: it takes the highest epoch among its sibling checkpoints (-1 if
    there are none) and is sorted before every other checkpoint.
    """
    out: list[Checkpoint] = []
    for d in sorted(p.train_dir.glob("lightning_logs/*/checkpoints")):
        found: list[Checkpoint] = []
        last: Path | None = None
        for f in sorted(d.glob("*.ckpt")):
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


def loss_series(p, tag: str = "loss_disc_all") -> list[tuple[int, float]]:
    """Scalar series for the UI chart, merged across every version_* run (a resumed training starts a
    new version dir) and sorted by step; a later version wins on a duplicate step. Falls back
    through the known loss tags: the first tag present in any run is used."""
    logs = p.train_dir / "lightning_logs"
    if not logs.is_dir():
        return []
    candidates = [tag] + [t for t in _LOSS_TAGS if t != tag]
    accs = [_accumulator(d, {"scalars": 0}) for d in _event_dirs(logs)]
    have = set().union(*(set(a.Tags().get("scalars", [])) for a in accs)) if accs else set()
    chosen = next((t for t in candidates if t in have), None)
    if chosen is None:
        return []
    merged: dict[int, float] = {}
    for acc in accs:
        if chosen in acc.Tags().get("scalars", []):
            for e in acc.Scalars(chosen):
                merged[e.step] = e.value
    return sorted(merged.items())
