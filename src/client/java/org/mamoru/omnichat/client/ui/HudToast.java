package org.mamoru.omnichat.client.ui;

import net.minecraft.client.MinecraftClient;
import net.minecraft.client.font.TextRenderer;
import net.minecraft.client.gui.DrawContext;
import net.minecraft.client.toast.Toast;
import net.minecraft.client.toast.ToastManager;
import net.minecraft.text.Text;

import java.util.List;

/** HUD-style toast: dark panel, colored left bar, title + up to two wrapped lines. ~5 s. */
public class HudToast implements Toast {
    private static final long DURATION_MS = 5000;
    private static final int WIDTH = 180;

    private final Text title;
    private final List<String> lines;
    private final int color;
    private Visibility visibility = Visibility.SHOW;

    private HudToast(Text title, Text description, int color) {
        this.title = title;
        TextRenderer tr = MinecraftClient.getInstance().textRenderer;
        this.lines = description == null ? List.of() : HudText.wrap(description.getString(), WIDTH - 14, 2, tr::getWidth);
        this.color = color;
    }

    public static void show(Text title, Text description, int color) {
        MinecraftClient client = MinecraftClient.getInstance();
        client.execute(() -> client.getToastManager().add(new HudToast(title, description, color)));
    }

    @Override
    public Visibility getVisibility() {
        return visibility;
    }

    @Override
    public void update(ToastManager manager, long time) {
        visibility = time >= DURATION_MS * manager.getNotificationDisplayTimeMultiplier() ? Visibility.HIDE : Visibility.SHOW;
    }

    @Override
    public int getWidth() {
        return WIDTH;
    }

    @Override
    public int getHeight() {
        return 14 + lines.size() * 10;
    }

    @Override
    public void draw(DrawContext ctx, TextRenderer tr, long startTime) {
        int h = getHeight();
        ctx.fill(0, 0, WIDTH, h, HudTheme.BG);
        HudTheme.frame(ctx, 0, 0, WIDTH, h, HudTheme.ACCENT_DIM);
        ctx.fill(0, 0, 2, h, color);
        ctx.drawText(tr, title, 7, 3, color, false);
        int y = 13;
        for (String line : lines) {
            ctx.drawText(tr, line, 7, y, HudTheme.TEXT, false);
            y += 10;
        }
    }
}
