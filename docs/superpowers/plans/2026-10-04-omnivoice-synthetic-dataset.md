# omnivoice: синтетический датасет (XTTS v2) — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** По нескольким оригинальным фразам персонажа сгенерировать 10–30 минут речи его голосом моделью XTTS v2, отфильтровать брак (Whisper + проверки аудио), дать пользователю досмотреть спорное и обучать Piper на оригинале (с весом) плюс принятой синтетике.

**Architecture:** Новая папка проекта `synth/` с `synth.json`; модули `corpus` (тексты), `synth_check` (вердикты), `synth` (хранилище и план), `teacher` (запуск генерации) и скрипт `piper_compat/xtts_gen.py`, который работает в отдельном venv `/opt/omnivoice/xtts` WSL-дистрибутива omnivoice. Обучение собирает `train/audio/` из жёстких ссылок и пишет csv с повтором оригинала. UI: новый шаг «Синтетика» и фоновый `SynthRunner` по образцу `TrainRunner`.

**Tech Stack:** Python 3.11+ (uv), Gradio 6, numpy/soundfile/soxr, faster-whisper (Windows-хост), WSL2 Ubuntu 24.04, coqui-tts 0.27.5 (XTTS v2), torch 2.8.0+cu126 в отдельном venv.

**Spec:** `docs/superpowers/specs/2026-10-04-omnivoice-synthetic-dataset-design.md`

Все пути ниже — относительно `tools/omnivoice/`, если не указано иное. Тесты: `.venv/Scripts/python -m pytest -q tests` (из `tools/omnivoice`). Перед стартом прочитать `.wolf/cerebrum.md` (правила UI: HUD-карточки, кнопки 40 px, текст по краю рамок, проверка при 1× и 3×; Gradio CSS-перезапись выкидывает `border:`-сокращение с последующим longhand).

## Global Constraints

- Язык первой версии — только русский (`language == "ru"`); английский — не делать, но не мешать: корпус и выбор файла по коду языка.
- XTTS v2 — лицензия CPML (некоммерческая): в README omnivoice пометка «голоса, обученные с синтетикой XTTS, — только для некоммерческого использования».
- Окружение XTTS — отдельный venv `/opt/omnivoice/xtts` в дистрибутиве `omnivoice`; основной `/opt/omnivoice/venv` (piper) не трогать.
- Пины XTTS-окружения: `torch==2.8.0+cu126`, `torchaudio==2.8.0+cu126`, `coqui-tts==0.27.5`, `transformers==4.57.1` (индекс `https://download.pytorch.org/whl/cu126`). Лицензию принимать через `COQUI_TOS_AGREED=1`.
- Установка XTTS — только по явному выбору пользователя (галочка на «Установке»), ≈ 3–4 ГБ; без GPU NVIDIA — недоступна.
- Синтетика: `synth/wavs/synth_NNNN.wav`, приводится к `p.sample_rate` (22 050 Гц), моно, PCM 16 бит.
- По умолчанию: 15 минут синтетики, 3–5 образцов (3–12 с каждый, суммарно ≤ 30 с), вес оригинала ×3.
- Пороги фильтра (точно): `cer` ≤ 0.10 принято, 0.10–0.30 спорно, > 0.30 брак; длительность/ожидаемая 0.6–1.7 принято, < 0.6 или 1.7–2.5 спорно, > 2.5 брак; пауза внутри > 1.2 с (тише −40 дБ от пика) спорно; клиппинг > 0.5 % спорно; длина вне 0.8–15 с брак.
- Спорное по умолчанию не идёт в обучение; ручное решение пользователя (`manual`) важнее автоматического и переживает повторную проверку.
- Мягкий «Стоп» генерации: файл `synth/STOP`, принудительно через 60 с.
- Все тексты UI — по-русски, в `ui/strings.py`; все UPPERCASE-имена в `strings.py` — простые строки (`test_strings_have_no_empty_values`).

## Review Focus

- Пустые фразы пользователя и строки из пробелов в «Свои фразы» → игнорируются, не создают пустых `items`.
- Проект без оригинальных фраз (или все выкинуты) → «Сгенерировать» неактивна и объясняет почему; `choose_refs` возвращает `[]`, `speech_rate` — разумное значение по умолчанию (14 символов/с).
- Повторное «Сгенерировать» после ручных решений → решения сохранены, сгенерированное заново не теряет `manual`.
- Остановка посреди фразы → недописанный wav не попадает в `done` (скрипт пишет через `.part` + `os.replace`).
- Обучение без синтетики (папки `synth/` нет или галочка снята) → набор = только оригинал, вес 1, поведение как до изменений.

Тест на каждую строку добавлен в задачу-владельца (Task 1, 3, 3, 4, 6 соответственно).

---

## File Structure

| Файл | Статус | Ответственность |
|---|---|---|
| `scripts/build_corpus.py` | create | Одноразовая сборка `corpus_ru.txt` из Common Voice (CC0). Не входит в пакет. |
| `omnivoice/data/corpus_ru.txt` | create | ~5 000 отобранных предложений. |
| `omnivoice/corpus.py` | create | `load(lang)`, `good_sentence(s)`, `pick(...)`. |
| `omnivoice/synth_check.py` | create | `normalize`, `cer`, `longest_pause`, `verdict`. |
| `omnivoice/synth.py` | create | `SynthItem`, `load/save`, `choose_refs`, `speech_rate`, `make_plan`, `sync_generated`, `apply_check`, `set_manual`, `summary`, `training_items`, `settings`. |
| `omnivoice/project.py` | modify | `STEPS` + `synth`, свойство `synth_dir`. |
| `omnivoice/piper_compat/xtts_gen.py` | create | Генерация в WSL: задание JSON → wav + `ITEM n/N id`, `.part`, `STOP`. |
| `omnivoice/piper_compat/xtts_setup.sh`, `xtts_constraints.txt` | create | Провижининг `/opt/omnivoice/xtts` + пробная генерация. |
| `omnivoice/wslenv.py` | modify | `XTTS_VERSION`, `xtts_ready(run)`, `provision_xtts(on_line)`. |
| `omnivoice/deps.py` | modify | Пункт чек-листа «Синтетика (XTTS v2)», `install_all(..., with_xtts=False)`. |
| `omnivoice/teacher.py` | create | `Teacher` протокол, `XttsTeacher` (команда, поток, мягкий стоп). |
| `omnivoice/dataset.py`, `omnivoice/train.py` | modify | csv с весом и синтетикой; `build_audio_dir`; `--data.audio_dir` → `train/audio/`. |
| `omnivoice/ui/helpers.py` | modify | `SynthRunner`, HTML-хелперы синтетики, шаги. |
| `omnivoice/ui/app.py`, `ui/strings.py`, `ui/theme.py` | modify | Страница «Синтетика», галочка установки, строка на «Обучении». |
| `README.md` | modify | Раздел «Синтетика» + лицензия. |
| `tests/test_corpus.py`, `tests/test_synth_check.py`, `tests/test_synth.py`, `tests/test_teacher.py`, `tests/test_xtts_gen.py` | create | Тесты новых модулей. |
| `tests/test_train.py`, `tests/test_wslenv.py`, `tests/test_deps.py`, `tests/test_ui.py`, `tests/test_ui_helpers.py` | modify | Тесты изменённых. |

---

### Task 1: Корпус текстов

**Files:**
- Create: `scripts/build_corpus.py`, `omnivoice/data/corpus_ru.txt`, `omnivoice/corpus.py`
- Modify: `pyproject.toml` (включить `omnivoice/data/*.txt` в пакет, если сборка пакета их не берёт)
- Test: `tests/test_corpus.py`

**Interfaces:**
- Produces: `corpus.good_sentence(s: str) -> bool`; `corpus.load(language: str) -> list[str]`; `corpus.pick(corpus: list[str], user_lines: list[str], minutes: float, chars_per_sec: float) -> list[tuple[str, str]]` (пары `(text, source)`, `source` ∈ `"user" | "corpus"`).

- [ ] **Step 1: Write the failing test** — `tests/test_corpus.py`

```python
from omnivoice import corpus


def test_good_sentence_rules():
    assert corpus.good_sentence("Во славу Плети, и пусть никто не уйдёт живым.")
    assert not corpus.good_sentence("Слишком коротко.")                       # < 4 слов
    assert not corpus.good_sentence("В 1999 году всё изменилось навсегда.")   # цифры
    assert not corpus.good_sentence("Он открыл Windows и ушёл.")             # латиница
    assert not corpus.good_sentence("Сотрудники МВД и ФСБ пришли рано утром.")  # аббревиатуры
    assert not corpus.good_sentence(" ".join(["слово"] * 21) + ".")           # > 20 слов


def test_pick_user_lines_first_and_minutes_budget():
    pool = [f"Это предложение номер {w} для проверки выбора." for w in
            ("один", "два", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять", "десять")]
    out = corpus.pick(pool, ["Ты не надейся на быструю смерть!", "   ", ""], minutes=0.1, chars_per_sec=10)
    assert out[0] == ("Ты не надейся на быструю смерть!", "user")
    assert all(src == "corpus" for _, src in out[1:]) and len(out) < 1 + len(pool)
    budget = 0.1 * 60 * 10  # символов
    assert sum(len(t) for t, _ in out[:-1]) < budget <= sum(len(t) for t, _ in out) + len(out[-1][0])


def test_pick_prefers_new_bigrams():
    pool = ["ааа ааа ааа ааа", "бвг дежз ийк лмн", "ааа ааа ааа ааб"]
    out = corpus.pick(pool, [], minutes=0.02, chars_per_sec=10)
    assert out[0][0] == "бвг дежз ийк лмн"


def test_bundled_russian_corpus():
    lines = corpus.load("ru")
    assert len(lines) >= 3000 and all(corpus.good_sentence(s) for s in lines[:200])
    assert corpus.load("xx") == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python -m pytest -q tests/test_corpus.py`
