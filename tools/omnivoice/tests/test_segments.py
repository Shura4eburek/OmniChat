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
