package org.mamoru.omnichat.client.ui.screen;

import net.fabricmc.fabric.api.client.networking.v1.ClientPlayNetworking;
import net.minecraft.client.MinecraftClient;
import net.minecraft.client.gl.RenderPipelines;
import net.minecraft.client.gui.DrawContext;
import net.minecraft.text.Text;
import net.minecraft.util.Identifier;
import org.mamoru.omnichat.client.OmnichatClient;
import org.mamoru.omnichat.client.config.OmnichatConfig;
import org.mamoru.omnichat.client.network.ClientNetworkHandler;
import org.mamoru.omnichat.client.network.ModelDownloadManager;
import org.mamoru.omnichat.client.network.VoiceCache;
import org.mamoru.omnichat.client.tts.SpeakerCounts;
import org.mamoru.omnichat.client.tts.VoicePreview;
import org.mamoru.omnichat.client.ui.*;
import org.mamoru.omnichat.client.ui.widget.HudButton;
import org.mamoru.omnichat.client.ui.widget.HudSlider;
import org.mamoru.omnichat.client.ui.widget.StatusLine;
import org.mamoru.omnichat.client.ui.widget.VoiceTile;
import org.mamoru.omnichat.network.VoiceSelectionC2SPayload;

import java.util.List;
import java.util.Locale;

public class VoiceTab implements HudTab {
    private static String selected;
    private static int scrollRow;

    private OmnichatScreen screen;
    private List<VoiceCatalog.Entry> entries = List.of();
    private int ticks;

    @Override
    public void init(OmnichatScreen screen, HudLayout l) {
        this.screen = screen;
        OmnichatConfig config = OmnichatClient.getConfig();
        entries = VoiceCatalog.current();
        selected = VoiceCatalog.selectOrFallback(entries, selected, config.getModelPath());
        if (entries.isEmpty()) return;

        var g = l.grid();
        int rowsVisible = Math.max(1, (g.h() + HudLayout.TILE_GAP) / (HudLayout.TILE + HudLayout.TILE_GAP));
        int totalRows = (entries.size() + l.columns() - 1) / l.columns();
        scrollRow = Math.clamp(scrollRow, 0, Math.max(0, totalRows - rowsVisible));
        for (int i = 0; i < entries.size(); i++) {
            int row = i / l.columns() - scrollRow, col = i % l.columns();
            if (row < 0 || row >= rowsVisible) continue;
            VoiceCatalog.Entry e = entries.get(i);
            int x = g.x() + col * (HudLayout.TILE + HudLayout.TILE_GAP);
            int y = g.y() + row * (HudLayout.TILE + HudLayout.TILE_GAP);
            boolean active = e.meta().model().equals(config.getModelPath());
            screen.add(new VoiceTile(x, y, e, e.meta().model().equals(selected), active, this::select, this::preview));
        }

        VoiceCatalog.Entry sel = selectedEntry();
        var d = l.detail();
        int bottom = d.bottom() - StatusLine.HEIGHT - 2;
        if (sel == null) return;
        switch (sel.state()) {
            case REMOTE, FAILED -> screen.add(new HudButton(d.x(), bottom - 18, d.w(), 16,
                    sel.state() == VoiceCatalog.State.FAILED
                            ? Text.translatable("omnichat.ui.voice.retry")
                            : Text.translatable("omnichat.ui.voice.download", formatSize(sel.meta().sizeBytes())),
                    () -> {
                        ModelDownloadManager.getInstance().requestDownload(sel.meta().model());
                        screen.rebuild();
                    }));
            case INSTALLED -> {
                int speakers = SpeakerCounts.get(sel.meta().model(), () -> MinecraftClient.getInstance().execute(screen::rebuild));
                if (speakers > 1 && sel.meta().model().equals(config.getModelPath())) {
                    screen.add(new HudSlider(d.x(), bottom - 16, d.w(), Text.translatable("omnichat.ui.voice.speaker"),
                            0, speakers - 1, config.getSpeakerId(), 1, v -> Text.literal(String.valueOf((int) v)), v -> {
                                config.setSpeakerId((int) v);
                                sendSelection(config);
                            }));
                }
            }
            default -> {
            }
        }
    }

    private VoiceCatalog.Entry selectedEntry() {
        for (VoiceCatalog.Entry e : entries) {
            if (e.meta().model().equals(selected)) return e;
        }
        return null;
    }

    private void select(String model) {
        VoicePreview.stop();
        selected = model;
        VoiceCatalog.Entry e = selectedEntry();
        OmnichatConfig config = OmnichatClient.getConfig();
        if (e != null && e.state() == VoiceCatalog.State.INSTALLED && !model.equals(config.getModelPath())) {
            config.setModelPath(model);
            config.setSpeakerId(0);
            config.save();
            OmnichatClient.getTts().applySettings();
            sendSelection(config);
        }
        screen.rebuild();
    }

    private static void sendSelection(OmnichatConfig config) {
        if (VoiceCache.getInstance().getServerModels().contains(config.getModelPath())
                && ClientNetworkHandler.canSend(VoiceSelectionC2SPayload.ID)) {
            ClientPlayNetworking.send(new VoiceSelectionC2SPayload(config.getModelPath(), config.getSpeakerId()));
        }
    }

    private void preview(String model) {
        selected = model;
        VoiceCatalog.Entry e = selectedEntry();
        if (e != null && e.state() == VoiceCatalog.State.INSTALLED) {
            String sample = e.meta().sample().isBlank()
                    ? Text.translatable("omnichat.ui.voice.default_sample").getString() : e.meta().sample();
            VoicePreview.play(model, sample);
        }
        screen.rebuild();
    }

