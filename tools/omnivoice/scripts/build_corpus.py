"""One-off: build omnivoice/data/corpus_ru.txt from Common Voice sentences (CC0).
Run from tools/omnivoice:  .venv/Scripts/python scripts/build_corpus.py"""
import random
import urllib.request
from pathlib import Path

from omnivoice.corpus import good_sentence

URL = "https://raw.githubusercontent.com/common-voice/common-voice/main/server/data/ru/sentence-collector.txt"
OUT = Path(__file__).resolve().parents[1] / "omnivoice/data/corpus_ru.txt"
N = 5000

text = urllib.request.urlopen(URL, timeout=60).read().decode("utf-8")
lines = sorted({s.strip() for s in text.splitlines() if good_sentence(s)})
random.Random(60).shuffle(lines)  # #60: fixed seed, reproducible file
OUT.write_text("\n".join(lines[:N]) + "\n", encoding="utf-8")
print(f"{min(N, len(lines))} of {len(lines)} good sentences → {OUT}")
