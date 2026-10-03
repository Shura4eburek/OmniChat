from pathlib import Path

from omnivoice import trainlog as tl

DATA = Path(__file__).parent / "data"
BAR = "█" * 10


def feed_all(clean, text):
    """Feed text the way TrainRunner sees it: universal-newline split (\\r and \\n both end a line)."""
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        clean.feed(line)


def epoch_block(n, val_mos=None, rate="1.70it/s", up=True):
    """One epoch of real Lightning/tqdm output: training bar redraws, validation bars (cursor-up
    escapes from tqdm's nested position), then the epoch bar redrawn with the fresh val metrics."""
    esc = "\x1b[A" if up else ""
    prev = ", val_mos=1.000" if n else ""
    post = f", v_num=1, val_mos={val_mos:.3f}" if val_mos is not None else ", v_num=1"
    return (f"\rEpoch {n}:   0%|          | 0/3 [00:00<?, ?it/s, v_num=1{prev}]"
            f"\rEpoch {n}:  67%|{BAR[:7]}   | 2/3 [00:01<00:00, {rate}, v_num=1{prev}]"
            f"\rEpoch {n}: 100%|{BAR}| 3/3 [00:01<00:00, {rate}, v_num=1{prev}]\n"
            f"\nValidation: |          | 0/? [00:00<?, ?it/s]{esc}\n"
            f"\nValidation DataLoader 0:   0%|          | 0/1 [00:00<?, ?it/s]{esc}\n"
            f"\nValidation DataLoader 0: 100%|{BAR}| 1/1 [00:00<00:00, 12.01it/s]{esc}\n"
            f"\r                                                                      {esc}\n"
            f"\rEpoch {n}: 100%|{BAR}| 3/3 [00:03<00:00,  0.27it/s{post}]")


def test_strip_ansi_and_redraws():
    assert tl.strip_ansi("\x1b[A\x1b[2KEpoch 1\x1b[0m") == "Epoch 1"
    assert tl.last_redraw("Epoch 1: 10%\rEpoch 1: 50%\r") == "Epoch 1: 50%"


def test_epoch_lines_from_tqdm_postfix():
    clean = tl.LogCleaner(offset=4139, target=4139 + 1000)
    feed_all(clean, epoch_block(4140, 2.3630) + epoch_block(4141, 2.1, rate="1.25s/it"))
    lines = clean.render({4140: {"val_mel": 0.3911}})
    assert lines == ["Эпоха 1/1000 · качество (MOS) 2.36 · mel 0.39 · 1.7 ит/с",
                     "Эпоха 2/1000 · качество (MOS) 2.10 · 1.25 с/ит"]
    assert clean.epoch == 4141 and clean.done_epoch == 4141


def test_mel_filled_in_later_from_events():
    clean = tl.LogCleaner(offset=0, target=10)
    feed_all(clean, epoch_block(3, 2.0))
    assert "mel" not in clean.render()[0]
    assert clean.render({3: {"val_mel": 0.5}})[0].endswith("mel 0.50 · 1.7 ит/с")


def test_epoch_without_mos_emitted_after_validation():
    clean = tl.LogCleaner(offset=0, target=10)
    feed_all(clean, epoch_block(1, None))
    assert clean.render() == ["Эпоха 1/10 · 1.7 ит/с"]


def test_epoch_never_validated_is_emitted_when_the_next_starts():
    clean = tl.LogCleaner(offset=0, target=10)
    feed_all(clean, f"Epoch 1: 100%|{BAR}| 3/3 [00:01<00:00, 2.00it/s, v_num=1]\n"
                    f"Epoch 2:   0%|          | 0/3 [00:00<?, ?it/s, v_num=1]")
    assert clean.render() == ["Эпоха 1/10 · 2.0 ит/с"]
    clean.finish()
    assert clean.render() == ["Эпоха 1/10 · 2.0 ит/с", "Эпоха 2/10"]