    @Override
    public void tick() {
        // Downloads progress, reloads and finished installs show up without reopening
        if (++ticks % 10 == 0) {
            List<VoiceCatalog.Entry> now = VoiceCatalog.current();
            if (!VoiceCatalog.signature(now).equals(VoiceCatalog.signature(entries))) screen.rebuild();
        }
    }

    @Override
    public boolean mouseScrolled(double mouseX, double mouseY, double vertical) {
        scrollRow = Math.max(0, scrollRow - (int) Math.signum(vertical));
        screen.rebuild();
        return true;
    }

    @Override
    public void render(DrawContext ctx, int mouseX, int mouseY, float delta, HudLayout l) {
        var tr = MinecraftClient.getInstance().textRenderer;
        var d = l.detail();
        ctx.fill(d.x() - 4, d.y(), d.x() - 3, d.bottom(), HudTheme.ACCENT_DIM);
        if (entries.isEmpty()) {
            int y = l.body().y() + 4;
            for (String line : HudText.wrap(Text.translatable("omnichat.ui.voices.empty").getString(), l.body().w(), 4, tr::getWidth)) {
                ctx.drawText(tr, line, l.body().x(), y, HudTheme.MUTED, false);
                y += 10;
            }
            return;
        }
        VoiceCatalog.Entry e = selectedEntry();
        if (e == null) return;

        int big = 40;
        Identifier portrait = PortraitTextures.get(e.meta());
        int size = PortraitTextures.sizeOf(portrait);
        ctx.fill(d.x(), d.y(), d.x() + big, d.y() + big, HudTheme.TILE_BG);
        ctx.drawTexture(RenderPipelines.GUI_TEXTURED, portrait, d.x() + 4, d.y() + 4, 0, 0, big - 8, big - 8, size, size, size, size);
        HudTheme.frame(ctx, d.x(), d.y(), big, big, HudTheme.ACCENT);

        int tx = d.x() + big + 6, tw = d.right() - tx;
        ctx.drawText(tr, HudText.ellipsize(e.meta().name().toUpperCase(Locale.ROOT), tw, tr::getWidth), tx, d.y(), HudTheme.ACCENT, false);
        String meta = String.join(" · ", List.of(e.meta().language(), formatSize(e.meta().sizeBytes())).stream()
                .filter(s -> !s.isBlank()).toList());
        ctx.drawText(tr, HudText.ellipsize(meta, tw, tr::getWidth), tx, d.y() + 10, HudTheme.MUTED, false);

        // Oscilloscope: live while previewing this voice, flat otherwise
        float[] bars = e.meta().model().equals(VoicePreview.playingModel()) ? VoicePreview.bars(12) : new float[12];
        for (int i = 0; i < bars.length; i++) {
            // Speech RMS sits around 0.05-0.25: amplify so the bars actually move
            int bh = Math.max(1, Math.round(Math.min(1f, bars[i] * 4f) * 16));
            int bx = tx + i * 4;
            ctx.fill(bx, d.y() + 30 - bh / 2, bx + 2, d.y() + 30 + (bh + 1) / 2, HudTheme.ACCENT);
        }

        int y = d.y() + big + 6;
        for (String line : HudText.wrap(e.meta().description(), d.w(), 4, tr::getWidth)) {
            ctx.drawText(tr, line, d.x(), y, HudTheme.TEXT, false);
            y += 10;
        }
        Text hint = e.state() == VoiceCatalog.State.INSTALLED
                ? Text.translatable("omnichat.ui.voice.preview_hint")
                : Text.translatable("omnichat.ui.voice.preview_remote");
        ctx.drawText(tr, hint, d.x(), y + 2, HudTheme.MUTED, false);

        OmnichatConfig config = OmnichatClient.getConfig();
        Text left, right;
        int color;
        switch (e.state()) {
            case DOWNLOADING -> {
                left = e.progress() < 0 ? Text.translatable("omnichat.ui.voice.queued")
                        : Text.translatable("omnichat.ui.voice.downloading", Math.round(e.progress() * 100));
                right = Text.literal(formatSize((long) (Math.max(0, e.progress()) * e.meta().sizeBytes())) + " / " + formatSize(e.meta().sizeBytes()));
                color = HudTheme.WARN;
            }
            case REMOTE -> {
                left = Text.translatable("omnichat.ui.voice.remote");
                right = Text.literal(formatSize(e.meta().sizeBytes()));
                color = HudTheme.WARN;
            }
            case FAILED -> {
                left = Text.translatable("omnichat.ui.voice.failed", e.failure());
                right = Text.literal("!");
                color = HudTheme.ERROR;
            }
            default -> {
                left = e.onServer() ? Text.translatable("omnichat.ui.voice.installed") : Text.translatable("omnichat.ui.voice.local_only");
                boolean active = e.meta().model().equals(config.getModelPath());
                right = active ? Text.translatable("omnichat.ui.voice.active") : Text.empty();
                color = HudTheme.OK;
            }
        }
        if (ClientNetworkHandler.isIncompatible()) {
            String warn = HudText.ellipsize(Text.translatable("omnichat.ui.voice.incompatible").getString(), d.w(), tr::getWidth);
            ctx.drawText(tr, warn, d.x(), d.bottom() - StatusLine.HEIGHT - 10, HudTheme.WARN, false);
        }
        StatusLine.draw(ctx, tr, d.x(), d.bottom() - StatusLine.HEIGHT, d.w(), left, right, color);
    }

    @Override
    public Text hints() {
        return Text.translatable("omnichat.ui.hints.voice");
    }

    static String formatSize(long bytes) {
        if (bytes <= 0) return "";
        double mb = bytes / (1024.0 * 1024.0);
        return mb >= 10 ? Math.round(mb) + " MB" : String.format(Locale.ROOT, "%.1f MB", mb);
    }
}
