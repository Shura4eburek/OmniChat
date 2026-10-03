package org.mamoru.omnichat.client.ui;

import org.junit.jupiter.api.Test;

import java.util.Arrays;

import static org.junit.jupiter.api.Assertions.*;

class PortraitGeneratorTest {
    @Test
    void isDeterministic() {
        assertArrayEquals(PortraitGenerator.generate("denis"), PortraitGenerator.generate("denis"));
    }

    @Test
    void differsBetweenNames() {
        assertFalse(Arrays.equals(PortraitGenerator.generate("denis"), PortraitGenerator.generate("irina")));
    }

    @Test
    void isSymmetricAndFilled() {
        int[] p = PortraitGenerator.generate("glados");
        assertEquals(256, p.length);
        int filled = 0;
        for (int y = 0; y < 16; y++) {
            for (int x = 0; x < 16; x++) {
                assertEquals(p[y * 16 + x], p[y * 16 + (15 - x)], "symmetry at " + x + "," + y);
                if (p[y * 16 + x] != PortraitGenerator.BACKGROUND) filled++;
            }
        }
        assertTrue(filled > 40, "portrait too empty: " + filled);
    }
}