def test_noise_is_dropped_errors_kept_verbatim():
    clean = tl.LogCleaner(offset=0, target=10)
    feed_all(clean, "\n".join([
        "/opt/x/torch/jit/_script.py:1491: FutureWarning: `torch.jit.script` is deprecated.",
        "  warnings.warn(",
        "GPU available: True (cuda), used: True",
        "  | Name    | Type                     | Params | Mode  | FLOPs",
        "Sanity Checking DataLoader 0: 100%|" + BAR + "| 1/1 [00:01<00:00,  0.57it/s]",
        "  1%|▏         | 5.88M/392M [00:00<00:18, 22.4MB/s]",
        "\x1b[A",
        "Не хватило видеопамяти — уменьшаю батч до 8 и продолжаю",
        "Traceback (most recent call last):",
        '  File "/opt/piper/train/__main__.py", line 5, in <module>',
        "    main()",
        "torch.OutOfMemoryError: CUDA out of memory. Tried to allocate 20.00 MiB",
        "    some indented noise after the traceback",
    ]))
    assert clean.render() == [
        "Не хватило видеопамяти — уменьшаю батч до 8 и продолжаю",
        "Traceback (most recent call last):",
        '  File "/opt/piper/train/__main__.py", line 5, in <module>',
        "    main()",
        "torch.OutOfMemoryError: CUDA out of memory. Tried to allocate 20.00 MiB",
    ]


def test_recorded_resume_log():
    raw = (DATA / "piper_resume_stdout.txt").read_text(encoding="utf-8")
    clean = tl.LogCleaner(offset=4139, target=4141)
    feed_all(clean, raw)
    clean.finish()
    out = clean.render()
    assert out == [
        "Продолжаю с чекпойнта version_0/last.ckpt",
        "Предупреждение piper: Train split (13) is not larger than batch_size (24)",
        "Эпоха 2/2 · качество (MOS) 3.73 · 0.8 ит/с",
        "Обучение дошло до заданного числа эпох",
    ]
    assert not any("it/s]" in line or "\x1b" in line or "Validation" in line for line in out)


def test_text_glued_after_a_bar_is_kept():
    clean = tl.LogCleaner(offset=0, target=5)
    clean.feed(f"Epoch 4: 100%|{BAR}| 1/1 [00:03<00:00,  0.27it/s, v_num=1]`Trainer.fit` stopped: "
               "`max_epochs=5` reached.")
    assert clean.render()[-1] == "Обучение дошло до заданного числа эпох"


def test_utmos_download_announced_once():
    clean = tl.LogCleaner(offset=0, target=5)
    clean.feed('Downloading: "https://github.com/tarepan/SpeechMOS/zipball/v1.2.0" to /root/.cache/x.zip')
    clean.feed('Downloading: "https://github.com/tarepan/SpeechMOS/releases/x.pt" to /root/.cache/y.pt')
    assert clean.render() == ["Скачиваю модель оценки качества (UTMOS, ~400 МБ) — только в первый раз"]


def test_timing_and_eta():
    t = [100.0]
    clean = tl.LogCleaner(offset=0, target=10, clock=lambda: t[0])
    assert clean.seconds_per_epoch() is None and clean.eta() is None
    for n in range(1, 4):
        feed_all(clean, epoch_block(n, 2.0))
        t[0] += 20
    # emitted at t=100, 120, 140 → 20 s per epoch; 7 epochs left after epoch 3
    assert clean.seconds_per_epoch() == 20 and clean.eta() == 140


def test_cap_keeps_last_lines():
    clean = tl.LogCleaner(offset=0, target=999, max_lines=3)
    for i in range(5):
        clean.add(f"строка {i}")
    assert clean.render() == ["строка 2", "строка 3", "строка 4"]


def test_duration_text():
    assert tl.duration_text(14) == "14 с"
    assert tl.duration_text(65) == "1 мин 5 с"
    assert tl.duration_text(3 * 3600 + 47 * 60 + 10) == "3 ч 47 мин"
