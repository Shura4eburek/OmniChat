import numpy as np
from omnivoice import audio

def test_clipping_ratio():
    x = np.zeros(1000, np.float32); x[:10] = 1.0
    assert abs(audio.clipping_ratio(x) - 0.01) < 1e-9

def test_resample_and_pad_lengths():
    x = np.zeros(44100, np.float32)
    y = audio.resample(x, 44100, 22050)
    assert abs(len(y) - 22050) <= 2
    assert len(audio.pad(y, 22050)) == len(y) + 2 * int(0.15 * 22050)
