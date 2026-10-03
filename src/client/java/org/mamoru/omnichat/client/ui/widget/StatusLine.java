package org.mamoru.omnichat.client.ui.widget;

import net.minecraft.client.font.TextRenderer;
import net.minecraft.client.gui.DrawContext;
import net.minecraft.text.Text;
import org.mamoru.omnichat.client.ui.HudTheme;

/** Divider + "left ........ right" status row. Not focusable, just drawn. */
public final class StatusLine {
    public static final int HEIGHT = 12;

    private StatusLine() {
    }

    public static void draw(DrawContext ctx, TextRenderer tr, int x, int y, int w, Text left, Text right, int rightColor) {
        HudTheme.divider(ctx, x, y, w);
        ctx.drawText(tr, left, x, y + 3, HudTheme.TEXT, false);
        ctx.drawText(tr, right, x + w - tr.getWidth(right), y + 3, rightColor, false);
    }
}
