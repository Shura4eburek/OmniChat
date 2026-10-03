"""Every user-visible UI string (Russian). UPPER_CASE str constants only."""

TITLE = "OMNIVOICE"
PAGE_TITLE = "omnivoice"

# Environment badge
ENV_CHECKING = "проверяю окружение…"
NO_GPU = "нет GPU"
GPU_PREFIX = "GPU: "
DOCKER_OK = "Docker ✓"
DOCKER_NO = "Docker ✗"
WSL_OK = "WSL ✓"
WSL_NO_GPU = "WSL: нет GPU"
GPU_DOCKER_NO = " (Docker её не видит)"

# Sidebar
PROJECT = "Проект"
NO_PROJECTS = "Проектов пока нет — создай новый"
NEW_PROJECT = "+ новый проект"
NEW_NAME = "Имя голоса"
NEW_LANGUAGE = "Язык"
CREATE = "Создать"
CREATED = "Проект «{name}» создан"
NAME_REQUIRED = "Укажи имя голоса"
PROJECT_EXISTS = "Папка «{name}» уже существует"
NO_PROJECT_SELECTED = "Сначала выбери или создай проект"

# Sections (also the step chips)
SEC_SETUP = "Установка"
SEC_AUDIO = "Аудио"
SEC_SLICE = "Нарезка"
SEC_PHRASES = "Фразы"
SEC_CHECK = "Проверка"
SEC_TRAIN = "Обучение"
SEC_PACK = "Упаковка"

# Audio
UPLOAD = "Загрузить аудио (можно несколько файлов)"
UPLOADED = "Загружено файлов: {n}"
RAW_FILES = "Файлы в raw/"
RAW_NAME = "файл"
RAW_SIZE = "размер"
ISOLATE = "Отделить голос от музыки"
SLICE = "Нарезать"
SLICING = "Нарезаю {name}"
SLICED_TEXT = "Нарезано фраз: {n}, текст распознан — проверь во «Фразах»"
SLICED_NO_TEXT = ("Нарезано фраз: {n} по паузам, текст не распознан (нет faster-whisper) — "
                  "нажми «Расшифровать» во «Фразах»")
SLICED_NONE = "Новых фраз нет: всё из raw/ уже нарезано или речь не найдена"

# Phrases
ONLY_FLAGGED = "только ⚑"
COL_ID = "id"
COL_TEXT = "текст"
COL_DURATION = "длит., с"
COL_FLAGS = "флаги"
COL_DROPPED = "выкинута"
PLAYER = "Выбранная фраза"
TRANSCRIBE = "Расшифровать"
TRANSCRIBING = "Распознаю {name}"
TRANSCRIBED = "Распознано фраз: {n}"
SAVE_EDITS = "Сохранить правки"
SAVED_EDITS = "Сохранено правок: {n}"
TOGGLE_DROP = "Выкинуть/Вернуть"
DROPPED = "Фраза {id} выкинута"
RESTORED = "Фраза {id} возвращена"
SELECT_ROW = "Сначала выбери фразу в таблице"
PHRASES_DONE = "Готово"
PHRASES_MARKED = "Фразы отмечены как готовые"
STAT_PHRASES = "фраз"
STAT_SPEECH = "речь"
STAT_MINUTES = "мин"
STAT_CHECK = "к проверке"
STAT_DROPPED = "выкинуто"

# Check
CHECK = "Проверить"
CHECK_SUMMARY = "Минут речи: {minutes}, фраз: {phrases}"
CHECK_OK = "Ошибок нет — можно обучать"
CHECK_ISSUES = "Проблемы по фразам"
CHECK_EMPTY = "Нажми «Проверить», чтобы оценить датасет"

# Train
EPOCHS = "Сколько эпох дообучать"
BATCH = "Размер батча"
TRAIN_START = "Старт"
TRAIN_STOP = "Стоп"
TRAIN_RESUME = "Продолжить"
TRAIN_LOG = "Журнал обучения"
TRAIN_IDLE = "Обучение не запущено"
TRAIN_RUNNING = "ОБУЧЕНИЕ · эпоха {epoch}/{target}"
TRAIN_RUNNING_NO_EPOCH = "ОБУЧЕНИЕ · запуск…"
TRAIN_DONE = "Обучение завершено"
TRAIN_STOPPED = "Обучение остановлено — нажми «Продолжить»"
TRAIN_FAILED = "Обучение прервалось (код {code}) — см. журнал"
TRAIN_ERROR = "Ошибка обучения — см. журнал"
TRAIN_BUSY = "Обучение уже идёт"
TRAIN_STOPPING = "Останавливаю контейнер…"
TRAIN_DOWNLOAD = "Скачиваю базовую модель: {pct}%"
LOSS = "Потери (loss)"
LOSS_STEP = "шаг"
LOSS_VALUE = "loss"
CHECKPOINTS = "Чекпойнты"
CHECKPOINT_LAST = "последний (эпоха {epoch})"
CHECKPOINT_ITEM = "эпоха {epoch}"
REFRESH = "Обновить"
PREVIEW_STEP = "Превью шага"
PREVIEW = "Превью {n}"
NO_CHECKPOINTS = "Чекпойнтов пока нет"
EXPORT = "Экспортировать этот чекпойнт"
EXPORTED = "Модель экспортирована: {path}. Дальше — «Упаковка»."
CHOOSE_CHECKPOINT = "Выбери чекпойнт"
COLAB_HINT = ("**Нет видеокарты NVIDIA для Docker** — обучай в Google Colab: скачай датасет кнопкой ниже "
              "и открой [ноутбук omnivoice]({url}).")
