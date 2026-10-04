"""Verdict on one synthetic phrase: did the teacher say the text, at a sane pace, without long gaps,
clipping or an impossible length (spec «Фильтр брака»)."""
from __future__ import annotations
import re
import numpy as np
from omnivoice.audio import clipping_ratio

CER_OK, CER_BAD = 0.10, 0.30
RATIO_OK, RATIO_BAD = (0.6, 1.7), 2.5
PAUSE_MAX = 1.2          # s
PAUSE_DB = -40.0         # below the peak
CLIP_MAX = 0.005
LENGTH = (0.8, 15.0)     # s, piper's comfortable range
REASONS = {"text": "Whisper услышал другое", "fast": "слишком быстро (проглочены слова?)",
           "slow": "слишком медленно (паузы, зацикливание?)", "pause": "длинная пауза внутри",
           "clip": "перегруз (клиппинг)", "length": "слишком короткая или длинная"}
_RANK = {"accepted": 0, "suspect": 1, "rejected": 2}


def normalize(text: str) -> str:
    t = text.lower().replace("ё", "е")
    return " ".join(re.sub(r"[^\w\s]|_", " ", t).split())


def cer(expected: str, heard: str) -> float:
    a, b = normalize(expected), normalize(heard or "")
    if not a:
        return 0.0 if not b else 1.0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return min(1.0, prev[-1] / len(a))


def longest_pause(x: np.ndarray, sr: int, frame: float = 0.02) -> float:
    """Longest run of 20 ms frames quieter than PAUSE_DB below the peak, between the first and last sound."""
    n = max(1, int(sr * frame))
    frames = len(x) // n
    if not frames:
        return 0.0
    rms = np.sqrt(np.mean(x[:frames * n].reshape(frames, n) ** 2, axis=1) + 1e-12)
    loud = 20 * np.log10(rms / (np.max(np.abs(x)) + 1e-9)) > PAUSE_DB
    idx = np.flatnonzero(loud)
    if len(idx) < 2:
        return 0.0
    gaps = np.diff(idx) - 1
    return float(gaps.max() * frame) if len(gaps) else 0.0


def verdict(text: str, heard: str | None, x: np.ndarray, sr: int, expected_s: float) -> tuple[str, list[str]]:
    seconds = len(x) / sr
    if not LENGTH[0] <= seconds <= LENGTH[1]:
        return "rejected", ["length"]
    if heard is None:
        return "unchecked", []
    checks: list[tuple[str, str]] = []
    c = cer(text, heard)
    if c > CER_OK:
        checks.append(("rejected" if c > CER_BAD else "suspect", "text"))
    ratio = seconds / expected_s if expected_s > 0 else 1.0
    if ratio > RATIO_BAD:
        checks.append(("rejected", "slow"))
    elif ratio > RATIO_OK[1]:
        checks.append(("suspect", "slow"))
    elif ratio < RATIO_OK[0]:
        checks.append(("suspect", "fast"))
    if longest_pause(x, sr) > PAUSE_MAX:
        checks.append(("suspect", "pause"))
    if clipping_ratio(x) > CLIP_MAX:
        checks.append(("suspect", "clip"))
    if not checks:
        return "accepted", []
    worst = max(checks, key=lambda v: _RANK[v[0]])[0]
    return worst, [code for _, code in checks]
