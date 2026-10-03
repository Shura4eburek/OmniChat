"""Readable training log: piper / Lightning stdout (tqdm bars, warnings, escape codes) → short
Russian lines, one per finished epoch, plus the messages that matter.

Pure: no I/O. TrainRunner feeds every raw line (the stream is split on \\r and \\n, so each tqdm
redraw arrives as its own line) and renders the result with the latest TensorBoard metrics, which
fill in values tqdm doesn't show (val_mel).
"""
from __future__ import annotations

import re
import time
from collections import deque
from dataclasses import dataclass

_ANSI = re.compile(r"\x1b(?:\[[0-9;?]*[ -/]*[@-~]|[()][0-9A-Za-z]|[=>78DEHMc])")
# tqdm: "<desc>: 42%|███▌    | 5/12 [00:03<00:04, 1.70it/s, v_num=1, val_mos=2.360]<glued text>"
_BAR = re.compile(r"(?P<desc>[^|]*?)(?::?\s*(?P<pct>\d+)%)?\|[^|]*\|\s*[\d.?]+[kMGTB]*/[\d.?]+[kMGTB]*\s*"
                  r"\[(?P<inside>[^\]]*)\]")
_EPOCH = re.compile(r"Epoch (\d+)\b")
_RATE = re.compile(r"^\s*([\d.]+)\s*(it/s|s/it)\s*$")
_WARN_HEADER = re.compile(r"^\S+\.py:\d+: ")
_ERROR = re.compile(r"Traceback|Error\b|Error:|Exception\b|error:|out of memory|Killed|^(?:wsl|docker):",
                    re.IGNORECASE)
_CYRILLIC = re.compile(r"[А-Яа-яЁё]")
_RESTORED = re.compile(r"Restored all states from the checkpoint at (\S+)")
_FIT_STOPPED = re.compile(r"`Trainer\.fit` stopped")
_PIPER_WARN = re.compile(r"^WARNING:piper[\w.]*:\s*(.*)$")
_UTMOS = re.compile(r'Downloading: ".*SpeechMOS')

EPOCH = "Эпоха {epoch}/{target}"
MOS = "качество (MOS) {v:.2f}"
MEL = "mel {v:.2f}"
RESUMED = "Продолжаю с чекпойнта {name}"
FIT_DONE = "Обучение дошло до заданного числа эпох"
PIPER_WARN = "Предупреждение piper: {msg}"
UTMOS = "Скачиваю модель оценки качества (UTMOS, ~400 МБ) — только в первый раз"


def strip_ansi(s: str) -> str:
    return _ANSI.sub("", s)


def last_redraw(s: str) -> str:
    """What a terminal shows for a line with \\r redraws: the last non-empty segment."""
    parts = [x for x in s.split("\r") if x.strip()]
    return parts[-1] if parts else ""


def rate_text(rate: str | None) -> str | None:
    m = _RATE.match(rate or "")
    if not m:
        return None
    v = float(m.group(1))
    num = f"{v:.0f}" if v >= 10 else (f"{v:.1f}" if round(v, 1) == round(v, 2) else f"{v:.2f}")
    return f"{num} {'ит/с' if m.group(2) == 'it/s' else 'с/ит'}"


def duration_text(seconds: float) -> str:
    s = int(round(seconds))
    if s < 60:
        return f"{s} с"
    if s < 3600:
        return f"{s // 60} мин {s % 60} с" if s % 60 else f"{s // 60} мин"
    return f"{s // 3600} ч {s % 3600 // 60} мин"


@dataclass
class EpochDone:
    epoch: int  # absolute (Lightning's 0-based number, as in checkpoint names)
    mos: float | None
    rate: str | None


def _short_ckpt(path: str) -> str:
    parts = path.replace("\\", "/").split("/")
    if "lightning_logs" in parts and len(parts) >= 3 and parts[-2] == "checkpoints":
        return f"{parts[-3]}/{parts[-1]}"
    return parts[-1]