Expected: FAIL — `ImportError: cannot import name 'corpus'`.

- [ ] **Step 3: Implement `omnivoice/corpus.py`**

```python
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
```

Также создать пустой `omnivoice/data/__init__.py` (пакет для `importlib.resources`).

- [ ] **Step 4: Write `scripts/build_corpus.py` and build the file**

```python
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
```

Run: `.venv/Scripts/python scripts/build_corpus.py` → файл ≈ 400–600 КБ. Добавить первой строкой README-заметку в `omnivoice/data/README.md`: «corpus_ru.txt — предложения Common Voice (CC0, https://github.com/common-voice/common-voice), отобраны scripts/build_corpus.py».

- [ ] **Step 5: Ensure the data file ships** — проверить `pyproject.toml`: если используется hatchling/setuptools без package-data, добавить включение `omnivoice/data/*.txt`. Проверка: `.venv/Scripts/python -c "from omnivoice import corpus; print(len(corpus.load('ru')))"` → ≥ 3000.

- [ ] **Step 6: Run tests** — `.venv/Scripts/python -m pytest -q tests/test_corpus.py` → PASS.

- [ ] **Step 7: Commit**

```bash
git add tools/omnivoice/scripts/build_corpus.py tools/omnivoice/omnivoice/corpus.py tools/omnivoice/omnivoice/data tools/omnivoice/tests/test_corpus.py tools/omnivoice/pyproject.toml
git commit -m "feat(omnivoice): add a cc0 russian corpus for synthetic speech"
```

---

### Task 2: Проверка синтетической фразы (`synth_check`)

**Files:**
- Create: `omnivoice/synth_check.py`
- Test: `tests/test_synth_check.py`

**Interfaces:**
- Produces: `normalize(text) -> str`; `cer(expected, heard) -> float`; `longest_pause(x: np.ndarray, sr: int) -> float`; `verdict(text: str, heard: str | None, x: np.ndarray, sr: int, expected_s: float) -> tuple[str, list[str]]` — вердикт `"accepted" | "suspect" | "rejected" | "unchecked"` и коды причин из `REASONS`; `REASONS: dict[str, str]` (код → русский текст).

- [ ] **Step 1: Write the failing test** — `tests/test_synth_check.py`

```python
import numpy as np
from omnivoice import synth_check as sc

SR = 22050


def tone(seconds, amp=0.3):
    t = np.arange(int(SR * seconds)) / SR
    return (amp * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def test_normalize_and_cer():
    assert sc.normalize("Ещё раз, ГЛУПЕЦ!") == "еще раз глупец"
    assert sc.cer("Говори, глупец!", "говори глупец") == 0.0
    assert 0.0 < sc.cer("никто не смеет", "никто не сметь") <= 0.2
    assert sc.cer("абв", "") == 1.0


def test_longest_pause():
    x = np.concatenate([tone(1), np.zeros(int(SR * 1.5), np.float32), tone(1)])
    assert 1.4 < sc.longest_pause(x, SR) < 1.6
    assert sc.longest_pause(tone(2), SR) < 0.05


def test_verdicts():
    ok = sc.verdict("Во славу Плети!", "во славу плети", tone(1.5), SR, expected_s=1.5)
    assert ok == ("accepted", [])
    v, why = sc.verdict("Во славу Плети!", "во славу плоти", tone(1.5), SR, expected_s=1.5)
    assert v == "suspect" and why == ["text"]
    assert sc.verdict("Во славу Плети!", "совсем другое что-то", tone(1.5), SR, 1.5)[0] == "rejected"
    assert sc.verdict("Во славу Плети!", "во славу плети", tone(0.5), SR, 0.5) == ("rejected", ["length"])
    assert sc.verdict("Во славу Плети!", "во славу плети", tone(4.0), SR, 1.5)[1] == ["slow"]      # 2.67×
    assert sc.verdict("Во славу Плети!", "во славу плети", tone(3.0), SR, 1.5) == ("suspect", ["slow"])  # 2×
    gap = np.concatenate([tone(0.6), np.zeros(int(SR * 1.3), np.float32), tone(0.6)])
    assert sc.verdict("Во славу Плети!", "во славу плети", gap, SR, 2.5) == ("suspect", ["pause"])
    hot = tone(1.5, amp=1.2)
    assert "clip" in sc.verdict("Во славу Плети!", "во славу плети", hot, SR, 1.5)[1]
    assert sc.verdict("Во славу Плети!", None, tone(1.5), SR, 1.5) == ("unchecked", [])
    assert set(sc.REASONS) >= {"text", "fast", "slow", "pause", "clip", "length"}
```

- [ ] **Step 2: Run to verify it fails** — `pytest -q tests/test_synth_check.py` → FAIL (`ImportError`).

- [ ] **Step 3: Implement `omnivoice/synth_check.py`**

```python
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
```

- [ ] **Step 4: Run tests** — `pytest -q tests/test_synth_check.py` → PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/omnivoice/omnivoice/synth_check.py tools/omnivoice/tests/test_synth_check.py
git commit -m "feat(omnivoice): add the synthetic phrase check"
```

---

### Task 3: Хранилище синтетики и план (`synth`)

**Files:**
- Create: `omnivoice/synth.py`
- Modify: `omnivoice/project.py` (`STEPS`, `synth_dir`)
- Test: `tests/test_synth.py`

**Interfaces:**
- Consumes: `corpus.pick`, `corpus.load`, `synth_check.verdict`, `dataset.load`, `audio.load_mono`, `project.atomic_write_text`.
- Produces:
  - `@dataclass SynthItem(id: str, text: str, source: str, status: str = "pending", duration: float = 0.0, heard: str | None = None, cer: float | None = None, verdict: str = "unchecked", reasons: list[str] = [], dropped: bool = True, manual: str | None = None, error: str | None = None)`
  - `@dataclass SynthState(refs: list[str], items: list[SynthItem], use: bool = True, weight: int = 3)`
  - `load(p) -> SynthState`, `save(p, state)`, `wav(p, item_id) -> Path`, `lines(p) -> list[str]`, `save_lines(p, text: str)`
  - `choose_refs(segments) -> list[str]`, `speech_rate(segments) -> float`
  - `make_plan(p, minutes: float, refs: list[str]) -> SynthState`
  - `sync_generated(p, state) -> SynthState` (wav есть → `done` + длительность)
  - `apply_check(p, state, recognize: Callable[[Path], str] | None) -> SynthState`
  - `set_manual(p, item_id: str, decision: str | None) -> SynthState` (`"accept" | "drop" | None`)
  - `summary(state) -> dict` (`accepted`, `accepted_min`, `suspect`, `rejected`, `failed`, `pending`)
  - `training_items(p) -> list[SynthItem]` (используемые в обучении)
- `project.STEPS == ("audio", "slice", "phrases", "check", "synth", "train", "pack")`; `Project.synth_dir == root / "synth"`.

- [ ] **Step 1: Write the failing test** — `tests/test_synth.py`

```python
import numpy as np
import pytest
from omnivoice import audio, dataset, synth
from omnivoice.dataset import Segment
from omnivoice.project import Project, STEPS


def project(tmp_path, durations=(4.0, 6.0, 2.0, 8.0, 13.0)):
    p = Project.create(tmp_path / "a", name="a", language="ru")
    segs = []
    for i, d in enumerate(durations):
        audio.write_wav(p.segments_dir / f"s{i}.wav", np.zeros(int(audio.SR * d), np.float32))
        segs.append(Segment(f"s{i}", "раз два три четыре пять шесть"[: 10 + i], d))
    dataset.save(p, segs)
    return p


def test_steps_and_dir(tmp_path):
    assert STEPS.index("synth") == STEPS.index("check") + 1 < STEPS.index("train")
    assert Project.create(tmp_path / "b", name="b", language="ru").synth_dir.name == "synth"


def test_choose_refs_and_rate(tmp_path):
    segs = dataset.load(project(tmp_path))
    refs = synth.choose_refs(segs)
    assert refs == ["s3", "s1", "s0"]                   # 3–12 s, longest first, ≤ 30 s, flagged/dropped skipped
    assert synth.choose_refs([]) == [] and synth.speech_rate([]) == 14.0
    segs[3].flags = ["check"]
    assert "s3" not in synth.choose_refs(segs)


def test_plan_lines_and_roundtrip(tmp_path):
    p = project(tmp_path)
    synth.save_lines(p, "Ты не надейся на быструю смерть!\n   \n")
    st = synth.make_plan(p, minutes=0.2, refs=["s1"])
    assert st.items[0].text == "Ты не надейся на быструю смерть!" and st.items[0].source == "user"
    assert all(i.status == "pending" and i.id.startswith("synth_") for i in st.items)
    synth.save(p, st)
    again = synth.load(p)
    assert again.items == st.items and again.refs == ["s1"] and again.weight == 3


def test_sync_check_manual_and_training(tmp_path):
    p = project(tmp_path)
    st = synth.make_plan(p, minutes=0.1, refs=["s1"])
    a, b, c = st.items[:3]
    for it, sec in ((a, 2.0), (b, 2.0), (c, 0.3)):
        audio.write_wav(synth.wav(p, it.id), (0.2 * np.sin(np.arange(int(audio.SR * sec)) / 9)).astype(np.float32))
    st = synth.sync_generated(p, st)
    assert [i.status for i in st.items[:3]] == ["done"] * 3 and st.items[3].status == "pending"
    heard = {a.id: a.text, b.id: "что-то совсем другое и не то", c.id: c.text}
    st = synth.apply_check(p, st, lambda wav: heard[wav.stem])
    v = {i.id: (i.verdict, i.dropped) for i in st.items[:3]}
    assert v[a.id][1] is False and v[b.id] == ("rejected", True) and v[c.id] == ("rejected", True)
    synth.save(p, st)
    st = synth.set_manual(p, b.id, "accept")
    st = synth.apply_check(p, st, lambda wav: heard[wav.stem])      # a re-check keeps the manual decision
    assert next(i for i in st.items if i.id == b.id).dropped is False
    synth.save(p, st)
    ids = {i.id for i in synth.training_items(p)}
    assert b.id in ids and c.id not in ids and (a.id in ids) == (not next(i for i in st.items if i.id == a.id).dropped)
    s = synth.summary(st)
    assert s["rejected"] == 1 and s["pending"] == len(st.items) - 3


def test_plan_keeps_done_and_manual(tmp_path):
    p = project(tmp_path)
    st = synth.make_plan(p, minutes=0.1, refs=["s1"])
    first = st.items[0]
    audio.write_wav(synth.wav(p, first.id), np.zeros(audio.SR * 2, np.float32))
    st = synth.sync_generated(p, st); first = st.items[0]; first.manual = "drop"; synth.save(p, st)
    st2 = synth.make_plan(p, minutes=0.1, refs=["s1"])                # same refs: kept
    kept = next(i for i in st2.items if i.text == first.text)
    assert kept.status == "done" and kept.manual == "drop"
    st3 = synth.make_plan(p, minutes=0.1, refs=["s0"])                # other refs: regenerate, manual kept
    redo = next(i for i in st3.items if i.text == first.text)
    assert redo.status == "pending" and redo.manual == "drop" and not synth.wav(p, redo.id).exists()


def test_no_synth_means_no_training_items(tmp_path):
    assert synth.training_items(project(tmp_path)) == []
    assert synth.load(project(tmp_path / "x")).items == []
```

- [ ] **Step 2: Run to verify it fails** — `pytest -q tests/test_synth.py` → FAIL.

- [ ] **Step 3: Modify `omnivoice/project.py`**

```python
STEPS = ("audio", "slice", "phrases", "check", "synth", "train", "pack")
```
and next to `segments_dir`:
```python
    synth_dir = property(lambda self: self.root / "synth")
```
`Project.load` already fills missing steps with `False` (old projects keep working).

- [ ] **Step 4: Implement `omnivoice/synth.py`**

```python
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


def make_plan(p, minutes: float, refs: list[str]) -> SynthState:
    """A fresh plan; phrases already generated with the same references keep their audio and verdict,
    every user decision is kept, the rest is (re)generated."""
    old = load(p)
    same_refs = old.refs == refs
    by_text = {it.text: it for it in old.items}
    segs = dataset.load(p)
    picked = corpus.pick(corpus.load(p.language), lines(p), minutes, speech_rate(segs))
    items = []
    for n, (text, source) in enumerate(picked, 1):
        prev = by_text.get(text)
        if prev is not None and same_refs and prev.status == "done":
            items.append(prev)
            continue
        item = SynthItem(f"synth_{n:04d}", text, source, manual=prev.manual if prev else None)
        if prev is not None and prev.id != item.id or not same_refs:
            wav(p, item.id).unlink(missing_ok=True)
        items.append(item)
    used = {it.id for it in items}
    for it in old.items:                       # files of phrases that left the plan
        if it.id not in used:
            wav(p, it.id).unlink(missing_ok=True)
    return SynthState(refs, items, old.use, old.weight)


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
            "rejected": sum(i.dropped and i.verdict == "rejected" for i in done),
            "failed": sum(i.status == "failed" for i in state.items),
            "pending": sum(i.status == "pending" for i in state.items)}


