import numpy as np
from omnivoice import synth_check as sc

SR = 22050


def tone(seconds, amp=0.3):
    t = np.arange(int(SR * seconds)) / SR
    return (amp * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def test_normalize_and_cer():
    assert sc.normalize("Ещё раз, ГЛУПЕЦ!") == "еще раз глупец"
    assert sc.cer("Говори, глупец!", "говори глупец") == 0.0
    assert 0.0 < sc.cer("никто не смеет", "никто не сметь") <= 0.2
    assert sc.cer("абв", "") == 1.0


def test_longest_pause():
    x = np.concatenate([tone(1), np.zeros(int(SR * 1.5), np.float32), tone(1)])
    assert 1.4 < sc.longest_pause(x, SR) < 1.6
    assert sc.longest_pause(tone(2), SR) < 0.05


def test_verdicts():
    ok = sc.verdict("Во славу Плети!", "во славу плети", tone(1.5), SR, expected_s=1.5)
    assert ok == ("accepted", [])
    v, why = sc.verdict("Во славу Плети!", "во славу плоти и", tone(1.5), SR, expected_s=1.5)  # 3/14 ≈ 0.21
    assert v == "suspect" and why == ["text"]
    assert sc.verdict("Во славу Плети!", "совсем другое что-то", tone(1.5), SR, 1.5)[0] == "rejected"
    assert sc.verdict("Во славу Плети!", "во славу плети", tone(0.5), SR, 0.5) == ("rejected", ["length"])
    assert sc.verdict("Во славу Плети!", "во славу плети", tone(4.0), SR, 1.5)[1] == ["slow"]      # 2.67×
    assert sc.verdict("Во славу Плети!", "во славу плети", tone(3.0), SR, 1.5) == ("suspect", ["slow"])  # 2×
    gap = np.concatenate([tone(0.6), np.zeros(int(SR * 1.3), np.float32), tone(0.6)])
    assert sc.verdict("Во славу Плети!", "во славу плети", gap, SR, 2.5) == ("suspect", ["pause"])
    hot = tone(1.5, amp=1.2)
    assert "clip" in sc.verdict("Во славу Плети!", "во славу плети", hot, SR, 1.5)[1]
    assert sc.verdict("Во славу Плети!", None, tone(1.5), SR, 1.5) == ("unchecked", [])
    assert set(sc.REASONS) >= {"text", "fast", "slow", "pause", "clip", "length"}
