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
