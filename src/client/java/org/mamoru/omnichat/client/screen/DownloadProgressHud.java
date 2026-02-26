package org.mamoru.omnichat.client.screen;

import net.fabricmc.fabric.api.client.rendering.v1.HudRenderCallback;
import net.minecraft.client.MinecraftClient;
import net.minecraft.client.font.TextRenderer;
import net.minecraft.client.gui.DrawContext;
import net.minecraft.client.render.RenderTickCounter;
import org.mamoru.omnichat.client.network.ModelDownloadManager;

import java.util.Map;

public class DownloadProgressHud implements HudRenderCallback {
    private static final int BAR_WIDTH = 160;
    private static final int BAR_HEIGHT = 10;
    private static final int PADDING = 4;
    private static final int BG_COLOR = 0xAA000000;
    private static final int BAR_BG_COLOR = 0xFF333333;
    private static final int BAR_FILL_COLOR = 0xFF55FF55;
    private static final int TEXT_COLOR = 0xFFFFFF;

    public static void register() {
        HudRenderCallback.EVENT.register(new DownloadProgressHud());
    }

    @Override
    public void onHudRender(DrawContext context, RenderTickCounter tickCounter) {
        Map<String, Float> downloads = ModelDownloadManager.getInstance().getActiveDownloads();
        if (downloads.isEmpty()) return;

        MinecraftClient client = MinecraftClient.getInstance();
        TextRenderer textRenderer = client.textRenderer;
        int screenWidth = client.getWindow().getScaledWidth();

        int x = screenWidth - BAR_WIDTH - PADDING * 2 - 4;
        int y = 4;

        for (Map.Entry<String, Float> entry : downloads.entrySet()) {
            String modelName = entry.getKey();
            float progress = entry.getValue();
            int percent = (int) (progress * 100);

            String label = modelName + " - " + percent + "%";
            int totalHeight = textRenderer.fontHeight + 2 + BAR_HEIGHT + PADDING * 2;

            // Background
            context.fill(x, y, x + BAR_WIDTH + PADDING * 2, y + totalHeight, BG_COLOR);

            // Label
            context.drawText(textRenderer, label, x + PADDING, y + PADDING, TEXT_COLOR, true);

            // Bar background
            int barX = x + PADDING;
            int barY = y + PADDING + textRenderer.fontHeight + 2;
            context.fill(barX, barY, barX + BAR_WIDTH, barY + BAR_HEIGHT, BAR_BG_COLOR);

            // Bar fill
            int fillWidth = (int) (BAR_WIDTH * progress);
            if (fillWidth > 0) {
                context.fill(barX, barY, barX + fillWidth, barY + BAR_HEIGHT, BAR_FILL_COLOR);
            }

            y += totalHeight + 2;
        }
    }
}
