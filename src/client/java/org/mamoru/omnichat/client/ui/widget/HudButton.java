package org.mamoru.omnichat.client.ui.widget;

import net.minecraft.client.MinecraftClient;
import net.minecraft.client.gui.Click;
import net.minecraft.client.gui.DrawContext;
import net.minecraft.client.gui.screen.narration.NarrationMessageBuilder;
import net.minecraft.client.gui.widget.ClickableWidget;
import net.minecraft.client.input.KeyInput;
import net.minecraft.text.Text;
import org.mamoru.omnichat.client.ui.HudText;
import org.mamoru.omnichat.client.ui.HudTheme;

public class HudButton extends ClickableWidget {
    private final Runnable onPress;

    public HudButton(int x, int y, int w, int h, Text label, Runnable onPress) {
        super(x, y, w, h, label);
        this.onPress = onPress;
    }

    @Override
    protected void renderWidget(DrawContext ctx, int mouseX, int mouseY, float delta) {
        var tr = MinecraftClient.getInstance().textRenderer;
        boolean hot = active && (isHovered() || isFocused());
        ctx.fill(getX(), getY(), getX() + width, getY() + height, hot ? 0x3335E0C8 : 0x22000000);
        HudTheme.frame(ctx, getX(), getY(), width, height, active ? (hot ? HudTheme.ACCENT : HudTheme.ACCENT_DIM) : 0x33FFFFFF);
        String label = HudText.ellipsize(getMessage().getString(), width - 6, tr::getWidth);
        int color = active ? (hot ? HudTheme.ACCENT : HudTheme.TEXT) : HudTheme.MUTED;
        ctx.drawText(tr, label, getX() + (width - tr.getWidth(label)) / 2, getY() + (height - 8) / 2, color, false);
    }

    @Override
    public void onClick(Click click, boolean doubled) {
        onPress.run();
    }

    @Override
    public boolean keyPressed(KeyInput input) {
        if (active && visible && input.isEnterOrSpace()) {
            playDownSound(MinecraftClient.getInstance().getSoundManager());
            onPress.run();
            return true;
        }
        return false;
    }

    @Override
    protected void appendClickableNarrations(NarrationMessageBuilder builder) {
        appendDefaultNarrations(builder);
    }
}
