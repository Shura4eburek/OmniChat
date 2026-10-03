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
import org.mamoru.omnichat.client.tts.ModelRepair;
import org.mamoru.omnichat.client.tts.SpeakerCounts;
import org.mamoru.omnichat.client.tts.VoicePreview;
import org.mamoru.omnichat.client.ui.*;
import org.mamoru.omnichat.client.ui.widget.HudButton;
import org.mamoru.omnichat.client.ui.widget.HudSlider;
import org.mamoru.omnichat.client.ui.widget.StatusLine;
import org.mamoru.omnichat.client.ui.widget.VoiceTile;
import org.mamoru.omnichat.network.VoiceSelectionC2SPayload;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

public class VoiceTab implements HudTab {
    private static final Logger LOGGER = LoggerFactory.getLogger("OmniChat");
    private static String selected;
    private static int scrollRow;
    // Language picked in the repair slider, per model (survives rebuilds); models being repaired right now
    private static final Map<String, String> PICKED_VOICE = new ConcurrentHashMap<>();
    private static final Set<String> REPAIRING = ConcurrentHashMap.newKeySet();

    private OmnichatScreen screen;
    // entries: what the widgets were built from; live: latest catalog, refreshed in tick() for progress
    private List<VoiceCatalog.Entry> entries = List.of();
    private List<VoiceCatalog.Entry> live = List.of();
    // What the widgets were built from, including model health (a finished check must rebuild the tab)
    private List<String> builtSignature = List.of();
    private HudLayout.Rect gridRect;
    private int maxScrollRow;
    private int ticks;