COLAB_ZIP = "Скачать датасет для Colab"
COLAB_FILE = "Датасет для Colab"

# Setup (dependencies)
SETUP_INTRO = ("Всё, что нужно для подготовки и обучения: пакеты, ffmpeg и среда обучения WSL "
               "(~15 ГБ в папке для зависимостей, ставится один раз). Уже установленное пропускается.")
SETUP_CHECKING = "Проверяю, что уже установлено…"
SETUP_OPTIONAL = "необязательно"
SETUP_INSTALL = "Установить зависимости"
SETUP_LOG = "Журнал установки"
SETUP_IDLE = "Установка не запущена"
SETUP_RUNNING = "Идёт установка — можно свернуть окно, но не закрывай его"
SETUP_DONE = "Готово — всё установлено"
SETUP_DONE_MISSING = "Установка завершилась, но не всё готово — см. список"
SETUP_REBOOT_TITLE = "Нужна перезагрузка"
SETUP_ERROR = "Установка прервалась"
SETUP_CHECK_FAILED = "Не удалось проверить зависимости: {error}"
SETUP_BUSY = "Установка уже идёт — подожди"
SETUP_STEP = "Шаг {n}/{total}"
SETUP_DOWNLOADING = "Скачиваю: {pct}%"
SETUP_FIRST = "Сначала установи зависимости"
SETUP_FIRST_HINT = "Среда обучения не найдена: ни WSL omnivoice, ни Docker с GPU. Сначала установи зависимости → «Установка»."
SETUP_GOTO = "Перейти к установке"

# Dependency folder (WSL disk, base models, ffmpeg)
DATA_DIR = "Папка для зависимостей"
DATA_DIR_INFO = "Среда WSL, базовые модели и ffmpeg (~15 ГБ). Уже установленное переносится целиком, проекты остаются на месте"
DATA_DIR_MOVE = "Сменить / перенести"
DATA_DIR_FREE = "Свободно на диске {drive} — {free}"
DATA_DIR_NO_DRIVE = "Диск {drive} недоступен"
DATA_DIR_ENV = "Задана переменной окружения OMNIVOICE_CACHE — сменить её можно только там"
DATA_DIR_DONE = "Готово — папка для зависимостей сменена"
DATA_DIR_ERROR = "Перенос не удался"

# Pack
F_NAME = "Имя"
F_DESCRIPTION = "Описание"
F_GENDER = "Пол"
F_SAMPLE = "Фраза-пример"
F_LICENSE = "Лицензия"
PORTRAIT = "Портрет (любая картинка — ужмётся до 32×32)"
PORTRAIT_PREVIEW = "Так он будет выглядеть"
PORTRAIT_BAD = "Не удалось прочитать картинку"
PACK = "Упаковать"
PACKED = "Голос собран: {path}"
SAMPLE_AUDIO = "Пример звучания"
INSTALL_TARGET = "Куда установить (папка models мода)"
INSTALL_OVERWRITE = "Заменить, если уже есть"
INSTALL = "Установить в Minecraft"
INSTALLED = "Голос установлен: {path}"
INSTALL_NO_TARGET = "Укажи папку models мода"
INSTALL_NO_VOICE = "Сначала упакуй голос"

# Errors
ERR_UNKNOWN = "Непредвиденная ошибка — подробности в консоли"
ERR_TITLE = "Ошибка"

# Helpers
BAD_FILE_NAME = "Недопустимое имя файла: {name}"
KB = "КБ"
NO_SEGMENT = "Нет фразы {id}"

# Concurrent operations on one project
PROJECT_BUSY = "Проект занят: идёт {op} — подожди"
OP_SLICE = "нарезка"
OP_TRANSCRIBE = "распознавание"
OP_SAVE = "сохранение правок"
OP_DROP = "изменение фразы"
OP_DONE = "отметка фраз"
OP_CHECK = "проверка"
OP_PACK = "упаковка"
OP_COLAB = "сборка датасета для Colab"
OP_TRAIN = "подготовка обучения"
OP_UPLOAD = "загрузка аудио"
OP_EXPORT = "экспорт в ONNX"

# Progress / status for slower actions
EXPORTING = "Экспортирую чекпойнт в ONNX…"
REFRESHING = "Ищу чекпойнты и превью…"
ZIPPING = "Собираю датасет для Colab…"
PACKING = "Упаковываю голос…"
VERIFYING = "Проверяю голос в sherpa-onnx…"
COLAB_READY = "Датасет готов: {path}"

# Install target
TARGET_NOT_ABSOLUTE = "Укажи полный путь к папке models (например C:\\…\\models)"
TARGET_NOT_FOUND = "Папка не найдена: {path}"

# Human labels for flag / issue codes (unknown codes are shown as is)
CODE_CHECK = "проверить"
CODE_FOREIGN_LETTERS = "чужие буквы"
CODE_TOO_SHORT = "слишком короткая"
CODE_TOO_LONG = "слишком длинная"
CODE_CLIPPING = "перегруз"
CODE_EMPTY_TEXT = "нет текста"
CODE_UNSPEAKABLE = "непроизносимо"
CODE_MISSING_AUDIO = "нет аудио"

# Not a str constant (lower-case on purpose, so the "UPPER_CASE values are str" rule still holds).
code_labels = {
    "check": CODE_CHECK, "foreign_letters": CODE_FOREIGN_LETTERS, "too_short": CODE_TOO_SHORT,
    "too_long": CODE_TOO_LONG, "clipping": CODE_CLIPPING, "empty_text": CODE_EMPTY_TEXT,
    "unspeakable": CODE_UNSPEAKABLE, "missing_audio": CODE_MISSING_AUDIO,
}
