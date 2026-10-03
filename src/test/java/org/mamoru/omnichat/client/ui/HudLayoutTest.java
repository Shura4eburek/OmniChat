package org.mamoru.omnichat.client.ui;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class HudLayoutTest {
    private static final int[][] WINDOWS = {{854, 480}, {1280, 720}, {1920, 1080}};

    @Test
    void maxGuiScaleMatchesMinecraft() {
        assertEquals(2, HudLayout.maxGuiScale(854, 480));
        assertEquals(3, HudLayout.maxGuiScale(1280, 720));
        assertEquals(4, HudLayout.maxGuiScale(1920, 1080));
    }

    @Test
    void everyRectFitsOnEveryValidScale() {
        for (int[] win : WINDOWS) {
            for (int s = 1; s <= HudLayout.maxGuiScale(win[0], win[1]); s++) {
                int w = (int) Math.ceil(win[0] / (double) s), h = (int) Math.ceil(win[1] / (double) s);
                HudLayout l = HudLayout.compute(w, h);
                HudLayout.Rect screen = new HudLayout.Rect(0, 0, w, h);
                String at = win[0] + "x" + win[1] + "@" + s;
                assertTrue(screen.contains(l.panel()), "panel " + at);
                for (HudLayout.Rect r : new HudLayout.Rect[]{l.header(), l.tabs(), l.body(), l.footer(), l.grid(), l.detail()}) {
                    assertTrue(l.panel().contains(r), r + " outside panel " + at);
                    assertTrue(r.w() > 0 && r.h() > 0, "empty rect " + r + " " + at);
                }
                assertTrue(l.columns() >= 2, "columns " + at);
                assertTrue(l.detail().w() >= 120, "detail too narrow " + at);
                assertTrue(l.body().h() >= 140, "body too short " + at);
            }
        }
    }

    @Test
    void panelIsCappedAndCentered() {
        HudLayout l = HudLayout.compute(1920, 1080);
        assertEquals(HudLayout.MAX_W, l.panel().w());
        assertEquals(HudLayout.MAX_H, l.panel().h());
        assertEquals((1920 - HudLayout.MAX_W) / 2, l.panel().x());
    }
}
