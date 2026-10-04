from dataclasses import dataclass

BASE_CHECKPOINTS = {
    "denis": "ru/ru_RU/denis/medium/epoch=4474-step=1521860.ckpt",
    "dmitri": "ru/ru_RU/dmitri/medium/epoch=5589-step=1478840.ckpt",
    "irina": "ru/ru_RU/irina/medium/epoch=4139-step=929464.ckpt",
    "ruslan": "ru/ru_RU/ruslan/medium/epoch=2436-step=1724372.ckpt",
    "lessac": "en/en_US/lessac/medium/epoch=2164-step=1355540.ckpt",
    "amy": "en/en_US/amy/medium/epoch=6679-step=1554200.ckpt",
    "hfc_female": "en/en_US/hfc_female/medium/epoch=2868-step=1575188.ckpt",
    "hfc_male": "en/en_US/hfc_male/medium/epoch=2785-step=2128064.ckpt",
    "joe": "en/en_US/joe/medium/epoch=7889-step=1221224.ckpt",
    "ryan": "en/en_US/ryan/medium/epoch=4641-step=3104302.ckpt",
}
# only checkpoints named epoch=N-…: train.base_epoch needs N to count the epochs trained on top
BASE_GENDER = {"denis": "m", "dmitri": "m", "irina": "f", "ruslan": "m", "lessac": "f", "amy": "f",
               "hfc_female": "f", "hfc_male": "m", "joe": "m", "ryan": "m"}

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


def bases_for(language: str) -> list[str]:
    """Base models of a language (their checkpoints live under "<code>/"), alphabetically."""
    return sorted(n for n, ck in BASE_CHECKPOINTS.items() if ck.startswith(f"{language}/"))


def default_base(language: str) -> str | None:
    lang = PRESETS.get(language)
    return next((n for n, ck in BASE_CHECKPOINTS.items() if lang and ck == lang.base_checkpoint), None)


def base_of(checkpoint: str) -> str | None:
    """The base model name of a project's base_checkpoint path."""
    return next((n for n, ck in BASE_CHECKPOINTS.items() if ck == checkpoint), None)
