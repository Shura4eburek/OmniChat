# omnivoice

Инструмент превращает сырое аудио или готовый датасет в обученный голос Piper — или упаковывает уже готовую модель — в папку формата OmniChat (sherpa-onnx). Результат кладётся в `config/omnichat/models/` мода.

> **Права.** Голоса из игр, фильмов и чужие записи защищены авторским правом и правами на голос. Обучайте и публикуйте голос только с разрешения владельца записей. В `voice.json` есть необязательное поле `license` (мод его игнорирует) — указывайте в нём условия использования. Ответственность за использование чужого голоса лежит на вас.

## Три точки входа

```
A. Сырое аудио ──► init ► slice ► transcribe ► (правка фраз) ► check ► train ► export ─┐
B. Готовый датасет ► init ► import ► check ► train ► export ───────────────────────────┼► pack ► verify ► install
C. Готовая модель (.onnx + .onnx.json) ────────────────────────────────────────────────┘
```

Все то же самое доступно в веб-интерфейсе: `omnivoice ui`.

## Требования

- [uv](https://docs.astral.sh/uv/), Python >= 3.11.4 (uv подтянет сам).
- Для пути A: `ffmpeg` в `PATH` (`winget install ffmpeg`).
- Для обучения локально: Docker Desktop с WSL2 и драйвер NVIDIA (GPU). Образ собирается командой `omnivoice train --build` и весит около 10 ГБ.
- Нет GPU — обучайте в Google Colab (см. ниже).
- Для пути C GPU, Docker и ffmpeg не нужны.

## Установка

```bash
cd tools/omnivoice
uv sync --all-extras     # всё сразу: база + нарезка/распознавание + веб-интерфейс
```

- `uv sync` — только база: упаковка, проверка, установка (включая sherpa-onnx-core). Хватает для пути C.
- `uv sync --extra prep --extra ui` — то же, что `--all-extras`: `prep` = нарезка и распознавание (faster-whisper, silero-vad, demucs, pyloudnorm), `ui` = веб-интерфейс (gradio, tensorboard).

Важно: `uv sync --extra X` ставит **только** перечисленные extras и удаляет остальные. Поэтому не запускайте `uv sync --extra prep`, а потом `uv sync --extra ui` — второй вызов снесёт `prep`. Перечисляйте всё нужное в одной команде.

torch и piper-train локально не ставятся: обучение идёт только в Docker или Colab.

## Быстрый старт

### C. Упаковать готовую модель (без GPU)

```bash
uv run omnivoice pack --onnx model.onnx --config model.onnx.json \
    --name "Мой голос" --language Russian --portrait portrait.png --out ./voices
uv run omnivoice verify ./voices/<папка>
uv run omnivoice install ./voices/<папка>
```

Опции `pack --onnx`: `--config` (.onnx.json), `--voice` (голос espeak, например `ru`; по умолчанию берётся из конфига), `--name` (обязательно), `--language` (английское название языка; по умолчанию выводится из `--voice` или из конфига: `ru` → `Russian`, `en-us` → `English`, иначе `Russian`), `--out` (куда собрать, по умолчанию текущая папка), `--portrait` (любая картинка, будет приведена к PNG для мода).

`install` без `--target` ищет папку `models` сам (`%APPDATA%\.minecraft`, Prism Launcher, `run/config/omnichat/models` рядом); если не нашёл — укажите `--target`. `--overwrite` заменяет уже установленный голос.

### A. Из сырого аудио

```bash
uv sync --all-extras
uv run omnivoice init ./my-voice --name "Мой голос" --language ru   # ru или en; --base denis|dmitri|irina|ruslan|lessac
# положите записи в ./my-voice/raw/
uv run omnivoice slice -p ./my-voice            # --isolate убирает музыку (demucs)
uv run omnivoice transcribe -p ./my-voice       # --model для выбора модели Whisper
uv run omnivoice check -p ./my-voice
uv run omnivoice train -p ./my-voice            # Docker + GPU
uv run omnivoice export -p ./my-voice           # ONNX + упаковка + проверка
uv run omnivoice install ./my-voice/export/<папка>
```

`export` сам упаковывает голос (как `pack`) и проверяет его (как `verify`) — отдельно запускать `pack` и `verify` не нужно. `pack -p ./my-voice --portrait portrait.png` нужен только чтобы пересобрать уже экспортированную модель, например добавить или сменить портрет.

Имя папки голоса берётся из имени голоса с транслитерацией: «Мой голос» → `moy_golos`.

Фразы после `transcribe` удобно проверять и править в веб-интерфейсе.

### B. Из готового датасета

```bash
uv run omnivoice init ./my-voice --name "Мой голос" --language ru
uv run omnivoice import ./dataset -p ./my-voice   # LJSpeech или пары .wav + .txt
uv run omnivoice check -p ./my-voice
uv run omnivoice train -p ./my-voice
uv run omnivoice export -p ./my-voice             # ONNX + упаковка + проверка
uv run omnivoice install ./my-voice/export/<папка>
```

Тексты при импорте нормализуются так же, как после `transcribe` (числа словами, ремарки `*смеётся*` и эмодзи убираются); такие фразы получают флаг для проверки.

### Обучение

`omnivoice train` дообучает голос поверх базового чекпойнта Piper. `--epochs` означает дополнительные эпохи сверх базового чекпойнта (по умолчанию 1000). Обучение продолжается с последнего чекпойнта; `--no-resume` начинает заново. `omnivoice train --build` только собирает Docker-образ. Если чекпойнт с нужной эпохой уже есть, `train` пишет «Цель уже достигнута» и ничего не запускает — увеличьте `--epochs`. Промежуточное качество: `omnivoice previews -p ./my-voice` показывает чекпойнты и достаёт аудио-превью из логов обучения; `omnivoice export --ckpt <файл>` экспортирует выбранный чекпойнт (по умолчанию последний).

### Веб-интерфейс

```bash
uv sync --all-extras
uv run omnivoice ui --projects ./voices      # --port 7860, --no-browser
```

Интерфейс слушает только `127.0.0.1` и показывает проекты из папки `--projects`.

Не работайте с одним проектом одновременно из CLI и из веб-интерфейса: такой режим не поддерживается (интерфейс блокирует проект только от своих же параллельных действий).

## Colab (нет GPU)

```bash
uv run omnivoice train -p ./my-voice --colab
```

Команда собирает zip с датасетом и печатает ссылку на ноутбук (`colab.NOTEBOOK_URL`). Откройте ноутбук, загрузите zip и дождитесь обучения — ноутбук сам экспортирует, упакует и проверит голос и отдаст архив с папкой голоса. Дальше локально:

1. скачайте zip из Colab;
2. распакуйте его — получится папка голоса;
3. выполните `uv run omnivoice install <папка>`.

Запускать `export` или `pack` локально после Colab не нужно. Ноутбук доступен по ссылке после слияния ветки в `main`.

## Что внутри папки голоса

Это тот же формат, что описан в корневом README, раздел «Оформление голосов»:

```
<имя>/
  <имя>.onnx          модель с метаданными sherpa-onnx (n_speakers, voice)
  <имя>.onnx.json     конфиг Piper
  tokens.txt          таблица токенов
  espeak-ng-data/     данные espeak (нужен phontab)
  voice.json          необязательно: оформление
  portrait.png        необязательно: PNG 16x16 или 32x32, не больше 8 КБ
```

`voice.json`:

```json
{ "name": "Денис", "description": "Спокойный мужской голос", "language": "ru",
  "gender": "male", "sample": "Привет, я Денис." }
```

| Поле | Лимит | Назначение |
|---|---|---|
| `name` | 32 символа | Имя в меню |
| `description` | 200 | Описание в карточке |
| `language` | 8 | Код языка |
| `gender` | 16 | Свободное поле |
| `sample` | 120 | Фраза для прослушивания |
| `license` | — | Необязательно, мод игнорирует |

`omnivoice verify` проверяет эти лимиты и загружает модель в sherpa-onnx отдельным процессом.

## Если что-то не работает

- **Нет GPU / Docker не запускается** — используйте Colab (`train --colab`) или путь C.
- **`verify` не прошёл** — прочитайте сообщение: чаще всего нет `n_speakers` или `voice` в метаданных `.onnx`, нет `tokens.txt` / `espeak-ng-data`, либо превышены лимиты `voice.json`/портрета. Пересоберите папку через `pack`.
- **Мало видеопамяти (VRAM)** — при ошибке `CUDA out of memory` `train` сам вдвое уменьшает батч (до минимума 4), пишет «Не хватило видеопамяти — уменьшаю батч до N и продолжаю» и продолжает с последнего чекпойнта. Если не хватает даже при батче 4 — закройте другие приложения с GPU или обучайте в Colab.
- **Проверка произносимости пропущена** (`check` пишет «Фонемизатор не установлен») — фонемизатор Piper не входит в зависимости; запустите проверку с ним: `uv run --with piper-tts omnivoice check -p ./my-voice`.
- **«Файл … повреждён»** — `project.toml`, `metadata.csv` или `review.json` испорчены (например, правкой вручную). Почините файл или восстановите из копии.
- **`ffmpeg не найден`** — `winget install ffmpeg` и перезапустите терминал.
- **`install` не нашёл папку models** — укажите `--target <путь>\config\omnichat\models`, затем в игре `/omnichat reload`.
