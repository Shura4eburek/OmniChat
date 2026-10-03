from __future__ import annotations
from dataclasses import dataclass, field
from omnivoice import audio, dataset

@dataclass
class Report:
    total_minutes: float = 0.0
    phrases: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    per_segment: dict[str, list[str]] = field(default_factory=dict)

def _default_phonemizer(p):
    try:
        from piper.phonemize_espeak import EspeakPhonemizer  # piper-tts
    except ImportError:
        return None
    except AttributeError:
        return None
    try:
        phon = EspeakPhonemizer()
    except Exception:
        return None
    return lambda text: [ph for sent in phon.phonemize(p.espeak_voice, text) for ph in sent]

def check_project(p, phonemize=None) -> Report:
    r = Report()
    ph = phonemize or _default_phonemizer(p)
    if ph is None:
        r.warnings.append("Фонемизатор не установлен — проверка произносимости пропущена")
    segs = [s for s in dataset.load(p) if not s.dropped]
    r.phrases = len(segs)
    phonemize_failures = 0

    for s in segs:
        issues = [f for f in s.flags if f in ("check", "foreign_letters")]
        path = p.segments_dir / f"{s.id}.wav"

        # Try to load audio
        try:
            try:
                import soundfile
                has_soundfile_error = hasattr(soundfile, 'SoundFileError')
            except ImportError:
                has_soundfile_error = False

            x, _ = audio.load_mono(path)
        except (FileNotFoundError, OSError, RuntimeError) as e:
            issues.append("missing_audio")
            if issues: r.per_segment[s.id] = issues
            continue
        except Exception as e:
            # Catch soundfile.SoundFileError or any other audio loading error
            if has_soundfile_error and isinstance(e, soundfile.SoundFileError):
                issues.append("missing_audio")
                if issues: r.per_segment[s.id] = issues
                continue
            raise

        dur = len(x) / audio.SR
        r.total_minutes += dur / 60
        if dur < 1.0: issues.append("too_short")
        if dur > 15.3: issues.append("too_long")
        if audio.clipping_ratio(x) > 0.001: issues.append("clipping")

        if not s.text.strip():
            issues.append("empty_text")
        elif ph is not None:
            try:
                if not ph(s.text):
                    issues.append("unspeakable")
                    phonemize_failures += 1
            except Exception:
                issues.append("unspeakable")
                phonemize_failures += 1

        if issues: r.per_segment[s.id] = issues

    # Check threshold before rounding
    total_minutes_unrounded = r.total_minutes
    r.total_minutes = round(r.total_minutes, 1)

    if r.phrases == 0: r.errors.append("Нет ни одной фразы")
    if any("empty_text" in v for v in r.per_segment.values()): r.errors.append("Есть фразы без текста")
    if any("missing_audio" in v for v in r.per_segment.values()): r.errors.append(f"Нет аудио у фраз: {sum(1 for v in r.per_segment.values() if 'missing_audio' in v)}")
    if total_minutes_unrounded < 10: r.warnings.append(f"Мало данных: {r.total_minutes} мин (минимум 10, лучше 30+)")
    if ph is not None and phonemize_failures == r.phrases and r.phrases > 0:
        r.warnings.append("Фонемизатор падает на всех фразах — проверь установку piper-tts")

    p.mark_fresh("check", not r.errors)

    return r
