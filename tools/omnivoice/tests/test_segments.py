from omnivoice.segments import plan_segments

def test_merges_close_regions_and_drops_tiny():
    out = plan_segments([(0.0, 0.8), (0.9, 2.5), (5.0, 5.2)], None)
    assert out == [(0.0, 2.5)]

def test_keeps_separate_when_gap_large():
    out = plan_segments([(0.0, 2.0), (3.0, 6.0)], None)
    assert out == [(0.0, 2.0), (3.0, 6.0)]

def test_long_speech_is_split_at_quietest_point():
    quiet_at = 22.0
    energy = lambda a, b: 0.0 if a <= quiet_at <= b else 1.0
    out = plan_segments([(0.0, 40.0)], energy)
    assert all(1.0 <= e - s <= 15.0 for s, e in out)
    assert any(abs(e - quiet_at) < 0.2 for s, e in out)
    assert out[0][0] == 0.0 and out[-1][1] == 40.0


# ---------------- transcript-driven planning ----------------
from omnivoice.segments import Word, plan_from_words


def _line(text: str, start: float, dur: float, gap: float = 0.05) -> list[Word]:
    """Words of `text` spread evenly over [start, start + dur] with `gap` between words."""
    toks = text.split()
    step = dur / len(toks)
    return [Word(round(start + i * step, 3), round(start + (i + 1) * step - gap, 3), " " + t)
            for i, t in enumerate(toks)]


def test_words_split_into_sentences_at_punctuation_even_with_tiny_pauses():
    words = _line("Привет, подопытный номер один.", 0.5, 3.0) + _line("Тест начнётся через минуту!", 3.62, 3.0)
    out = plan_from_words(words)
    assert [t for _, _, t in out] == ["Привет, подопытный номер один.", "Тест начнётся через минуту!"]
    (s0, e0, _), (s1, e1, _) = out
    first_end, second_start = words[3].end, words[4].start
    assert first_end <= e0 <= s1 <= second_start          # cut inside the gap, no word is cut
    assert abs(e0 - (first_end + second_start) / 2) < 1e-6  # in its middle
    assert s0 == round(0.5 - 0.15, 3)                       # head margin is the pad


def test_long_word_gap_splits_a_sentence_without_punctuation():
    words = _line("первая часть фразы", 0.0, 2.0) + _line("вторая часть фразы", 2.7, 2.0)
    out = plan_from_words(words)
    assert [t for _, _, t in out] == ["первая часть фразы", "вторая часть фразы"]


def test_question_ellipsis_and_closing_quote_end_sentences():
    words = (_line("Ты уверен?", 0.0, 1.5) + _line("Ну что ж…", 1.6, 1.5)
             + _line("Он сказал «нет».", 3.2, 1.5) + _line("Ладно тогда", 4.8, 1.5))
    out = plan_from_words(words)
    assert [t for _, _, t in out] == ["Ты уверен?", "Ну что ж…", "Он сказал «нет».", "Ладно тогда"]


def test_one_word_line_that_fits_with_padding_stays_alone():
    words = (_line("Никто не смеет мне приказывать!", 0.0, 2.0) + _line("Полегче!", 2.17, 0.73)
             + _line("Ну что ещё?", 3.8, 1.0))
    out = plan_from_words(words)
    assert [t for _, _, t in out] == ["Никто не смеет мне приказывать!", "Полегче!", "Ну что ещё?"]


def test_too_short_piece_merges_into_closer_neighbour():
    words = (_line("Никто не смеет мне приказывать!", 0.0, 2.0) + _line("Ну!", 2.2, 0.25)
             + _line("Потом другое.", 3.0, 1.5))
    out = plan_from_words(words)
    assert [t for _, _, t in out] == ["Никто не смеет мне приказывать! Ну!", "Потом другое."]


def test_too_short_piece_is_dropped_when_merge_is_impossible():
    words = (_line("Раз два три четыре.", 0.0, 1.8) + _line("Пять шесть семь.", 2.0, 1.8)
             + _line("Ай.", 4.6, 0.25) + _line("Долгая фраза где-то потом.", 5.5, 2.0))
    out = plan_from_words(words)        # "Ай." has 0.8 s / 0.65 s gaps: too far to merge
    assert [t for _, _, t in out] == ["Раз два три четыре.", "Пять шесть семь.", "Долгая фраза где-то потом."]
    out = plan_from_words(_line("Раз два три четыре пять.", 0.0, 2.9) + _line("Ай.", 3.0, 0.2), target_s=3.0)
    assert [t for _, _, t in out] == ["Раз два три четыре пять."]


