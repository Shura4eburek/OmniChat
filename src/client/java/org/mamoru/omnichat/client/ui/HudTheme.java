package org.mamoru.omnichat.client.ui;

import net.minecraft.client.font.TextRenderer;
import net.minecraft.client.gui.DrawContext;
import net.minecraft.text.Text;

/** HUD palette and drawing primitives (see spec "Визуальный стиль"). */
public final class HudTheme {
    public static final int ACCENT = 0xFF35E0C8;
    public static final int ACCENT_DIM = 0x7335E0C8;
    public static final int BG = 0xDB0A080C;
    public static final int TILE_BG = 0xFF15111A;
    public static final int TEXT = 0xFFD9D4DC;
    public static final int MUTED = 0xFF9A93A0;
    public static final int OK = 0xFF59E36B;
    public static final int WARN = 0xFFFFCF4A;
    public static final int ERROR = 0xFFFF5A5A;
    private static final int BRACKET = 6;

    private HudTheme() {
    }

    /** Panel: background, 1 px accent border, 2 px corner brackets top-left and bottom-right. */
    public static void frame(DrawContext ctx, HudLayout.Rect r) {
        ctx.fill(r.x(), r.y(), r.right(), r.bottom(), BG);
        ctx.drawStrokedRectangle(r.x(), r.y(), r.w(), r.h(), ACCENT);
        ctx.fill(r.x() - 2, r.y() - 2, r.x() + BRACKET, r.y(), ACCENT);
        ctx.fill(r.x() - 2, r.y() - 2, r.x(), r.y() + BRACKET, ACCENT);
        ctx.fill(r.right() - BRACKET, r.bottom(), r.right() + 2, r.bottom() + 2, ACCENT);
        ctx.fill(r.right(), r.bottom() - BRACKET, r.right() + 2, r.bottom() + 2, ACCENT);
    }

    /** Thin 1 px outline (tiles, inputs). */
    public static void frame(DrawContext ctx, int x, int y, int w, int h, int color) {
        ctx.drawStrokedRectangle(x, y, w, h, color);
    }

    public static void divider(DrawContext ctx, int x, int y, int w) {
        ctx.fill(x, y, x + w, y + 1, ACCENT_DIM);
    }

    /** Letter-spaced caps title, like "O M N I C H A T". */
    public static void spacedTitle(DrawContext ctx, TextRenderer tr, String s, int x, int y, int color) {
        int cx = x;
        for (int i = 0; i < s.length(); i++) {
            String ch = String.valueOf(s.charAt(i));
            ctx.drawText(tr, ch, cx, y, color, false);
            cx += tr.getWidth(ch) + 3;
        }
    }

    public static void text(DrawContext ctx, TextRenderer tr, Text t, int x, int y, int color) {
        ctx.drawText(tr, t, x, y, color, false);
    }
}