    @Override
    public void init(OmnichatScreen screen, HudLayout l) {
        this.screen = screen;
        OmnichatConfig config = OmnichatClient.getConfig();
        entries = VoiceCatalog.current();
        live = entries;
        builtSignature = signature(entries);
        selected = VoiceCatalog.selectOrFallback(entries, selected, config.getModelPath());
        gridRect = null;
        if (entries.isEmpty()) return;

        var g = l.grid();
        gridRect = g;
        List<String> pending = entries.stream()
                .filter(e -> e.state() == VoiceCatalog.State.REMOTE || e.state() == VoiceCatalog.State.FAILED)
                .map(e -> e.meta().model()).toList();
        // "Download all" sits under the grid; tiles only use the rows above it
        int gridH = pending.isEmpty() ? g.h() : g.h() - 18;
        int rowsVisible = Math.max(1, (gridH + HudLayout.TILE_GAP) / (HudLayout.TILE + HudLayout.TILE_GAP));
        int totalRows = (entries.size() + l.columns() - 1) / l.columns();
        maxScrollRow = Math.max(0, totalRows - rowsVisible);
        scrollRow = Math.clamp(scrollRow, 0, maxScrollRow);
        for (int i = 0; i < entries.size(); i++) {
            int row = i / l.columns() - scrollRow, col = i % l.columns();
            if (row < 0 || row >= rowsVisible) continue;
            VoiceCatalog.Entry e = entries.get(i);
            int x = g.x() + col * (HudLayout.TILE + HudLayout.TILE_GAP);
            int y = g.y() + row * (HudLayout.TILE + HudLayout.TILE_GAP);
            boolean active = e.meta().model().equals(config.getModelPath());
            String model = e.meta().model();
            ModelHealthView.Badge badge = ModelHealthView.badge(e.state(), health(e));
            screen.add(new VoiceTile(x, y, e, () -> liveEntry(model, e), model.equals(selected), active, badge,
                    this::select, this::preview));
        }
        if (!pending.isEmpty()) {
            screen.add(new HudButton(g.x(), g.bottom() - 16, g.w(), 16,
                    Text.translatable("omnichat.ui.voice.download_all", pending.size()), () -> {
                        // The manager queues them and downloads one at a time
                        for (String model : pending) ModelDownloadManager.getInstance().requestDownload(model);
                        screen.rebuild();
                    }));
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
                if (addRepairControls(sel, d.x(), bottom, d.w())) return;
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

    /** Health of an installed model (null while its check is pending, and for other states). */
    private static ModelRepair.Health health(VoiceCatalog.Entry e) {
        return e.state() == VoiceCatalog.State.INSTALLED ? ModelHealthCache.INSTANCE.get(e.meta().model()) : null;
    }

    private static List<String> signature(List<VoiceCatalog.Entry> list) {
        List<String> sig = new ArrayList<>(VoiceCatalog.signature(list));
        for (VoiceCatalog.Entry e : list) {
            sig.add(ModelHealthView.token(health(e)) + (REPAIRING.contains(e.meta().model()) ? "+" : ""));
        }
        return sig;
    }

    /** Fix button (and language picker) for a fixable model; true if the model has a known problem. */
    private boolean addRepairControls(VoiceCatalog.Entry sel, int x, int bottom, int w) {
        ModelRepair.Health h = health(sel);
        if (h == null || h.status() == ModelRepair.Status.OK) return false;
        String model = sel.meta().model();
        HudButton button;
        switch (ModelHealthView.fixMode(h)) {
            case BUTTON -> {
                String voice = ModelHealthView.autoVoice(h);
                button = new HudButton(x, bottom - 18, w, 16,
                        Text.translatable("omnichat.ui.voice.repair_auto", voice), () -> repair(sel, voice));
            }
            case PICKER -> {
                List<String> voices = h.voices();
                int start = ModelHealthView.initialVoiceIndex(voices, PICKED_VOICE.get(model), sel.meta().language());
                PICKED_VOICE.put(model, voices.get(start));
                screen.add(new HudSlider(x, bottom - 34, w, Text.translatable("omnichat.ui.voice.repair_language"),
                        0, voices.size() - 1, start, 1, v -> Text.literal(voices.get((int) v)),
                        v -> PICKED_VOICE.put(model, voices.get((int) v))));
                button = new HudButton(x, bottom - 18, w, 16, Text.translatable("omnichat.ui.voice.repair"),
                        () -> repair(sel, PICKED_VOICE.getOrDefault(model, voices.get(start))));
            }
            default -> {
                return true;
            }
        }
        if (REPAIRING.contains(model)) {
            button.setMessage(Text.translatable("omnichat.ui.voice.repairing"));
            button.active = false;
        }
        screen.add(button);
        return true;
    }

    /** Repairs off the render thread, then drops everything that cached the broken model. */
    private void repair(VoiceCatalog.Entry e, String voice) {
        String model = e.meta().model();
        Path dir = OmnichatConfig.resolveModelDir(model);
        if (dir == null || !REPAIRING.add(model)) return;
        VoicePreview.stop();
        boolean onServer = e.onServer();
        screen.rebuild();
        Thread t = new Thread(() -> {
            try {
                ModelRepair.apply(dir, voice);
                ModelRepair.Health after = ModelRepair.check(dir);
                if (after.status() != ModelRepair.Status.OK) {
                    throw new ModelRepair.RepairException(ModelRepair.Failure.VERIFY_FAILED, "still broken: " + after.problem(), null);
                }
                LOGGER.info("Repaired model '{}' (espeak voice '{}')", model, voice);
                HudToast.show(Text.translatable("omnichat.toast.repaired"),
                        onServer ? Text.translatable("omnichat.toast.repaired.server") : null, HudTheme.OK);
            } catch (IOException | RuntimeException ex) {
                String reason = ex.getMessage() == null ? ex.getClass().getSimpleName() : ex.getMessage();
                LOGGER.warn("Failed to repair model '{}': {}", model, reason);
                HudToast.show(Text.translatable("omnichat.toast.repair_failed"),
                        Text.translatable(ModelHealthView.failureKey(ex)), HudTheme.ERROR);
            } finally {
                ModelHealthCache.INSTANCE.invalidate(model);
                VoiceCatalog.invalidateLocal(model);
                // Evicts a cached engine of this model; rebuilds TTS if it is the configured voice not running yet
                OmnichatClient.getTts().onModelDownloaded(model);
                REPAIRING.remove(model);
                MinecraftClient.getInstance().execute(OmnichatScreen::rebuildIfOpen);
            }
        }, "OmniChat-Model-Repair");
        t.setDaemon(true);
        t.start();
    }

    private VoiceCatalog.Entry liveEntry(String model, VoiceCatalog.Entry fallback) {
        for (VoiceCatalog.Entry e : live) {
            if (e.meta().model().equals(model)) return e;
        }
        return fallback;
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
        if (e != null && ModelHealthView.canActivate(e.state(), health(e)) && !model.equals(config.getModelPath())) {
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
        if (e != null && ModelHealthView.canActivate(e.state(), health(e))) {
            String sample = e.meta().sample().isBlank()
                    ? Text.translatable("omnichat.ui.voice.default_sample").getString() : e.meta().sample();
            VoicePreview.play(model, sample);
        }
        screen.rebuild();
    }

    @Override
    public void tick() {
        // Progress is just redrawn from `live`; reloads, new states and finished installs rebuild the
        // widgets, but never mid-drag (a rebuild would drop the slider being dragged)
        if (++ticks % 10 == 0) {
            live = VoiceCatalog.current();
            if (!screen.isDragging() && !signature(live).equals(builtSignature)) {
                screen.rebuild();
            }
        }
    }

    @Override
    public boolean mouseScrolled(double mouseX, double mouseY, double vertical) {
        if (gridRect == null || mouseX < gridRect.x() || mouseX >= gridRect.right()
                || mouseY < gridRect.y() || mouseY >= gridRect.bottom()) return false;
        int row = Math.clamp(scrollRow - (int) Math.signum(vertical), 0, maxScrollRow);
        if (row != scrollRow) {
            scrollRow = row;
            screen.rebuild();
        }
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
        VoiceCatalog.Entry sel = selectedEntry();
        if (sel == null) return;
        VoiceCatalog.Entry e = liveEntry(sel.meta().model(), sel);

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
        Text hint = e.state() != VoiceCatalog.State.INSTALLED ? Text.translatable("omnichat.ui.voice.preview_remote")
                : ModelHealthView.canActivate(e.state(), health(e)) ? Text.translatable("omnichat.ui.voice.preview_hint")
                : Text.empty();
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
                ModelRepair.Health h = health(e);
                String key = ModelHealthView.statusKey(h);
                boolean active = e.meta().model().equals(config.getModelPath());
                if (h == null) {
                    left = Text.translatable(key);
                    right = active ? Text.translatable("omnichat.ui.voice.active") : Text.empty();
                    color = HudTheme.MUTED;
                    break;
                }
                if (key != null) {
                    left = Text.translatable(key, Text.translatable(ModelHealthView.reasonKey(h.reason())));
                    boolean fixable = ModelHealthView.badge(e.state(), h) == ModelHealthView.Badge.WARN;
                    String mark = fixable ? "⚠" : "!";
                    // The configured voice stays "selected" even while broken (TTS falls back meanwhile)
                    right = active ? Text.translatable("omnichat.ui.voice.active").append(" " + mark) : Text.literal(mark);
                    color = fixable ? HudTheme.WARN : HudTheme.ERROR;
                    break;
                }
                left = e.onServer() ? Text.translatable("omnichat.ui.voice.installed") : Text.translatable("omnichat.ui.voice.local_only");
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
