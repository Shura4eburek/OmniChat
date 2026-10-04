"""Texts for synthetic speech: a bundled open corpus (Common Voice sentences, CC0) plus the user's own
lines. Chosen greedily so that every next sentence adds the most new letter pairs — Russian spelling is
close to pronunciation, so this approximates covering the language's sound combinations."""
from __future__ import annotations
import re
from importlib import resources

_WORD = re.compile(r"[А-Яа-яЁё-]+")
_BAD = re.compile(r"[0-9A-Za-z]|\b[А-ЯЁ]{2,}\b")  # digits, latin, abbreviations (2+ capitals)


def good_sentence(s: str) -> bool:
    s = s.strip()
    words = _WORD.findall(s)
    return 4 <= len(words) <= 20 and not _BAD.search(s) and s[-1:] in ".!?…"


def load(language: str) -> list[str]:
    try:
        text = resources.files("omnivoice.data").joinpath(f"corpus_{language}.txt").read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError):
        return []
    return [line.strip() for line in text.splitlines() if line.strip()]


def _bigrams(s: str) -> set[str]:
    t = re.sub(r"[^а-яё ]", "", s.lower().replace("ё", "е"))
    return {t[i:i + 2] for i in range(len(t) - 1)}


def pick(corpus: list[str], user_lines: list[str], minutes: float,
         chars_per_sec: float) -> list[tuple[str, str]]:
    """User lines first (blank ones skipped), then corpus sentences until about `minutes` of speech
    at `chars_per_sec`; each next one brings the most letter pairs not seen yet."""
    budget = max(0.0, minutes) * 60 * max(1.0, chars_per_sec)
    out = [(s.strip(), "user") for s in user_lines if s.strip()]
    used = sum(len(t) for t, _ in out)
    seen: set[str] = set().union(*(_bigrams(t) for t, _ in out)) if out else set()
    pool = [(s, _bigrams(s)) for s in dict.fromkeys(corpus)]
    while pool and used < budget:
        i = max(range(len(pool)), key=lambda k: (len(pool[k][1] - seen), -k))
        s, grams = pool.pop(i)
        out.append((s, "corpus"))
        seen |= grams
        used += len(s)
    return out
