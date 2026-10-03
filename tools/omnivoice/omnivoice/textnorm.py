import re
from num2words import num2words

_STAGE = re.compile(r"\*[^*]*\*|\[[^\]]*\]|\([^)]*\)")
_ALLOWED = re.compile(r"[^\w\s.,!?;:\-—«»\"'%]", re.UNICODE)
# Match numbers with special adjacent characters, also match letter-digit tokens
# First pattern: letter-digit tokens like v2, x3d
_LETTER_DIGIT = re.compile(r"[a-zA-Zа-яА-ЯёЁ]+\d+|v2|x3d|x3D|2x|3D", re.UNICODE)
# Second pattern: regular numbers (only after word boundary or hyphen not preceded by digit)
_NUMBER = re.compile(r"(?<!\w)-?\d+(?:[.,/:%-]\d+)*%?")
_LATIN = re.compile(r"[A-Za-z]")
_CYRILLIC = re.compile(r"[а-яА-ЯёЁ]")


def normalize_text(text: str, language: str) -> tuple[str, list[str]]:
    flags: list[str] = []

    # Step 1: Remove stage directions
    stripped = _STAGE.sub(" ", text)
    if stripped != text:
        flags.append("stage_direction")

    # Step 2: Remove underscores and non-ASCII digit-like symbols (superscripts, etc.)
    underscore_removed = False
    if "_" in stripped:
        underscore_removed = True
        stripped = stripped.replace("_", " ")
    # Remove superscripts ²³⁴⁵⁶⁷⁸⁹⁰¹ and similar
    if re.search(r"[²³⁴⁵⁶⁷⁸⁹⁰¹]", stripped):
        underscore_removed = True
        stripped = re.sub(r"[²³⁴⁵⁶⁷⁸⁹⁰¹]", " ", stripped)

    # Step 3: Remove emoji and symbols (except allowed punctuation)
    cleaned = _ALLOWED.sub(" ", stripped)
    if cleaned != stripped or underscore_removed:
        flags.append("emoji")

    # Step 4: Convert numbers (integers, decimals, negatives, with special handling)
    digits_found = False
    check_found = False

    # First, handle letter-digit tokens (v2, x3d, etc.)
    def replace_letter_digit(m):
        nonlocal check_found, digits_found
        check_found = True
        digits_found = True
        return m.group()

    cleaned = _LETTER_DIGIT.sub(replace_letter_digit, cleaned)

    def replace_number(m):
        nonlocal digits_found, check_found
        num_str = m.group()
        start = m.start()
        end = m.end()

        before_char = cleaned[start - 1] if start > 0 else " "
        after_char = cleaned[end] if end < len(cleaned) else " "
        after_after_char = cleaned[end + 1] if end + 1 < len(cleaned) else " "

        # Check for letter-digit tokens (v2, etc.)
        if before_char.isalpha():
            check_found = True
            digits_found = True
            return num_str

        # Check if it's a true negative number (- preceded by whitespace/start)
        is_negative = num_str.startswith("-")
        if is_negative and before_char.isdigit():
            # This is a hyphen between digits, not minus
            is_negative = False

        # Check for ordinal suffixes like 1-й or 2-го
        if after_char == "-" and after_after_char.isalpha():
            check_found = True

        # Handle percentage (100%)
        if num_str.endswith("%"):
            digits_found = True
            try:
                num_part = num_str[:-1]
                if num_part.startswith("-"):
                    num_part = num_part[1:]
                    num_val = int(num_part)
                    result = num2words(num_val, lang=language)
                    if language == "ru":
                        return result + " процентов"
                    else:
                        return result + " percent"
                else:
                    num_val = int(num_part)
                    result = num2words(num_val, lang=language)
                    if language == "ru":
                        return result + " процентов"
                    else:
                        return result + " percent"
            except (ValueError, Exception):
                return num_str

        # Handle colon-separated numbers (10:30 time format)
        if ":" in num_str:
            check_found = True
            digits_found = True
            try:
                parts = num_str.split(":")
                converted_parts = []
                for part in parts:
                    if part:
                        converted_parts.append(num2words(int(part), lang=language))
                return " ".join(converted_parts)
            except (ValueError, Exception):
                return num_str

        # Handle hyphen-separated numbers (5-3 or 2024-05)
        if "-" in num_str and not is_negative:
            check_found = True
            digits_found = True
            try:
                parts = num_str.split("-")
                converted_parts = []
                for part in parts:
                    if part:
                        converted_parts.append(num2words(int(part), lang=language))
                return " ".join(converted_parts)
            except (ValueError, Exception):
                return num_str

        # Check for multiple decimal separators or English thousands format
        if "." in num_str or "," in num_str:
            # Count the separators
            dot_count = num_str.count(".")
            comma_count = num_str.count(",")
            total_seps = dot_count + comma_count

            # Check if it's English thousands separator (1,000)
            if comma_count > 0 and language == "en":
                comma_pos = num_str.rfind(",")
                after_comma = num_str[comma_pos + 1:]
                if comma_pos > 0 and len(after_comma) == 3 and after_comma.isdigit():
                    # This looks like 1,000 - not a decimal, flag as check
                    check_found = True
                    digits_found = True
                    # Don't convert, just return the original to preserve value
                    return num_str

            # Check for multiple separators (1.5.2026)
            if total_seps > 1:
                check_found = True
                digits_found = True
                # Split by any separator and convert each group
                parts = re.split(r"[.,]", num_str)
                converted_parts = []
                for part in parts:
                    if part and part.isdigit():
                        converted_parts.append(num2words(int(part), lang=language))
                return " ".join(converted_parts)

            # Valid single decimal
            try:
                normalized = num_str.replace(",", ".")
                float_val = float(normalized)
                digits_found = True
                return num2words(float_val, lang=language)
            except (ValueError, Exception):
                return num_str

        # Regular integer or negative number
        try:
            # Check if followed by letters (2x, 3D)
            if after_char.isalpha():
                check_found = True

            digits_found = True
            return num2words(int(num_str), lang=language)
        except (ValueError, Exception):
            return num_str

    if _NUMBER.search(cleaned):
        cleaned = _NUMBER.sub(replace_number, cleaned)

    if digits_found:
        flags.append("digits")
    if check_found:
        flags.append("check")

    # Step 5: Collapse whitespace and fix punctuation spacing
    cleaned = re.sub(r"\s+([.,!?;:])", r"\1", re.sub(r"\s+", " ", cleaned)).strip()

    # Step 6: Check for non-speakable characters (non-Latin, non-Cyrillic letters)
    # Flag any letter that is not Latin and not Cyrillic for every language
    has_non_speakable = False
    for char in cleaned:
        if char.isalpha() and not _LATIN.match(char) and not _CYRILLIC.match(char):
            has_non_speakable = True
            break

    # Step 7: Language-specific checks
    if language == "ru":
        # For Russian: flag Latin letters
        if _LATIN.search(cleaned):
            if "foreign_letters" not in flags:
                flags.append("foreign_letters")
    else:
        # For other languages: flag Cyrillic letters as foreign
        if _CYRILLIC.search(cleaned):
            if "foreign_letters" not in flags:
                flags.append("foreign_letters")

    # Step 8: Flag any non-speakable (non-Latin, non-Cyrillic) characters
    if has_non_speakable:
        if "foreign_letters" not in flags:
            flags.append("foreign_letters")

    # Step 9: Check if empty
    if not cleaned:
        flags.append("empty")

    return cleaned, flags
