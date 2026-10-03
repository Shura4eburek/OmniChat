package org.mamoru.omnichat.client.ui.widget;

import net.minecraft.client.MinecraftClient;
import net.minecraft.client.gl.RenderPipelines;
import net.minecraft.client.gui.Click;
import net.minecraft.client.gui.DrawContext;
import net.minecraft.client.gui.screen.narration.NarrationMessageBuilder;
import net.minecraft.client.gui.widget.ClickableWidget;
import net.minecraft.client.input.KeyInput;
import net.minecraft.client.input.MouseInput;
import net.minecraft.text.Text;
import net.minecraft.util.Identifier;
import org.mamoru.omnichat.client.ui.HudLayout;
import org.mamoru.omnichat.client.ui.HudTheme;
import org.mamoru.omnichat.client.ui.ModelHealthView;
import org.mamoru.omnichat.client.ui.PortraitTextures;
import org.mamoru.omnichat.client.ui.VoiceCatalog;

import java.util.function.Consumer;
import java.util.function.Supplier;

/** Portrait tile. LMB/Enter selects, RMB previews. Badge: ✓ active, ↓ remote, % downloading, ! failed,
 * ⚠ installed model needs a fix, ! installed model is incompatible. */
public class VoiceTile extends ClickableWidget {
    private final VoiceCatalog.Entry entry;
    // Latest catalog entry for this model: download progress changes without a rebuild
    private final Supplier<VoiceCatalog.Entry> live;
    private final boolean selected, activeVoice;
    private final ModelHealthView.Badge problem;
    private final Consumer<String> onSelect, onPreview;

    public VoiceTile(int x, int y, VoiceCatalog.Entry entry, Supplier<VoiceCatalog.Entry> live, boolean selected,
                     boolean activeVoice, ModelHealthView.Badge problem, Consumer<String> onSelect, Consumer<String> onPreview) {
        super(x, y, HudLayout.TILE, HudLayout.TILE, Text.literal(entry.meta().name()));
        this.entry = entry;
        this.live = live;
        this.selected = selected;
        this.activeVoice = activeVoice;
        this.problem = problem;
        this.onSelect = onSelect;
        this.onPreview = onPreview;
    }

    @Override
    protected void renderWidget(DrawContext ctx, int mouseX, int mouseY, float delta) {
        int x = getX(), y = getY(), s = HudLayout.TILE;
        ctx.fill(x, y, x + s, y + s, HudTheme.TILE_BG);
        Identifier portrait = PortraitTextures.get(entry.meta());
        int size = PortraitTextures.sizeOf(portrait);
        ctx.drawTexture(RenderPipelines.GUI_TEXTURED, portrait, x + 3, y + 3, 0, 0, s - 6, s - 6, size, size, size, size);
        if (entry.state() == VoiceCatalog.State.REMOTE || entry.state() == VoiceCatalog.State.FAILED) {
            ctx.fill(x + 3, y + 3, x + s - 3, y + s - 3, 0x88000000); // dim what isn't installed
        }
        boolean hot = isHovered() || isFocused();
        int border = selected ? HudTheme.ACCENT : hot ? 0xCC35E0C8 : HudTheme.ACCENT_DIM;
        HudTheme.frame(ctx, x, y, s, s, border);
        if (selected) HudTheme.frame(ctx, x - 1, y - 1, s + 2, s + 2, HudTheme.ACCENT);
        drawBadge(ctx, x + s, y + s);
    }

    public String model() {
        return entry.meta().model();
    }

    private void drawBadge(DrawContext ctx, int right, int bottom) {
        VoiceCatalog.Entry now = live.get();
        String text;
        int color;
        switch (now.state()) {
            case DOWNLOADING -> {
                text = now.progress() < 0 ? "…" : Math.round(now.progress() * 100) + "%";
                color = HudTheme.WARN;
            }
            case REMOTE -> { text = "↓"; color = HudTheme.WARN; }
            case FAILED -> { text = "!"; color = HudTheme.ERROR; }
            default -> {
                if (problem == ModelHealthView.Badge.WARN) { text = "⚠"; color = HudTheme.WARN; break; }
                if (problem == ModelHealthView.Badge.ERROR) { text = "!"; color = HudTheme.ERROR; break; }
                if (!activeVoice) return;
                text = "✓";
                color = HudTheme.ACCENT;
            }
        }
        var tr = MinecraftClient.getInstance().textRenderer;
        int w = tr.getWidth(text) + 3;
        ctx.fill(right - w, bottom - 10, right, bottom, 0xFF0A080C);
        HudTheme.frame(ctx, right - w, bottom - 10, w, 10, color);
        ctx.drawText(tr, text, right - w + 2, bottom - 9, color, false);
    }

    @Override
    protected boolean isValidClickButton(MouseInput input) {
        return input.button() == 0 || input.button() == 1;
    }

    @Override
    public void onClick(Click click, boolean doubled) {
        if (click.button() == 1) onPreview.accept(entry.meta().model());
        else onSelect.accept(entry.meta().model());
    }

    @Override
    public boolean keyPressed(KeyInput input) {
        if (active && visible && input.isEnterOrSpace()) {
            playDownSound(MinecraftClient.getInstance().getSoundManager());
            onSelect.accept(entry.meta().model());
            return true;
        }
        return false;
    }

    @Override
    protected void appendClickableNarrations(NarrationMessageBuilder builder) {
        appendDefaultNarrations(builder);
    }
}
