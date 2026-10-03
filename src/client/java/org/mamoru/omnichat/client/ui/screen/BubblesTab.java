package org.mamoru.omnichat.client.ui.screen;

import net.minecraft.client.gui.DrawContext;
import net.minecraft.client.gui.widget.ClickableWidget;
import net.minecraft.text.Text;
import org.mamoru.omnichat.client.OmnichatClient;
import org.mamoru.omnichat.client.config.OmnichatConfig;
import org.mamoru.omnichat.client.ui.HudLayout;
import org.mamoru.omnichat.client.ui.widget.HudSlider;
import org.mamoru.omnichat.client.ui.widget.HudToggle;

import java.util.ArrayList;
import java.util.List;
import java.util.function.Function;

public class BubblesTab implements HudTab {
    @Override
    public void init(OmnichatScreen screen, HudLayout l) {
        OmnichatConfig c = OmnichatClient.getConfig();
        List<Function<int[], ClickableWidget>> rows = new ArrayList<>();
        rows.add(p -> new HudToggle(p[0], p[1], p[2], Text.translatable("omnichat.ui.bubbles.enabled"), c.isShowChatBubbles(), c::setShowChatBubbles));
        rows.add(p -> new HudSlider(p[0], p[1], p[2], Text.translatable("omnichat.ui.bubbles.speed"), 0, 100, c.getBubbleTextSpeed(), 5,
                v -> v <= 0 ? Text.translatable("omnichat.ui.bubbles.instant") : Text.literal(Math.round(v) + "/s"),
                v -> c.setBubbleTextSpeed((float) v)));
        rows.add(p -> new HudToggle(p[0], p[1], p[2], Text.translatable("omnichat.ui.bubbles.whispers"), c.isBubbleWhispers(), c::setBubbleWhispers));
        rows.add(p -> new HudToggle(p[0], p[1], p[2], Text.translatable("omnichat.ui.bubbles.emotes"), c.isBubbleEmotes(), c::setBubbleEmotes));
        rows.add(p -> new HudToggle(p[0], p[1], p[2], Text.translatable("omnichat.ui.bubbles.team"), c.isBubbleTeamMessages(), c::setBubbleTeamMessages));
        rows.add(p -> new HudToggle(p[0], p[1], p[2], Text.translatable("omnichat.ui.bubbles.typing"), c.isSendTypingIndicator(), c::setSendTypingIndicator));
        AudioTab.layoutRows(screen, l, rows);
    }

    @Override
    public void render(DrawContext ctx, int mouseX, int mouseY, float delta, HudLayout layout) {
    }

    @Override
    public Text hints() {
        return Text.translatable("omnichat.ui.hints.settings");
    }
}