class LogCleaner:
    """offset: the base checkpoint's epoch (absolute − offset = new epochs); target: the absolute
    number of the last epoch of this run."""

    def __init__(self, offset: int = 0, target: int | None = None, max_lines: int = 400, clock=time.monotonic):
        self.offset, self.target = offset, target
        self.entries: deque = deque(maxlen=max_lines)
        self.clock = clock
        self.epoch: int | None = None       # epoch in progress (absolute)
        self.done_epoch: int | None = None  # last finished epoch (absolute)
        self._times: deque[float] = deque(maxlen=11)
        self._emitted: set[int] = set()
        self._saw_val = False
        self._rate: str | None = None
        self._in_tb = False
        self._utmos = False

    # ---- input ----
    def add(self, text: str) -> None:
        self.entries.append(text)

    def feed(self, raw: str) -> None:
        for seg in strip_ansi(raw).split("\r"):
            self._segment(seg)

    def finish(self) -> None:
        """The process ended: an epoch still in flight that printed nothing else counts as done."""
        if self.epoch is not None and self.epoch not in self._emitted:
            self._emit(self.epoch, None)

    def _segment(self, seg: str) -> None:
        if not seg.strip():
            return
        if len(seg) - len(seg.lstrip(" ")) >= 10:  # tqdm wiped the bar with spaces, then printed text
            seg = seg.lstrip(" ")
        m = _BAR.match(seg.strip()) if "|" in seg else None
        if m:
            self._bar(m.group("desc").strip(), m.group("inside"))
            rest = seg.strip()[m.end():]
            if rest.strip():
                self._segment(rest)
            return
        em = _EPOCH.match(seg.strip())
        if em and "%" in seg:  # an epoch bar we can't fully parse: still tracks the epoch
            self._epoch_start(int(em.group(1)))
            return
        self._text(seg.rstrip())

    def _bar(self, desc: str, inside: str) -> None:
        em = _EPOCH.match(desc)
        if em:
            n = int(em.group(1))
            self._epoch_start(n)
            fields = [f.strip() for f in inside.split(",")]
            post = dict(f.split("=", 1) for f in fields[2:] if "=" in f)
            if self._saw_val:  # the first redraw after validation carries this epoch's val metrics
                try:
                    mos = float(post["val_mos"]) if "val_mos" in post else None
                except ValueError:
                    mos = None
                self._emit(n, mos)
            elif len(fields) > 1 and rate_text(fields[1]):
                self._rate = fields[1]
        elif desc.startswith("Validation"):
            if self.epoch is not None:
                self._saw_val = True
        # Sanity Checking / download bars / anything else: noise

    def _epoch_start(self, n: int) -> None:
        if n == self.epoch:
            return
        if self.epoch is not None and self.epoch not in self._emitted:
            self._emit(self.epoch, None)  # finished without a validation we could see
        self.epoch, self._saw_val, self._rate = n, False, None

    def _emit(self, n: int, mos: float | None) -> None:
        if n in self._emitted:
            return
        self._emitted.add(n)
        self.done_epoch = n
        self._times.append(self.clock())
        self.entries.append(EpochDone(n, mos, self._rate))
        self._saw_val = False

    def _text(self, line: str) -> None:
        s = line.strip()
        if self._in_tb:
            self.entries.append(line)
            if not line[:1].isspace():  # the exception line closes the traceback
                self._in_tb = False
            return
        if s.startswith("Traceback"):
            self._in_tb = True
            self.entries.append(s)
            return
        if _WARN_HEADER.match(s) or line[:1].isspace():
            return  # python warnings and their indented source lines, summary tables
        if m := _RESTORED.search(s):
            self.entries.append(RESUMED.format(name=_short_ckpt(m.group(1))))
        elif _FIT_STOPPED.search(s):
            self.finish()
            self.entries.append(FIT_DONE)
        elif m := _PIPER_WARN.match(s):
            self.entries.append(PIPER_WARN.format(msg=m.group(1)))
        elif _UTMOS.search(s):
            if not self._utmos:
                self._utmos = True
                self.entries.append(UTMOS)
        elif _CYRILLIC.search(s) or _ERROR.search(s):
            self.entries.append(s)

    # ---- output ----
    def epoch_line(self, e: EpochDone, metrics: dict | None = None) -> str:
        m = (metrics or {}).get(e.epoch, {})
        target = self.target - self.offset if self.target is not None else "?"
        parts = [EPOCH.format(epoch=e.epoch - self.offset, target=target)]
        mos = e.mos if e.mos is not None else m.get("val_mos")
        if mos is not None:
            parts.append(MOS.format(v=mos))
        if m.get("val_mel") is not None:
            parts.append(MEL.format(v=m["val_mel"]))
        if rate_text(e.rate):
            parts.append(rate_text(e.rate))
        return " · ".join(parts)

    def render(self, metrics: dict | None = None) -> list[str]:
        """metrics: {absolute epoch: {"val_mos": .., "val_mel": ..}} from the TensorBoard events."""
        return [self.epoch_line(e, metrics) if isinstance(e, EpochDone) else e for e in list(self.entries)]

    def seconds_per_epoch(self) -> float | None:
        t = list(self._times)
        return (t[-1] - t[0]) / (len(t) - 1) if len(t) >= 2 else None

    def eta(self) -> float | None:
        spe = self.seconds_per_epoch()
        if spe is None or self.target is None or self.done_epoch is None:
            return None
        return max(0, self.target - self.done_epoch) * spe
