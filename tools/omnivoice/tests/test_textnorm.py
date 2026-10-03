from omnivoice.textnorm import normalize_text


# Original tests (must keep passing)
def test_digits_become_words():
    t, f = normalize_text("Тест номер 3.", "ru")
    assert t == "Тест номер три." and "digits" in f


def test_stage_directions_and_emoji_are_removed_and_flagged():
    t, f = normalize_text("*звук двери* Ты здесь? 😀 [неразборчиво]", "ru")
    assert t == "Ты здесь?" and {"stage_direction", "emoji"} <= set(f)


def test_latin_in_russian_is_flagged_not_removed():
    t, f = normalize_text("Запусти Aperture Science.", "ru")
    assert "Aperture" in t and "foreign_letters" in f


def test_empty():
    t, f = normalize_text("*тишина*", "ru")
    assert t == "" and "empty" in f


def test_english():
    t, f = normalize_text("I have 2 cakes!", "en")
    assert t == "I have two cakes!" and f == ["digits"]


# Fix round 1: new tests for decimals, negative numbers, glued digits, non-speakable

def test_decimal_with_dot():
    t, f = normalize_text("Температура 3.5 градуса.", "ru")
    assert "три целых пять десятых" in t and "digits" in f


def test_decimal_with_comma():
    t, f = normalize_text("Цена 9,99 рублей.", "ru")
    assert "девять целых девяносто девять сотых" in t and "digits" in f


def test_decimal_english():
    t, f = normalize_text("The value is 2.5 meters.", "en")
    assert "two point five" in t and "digits" in f


def test_negative_number_at_boundary():
    t, f = normalize_text("Температура -5 градусов.", "ru")
    assert "минус пять" in t and "digits" in f


def test_negative_english():
    t, f = normalize_text("The temperature is -10 degrees.", "en")
    assert "minus ten" in t and "digits" in f


def test_digit_glued_to_ordinal_suffix_russian():
    t, f = normalize_text("1-й день и 2-го месяца.", "ru")
    assert "digits" in f and "check" in f


def test_digit_glued_to_latin_letter():
    t, f = normalize_text("Это 2x более быстро и 3D видео.", "ru")
    assert "digits" in f and "check" in f


def test_underscore_removed_and_flagged():
    t, f = normalize_text("hello_world test", "en")
    assert "_" not in t and "emoji" in f


def test_superscripts_removed_and_flagged():
    t, f = normalize_text("x² плюс y³ равно z.", "ru")
    assert "²" not in t and "³" not in t and "emoji" in f


def test_cyrillic_foreign_letters_in_english():
    t, f = normalize_text("Это текст на русском языке.", "en")
    # Cyrillic letters should be flagged as foreign_letters for English
    assert "foreign_letters" in f


def test_cjk_characters_flagged():
    t, f = normalize_text("Привет 你好 мир.", "ru")
    assert "foreign_letters" in f  # CJK is not Latin or Cyrillic


def test_arabic_characters_flagged():
    t, f = normalize_text("Привет السلام мир.", "ru")
    assert "foreign_letters" in f  # Arabic is not Latin or Cyrillic


# Fix round 2: silent mangling prevention

def test_hyphen_between_digits_not_minus():
    t, f = normalize_text("5-3 дня.", "ru")
    # Should NOT convert to minus, should keep/convert with check flag
    assert "пять" in t and "три" in t and "check" in f


def test_date_format_with_hyphens():
    t, f = normalize_text("2024-05 был хорош.", "ru")
    assert "check" in f  # Flag the ambiguous format


def test_multiple_dots_not_decimal():
    t, f = normalize_text("Файл 1.5.2026 создан.", "ru")
    assert "check" in f  # Multiple dots, not a decimal


def test_comma_thousands_not_decimal_english():
    t, f = normalize_text("It costs 1,000 dollars.", "en")
    # Should NOT become "one" (silent mangling)
    assert "1" in t and "000" in t and "check" in f


def test_colon_time_format():
    t, f = normalize_text("В 10:30 встреча.", "ru")
    assert "check" in f  # Time format, ambiguous


def test_percent_symbol():
    t, f = normalize_text("100% работает.", "ru")
    assert "digits" in f


def test_letter_digit_token_flagged():
    t, f = normalize_text("v2 версия.", "ru")
    assert "check" in f  # Neither fully converted nor removed


def test_valid_negative_number_still_works():
    t, f = normalize_text("-5 градусов.", "ru")
    assert "минус пять" in t and "digits" in f


def test_valid_decimal_still_works():
    t, f = normalize_text("3.5 метра.", "ru")
    assert "целых" in t or ("три" in t and "пять" in t)
    assert "digits" in f