def test_word_pieces_are_joined_as_recognised():
    words = [Word(0.0, 0.6, " Наконец"), Word(0.6, 1.0, "-то!"), Word(1.1, 1.6, " Вот")]
    assert plan_from_words(words)[0][2] == "Наконец-то!"


def test_long_sentence_is_split_at_largest_word_gap():
    words = _line(" ".join(["слово"] * 20), 0.0, 9.0) + _line(" ".join(["ещё"] * 20), 9.35, 9.0)
    out = plan_from_words(words)
    assert len(out) == 2
    assert all(e - s <= 15.0 for s, e, _ in out)
    assert words[19].end <= out[0][1] <= out[1][0] <= words[20].start


def test_lone_short_piece_is_dropped_and_empty_input_is_empty():
    assert plan_from_words([]) == []
    assert plan_from_words(_line("Ай.", 0.0, 0.3)) == []


def test_margins_are_clamped_to_file_bounds():
    words = _line("Самое начало файла тут.", 0.05, 2.0)
    (s, e, _), = plan_from_words(words, total=2.1)
    assert s == 0.0 and e == 2.1


def _loud(*spans):
    return lambda a, b: 1.0 if any(a < e and b > s for s, e in spans) else 0.0


def test_energy_moves_cut_into_the_real_pause_when_timestamps_touch():
    # Whisper glued the lines (end == start == 1.0) but the audio pause is 1.15–1.30
    words = [Word(0.0, 0.5, " Твоя"), Word(0.5, 1.0, " душа!"), Word(1.0, 1.6, " Как"), Word(1.6, 2.2, " глупо!")]
    out = plan_from_words(words, energy=_loud((0.0, 1.15), (1.3, 2.2)), quiet=0.5)
    assert len(out) == 2 and out[0][1] == out[1][0] and 1.15 <= out[0][1] <= 1.3


def test_energy_trims_silence_to_pad_from_the_real_onset():
    # long pause; Whisper says the second line starts at 3.5, audio says 3.3
    words = [Word(0.0, 1.0, " Первая"), Word(1.0, 2.0, " фраза."), Word(3.5, 4.5, " Вторая"), Word(4.5, 5.0, " фраза.")]
    out = plan_from_words(words, energy=_loud((0.0, 2.0), (3.3, 5.0)), quiet=0.5)
    assert abs(out[0][1] - 2.15) < 0.03 and abs(out[1][0] - 3.15) < 0.03


def test_energy_keeps_untranscribed_sound_before_the_first_word_out():
    words = [Word(2.3, 3.0, " Говори,"), Word(3.0, 3.6, " глупец!")]
    out = plan_from_words(words, total=5.0, energy=_loud((0.4, 1.8), (2.1, 3.6)), quiet=0.5)
    assert 1.8 <= out[0][0] <= 2.1 and abs(out[0][1] - 3.75) < 0.03


def test_uncovered_finds_loud_audio_without_words():
    from omnivoice.segments import uncovered
    words = [Word(2.3, 3.0, " Говори,"), Word(3.0, 3.6, " глупец!"), Word(15.4, 16.0, " За")]
    loud = [(0.4, 1.8), (2.1, 3.7), (14.1, 17.5), (20.0, 20.2)]
    assert uncovered(words, loud) == [(0.4, 1.8), (14.1, 15.3), (16.1, 17.5)]
    assert uncovered([], [(1.0, 1.2)]) == []          # shorter than min_len


def test_near_equal_energy_prefers_the_gap_middle():
    words = [Word(0.0, 1.0, " Раз."), Word(2.0, 3.0, " Два.")]
    wobble = lambda a, b: 1.0 + 0.01 * ((a * 100) % 7)       # loud everywhere, tiny ripple
    out = plan_from_words(words, energy=wobble, quiet=0.5)
    assert abs(out[0][1] - 1.5) < 1e-6 and abs(out[1][0] - 1.5) < 1e-6   # no pause: cut at the middle
