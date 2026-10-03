package org.mamoru.omnichat.client.ui.screen;

import net.minecraft.client.MinecraftClient;
import net.minecraft.client.gui.Click;
import net.minecraft.client.gui.Drawable;
import net.minecraft.client.gui.DrawContext;
import net.minecraft.client.gui.Element;
import net.minecraft.client.gui.Selectable;
import net.minecraft.client.gui.screen.Screen;
import net.minecraft.client.input.KeyInput;
import net.minecraft.text.Text;
import org.lwjgl.glfw.GLFW;
import org.mamoru.omnichat.client.OmnichatClient;
import org.mamoru.omnichat.client.tts.VoicePreview;
import org.mamoru.omnichat.client.ui.HudLayout;
import org.mamoru.omnichat.client.ui.HudTheme;
import org.mamoru.omnichat.client.ui.widget.TabBar;
import org.mamoru.omnichat.client.ui.widget.VoiceTile;

import java.util.List;

/** The OmniChat HUD: header, tabs, active tab, hint footer, inside an adaptive panel. */
public class OmnichatScreen extends Screen {
    public static final int TAB_VOICE = 0, TAB_AUDIO = 1, TAB_BUBBLES = 2;
    private static int lastTab = TAB_VOICE;

    private final Screen parent;
    private final HudTab[] tabs = {new VoiceTab(), new AudioTab(), new BubblesTab()};
    private HudLayout layout;
    private long openedAt;

    public OmnichatScreen(Screen parent) {
        super(Text.translatable("omnichat.ui.title"));
        this.parent = parent;
    }

    @Override
    protected void init() {
        if (openedAt == 0) openedAt = System.currentTimeMillis();
        layout = HudLayout.compute(width, height);
        addDrawableChild(new TabBar(layout.tabs().x(), layout.tabs().y(), layout.tabs().w(), List.of(
                Text.translatable("omnichat.ui.tab.voice"),
                Text.translatable("omnichat.ui.tab.audio"),
                Text.translatable("omnichat.ui.tab.bubbles")), lastTab, this::selectTab));
        tabs[lastTab].init(this, layout);
    }

    public <T extends Element & Drawable & Selectable> T add(T widget) {
        return addDrawableChild(widget);
    }

    /** Render thread: rebuilds the open HUD screen, unless a slider is being dragged (tabs re-check on tick). */
    public static void rebuildIfOpen() {
        if (MinecraftClient.getInstance().currentScreen instanceof OmnichatScreen s && !s.isDragging()) s.rebuild();
    }

    /** Re-creates all widgets, keeping keyboard focus on the same voice tile (or the same slot). */
    public void rebuild() {
        Element focused = getFocused();
        int focusedIndex = focused == null ? -1 : children().indexOf(focused);
        clearAndInit();
        refocus(focused, focusedIndex);
    }

    private void refocus(Element focused, int focusedIndex) {
        if (focused == null) return;
        String focusedModel = focused instanceof VoiceTile t ? t.model() : null;
        Element target = null;
        for (Element e : children()) {
            if (focusedModel != null && e instanceof VoiceTile t && t.model().equals(focusedModel)) target = e;
        }
        if (target == null && focusedModel == null && focusedIndex >= 0 && focusedIndex < children().size()) {
            target = children().get(focusedIndex);
        }
        if (target != null) setFocused(target);
    }

    private void selectTab(int tab) {
        if (tab == lastTab || tab < 0 || tab >= tabs.length) return;
        lastTab = tab;
        rebuild();
    }

    @Override
    public void renderBackground(DrawContext ctx, int mouseX, int mouseY, float delta) {
        // No blur: the world stays visible behind the HUD, like the reference
        ctx.fill(0, 0, width, height, 0x55000000);
    }

    @Override
    public void render(DrawContext ctx, int mouseX, int mouseY, float delta) {
        float fade = Math.min(1f, (System.currentTimeMillis() - openedAt) / 150f);
        HudTheme.frame(ctx, layout.panel());
        var h = layout.header();
        ctx.fill(h.x(), h.y(), h.x() + 20, h.y() + 20, 0x22000000);
        HudTheme.frame(ctx, h.x(), h.y(), 20, 20, HudTheme.ACCENT);
        ctx.drawText(textRenderer, "OC", h.x() + 4, h.y() + 6, HudTheme.ACCENT, false);
        HudTheme.spacedTitle(ctx, textRenderer, Text.translatable("omnichat.ui.title").getString(), h.x() + 26, h.y() + 1, HudTheme.ACCENT);
        boolean cursor = (System.currentTimeMillis() / 500) % 2 == 0;
        ctx.drawText(textRenderer, Text.translatable("omnichat.ui.subtitle").getString() + (cursor ? " _" : ""),
                h.x() + 26, h.y() + 12, HudTheme.MUTED, false);
        HudTheme.divider(ctx, h.x(), h.bottom(), h.w());

        tabs[lastTab].render(ctx, mouseX, mouseY, delta, layout);
        super.render(ctx, mouseX, mouseY, delta);

        var f = layout.footer();
        HudTheme.divider(ctx, f.x(), f.y(), f.w());
        Text hints = tabs[lastTab].hints();
        ctx.drawText(textRenderer, hints, f.x() + (f.w() - textRenderer.getWidth(hints)) / 2, f.y() + 4, HudTheme.MUTED, false);
        if (fade < 1f) ctx.fill(0, 0, width, height, ((int) ((1f - fade) * 255) << 24) | 0x0A080C);
    }

    @Override
    public void tick() {
        tabs[lastTab].tick();
    }

    @Override
    public boolean mouseClicked(Click click, boolean doubled) {
        Element before = getFocused();
        int beforeIndex = before == null ? -1 : children().indexOf(before);
        boolean handled = super.mouseClicked(click, doubled);
        // A click handler that rebuilt the screen gets its old, removed widget focused afterwards
        Element after = getFocused();
        if (after != null && !children().contains(after)) {
            setFocused(null);
            refocus(after, after == before ? beforeIndex : -1);
        }
        return handled;
    }

    @Override
    public boolean mouseScrolled(double mouseX, double mouseY, double horizontal, double vertical) {
        return tabs[lastTab].mouseScrolled(mouseX, mouseY, vertical) || super.mouseScrolled(mouseX, mouseY, horizontal, vertical);
    }

    @Override
    public boolean keyPressed(KeyInput input) {
        int key = input.key();
        if (key >= GLFW.GLFW_KEY_1 && key <= GLFW.GLFW_KEY_3) {
            selectTab(key - GLFW.GLFW_KEY_1);
            return true;
        }
        if (key == GLFW.GLFW_KEY_O) {
            close();
            return true;
        }
        return super.keyPressed(input);
    }

    @Override
    public boolean shouldPause() {
        return false;
    }

    @Override
    public void removed() {
        VoicePreview.stop();
        OmnichatClient.getConfig().save();
    }

    @Override
    public void close() {
        client.setScreen(parent);
    }
}