def training_items(p) -> list[SynthItem]:
    state = load(p)
    if not state.use:
        return []
    return [i for i in state.items if i.status == "done" and not i.dropped and wav(p, i.id).is_file()]
```

- [ ] **Step 5: Run tests** — `pytest -q tests/test_synth.py` → PASS. Then the full suite (`pytest -q tests`): fix tests that assert the old `STEPS` tuple or the 6-chip steps bar (they belong to Task 8's UI changes; if any fails here because of `STEPS`, update that assertion to the new tuple).

- [ ] **Step 6: Commit**

```bash
git add tools/omnivoice/omnivoice/synth.py tools/omnivoice/omnivoice/project.py tools/omnivoice/tests/test_synth.py
git commit -m "feat(omnivoice): add the synthetic phrase store and plan"
```

---

### Task 4: Генерация в WSL (`xtts_gen.py` + `teacher.py`)

**Files:**
- Create: `omnivoice/piper_compat/xtts_gen.py`, `omnivoice/teacher.py`
- Test: `tests/test_xtts_gen.py`, `tests/test_teacher.py`

**Interfaces:**
- Consumes: `synth.SynthState`, `synth.wav`, `wslenv.wsl_cmd`, `wslenv.wsl_path`.
- Produces:
  - Job JSON (written by teacher, read by script): `{"language": "ru", "sample_rate": 22050, "refs": [<wsl paths>], "out_dir": <wsl path>, "stop_file": <wsl path>, "items": [{"id": "synth_0001", "text": "..."}]}`.
  - Script stdout: `ITEM <n>/<N> <id>` after each written wav; `FAIL <id> <message>` on a failed phrase; exit 0 when done or stopped.
  - `xtts_gen.run_job(job: dict, synthesize: Callable[[str, list[str]], tuple[np.ndarray, int]], out=print) -> int` (pure, testable; `synthesize(text, ref_paths)` returns `(audio, sr)`).
  - `teacher.XTTS_PY = "/opt/omnivoice/xtts/bin/python"`; `teacher.GEN_SCRIPT = Path(.../piper_compat/xtts_gen.py)`; `teacher.STOP_FILE = "STOP"`.
  - `class XttsTeacher: name = "xtts"; command(job_path: Path) -> list[str]; write_job(p, state) -> Path; generate(p, state, on_line, popen=subprocess.Popen) -> int; request_stop(p); kill(run=subprocess.run)`.

- [ ] **Step 1: Write the failing tests**

`tests/test_xtts_gen.py`:
```python
import json
import numpy as np
import soundfile as sf
from omnivoice.piper_compat import xtts_gen


def test_run_job_writes_resampled_wavs_skips_existing_and_reports(tmp_path):
    (tmp_path / "synth_0002.wav").write_bytes(b"done before")
    job = {"language": "ru", "sample_rate": 22050, "refs": ["/r.wav"], "out_dir": str(tmp_path),
           "stop_file": str(tmp_path / "STOP"),
           "items": [{"id": "synth_0001", "text": "раз"}, {"id": "synth_0002", "text": "два"},
                     {"id": "synth_0003", "text": "boom"}]}
    said, lines = [], []

    def synthesize(text, refs):
        said.append(text)
        if text == "boom":
            raise RuntimeError("cuda oom")
        return np.zeros(24000, np.float32), 24000

    assert xtts_gen.run_job(job, synthesize, out=lines.append) == 0
    assert said == ["раз", "boom"]                                   # synth_0002 already there
    info = sf.info(str(tmp_path / "synth_0001.wav"))
    assert info.samplerate == 22050 and info.channels == 1 and info.subtype == "PCM_16"
    assert lines[0] == "ITEM 1/3 synth_0001" and lines[1].startswith("FAIL synth_0003 cuda oom")
    assert not list(tmp_path.glob("*.part"))


def test_run_job_stops_on_the_stop_file(tmp_path):
    job = {"language": "ru", "sample_rate": 22050, "refs": [], "out_dir": str(tmp_path),
           "stop_file": str(tmp_path / "STOP"), "items": [{"id": f"synth_{i:04d}", "text": "а"} for i in range(1, 4)]}

    def synthesize(text, refs):
        (tmp_path / "STOP").write_text("")
        return np.zeros(100, np.float32), 22050

    assert xtts_gen.run_job(job, synthesize, out=lambda s: None) == 0
    assert [f.name for f in tmp_path.glob("synth_*.wav")] == ["synth_0001.wav"]
```

`tests/test_teacher.py`:
```python
import json
from omnivoice import synth, teacher, wslenv
from omnivoice.project import Project


def test_job_and_command(tmp_path):
    p = Project.create(tmp_path / "a", name="a", language="ru")
    (p.segments_dir / "s1.wav").write_bytes(b"x")
    st = synth.SynthState(["s1"], [synth.SynthItem("synth_0001", "раз", "corpus"),
                                    synth.SynthItem("synth_0002", "два", "corpus", status="done")])
    t = teacher.XttsTeacher()
    job = json.loads(t.write_job(p, st).read_text(encoding="utf-8"))
    assert job["refs"] == [wslenv.wsl_path((p.segments_dir / "s1.wav").resolve())]
    assert [i["id"] for i in job["items"]] == ["synth_0001"]                 # only what is pending
    assert job["stop_file"].endswith("/synth/STOP") and job["sample_rate"] == 22050
    cmd = t.command(p.synth_dir / "job.json")
    assert cmd[:7] == wslenv.wsl_cmd(teacher.XTTS_PY)[:7] and cmd[-1].endswith("/synth/job.json")
    assert cmd[-2] == wslenv.wsl_path(teacher.GEN_SCRIPT)


