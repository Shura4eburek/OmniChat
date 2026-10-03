package org.mamoru.omnichat.client.ui.widget;

import net.minecraft.client.MinecraftClient;
import net.minecraft.client.gui.Click;
import net.minecraft.client.gui.DrawContext;
import net.minecraft.client.gui.screen.narration.NarrationMessageBuilder;
import net.minecraft.client.gui.widget.ClickableWidget;
import net.minecraft.client.input.KeyInput;
import net.minecraft.text.Text;
import org.mamoru.omnichat.client.ui.HudTheme;

import java.util.List;
import java.util.function.IntConsumer;

/** Row of tabs. Left/Right when focused, or 1..9 handled by the screen. */
public class TabBar extends ClickableWidget {
    public static final int HEIGHT = 14;
    private final List<Text> labels;
    private final IntConsumer onSelect;
    private final int active;

    public TabBar(int x, int y, int w, List<Text> labels, int active, IntConsumer onSelect) {
        super(x, y, w, HEIGHT, labels.get(active));
        this.labels = labels;
        this.active = active;
        this.onSelect = onSelect;
    }

    private int tabX(int i) {
        var tr = MinecraftClient.getInstance().textRenderer;
        int x = getX();
        for (int j = 0; j < i; j++) x += tr.getWidth(labels.get(j)) + 14;
        return x;
    }

    @Override
    protected void renderWidget(DrawContext ctx, int mouseX, int mouseY, float delta) {
        var tr = MinecraftClient.getInstance().textRenderer;
        for (int i = 0; i < labels.size(); i++) {
            int x = tabX(i), w = tr.getWidth(labels.get(i)) + 12;
            boolean on = i == active;
            boolean hover = mouseX >= x && mouseX < x + w && mouseY >= getY() && mouseY < getY() + HEIGHT;
            if (on) ctx.fill(x, getY(), x + w, getY() + HEIGHT, 0x1435E0C8);
            HudTheme.frame(ctx, x, getY(), w, HEIGHT, on ? HudTheme.ACCENT : HudTheme.ACCENT_DIM);
            ctx.drawText(tr, labels.get(i), x + 6, getY() + 3, on || hover ? HudTheme.ACCENT : HudTheme.MUTED, false);
        }
        if (isFocused()) ctx.fill(tabX(active), getY() + HEIGHT, tabX(active) + 8, getY() + HEIGHT + 1, HudTheme.ACCENT);
    }

    @Override
    public void onClick(Click click, boolean doubled) {
        var tr = MinecraftClient.getInstance().textRenderer;
        for (int i = 0; i < labels.size(); i++) {
            int x = tabX(i), w = tr.getWidth(labels.get(i)) + 12;
            if (click.x() >= x && click.x() < x + w && i != active) onSelect.accept(i);
        }
    }

    @Override
    public boolean keyPressed(KeyInput input) {
        if (input.isLeft() && active > 0) {
            onSelect.accept(active - 1);
            return true;
        }
        if (input.isRight() && active < labels.size() - 1) {
            onSelect.accept(active + 1);
            return true;
        }
        return false;
    }

    @Override
    protected void appendClickableNarrations(NarrationMessageBuilder builder) {
        appendDefaultNarrations(builder);
    }
}
