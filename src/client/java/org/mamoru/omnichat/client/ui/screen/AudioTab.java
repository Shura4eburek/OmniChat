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

public class AudioTab implements HudTab {
    static final int ROW = 18;

    /** Lays rows top-to-bottom, wrapping into a second column if the body is too short. */
    static void layoutRows(OmnichatScreen screen, HudLayout l, List<Function<int[], ClickableWidget>> rows) {
        var b = l.body();
        int perColumn = Math.max(1, b.h() / ROW);
        int columns = rows.size() > perColumn ? 2 : 1;
        int colW = (b.w() - (columns - 1) * 12) / columns;
        for (int i = 0; i < rows.size(); i++) {
            int col = i / perColumn, row = i % perColumn;
            screen.add(rows.get(i).apply(new int[]{b.x() + col * (colW + 12), b.y() + row * ROW, colW}));
        }
    }

    @Override
    public void init(OmnichatScreen screen, HudLayout l) {
        OmnichatConfig c = OmnichatClient.getConfig();
        List<Function<int[], ClickableWidget>> rows = new ArrayList<>();
        rows.add(p -> new HudToggle(p[0], p[1], p[2], Text.translatable("omnichat.ui.audio.enabled"), c.isEnabled(), v -> {
            c.setEnabled(v);
            OmnichatClient.getTts().applySettings();
        }));
        rows.add(p -> new HudSlider(p[0], p[1], p[2], Text.translatable("omnichat.ui.audio.volume"), 0, 2, c.getVolume(), 0.05,
                v -> Text.literal(Math.round(v * 100) + "%"), v -> c.setVolume((float) v)));
        rows.add(p -> new HudSlider(p[0], p[1], p[2], Text.translatable("omnichat.ui.audio.speed"), 0.5, 2, c.getSpeed(), 0.05,
                v -> Text.literal(String.format("%.2fx", v)), v -> c.setSpeed((float) v)));
        rows.add(p -> new HudToggle(p[0], p[1], p[2], Text.translatable("omnichat.ui.audio.robot"), c.isRobotEffect(), c::setRobotEffect));
        rows.add(p -> new HudToggle(p[0], p[1], p[2], Text.translatable("omnichat.ui.audio.own"), c.isReadOwnMessages(), c::setReadOwnMessages));
        rows.add(p -> new HudToggle(p[0], p[1], p[2], Text.translatable("omnichat.ui.audio.whispers"), c.isSpeakWhispers(), c::setSpeakWhispers));
        rows.add(p -> new HudToggle(p[0], p[1], p[2], Text.translatable("omnichat.ui.audio.emotes"), c.isSpeakEmotes(), c::setSpeakEmotes));
        rows.add(p -> new HudToggle(p[0], p[1], p[2], Text.translatable("omnichat.ui.audio.team"), c.isSpeakTeamMessages(), c::setSpeakTeamMessages));
        layoutRows(screen, l, rows);
    }

    @Override
    public void render(DrawContext ctx, int mouseX, int mouseY, float delta, HudLayout layout) {
    }

    @Override
    public Text hints() {
        return Text.translatable("omnichat.ui.hints.settings");
    }
}
