package org.mamoru.omnichat.client.ui.screen;

import net.minecraft.client.gui.DrawContext;
import net.minecraft.text.Text;
import org.mamoru.omnichat.client.ui.HudLayout;

/** One tab of OmnichatScreen: adds its widgets in init, draws extra decoration in render. */
public interface HudTab {
    void init(OmnichatScreen screen, HudLayout layout);

    void render(DrawContext ctx, int mouseX, int mouseY, float delta, HudLayout layout);

    Text hints();

    default void tick() {
    }

    default boolean mouseScrolled(double mouseX, double mouseY, double vertical) {
        return false;
    }
}
