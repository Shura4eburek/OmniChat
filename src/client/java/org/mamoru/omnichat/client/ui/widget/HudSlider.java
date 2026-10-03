package org.mamoru.omnichat.client.ui.widget;

import net.minecraft.client.MinecraftClient;
import net.minecraft.client.gui.DrawContext;
import net.minecraft.client.gui.widget.SliderWidget;
import net.minecraft.text.Text;
import org.mamoru.omnichat.client.ui.HudTheme;

import java.util.function.DoubleConsumer;
import java.util.function.DoubleFunction;

/** "Label  value  [====|-----]" row with snapping to {@code step}. */
public class HudSlider extends SliderWidget {
    public static final int HEIGHT = 14;
    private final Text label;
    private final double min, max, step;
    private final DoubleFunction<Text> format;
    private final DoubleConsumer onChange;

    public HudSlider(int x, int y, int w, Text label, double min, double max, double value, double step,
                     DoubleFunction<Text> format, DoubleConsumer onChange) {
        super(x, y, w, HEIGHT, Text.empty(), (Math.clamp(value, min, max) - min) / (max - min));
        this.label = label;
        this.min = min;
        this.max = max;
        this.step = step;
        this.format = format;
        this.onChange = onChange;
        updateMessage();
    }

    public double current() {
        double v = min + value * (max - min);
        return step > 0 ? Math.round(v / step) * step : v;
    }

    @Override
    protected void updateMessage() {
        setMessage(Text.empty().append(label).append(": ").append(format.apply(current())));
    }

    @Override
    protected void applyValue() {
        onChange.accept(current());
    }

    @Override
    public void renderWidget(DrawContext ctx, int mouseX, int mouseY, float delta) {
        var tr = MinecraftClient.getInstance().textRenderer;
        boolean hot = isHovered() || isFocused();
        int labelW = width / 2;
        ctx.drawText(tr, label, getX(), getY() + 3, hot ? HudTheme.ACCENT : HudTheme.TEXT, false);
        Text v = format.apply(current());
        ctx.drawText(tr, v, getX() + labelW - tr.getWidth(v) - 4, getY() + 3, HudTheme.MUTED, false);
        int bx = getX() + labelW, bw = width - labelW, by = getY() + 6;
        ctx.fill(bx, by, bx + bw, by + 2, 0xFF2A2430);
        int fill = (int) (value * bw);
        ctx.fill(bx, by, bx + fill, by + 2, HudTheme.ACCENT);
        int kx = Math.min(bx + fill, bx + bw - 3);
        ctx.fill(kx, getY() + 2, kx + 3, getY() + 12, hot ? 0xFFFFFFFF : HudTheme.TEXT);
    }
}
