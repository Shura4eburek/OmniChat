package org.mamoru.omnichat.client.ui.widget;

import net.minecraft.client.MinecraftClient;
import net.minecraft.client.gui.Click;
import net.minecraft.client.gui.DrawContext;
import net.minecraft.client.gui.screen.narration.NarrationMessageBuilder;
import net.minecraft.client.gui.widget.ClickableWidget;
import net.minecraft.client.input.KeyInput;
import net.minecraft.screen.ScreenTexts;
import net.minecraft.text.Text;
import org.mamoru.omnichat.client.ui.HudText;
import org.mamoru.omnichat.client.ui.HudTheme;

import java.util.function.Consumer;

/** "Label ........ [■ ]" row; click or Enter flips it. */
public class HudToggle extends ClickableWidget {
    public static final int HEIGHT = 14;
    private final Text label;
    private final Consumer<Boolean> onChange;
    private boolean value;

    public HudToggle(int x, int y, int w, Text label, boolean value, Consumer<Boolean> onChange) {
        super(x, y, w, HEIGHT, label);
        this.label = label;
        this.value = value;
        this.onChange = onChange;
        updateMessage();
    }

    private void updateMessage() {
        setMessage(ScreenTexts.composeToggleText(label, value));
    }

    private void flip() {
        value = !value;
        updateMessage();
        onChange.accept(value);
    }

    @Override
    protected void renderWidget(DrawContext ctx, int mouseX, int mouseY, float delta) {
        var tr = MinecraftClient.getInstance().textRenderer;
        boolean hot = isHovered() || isFocused();
        int sw = 18, sx = getX() + width - sw;
        String text = HudText.ellipsize(label.getString(), width - sw - 6, tr::getWidth);
        ctx.drawText(tr, text, getX(), getY() + 3, hot ? HudTheme.ACCENT : HudTheme.TEXT, false);
        HudTheme.frame(ctx, sx, getY() + 2, sw, 10, hot ? HudTheme.ACCENT : HudTheme.ACCENT_DIM);
        int kx = value ? sx + sw - 8 : sx + 2;
        ctx.fill(kx, getY() + 4, kx + 6, getY() + 10, value ? HudTheme.ACCENT : HudTheme.MUTED);
    }

    @Override
    public void onClick(Click click, boolean doubled) {
        flip();
    }

    @Override
    public boolean keyPressed(KeyInput input) {
        if (active && visible && input.isEnterOrSpace()) {
            playDownSound(MinecraftClient.getInstance().getSoundManager());
            flip();
            return true;
        }
        return false;
    }

    @Override
    protected void appendClickableNarrations(NarrationMessageBuilder builder) {
        appendDefaultNarrations(builder);
    }
}