def test_generate_streams_lines_and_stop_request(tmp_path):
    p = Project.create(tmp_path / "a", name="a", language="ru")
    st = synth.SynthState([], [synth.SynthItem("synth_0001", "раз", "corpus")])

    class Proc:
        stdout = iter([b"ITEM 1/1 synth_0001\n"])
        def wait(self): return 0

    seen = []
    assert teacher.XttsTeacher().generate(p, st, seen.append, popen=lambda *a, **k: Proc()) == 0
    assert seen == ["ITEM 1/1 synth_0001"]
    teacher.XttsTeacher().request_stop(p)
    assert (p.synth_dir / teacher.STOP_FILE).exists()
```

- [ ] **Step 2: Run to verify they fail** — `pytest -q tests/test_xtts_gen.py tests/test_teacher.py` → FAIL.

- [ ] **Step 3: Implement `omnivoice/piper_compat/xtts_gen.py`**

```python
"""Generate synthetic phrases with XTTS v2 (runs inside the WSL venv /opt/omnivoice/xtts).

python xtts_gen.py <job.json>   — see omnivoice.teacher for the job format. Prints `ITEM n/N id` after
every written wav and `FAIL id message` for a phrase that failed; stops between phrases when the job's
stop_file appears. Each wav goes through <id>.wav.part and os.replace, so a stop never leaves half a file.
"""
import json
import os
import sys
from pathlib import Path

import numpy as np


def _write(path: Path, x: np.ndarray, sr: int, target_sr: int) -> None:
    import soundfile as sf
    import soxr
    if sr != target_sr:
        x = soxr.resample(x.astype(np.float32), sr, target_sr)
    part = path.with_name(path.name + ".part")
    sf.write(str(part), np.clip(x, -1, 1), target_sr, subtype="PCM_16", format="WAV")
    os.replace(part, path)


def run_job(job: dict, synthesize, out=print) -> int:
    out_dir, stop = Path(job["out_dir"]), Path(job["stop_file"])
    out_dir.mkdir(parents=True, exist_ok=True)
    items = job["items"]
    for n, it in enumerate(items, 1):
        if stop.exists():
            break
        target = out_dir / f"{it['id']}.wav"
        if target.exists():
            continue
        try:
            x, sr = synthesize(it["text"], job["refs"])
            _write(target, np.asarray(x, np.float32).reshape(-1), int(sr), int(job["sample_rate"]))
        except Exception as e:  # one phrase failing must not stop the rest
            out(f"FAIL {it['id']} {str(e).splitlines()[0] if str(e) else type(e).__name__}")
            continue
        out(f"ITEM {n}/{len(items)} {it['id']}")
    return 0


def xtts_synthesizer(language: str, refs: list[str]):
    """XTTS v2 with the conditioning computed once for all phrases."""
    import torch
    from TTS.api import TTS
    os.environ.setdefault("COQUI_TOS_AGREED", "1")
    tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to("cuda" if torch.cuda.is_available() else "cpu")
    model = tts.synthesizer.tts_model
    latent, speaker = model.get_conditioning_latents(audio_path=refs)
    sr = tts.synthesizer.output_sample_rate

    def synthesize(text, _refs):
        out = model.inference(text, language, latent, speaker, temperature=0.65, enable_text_splitting=True)
        return np.asarray(out["wav"], np.float32), sr
    return synthesize


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    job = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    return run_job(job, xtts_synthesizer(job["language"], job["refs"]), out=lambda s: print(s, flush=True))


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Implement `omnivoice/teacher.py`**

```python
"""The teacher model behind synthetic phrases (spec «Модули»). XttsTeacher writes a job, runs
piper_compat/xtts_gen.py in the WSL venv /opt/omnivoice/xtts and streams its lines."""
from __future__ import annotations
import json
import os
import subprocess
from pathlib import Path

from omnivoice import synth, wslenv

XTTS_PY = "/opt/omnivoice/xtts/bin/python"
GEN_SCRIPT = Path(__file__).resolve().parent / "piper_compat" / "xtts_gen.py"
STOP_FILE = "STOP"
STOP_GRACE = 60  # s before a stop turns into a kill


class XttsTeacher:
    name = "xtts"

    def write_job(self, p, state: "synth.SynthState") -> Path:
        p.synth_dir.mkdir(parents=True, exist_ok=True)
        job = {"language": p.language, "sample_rate": p.sample_rate,
               "refs": [wslenv.wsl_path((p.segments_dir / f"{r}.wav").resolve()) for r in state.refs],
               "out_dir": wslenv.wsl_path((p.synth_dir / "wavs").resolve()),
               "stop_file": wslenv.wsl_path((p.synth_dir / STOP_FILE).resolve()),
               "items": [{"id": i.id, "text": i.text} for i in state.items if i.status == "pending"]}
        path = p.synth_dir / "job.json"
        path.write_text(json.dumps(job, ensure_ascii=False, indent=1), encoding="utf-8")
        return path

    def command(self, job_path: Path) -> list[str]:
        return wslenv.wsl_cmd(XTTS_PY, "-W", "ignore", wslenv.wsl_path(GEN_SCRIPT),
                              wslenv.wsl_path(Path(job_path).resolve()))

    def generate(self, p, state, on_line, popen=subprocess.Popen) -> int:
        (p.synth_dir / STOP_FILE).unlink(missing_ok=True)
        proc = popen(self.command(self.write_job(p, state)), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                     env={**os.environ, "WSL_UTF8": "1"})
        for raw in proc.stdout:
            on_line(wslenv.decode(raw).rstrip("\r\n"))
        return proc.wait()

    def request_stop(self, p) -> None:
        p.synth_dir.mkdir(parents=True, exist_ok=True)
        (p.synth_dir / STOP_FILE).touch()

    def kill(self, run=subprocess.run) -> None:
        run(wslenv.wsl_cmd("pkill", "-f", "piper_compat/xtts_gen.py"), capture_output=True)
```

