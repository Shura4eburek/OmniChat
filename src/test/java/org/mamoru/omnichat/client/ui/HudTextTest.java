package org.mamoru.omnichat.client.ui;

import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.function.ToIntFunction;

import static org.junit.jupiter.api.Assertions.*;

class HudTextTest {
    // 6 px per char, like most vanilla glyphs
    static final ToIntFunction<String> W = s -> s.length() * 6;

    @Test
    void keepsShortText() {
        assertEquals("Denis", HudText.ellipsize("Denis", 100, W));
    }

    @Test
    void ellipsizesLongNames() {
        String out = HudText.ellipsize("Ш".repeat(32), 60, W);
        assertTrue(out.endsWith("…"));
        assertTrue(W.applyAsInt(out) <= 60);
    }

    @Test
    void wrapsAndLimitsLines() {
        List<String> lines = HudText.wrap("one two three four five six seven", 30, 2, W);
        assertEquals(2, lines.size());
        assertTrue(lines.get(1).endsWith("…"));
        for (String l : lines) assertTrue(W.applyAsInt(l) <= 30);
    }

    @Test
    void wrapsUnbreakableWords() {
        List<String> lines = HudText.wrap("x".repeat(40), 60, 3, W);
        assertEquals(3, lines.size());
        for (String l : lines) assertTrue(W.applyAsInt(l) <= 60);
    }
}
