from dataclasses import dataclass

BASE_CHECKPOINTS = {
    "denis": "ru/ru_RU/denis/medium/epoch=4474-step=1521860.ckpt",
    "dmitri": "ru/ru_RU/dmitri/medium/epoch=5589-step=1478840.ckpt",
    "irina": "ru/ru_RU/irina/medium/epoch=4139-step=929464.ckpt",
    "ruslan": "ru/ru_RU/ruslan/medium/epoch=2436-step=1724372.ckpt",
    "lessac": "en/en_US/lessac/medium/epoch=2164-step=1355540.ckpt",
}

@dataclass(frozen=True)
class Language:
    code: str
    espeak_voice: str
    iso_name: str
    base_checkpoint: str
    test_phrase: str

PRESETS = {
    "ru": Language("ru", "ru", "Russian", BASE_CHECKPOINTS["irina"], "Привет! Вот так я звучу."),
    "en": Language("en", "en-us", "English", BASE_CHECKPOINTS["lessac"], "Hello! This is how I sound."),
}