- [ ] **Step 5: Run tests** — `pytest -q tests/test_xtts_gen.py tests/test_teacher.py` → PASS (the script's `xtts_synthesizer` is exercised only in the real run, Task 9).

- [ ] **Step 6: Commit**

```bash
git add tools/omnivoice/omnivoice/piper_compat/xtts_gen.py tools/omnivoice/omnivoice/teacher.py tools/omnivoice/tests/test_xtts_gen.py tools/omnivoice/tests/test_teacher.py
git commit -m "feat(omnivoice): generate synthetic phrases with xtts v2 in wsl"
```

---

### Task 5: Окружение XTTS (установка)

**Files:**
- Create: `omnivoice/piper_compat/xtts_setup.sh`, `omnivoice/piper_compat/xtts_constraints.txt`
- Modify: `omnivoice/wslenv.py`, `omnivoice/deps.py`
- Test: `tests/test_wslenv.py`, `tests/test_deps.py`

**Interfaces:**
- Produces: `wslenv.XTTS_VERSION: str`; `wslenv.XTTS_READY = "/opt/omnivoice/xtts/READY"`; `wslenv.xtts_ready(run=subprocess.run) -> bool`; `wslenv.provision_xtts(on_line, run=subprocess.run, popen=subprocess.Popen) -> None`; `deps.XTTS = "Синтетика (XTTS v2)"`; `deps.check_all()` gains an optional `Item(XTTS, ...)`; `deps.install_all(on_line, progress=None, run=subprocess.run, with_xtts: bool = False)`.

- [ ] **Step 1: Write the failing tests** (append)

`tests/test_wslenv.py`:
```python
def test_xtts_ready_and_provision(monkeypatch):
    from omnivoice import wslenv
    calls = []
    def run(cmd, **kw):
        calls.append(cmd)
        out = wslenv.XTTS_VERSION if cmd[-1] == wslenv.XTTS_READY else ""
        return subprocess.CompletedProcess(cmd, 0, stdout=out.encode(), stderr=b"")
    assert wslenv.xtts_ready(run)
    lines = []
    class Proc:
        stdout = iter([b"STEP 1/4 x\n", b"ok\n"])
        def wait(self): return 0
    wslenv.provision_xtts(lines.append, run=run, popen=lambda *a, **k: Proc())
    copied = [c for c in calls if "cat >" in " ".join(c)]
    assert any("xtts_setup.sh" in " ".join(c) for c in copied) and any("xtts_constraints.txt" in " ".join(c) for c in copied)
    assert lines == ["STEP 1/4 x", "ok"]
```
(`import subprocess` at the top of the file if missing.)

`tests/test_deps.py`:
```python
def test_xtts_item_is_optional_and_installed_only_on_request(monkeypatch):
    from omnivoice import deps, wslenv
    monkeypatch.setattr(deps, "prep_ok", lambda: True)
    monkeypatch.setattr(deps, "ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(deps, "host_gpu", lambda run=None: True)
    monkeypatch.setattr(wslenv, "status", lambda run=None: wslenv.EnvStatus(True, True, True, True, True, "ok"))
    monkeypatch.setattr(wslenv, "xtts_ready", lambda run=None: False)
    item = next(i for i in deps.check_all() if i.name == deps.XTTS)
    assert item.optional and not item.ok
    done = []
    monkeypatch.setattr(wslenv, "provision_xtts", lambda on_line, **kw: done.append(1))
    deps.install_all(lambda s: None)
    assert done == []
    deps.install_all(lambda s: None, with_xtts=True)
    assert done == [1]
```

- [ ] **Step 2: Run to verify they fail.**

- [ ] **Step 3: Create `omnivoice/piper_compat/xtts_constraints.txt`**

```
torch==2.8.0+cu126
torchaudio==2.8.0+cu126
coqui-tts==0.27.5
transformers==4.57.1
numpy<2.3
soundfile
soxr
```

- [ ] **Step 4: Create `omnivoice/piper_compat/xtts_setup.sh`** (LF line endings)

```bash
#!/usr/bin/env bash
# Builds /opt/omnivoice/xtts: a venv of its own for XTTS v2 (coqui-tts), apart from piper's venv.
# Idempotent; one "STEP n/4 title" line per step (parsed like wsl_setup.sh). Usage: bash xtts_setup.sh <version>
set -euo pipefail
VERSION="${1:?usage: xtts_setup.sh <version>}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV=/opt/omnivoice/xtts
TORCH_INDEX=https://download.pytorch.org/whl/cu126
C="$HERE/xtts_constraints.txt"
export DEBIAN_FRONTEND=noninteractive PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_INPUT=1 PIP_NO_CACHE_DIR=1 COQUI_TOS_AGREED=1
step() { echo "STEP $1/4 $2"; }
rm -f "$VENV/READY"

step 1 "Окружение Python для XTTS"
[ -x "$VENV/bin/python" ] || python3 -m venv --clear "$VENV"

step 2 "PyTorch 2.8 и coqui-tts"
"$VENV/bin/python" -m pip install --progress-bar off -c "$C" --extra-index-url "$TORCH_INDEX" \
  torch torchaudio coqui-tts transformers soundfile soxr

step 3 "Модель XTTS v2 (~1.8 ГБ)"
"$VENV/bin/python" -c 'from TTS.api import TTS; TTS("tts_models/multilingual/multi-dataset/xtts_v2")'

step 4 "Пробная генерация"
"$VENV/bin/python" - <<'EOF'
import numpy as np, soundfile as sf, tempfile, torch, os
from TTS.api import TTS
ref = os.path.join(tempfile.gettempdir(), "omnivoice_ref.wav")
sf.write(ref, (0.1 * np.sin(np.arange(22050 * 3) / 7)).astype("float32"), 22050)
tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to("cuda" if torch.cuda.is_available() else "cpu")
wav = tts.tts("Проверка связи.", speaker_wav=ref, language="ru")
assert len(wav) > 1000, "XTTS returned no audio"
print("xtts ok, cuda:", torch.cuda.is_available())
EOF
echo "$VERSION" > "$VENV/READY"
echo "XTTS v2 готов ($VERSION)"
```

If step 4 fails on the real machine (Task 9) because of a library version, change only `xtts_constraints.txt`, bump `XTTS_VERSION`, and note the reason in a comment line in the constraints file.

- [ ] **Step 5: Modify `omnivoice/wslenv.py`** — add after `SETUP_FILES`:

```python
XTTS_VERSION = "1 coqui-tts-0.27.5 torch-2.8.0+cu126"  # bump with xtts_setup.sh / xtts_constraints.txt
XTTS_READY = f"{ROOT}/xtts/READY"
XTTS_FILES = ("xtts_setup.sh", "xtts_constraints.txt")


def xtts_ready(run: Run = subprocess.run) -> bool:
    rc, out = _run(run, wsl_cmd("cat", XTTS_READY))
    return rc == 0 and out.strip() == XTTS_VERSION


def provision_xtts(on_line: Callable[[str], None], run: Run = subprocess.run, popen=subprocess.Popen) -> None:
    """Copy xtts_setup.sh + constraints into the distro and run it (≈ 3–4 GB the first time)."""
    for name in XTTS_FILES:
        data = (COMPAT_DIR / name).read_bytes().replace(b"\r\n", b"\n")
        rc, out = _run(run, wsl_cmd("sh", "-c", f"mkdir -p {SETUP_DIR} && cat > {SETUP_DIR}/{name}"), input=data)
        if rc != 0:
            raise WslError(f"Не удалось скопировать {name} в среду WSL «{DISTRO}»: {_hint(out)}")
    proc = popen(wsl_cmd("bash", f"{SETUP_DIR}/xtts_setup.sh", XTTS_VERSION), stdout=subprocess.PIPE,
                 stderr=subprocess.STDOUT, env={**os.environ, "WSL_UTF8": "1"})
    tail = []
    for raw in proc.stdout:
        line = decode(raw).rstrip("\r\n")
        tail = (tail + [line])[-8:]
        on_line(line)
    if proc.wait() != 0:
        raise WslError("Установка XTTS v2 не удалась. Повтори — готовые шаги не повторятся. Последние строки:\n"
                       + "\n".join(tail))
```

- [ ] **Step 6: Modify `omnivoice/deps.py`**

```python
XTTS = "Синтетика (XTTS v2)"
XTTS_DETAIL_MISSING = "не установлена (необязательно, ≈ 3–4 ГБ) — галочка «и XTTS v2» на этой странице"
```
In `check_all()`, append (only checked when the WSL environment is ready, otherwise optional & not ok):
```python
    xtts = bool(st.ready and wslenv.xtts_ready(run))
    items.append(Item(XTTS, xtts, "установлена" if xtts else XTTS_DETAIL_MISSING, optional=True))
```
(convert the returned list literal into `items = [...]` then `return items`.)
`install_all` signature becomes `install_all(on_line, progress=None, run=subprocess.run, with_xtts: bool = False)`; after the WSL environment block and before `on_line("Готово.")`:
```python
    if with_xtts and gpu_ok(items) and not _ok(items, XTTS):
        on_line("Устанавливаю XTTS v2 для синтетики…")
        wslenv.provision_xtts(on_line)
```
with helpers:
```python
def _ok(items, name):
    return any(i.name == name and i.ok for i in items)


def gpu_ok(items) -> bool:
    return not any(i.name == ENV and i.optional for i in items)  # ENV is optional only without an NVIDIA GPU
```

- [ ] **Step 7: Run tests** — `pytest -q tests/test_wslenv.py tests/test_deps.py` → PASS; full suite → PASS.

- [ ] **Step 8: Commit**

```bash
git add tools/omnivoice/omnivoice/piper_compat/xtts_setup.sh tools/omnivoice/omnivoice/piper_compat/xtts_constraints.txt tools/omnivoice/omnivoice/wslenv.py tools/omnivoice/omnivoice/deps.py tools/omnivoice/tests/test_wslenv.py tools/omnivoice/tests/test_deps.py
git commit -m "feat(omnivoice): optional xtts v2 environment in the wsl distro"
```

---

### Task 6: Обучение на оригинале + синтетике

**Files:**
- Modify: `omnivoice/dataset.py` (`piper_csv`), `omnivoice/train.py` (`build_audio_dir`, `fit_args`, `train_project`)
- Test: `tests/test_train.py`

**Interfaces:**
- Consumes: `synth.training_items(p)`, `synth.load(p).weight`, `synth.wav`.
- Produces: `dataset.piper_csv(p, out, synth_items=(), weight=1) -> int` (rows written); `train.build_audio_dir(p, synth_items) -> Path` (`p.train_dir / "audio"`); `fit_args(..., root)` uses `--data.audio_dir {root}/train/audio/`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_train.py`)

```python
def test_piper_csv_weights_original_and_adds_synth(tmp_path):
    import numpy as np
    from omnivoice import audio, dataset, synth
    from omnivoice.dataset import Segment
    p = Project.create(tmp_path / "a", name="a", language="ru")
    dataset.save(p, [Segment("s1", "раз", 1.0), Segment("s2", "", 1.0), Segment("s3", "три", 1.0, dropped=True)])
    item = synth.SynthItem("synth_0001", "четыре", "corpus", status="done", verdict="accepted", dropped=False)
    n = dataset.piper_csv(p, p.train_dir / "train.csv", [item], weight=3)
    rows = (p.train_dir / "train.csv").read_text(encoding="utf-8").splitlines()
    assert n == 4 and rows == ["s1.wav|раз"] * 3 + ["synth_0001.wav|четыре"]


def test_build_audio_dir_links_both(tmp_path):
    import numpy as np
    from omnivoice import audio, synth
    p = Project.create(tmp_path / "a", name="a", language="ru")
    audio.write_wav(p.segments_dir / "s1.wav", np.zeros(100, np.float32))
    synth.wav(p, "synth_0001").parent.mkdir(parents=True)
    audio.write_wav(synth.wav(p, "synth_0001"), np.zeros(100, np.float32))
    (p.train_dir / "audio").mkdir(parents=True); (p.train_dir / "audio" / "stale.wav").write_bytes(b"x")
    item = synth.SynthItem("synth_0001", "x", "corpus", status="done", dropped=False)
    d = train.build_audio_dir(p, [item])
    assert sorted(f.name for f in d.iterdir()) == ["s1.wav", "synth_0001.wav"]
    assert (d / "s1.wav").read_bytes() == (p.segments_dir / "s1.wav").read_bytes()


def test_training_without_synth_is_unchanged(tmp_path, monkeypatch):
    p = _setup_train(tmp_path, monkeypatch)
    fake = Fake({})
    train.train_project(p, env=ENV12, run=fake, batch=16)
    csv = (p.train_dir / "train.csv").read_text(encoding="utf-8").splitlines()
    assert len(csv) == len(set(csv))                                  # weight 1: no repeats
    fit = next(" ".join(c) for c in fake.calls if "fit.py" in " ".join(c))
    assert "/train/audio/" in fit and "/segments/" not in fit
```

- [ ] **Step 2: Run to verify they fail.**

- [ ] **Step 3: Modify `omnivoice/dataset.py`**

```python
def piper_csv(p: Project, out: Path, synth_items=(), weight: int = 1) -> int:
    """Rows for piper: every original phrase with text `weight` times, then the synthetic ones."""
    rows = [f"{s.id}.wav|{clean_text(s.text)}\n" for s in load(p) if not s.dropped and s.text.strip()] * max(1, weight)
    rows += [f"{i.id}.wav|{clean_text(i.text)}\n" for i in synth_items]
    Path(out).parent.mkdir(parents=True, exist_ok=True)  # train/ may have been deleted to free disk space
    with Path(out).open("w", encoding="utf-8", newline="") as f:
        f.writelines(rows)
    return len(rows)
```
Note: repeated rows keep piper's order stable (originals first). Keep the `rows *= weight` semantics exactly as written: the list of originals is repeated as a block.

- [ ] **Step 4: Modify `omnivoice/train.py`**

Add:
```python
def build_audio_dir(p, synth_items=()) -> Path:
    """train/audio: hard links (a copy where a link is impossible) to segments/*.wav and the used synth wavs —
    piper reads audio from one folder. Rebuilt every run so dropped phrases never linger."""
    from omnivoice import synth
    d = p.train_dir / "audio"
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    sources = list(p.segments_dir.glob("*.wav")) + [synth.wav(p, i.id) for i in synth_items]
    for src in sources:
        try:
            os.link(src, d / src.name)
        except OSError:
            shutil.copy2(src, d / src.name)
    return d
```
(`import shutil` at the top.) In `fit_args`, change `"--data.audio_dir", f"{root}/segments/",` to `"--data.audio_dir", f"{root}/train/audio/",`. In `train_project`, replace the `dataset.piper_csv(p, p.train_dir / "train.csv") == 0` check with:
```python
    from omnivoice import synth
    synth_items = synth.training_items(p)
    weight = synth.load(p).weight if synth_items else 1
    if dataset.piper_csv(p, p.train_dir / "train.csv", synth_items, weight) == 0:
        raise TrainError("Нет ни одной фразы с текстом для обучения")
    build_audio_dir(p, synth_items)
```
Also update `tests/test_train.py::test_wsl_fit_command_exact` and `test_fit_command_args`: the expected `--data.audio_dir` is now `{r}/train/audio/` (Docker: `/work/train/audio/`). Colab (`notebooks/omnivoice_colab.ipynb`) keeps `segments/`: it calls `fit_args` with `/content/project` — check its cell builds `train/audio` or pass; simplest: in the notebook cell after `fit_args`, run `train.build_audio_dir(p)` first (edit the cell source in the notebook JSON: add the line `train.build_audio_dir(p)` before `cmd = train.fit_args(...)`), and keep `tests/test_colab.py` passing.

- [ ] **Step 5: Run tests** — full suite → PASS.

- [ ] **Step 6: Commit**

```bash
git add tools/omnivoice/omnivoice/dataset.py tools/omnivoice/omnivoice/train.py tools/omnivoice/tests/test_train.py tools/omnivoice/notebooks/omnivoice_colab.ipynb
git commit -m "feat(omnivoice): train on weighted originals plus accepted synthetic phrases"
```

---

### Task 7: Фоновая генерация (`SynthRunner`)

**Files:**
- Modify: `omnivoice/ui/helpers.py`, `omnivoice/ui/strings.py`
- Test: `tests/test_ui_helpers.py`

**Interfaces:**
- Consumes: `teacher.XttsTeacher`, `synth.*`, `transcriber._default_recognizer`, `transcriber.has_whisper`.
- Produces: `class SynthRunner(teacher=None, recognizer_factory=None, run=subprocess.run)` with `start(p, minutes: float, refs: list[str])`, `stop(grace: float | None = None)`, `running: bool`, `status: str` (`idle|running|checking|done|stopped|failed|error`), `status_text() -> str`, `log_text() -> str`, `progress: tuple[int, int]` (done, total).

- [ ] **Step 1: Write the failing test** (append to `tests/test_ui_helpers.py`)

```python
def test_synth_runner_generates_checks_and_stops(tmp_path):
    import numpy as np
    from omnivoice import audio, dataset, synth
    from omnivoice.dataset import Segment
    from omnivoice.project import Project
    p = Project.create(tmp_path / "a", name="a", language="ru")
    audio.write_wav(p.segments_dir / "s1.wav", np.zeros(audio.SR * 5, np.float32))
    dataset.save(p, [Segment("s1", "раз два три четыре", 5.0)])

    class Teacher:
        def generate(self, p, state, on_line):
            pending = [i for i in state.items if i.status == "pending"]
            for i, it in enumerate(pending[:2], 1):
                synth.wav(p, it.id).parent.mkdir(parents=True, exist_ok=True)
                audio.write_wav(synth.wav(p, it.id), (0.2 * np.sin(np.arange(audio.SR * 2) / 9)).astype(np.float32))
                on_line(f"ITEM {i}/2 {it.id}")
            on_line(f"FAIL {pending[2].id} cuda oom")
            return 0
        def request_stop(self, p): pass
        def kill(self, run=None): pass

    r = h.SynthRunner(teacher=Teacher(), recognizer_factory=lambda lang: (lambda wav: "текст"))
    r.start(p, minutes=2, refs=["s1"])   # ≈ 430 characters at 3.6 chars/s: several phrases
    r.join(10)
    st = synth.load(p)
    assert r.status == "done" and sum(i.status == "done" for i in st.items) == 2
    assert all(i.verdict != "unchecked" for i in st.items if i.status == "done")
    failed = [i for i in st.items if i.status == "failed"]
    assert len(failed) == 1 and failed[0].error == "cuda oom" and synth.summary(st)["failed"] == 1
    assert "ITEM 2/2" in r.log_text() or S.SYNTH_DONE.split("{")[0] in r.log_text()
```

- [ ] **Step 2: Run to verify it fails.**

- [ ] **Step 3: Strings** (`ui/strings.py`, section `# Synth`)

```python
SEC_SYNTH = "Синтетика"
SYNTH_IDLE = "Синтетика не запущена"
SYNTH_RUNNING = "Генерирую {done}/{total}"
SYNTH_ETA = " · осталось ≈ {eta}"
SYNTH_CHECKING = "Проверяю сгенерированное (Whisper)…"
SYNTH_STOPPING = "Останавливаю: дописываю текущую фразу…"
SYNTH_STOPPED = "Генерация остановлена — «Догенерировать» доделает остальное"
SYNTH_DONE = "Готово: принято {accepted} ({minutes} мин) · спорно {suspect} · брак {rejected} · не удалось {failed}"
SYNTH_FAILED = "Генерация прервалась (код {code}) — см. журнал"
SYNTH_ERROR = "Ошибка генерации — см. журнал"
SYNTH_BUSY = "Генерация уже идёт"
SYNTH_NO_WHISPER = "Whisper не установлен — фразы не проверены и в обучение не пойдут. Поставь пакеты подготовки на «Установке»"
SYNTH_NO_REFS = "Нет подходящих фраз-образцов (3–12 с, без меток) — сначала нарежь и проверь оригинал"
```

- [ ] **Step 4: Implement `SynthRunner`** in `ui/helpers.py` (next to `TrainRunner`)

```python
class SynthRunner:
    """One background generation per project: plan → teacher (WSL) → Whisper check → synth.json.
    Stop asks xtts_gen.py to finish its phrase (teacher.request_stop) and kills it after STOP_GRACE s."""

    def __init__(self, teacher=None, recognizer_factory=None, run=subprocess.run, clock=None):
        from omnivoice import teacher as teacher_mod
        self._teacher = teacher or teacher_mod.XttsTeacher()
        self._recognizer_factory = recognizer_factory
        self._run = run
        self._clock = clock or time.monotonic
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._lines: deque[str] = deque(maxlen=400)
        self.status = "idle"
        self.code: int | None = None
        self.done = self.total = 0
        self._failed: dict[str, str] = {}   # id → message, from xtts_gen's FAIL lines
        self._started = 0.0
        self._p = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _note(self, line: str) -> None:
        with self._lock:
            self._lines.append(line)

    def log_text(self) -> str:
        with self._lock:
            return "\n".join(self._lines)

    def _line(self, line: str) -> None:
        if re.match(r"ITEM \d+/\d+", line):
            self.done += 1
        m = re.match(r"FAIL (\S+) ?(.*)$", line)
        if m:
            self._failed[m.group(1)] = m.group(2) or "?"
        self._note(line)

    def start(self, p, minutes: float, refs: list[str]) -> None:
        with self._lock:
            if self.running:
                raise RuntimeError(S.SYNTH_BUSY)
            self._p, self.status, self.code, self.done, self._failed = p, "running", None, 0, {}
            self._started = self._clock()
            self._lines.clear()
            self._thread = threading.Thread(target=self._work, args=(p, minutes, refs), daemon=True,
                                            name=f"omnivoice-synth-{p.name}")
            self._thread.start()

    def _recognizer(self, language):
        from omnivoice import transcriber
        if self._recognizer_factory:
            return self._recognizer_factory(language)
        if not transcriber.has_whisper():
            return None
        rec = transcriber._default_recognizer(language, None)
        return lambda wav: " ".join(t.strip() for t, _, _ in rec(wav))

    def _work(self, p, minutes, refs) -> None:
        from omnivoice import synth
        try:
            state = synth.make_plan(p, minutes, refs)
            synth.save(p, state)
            pending = [i for i in state.items if i.status == "pending"]
            self.total = len(pending)
            code = self._teacher.generate(p, state, self._line) if pending else 0
            self.code = code
            state = synth.sync_generated(p, state)
            for it in state.items:  # «не удалась»: retried by the next «Догенерировать» (make_plan re-plans it)
                if it.id in self._failed and it.status != "done":
                    it.status, it.error = "failed", self._failed[it.id]
            if self.status == "running":
                self.status = "checking"
            rec = self._recognizer(p.language)
            if rec is None:
                self._note(S.SYNTH_NO_WHISPER)
            state = synth.apply_check(p, state, rec)
            synth.save(p, state)
            if self.status != "stopped":
                self.status = "done" if code == 0 else "failed"
            s = synth.summary(state)
            self._note(S.SYNTH_DONE.format(accepted=s["accepted"], minutes=s["accepted_min"], suspect=s["suspect"],
                                           rejected=s["rejected"], failed=s["failed"]))
        except Exception as e:  # WslError / OSError …: shown in the log, never a traceback
            self._note(str(e) or type(e).__name__)
            self.status = "error" if self.status != "stopped" else "stopped"

    def stop(self, grace: float | None = None) -> None:
        if not self.running or self._p is None:
            return
        from omnivoice import teacher as teacher_mod
        self.status = "stopped"
        self._note(S.SYNTH_STOPPING)
        self._teacher.request_stop(self._p)
        thread, grace = self._thread, teacher_mod.STOP_GRACE if grace is None else grace

        def kill_if_stuck():
            thread.join(grace)
            if thread.is_alive():
                self._teacher.kill(self._run)
        threading.Thread(target=kill_if_stuck, daemon=True).start()

    def join(self, timeout=None) -> None:
        if self._thread:
            self._thread.join(timeout)

    def status_text(self) -> str:
        if self.status == "running":
            text = S.SYNTH_RUNNING.format(done=self.done, total=self.total or "?")
            if self.done and self.total:
                per = (self._clock() - self._started) / self.done
                text += S.SYNTH_ETA.format(eta=trainlog.duration_text(per * (self.total - self.done)))
            return text
        if self.status == "stopped" and self.running:
            return S.SYNTH_STOPPING
        return {"idle": S.SYNTH_IDLE, "checking": S.SYNTH_CHECKING, "done": S.SYNTH_IDLE, "stopped": S.SYNTH_STOPPED,
                "failed": S.SYNTH_FAILED.format(code=self.code), "error": S.SYNTH_ERROR}[self.status]
```

- [ ] **Step 5: Run tests** — `pytest -q tests/test_ui_helpers.py -k synth_runner` → PASS; full suite → PASS.

- [ ] **Step 6: Commit**

```bash
git add tools/omnivoice/omnivoice/ui/helpers.py tools/omnivoice/omnivoice/ui/strings.py tools/omnivoice/tests/test_ui_helpers.py
git commit -m "feat(omnivoice): background synthetic generation with check and soft stop"
```

---

### Task 8: Страница «Синтетика», установка и строка на «Обучении»

**Files:**
- Modify: `omnivoice/ui/app.py`, `omnivoice/ui/helpers.py`, `omnivoice/ui/strings.py`, `omnivoice/ui/theme.py`
- Test: `tests/test_ui.py`, `tests/test_ui_helpers.py`

**Interfaces:**
- Consumes: `SynthRunner`, `synth.*`, `wslenv.xtts_ready`, `deps.install_all(with_xtts=...)`, existing `phrase`-card CSS (`phr-row`, `phr-btn`, `phr-play`, `phr-rm`, `phr-back`), `hud_player_html`, `listen_html`.
- Produces: helpers `synth_card_html(item, rate_note) -> str`, `synth_summary_html(summary) -> str`; UI handlers `on_synth_start`, `on_synth_stop`, `on_synth_tick`, `on_synth_decide`, `synth_buttons(name)`; nav: `SECTIONS` gains `S.SEC_SYNTH` after `S.SEC_CHECK`, `SECTION_STEP[S.SEC_SYNTH] = "synth"`.

- [ ] **Step 1: Write the failing tests**

`tests/test_ui_helpers.py`:
```python
def test_synth_section_in_nav_and_steps_bar():
    assert h.SECTIONS.index(S.SEC_SYNTH) == h.SECTIONS.index(S.SEC_CHECK) + 1
    bar = h.steps_bar_html({}, "synth")
    assert "СИНТЕТИКА" in bar and 'class="st on' in bar and S.STEP_OPTIONAL in bar


def test_synth_card_and_summary():
    from omnivoice.synth import SynthItem
    it = SynthItem("synth_0007", "Во славу Плети!", "corpus", status="done", duration=1.6, heard="во славу плоти",
                   cer=0.07, verdict="suspect", reasons=["text"], dropped=True)
    card = h.synth_card_html(it)
    assert "Во славу Плети!" in card and "Whisper услышал: «во славу плоти»" in card and "Whisper услышал другое" in card
    s = h.synth_summary_html({"accepted": 212, "accepted_min": 13.6, "suspect": 19, "rejected": 9, "failed": 0,
                              "pending": 0})
    assert "212" in s and "13.6" in s and "19" in s
```

`tests/test_ui.py`:
```python
def test_synth_page_buttons_and_decision(tmp_path, monkeypatch):
    from omnivoice import synth, wslenv
    from omnivoice.ui import strings as S
    monkeypatch.setattr(wslenv, "xtts_ready", lambda run=None: True)
    p = Project.create(tmp_path / "Arthas", name="Arthas", language="ru")
    demo = build(tmp_path)
    start, stop, more = _handler(demo, "synth_buttons")("Arthas")
    assert not start["interactive"] and not stop["interactive"]          # no reference phrases yet
    st = synth.SynthState(["s1"], [synth.SynthItem("synth_0001", "раз", "corpus", status="done",
                                                   verdict="suspect", reasons=["text"], dropped=True)])
    synth.save(p, st)
    _handler(demo, "on_synth_decide")("Arthas", "synth_0001#accept#1")
    assert synth.load(p).items[0].dropped is False
```

- [ ] **Step 2: Run to verify they fail.**

- [ ] **Step 3: Nav, steps bar, strings**
  - `helpers.SECTIONS = (S.SEC_AUDIO, S.SEC_SLICE, S.SEC_PHRASES, S.SEC_CHECK, S.SEC_SYNTH, S.SEC_TRAIN, S.SEC_PACK)` and the step keys tuple gains `"synth"` in the same position; `first_open_section` in `app.py` skips `S.SEC_SYNTH` (optional step: `if section in (S.SEC_SLICE, S.SEC_SYNTH)`).
  - `steps_bar_html`: for `step == "synth"` add `<span class="st-opt">{S.STEP_OPTIONAL}</span>` inside the chip; strings `STEP_OPTIONAL = "необяз."`; CSS `.st-opt {{ font-size:9px; opacity:.7; margin-left:6px; }}`.
  - Strings for the page:
```python
SYNTH_INTRO = ("XTTS v2 озвучит голосом персонажа много новых фраз — Piper учится лучше, чем на одной минуте записей. "
               "Голоса с синтетикой XTTS — только для некоммерческого использования.")
SYNTH_NEED_XTTS = "Нужна установка XTTS v2 (≈ 3–4 ГБ): «Установка» → галочка «и XTTS v2» → «Установить зависимости»"
SYNTH_GOTO_SETUP = "К установке →"
SYNTH_REFS = "Образцы голоса"
SYNTH_REFS_AUTO = "Подобрать автоматически"
SYNTH_MINUTES = "Сколько минут синтетики"
SYNTH_LINES = "Свои фразы в стиле персонажа (по одной на строку)"
SYNTH_START = "Сгенерировать"
SYNTH_MORE = "Догенерировать"
SYNTH_STOP = "Стоп"
SYNTH_FILTER = ("Спорные", "Принятые", "Брак")
SYNTH_HEARD = "Whisper услышал: «{text}»"
SYNTH_ACCEPT = "Принять"
SYNTH_DROP = "Выкинуть"
SYNTH_USE = "Использовать синтетику при обучении"
SYNTH_WEIGHT = "Вес оригинала"
SYNTH_TRAIN_LINE = "Синтетика: {n} фраз · {minutes} мин"
SETUP_WITH_XTTS = "и XTTS v2 для синтетики (≈ 3–4 ГБ, необязательно)"
```
  (`SYNTH_FILTER` is a tuple: put it in `helpers.py` as `SYNTH_FILTERS = (S.SYNTH_F_SUSPECT, S.SYNTH_F_ACCEPTED, S.SYNTH_F_REJECTED)` with three separate strings, per the strings rule.)

- [ ] **Step 4: Helpers** (`ui/helpers.py`)

```python
def synth_card_html(it) -> str:
    """A synthetic phrase like a phrase card: ▶ (data-play, the bottom player), text, what Whisper heard,
    the reasons, and ✓ / ✕ (↺) buttons that report "<id>#<accept|drop|reset>#<time>" to #synth-pick."""
    from omnivoice import synth_check
    why = " · ".join(synth_check.REASONS.get(r, r) for r in it.reasons)
    heard = (f'<div class="muted">{html.escape(S.SYNTH_HEARD.format(text=it.heard))}</div>'
             if it.heard is not None and it.heard.strip().lower() != it.text.strip().lower() else "")
    act = (f'<button type="button" class="syn-btn phr-back" data-act="reset" title="{html.escape(S.PHRASE_RESTORE_HINT)}"></button>'
           if it.dropped else
           f'<button type="button" class="syn-btn phr-rm" data-act="drop" title="{html.escape(S.SYNTH_DROP)}"></button>')
    accept = ("" if not it.dropped else
              f'<button type="button" class="syn-btn syn-ok" data-act="accept" title="{html.escape(S.SYNTH_ACCEPT)}"></button>')
    cls = "syn-row dropped" if it.dropped else "syn-row"
    return (f'<div class="{cls}" data-id="{html.escape(it.id)}">'
            f'<button type="button" class="syn-btn phr-play" data-act="play" title="{html.escape(S.PLAY)}"></button>'
            f'<div class="syn-body"><div class="phr-meta"><b>{html.escape(it.id)}</b>'
            f'<span class="muted">{html.escape(S.PHRASE_SECONDS.format(v=it.duration))}</span>'
            + (f'<span class="phr-chip flag">{html.escape(why)}</span>' if why else "") +
            f'</div><div class="syn-text">{html.escape(it.text)}</div>{heard}</div>{accept}{act}</div>')


def synth_summary_html(s: dict) -> str:
    return f'<div class="stat">{html.escape(S.SYNTH_DONE.format(accepted=s["accepted"], minutes=s["accepted_min"], suspect=s["suspect"], rejected=s["rejected"], failed=s["failed"]))}</div>'
```

- [ ] **Step 5: App layout** (`ui/app.py`, new group after `g_check`)

```python
                    with gr.Column(visible=sec0 == S.SEC_SYNTH, elem_classes="hud-section") as g_synth:
                        gr.HTML(f'<div class="sub-head">{S.SEC_SYNTH}</div>' + msg_html(S.SYNTH_INTRO, muted=True))
                        synth_need = gr.HTML()            # yellow card when XTTS is missing (pack-model style)
                        gr.HTML(f'<div class="sub-head">{S.SYNTH_REFS}</div>')
                        synth_refs = gr.HTML()            # reference cards: hud_player_html + ✕ (data-act=unref)
                        synth_refs_auto = gr.Button(S.SYNTH_REFS_AUTO)
                        with gr.Row(equal_height=True):
                            synth_minutes = gr.Number(15, label=S.SYNTH_MINUTES, precision=0, minimum=1, maximum=60)
                        synth_lines = gr.Textbox(label=S.SYNTH_LINES, lines=4, max_lines=12)
                        with gr.Row():
                            synth_start = gr.Button(S.SYNTH_START, variant="primary")
                            synth_stop = gr.Button(S.SYNTH_STOP, variant="stop", interactive=False)
                            synth_more = gr.Button(S.SYNTH_MORE)
                        synth_status = gr.HTML(f'<div class="train-status">{S.SYNTH_IDLE}</div>')
                        synth_log = gr.Textbox(label=S.TRAIN_LOG, lines=8, max_lines=8, interactive=False,
                                               autoscroll=False, elem_classes="log-box")
                        synth_summary = gr.HTML()
                        synth_filter = gr.Radio(list(SYNTH_FILTERS), value=SYNTH_FILTERS[0], show_label=False)
                        synth_list = gr.HTML(elem_classes="syn-list")
                        synth_pick = gr.Textbox(elem_id="synth-pick", elem_classes="hidden-input", container=False,
                                                show_label=False)
                        synth_player = gr.Audio(label=S.PLAYER, type="filepath", interactive=False, autoplay=True)
                        synth_msg = gr.HTML()
```
Add `g_synth` to `groups` / `group_of` (`S.SEC_SYNTH: g_synth`), `synth_msg` to `section_msgs`. State: `synth_refs_state = gr.State([])` (ids), `synth_runners: dict[str, SynthRunner] = {}` beside `runners`.

Handlers (all `@guarded`):
- `synth_view(name, flt)` → `(need_html, refs_html, lines_text, summary_html, list_html, refs_ids)`: `refs = synth.load(p).refs or synth.choose_refs(dataset.load(p))`; `need_html` = yellow card (reuse `.pack-model none` + `.pack-goto` with `data-section="Установка"`) when `not wslenv.xtts_ready()`; list filtered by `flt` (`suspect`: `verdict == "suspect" and manual is None`; `accepted`: `not dropped`; `rejected`: `dropped and verdict == "rejected"`). Wire on `section.change` (when `SEC_SYNTH`), `project_dd.change`, `synth_filter.change`.
- `synth_buttons(name)` → `(start, stop, more)` updates: start enabled iff XTTS ready and refs exist and runner idle; stop iff runner running and not stopping; more iff ready and summary `pending > 0` and idle. Wire like `train_buttons` (load, project change, tick).
- `on_synth_start(name, minutes, lines_text, refs_ids)`: `synth.save_lines(p, lines_text)`; `if not refs_ids: raise ValueError(S.SYNTH_NO_REFS)`; `synth_runner(name).start(p, minutes, refs_ids)`; returns status + buttons. Double click while running: return current state (as `start_training`).
- `on_synth_more(name, minutes, lines_text, refs_ids)`: exactly `on_synth_start` — `make_plan` keeps every phrase already `done` with the same references, so only `pending` / `failed` ones are generated again.
- `on_synth_stop(name)`.
- `on_synth_tick(name)` on a `gr.Timer(2.0)`: status, log, buttons; when the runner finishes (status changes to done/failed/stopped), also refresh summary + list.
- `on_synth_decide(name, picked)`: `picked = "<id>#<accept|drop|reset>#<t>"`; `reset` → `set_manual(p, id, None)`, else `set_manual(p, id, act)`; return refreshed list + summary. `play` acts are handled client-side? No: `play` → return `synth.wav(p, id)` into `synth_player` — route through the same pick box with act `play`.
- refs ✕: act `unref` removes the id from `refs_ids` state and re-renders `synth_refs`; «Подобрать автоматически» → `synth.choose_refs(dataset.load(p))`.

JS (`theme.HEAD`): delegate clicks on `.syn-row .syn-btn` and `.syn-ref .syn-btn` → set `#synth-pick textarea` to `"<data-id>#<data-act>#<Date.now()>"` and dispatch `input` (fires `.change`, as #ckpt-pick); add `current` class to the played row.

CSS (`theme.py`): `.syn-list`, `.syn-row` copy the `.phr-row` look (border, PANEL, 8px 10px padding, gap 12px, `align-items:center`), `.syn-body` (flex column, gap 2px, `min-width:0`, `flex:1`), `.syn-text` (TEXT colour, 14px), `.syn-btn` = the absolute-centred 32×32 icon buttons (copy the `button.phr-btn` rules with selector `.syn-btn`, incl. `font-size:0`), `.syn-ok` icon: two 2px lines forming ✓ (::before rotated 45° short arm, ::after rotated −45° long arm, `var(--ok)`), `.syn-row.dropped .syn-body {{ opacity:.45 }}`. Use border longhands (Gradio drops `border:` shorthand followed by a longhand).

Setup page: add `setup_xtts = gr.Checkbox(label=S.SETUP_WITH_XTTS, value=False)` above `setup_btn`; `on_setup(with_xtts)` → `setup.start(job=lambda on_line, progress: deps.install_all(on_line, progress, with_xtts=with_xtts))`.

Training page: under the log, `synth_train = gr.HTML()` + row `synth_use = gr.Checkbox(S.SYNTH_USE)`, `synth_weight = gr.Number(3, label=S.SYNTH_WEIGHT, precision=0, minimum=1, maximum=10)`; shown only when `synth.training_items` is non-empty (or `use` False with done items); changes save into `synth.json` (`state.use`, `state.weight`).

- [ ] **Step 6: Run tests** — full suite → PASS.

- [ ] **Step 7: Visual check** (Chrome DevTools, test UI on port 7861 with a copy of a project; never the user's live project): page at 1× and 3×; measure with `getBoundingClientRect` that buttons in a card share their vertical centre and cards share left/right padding; icons (▶, ✓, ✕, ↺) centred at 4×; no element clipped; steps bar shows 7 chips with «необяз.». Fix and re-check before committing.

- [ ] **Step 8: Commit**

```bash
git add tools/omnivoice/omnivoice/ui tools/omnivoice/tests/test_ui.py tools/omnivoice/tests/test_ui_helpers.py
git commit -m "feat(omnivoice): synthetic data page, xtts install option and training toggle"
```

---

### Task 9: Документация и настоящий прогон

**Files:**
- Modify: `README.md` (omnivoice), `.wolf/anatomy.md`, `.wolf/cerebrum.md`, `.wolf/memory.md`

- [ ] **Step 1: README** — раздел «Синтетика (XTTS v2)»: зачем, как включить (галочка на «Установке»), шаги на странице, вес оригинала, лицензия: «XTTS v2 распространяется по CPML — голоса, обученные с синтетикой XTTS, только для некоммерческого использования»; источник корпуса (Common Voice, CC0).

- [ ] **Step 2: Real install** — на «Установке» поставить галочку «и XTTS v2», «Установить зависимости»; ожидание: 4 шага, «xtts ok, cuda: True». Если пробная генерация падает из-за версий — правка `xtts_constraints.txt` + `XTTS_VERSION` (Task 5, Step 4), повторить.

- [ ] **Step 3: Real generation on a copy** — скопировать проект пользователя без `train/` в scratchpad, UI на 7861, «Синтетика»: 2 минуты, «Сгенерировать»; проверить: прогресс и ETA, журнал, итоговая сводка, спорные карточки, ▶ играет, ✓/✕/↺ меняют сводку, «Стоп» посреди и «Догенерировать» доделывают только недостающее, `synth/wavs/*.wav` 22050 Гц моно.

- [ ] **Step 4: Training uses synth** — на копии «Старт» обучения на 3 эпохи: в `train/train.csv` оригинальные строки ×3 и принятые `synth_*`; `train/audio/` содержит оба вида; обучение идёт.

- [ ] **Step 5: Wolf notes, full test run, commit**

```bash
.venv/Scripts/python -m pytest -q tests
git add README.md .wolf
git commit -m "docs(omnivoice): document synthetic data and its licence"
```

- [ ] **Step 6: Hand-off to the user** — сгенерировать ~15 минут на реальном Arthas, обучить от `ruslan` (1000–1500 эпох), сравнить на слух с текущей моделью на одних фразах (критерий из ишью #60).
