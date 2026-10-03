package org.mamoru.omnichat.client.screen;

import net.fabricmc.fabric.api.client.rendering.v1.HudRenderCallback;
import net.minecraft.client.MinecraftClient;
import net.minecraft.client.font.TextRenderer;
import net.minecraft.client.gui.DrawContext;
import net.minecraft.client.render.RenderTickCounter;
import net.minecraft.text.Text;
import org.mamoru.omnichat.client.network.ModelDownloadManager;
import org.mamoru.omnichat.client.ui.HudText;
import org.mamoru.omnichat.client.ui.HudTheme;

import java.util.Map;

public class DownloadProgressHud implements HudRenderCallback {
    public static void register() {
        HudRenderCallback.EVENT.register(new DownloadProgressHud());
    }

    @Override
    public void onHudRender(DrawContext context, RenderTickCounter tickCounter) {
        Map<String, Float> downloads = ModelDownloadManager.getInstance().getActiveDownloads();
        if (downloads.isEmpty()) return;
        MinecraftClient client = MinecraftClient.getInstance();
        TextRenderer tr = client.textRenderer;
        int w = 150, rowH = 18;
        int x = context.getScaledWindowWidth() - w - 6, y = 6;
        int h = downloads.size() * rowH + 4;
        context.fill(x, y, x + w, y + h, HudTheme.BG);
        HudTheme.frame(context, x, y, w, h, HudTheme.ACCENT_DIM);
        int ry = y + 3;
        for (Map.Entry<String, Float> e : downloads.entrySet()) {
            float p = e.getValue();
            String name = HudText.ellipsize(e.getKey(), 90, tr::getWidth);
            String pct = p < 0 ? Text.translatable("omnichat.hud.queued").getString() : Math.round(p * 100) + "%";
            context.drawText(tr, name, x + 5, ry, HudTheme.TEXT, false);
            context.drawText(tr, pct, x + w - 5 - tr.getWidth(pct), ry, p < 0 ? HudTheme.MUTED : HudTheme.WARN, false);
            context.fill(x + 5, ry + 11, x + w - 5, ry + 13, 0xFF2A2430);
            if (p > 0) context.fill(x + 5, ry + 11, x + 5 + (int) ((w - 10) * p), ry + 13, HudTheme.ACCENT);
            ry += rowH;
        }
    }
}
