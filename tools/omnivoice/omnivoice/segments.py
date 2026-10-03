from dataclasses import dataclass
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


# ---------------- transcript-driven planning ----------------

@dataclass(frozen=True)
class Word:
    """One recognised word on the source file's timeline (seconds)."""
    start: float
    end: float
    text: str
    prob: float = 1.0       # recogniser's word probability
    no_speech: float = 0.0  # no-speech probability of the recogniser segment it came from

_CLOSERS = "\"'»”’)]"
_FINAL = (".", "!", "?", "…")

def _ends_sentence(w: Word) -> bool:
    return w.text.strip().rstrip(_CLOSERS).endswith(_FINAL)

def _span(ws: list[Word]) -> float:
    return ws[-1].end - ws[0].start

def _split_long(ws: list[Word], limit: float) -> list[list[Word]]:
    if _span(ws) <= limit or len(ws) < 2:
        return [ws]
    k = max(range(1, len(ws)), key=lambda i: ws[i].start - ws[i - 1].end)
    return _split_long(ws[:k], limit) + _split_long(ws[k:], limit)

def plan_from_words(words: list[Word], *, total: float | None = None, min_s: float = 1.0, max_s: float = 15.0,
                    target_s: float = 10.0, split_gap: float = 0.5, merge_gap: float = 0.6,
                    pad: float = 0.15, energy: Callable[[float, float], float] | None = None,
                    quiet: float = 0.0, snap: float = 1.5) -> list[tuple[float, float, str]]:
    """Cut a transcript into dataset phrases, one sentence (game line) each.

    Sentences end at . ! ? … and at word gaps >= split_gap; a sentence longer than max_s is split at
    its largest word gap. Cut points take up to `pad` of real audio around the words but never pass
    the middle of the gap to a neighbouring word (nor [0, total]). A piece whose clip would be shorter
    than min_s (cut span + 2*pad of zero padding added by audio.pad) is merged into the closer
    neighbour when that gap <= merge_gap and the result stays <= target_s, otherwise dropped.
    Returns (start, end, text); every cut span is <= max_s.

    With `energy(a, b)` (RMS of the audio between a and b) Whisper's imprecise word timestamps are
    corrected: the boundary between two pieces moves to the quietest point between the middles of the
    two neighbouring words (at most `snap` s from the gap middle), and each side is trimmed to `pad` before
    the real onset / after the real offset, i.e. where energy rises above `quiet`."""
    ws = sorted((w for w in words if w.text.strip()), key=lambda w: w.start)
    if not ws:
        return []
    sentences: list[list[Word]] = [[ws[0]]]
    for prev, w in zip(ws, ws[1:]):
        if _ends_sentence(prev) or w.start - prev.end >= split_gap:
            sentences.append([w])
        else:
            sentences[-1].append(w)
    pos = {id(w): k for k, w in enumerate(ws)}

    win, step = 0.02, 0.01
    level = (lambda t: energy(t - win, t + win)) if energy else None
    end_of_file = total if total is not None else ws[-1].end + pad

    def boundary(k: int) -> float:
        """Cut point before ws[k] (k == 0: file start, k == len(ws): file end)."""
        if k == 0:
            first = ws[0]
            mid = max(0.0, first.start - pad)
            lo, hi = max(0.0, mid - snap), (first.start + first.end) / 2
        elif k == len(ws):
            last = ws[-1]
            mid = min(end_of_file, last.end + pad)
            lo, hi = (last.start + last.end) / 2, min(end_of_file, mid + snap)
        else:
            a, b = ws[k - 1], ws[k]
            mid = (a.end + b.start) / 2
            lo, hi = max((a.start + a.end) / 2, mid - snap), min((b.start + b.end) / 2, mid + snap)
        if not level:
            return mid
        n = max(0, int((hi - lo) / step))
        grid = [(t, level(t)) for t in (lo + i * (hi - lo) / max(1, n) for i in range(n + 1))]
        floor = min(v for _, v in grid)
        return min((t for t, v in grid if v <= floor * 1.1 + 1e-9), key=lambda t: abs(t - mid))

    def cut(piece: list[Word]) -> list:
        i, j = pos[id(piece[0])], pos[id(piece[-1])]
        q0, q1 = boundary(i), boundary(j + 1)
        start, end = max(q0, piece[0].start - pad), min(q1, piece[-1].end + pad)
        if level:
            t = q0
            while t < piece[0].end and level(t) <= quiet:
                t += step
            start = max(q0, min(t, piece[0].start) - pad) if t < piece[0].end else start
            t = q1
            while t > piece[-1].start and level(t) <= quiet:
                t -= step
            end = min(q1, max(t, piece[-1].end) + pad) if t > piece[-1].start else end
        start, end = max(0.0, start), min(end, end_of_file)
        if end - start > max_s:   # snapping reached far into untranscribed sound: fall back to the words
            start, end = max(start, piece[0].start - pad), min(end, piece[-1].end + pad)
        return [start, end, piece]

    items = [cut(part) for snt in sentences for part in _split_long(snt, max_s - 2 * pad)]
    short = lambda it: it[1] - it[0] + 2 * pad < min_s
    gap = lambda a, b: b[2][0].start - a[2][-1].end
    fits = lambda a, b: gap(a, b) <= merge_gap and b[2][-1].end - a[2][0].start <= target_s
    out: list = []
    for k, it in enumerate(items):
        if not short(it):
            out.append(it)
            continue
        nxt = items[k + 1] if k + 1 < len(items) else None
        to_prev = bool(out) and out[-1][2][-1] is ws[pos[id(it[2][0])] - 1] and fits(out[-1], it)
        to_next = nxt is not None and fits(it, nxt)
        if to_prev and (not to_next or gap(out[-1], it) <= gap(it, nxt)):
            out[-1] = [out[-1][0], it[1], out[-1][2] + it[2]]
        elif to_next:
            items[k + 1] = [it[0], nxt[1], it[2] + nxt[2]]
    return [(round(s, 3), round(e, 3), "".join(w.text for w in piece).strip()) for s, e, piece in out]


def uncovered(words: list[Word], loud: list[Span], min_len: float = 0.4, slack: float = 0.1) -> list[Span]:
    """Parts of the loud (speech-like) spans that no recognised word covers, at least min_len long:
    lines Whisper skipped, worth recognising again on their own."""
    covered = sorted((w.start - slack, w.end + slack) for w in words)
    out: list[Span] = []
    for s, e in sorted(loud):
        cur = s
        for cs, ce in covered:
            if ce <= cur or cs >= e:
                continue
            if cs > cur:
                out.append((cur, cs))
            cur = max(cur, ce)
        if cur < e:
            out.append((cur, e))
    return [(round(a, 3), round(b, 3)) for a, b in out if b - a >= min_len]
