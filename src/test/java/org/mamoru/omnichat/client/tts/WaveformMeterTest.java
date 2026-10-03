package org.mamoru.omnichat.client.tts;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class WaveformMeterTest {
    @Test
    void silenceThenTone() {
        int sr = 1000;
        float[] s = new float[sr]; // 1 s
        for (int i = 500; i < 1000; i++) s[i] = (i % 2 == 0) ? 0.5f : -0.5f;
        WaveformMeter m = new WaveformMeter(s, sr);
        assertEquals(0f, m.level(200), 1e-6);
        assertEquals(0.5f, m.level(800), 1e-3);
        assertFalse(m.finished(900));
        assertTrue(m.finished(1001));
    }

    @Test
    void barsHaveRequestedCountAndRange() {
        float[] s = new float[2000];
        java.util.Arrays.fill(s, 2f); // over-range input is clamped
        float[] bars = new WaveformMeter(s, 1000).bars(1500, 9);
        assertEquals(9, bars.length);
        for (float b : bars) assertTrue(b >= 0f && b <= 1f);
    }
}
