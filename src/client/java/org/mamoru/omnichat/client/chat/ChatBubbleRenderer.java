package org.mamoru.omnichat.client.chat;

import net.fabricmc.fabric.api.client.rendering.v1.world.WorldRenderEvents;
import net.minecraft.client.MinecraftClient;
import net.minecraft.client.font.TextRenderer;
import net.minecraft.client.render.LightmapTextureManager;
import net.minecraft.client.render.command.OrderedRenderCommandQueue;
import net.minecraft.client.render.state.CameraRenderState;
import net.minecraft.client.util.math.MatrixStack;
import net.minecraft.entity.player.PlayerEntity;
import net.minecraft.scoreboard.AbstractTeam;
import net.minecraft.text.StringVisitable;
import net.minecraft.text.Style;
import net.minecraft.text.Text;
import net.minecraft.util.math.Vec3d;
import org.mamoru.omnichat.client.HearingRange;
import org.mamoru.omnichat.client.OmnichatClient;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

public class ChatBubbleRenderer {
    /** Vanilla hides a sneaking player's name tag from this distance on. */
    private static final double SNEAKING_LABEL_DISTANCE = 32.0;
    private static final int MAX_LINE_WIDTH = 200;
    private static final double LINE_HEIGHT = 0.25;

    public static void register() {
        WorldRenderEvents.AFTER_ENTITIES.register(context -> {
            if (!OmnichatClient.getConfig().isShowChatBubbles()) {
                return;
            }

            MinecraftClient client = MinecraftClient.getInstance();
            if (client.world == null || client.player == null || !MinecraftClient.isHudEnabled()) {
                return;
            }

            ChatBubbleManager manager = ChatBubbleManager.getInstance();
            if (manager.getActiveBubbles().isEmpty() && manager.getTypingPlayers().isEmpty()) {
                return;
            }

            MatrixStack matrices = context.matrices();
            OrderedRenderCommandQueue commandQueue = context.commandQueue();
            CameraRenderState cameraState = context.worldState().cameraRenderState;

            // Render chat bubbles
            for (Map.Entry<UUID, ChatBubbleManager.ChatBubble> entry : manager.getActiveBubbles().entrySet()) {
                UUID uuid = entry.getKey();
                ChatBubbleManager.ChatBubble bubble = entry.getValue();
                List<String> lines = bubble.getWrappedLines(text -> wrapText(text, client.textRenderer));
                if (lines.isEmpty()) continue;

                renderBubble(client, matrices, commandQueue, cameraState, uuid, lines);
            }

            // Render typing indicators
            long time = System.currentTimeMillis();
            Set<UUID> typingPlayers = manager.getTypingPlayers();
            for (UUID uuid : typingPlayers) {
                if (manager.getActiveBubbles().containsKey(uuid)) continue;

                int dots = (int) ((time / 500) % 4);
                String typingText = ".".repeat(dots);
                if (typingText.isEmpty()) typingText = " ";

                renderBubble(client, matrices, commandQueue, cameraState, uuid, List.of(typingText));
            }
        });
    }

    /**
     * Wraps at {@link #MAX_LINE_WIDTH} pixels like vanilla chat: on spaces where possible, and
     * mid-token for words that do not fit on a line by themselves (URLs, CJK text).
     */
    private static List<String> wrapText(String text, TextRenderer textRenderer) {
        if (text.isEmpty()) return List.of();
        List<String> lines = new ArrayList<>();
        for (StringVisitable line : textRenderer.getTextHandler().wrapLines(text, MAX_LINE_WIDTH, Style.EMPTY)) {
            lines.add(line.getString());
        }
        return lines;
    }

    private static void renderBubble(MinecraftClient client, MatrixStack matrices,
                                      OrderedRenderCommandQueue commandQueue,
                                      CameraRenderState cameraState, UUID playerUuid,
                                      List<String> lines) {
        PlayerEntity player = client.world.getPlayerByUuid(playerUuid);
        if (player == null) return;
        if (player == client.player) return;

        // Interpolated like the player model, so the bubble does not jitter at more than 20 FPS
        Vec3d playerPos = player.getLerpedPos(client.getRenderTickCounter().getTickProgress(true));
        double squaredDist = cameraState.pos.squaredDistanceTo(playerPos);
        if (squaredDist > HearingRange.BLOCKS * HearingRange.BLOCKS) return;
        if (!isLabelVisible(client, player, squaredDist)) return;

        matrices.push();
        matrices.translate(
                playerPos.x - cameraState.pos.x,
                playerPos.y - cameraState.pos.y,
                playerPos.z - cameraState.pos.z
        );

        // Render lines bottom-to-top so first line is highest
        double baseY = player.getHeight() + 0.5;
        for (int i = 0; i < lines.size(); i++) {
            double yOffset = baseY + (lines.size() - 1 - i) * LINE_HEIGHT;
            Vec3d labelOffset = new Vec3d(0, yOffset, 0);

            commandQueue.submitLabel(matrices, labelOffset, 0,
                    // Sneaking players' bubbles are dimmed and hidden behind walls, like name tags
                    Text.literal(lines.get(i)), !player.isSneaky(),
                    LightmapTextureManager.MAX_LIGHT_COORDINATE,
                    squaredDist, cameraState);
        }

        matrices.pop();
    }

    /**
     * Mirrors vanilla's name tag rules (LivingEntityRenderer#hasLabel) so a bubble or typing
     * indicator never reveals a player whose name tag would be hidden.
     */
    private static boolean isLabelVisible(MinecraftClient client, PlayerEntity player, double squaredDist) {
        if (player == client.getCameraEntity()) return false;
        if (player.isSneaky() && squaredDist >= SNEAKING_LABEL_DISTANCE * SNEAKING_LABEL_DISTANCE) return false;

        // Covers the invisibility effect, including teammates seen via seeFriendlyInvisibles
        boolean visible = !player.isInvisibleTo(client.player);

        AbstractTeam team = player.getScoreboardTeam();
        AbstractTeam viewerTeam = client.player.getScoreboardTeam();
        if (team != null) {
            switch (team.getNameTagVisibilityRule()) {
                case NEVER:
                    return false;
                case HIDE_FOR_OTHER_TEAMS:
                    if (viewerTeam != null && !team.isEqual(viewerTeam)) return false;
                    break;
                case HIDE_FOR_OWN_TEAM:
                    if (viewerTeam != null && team.isEqual(viewerTeam)) return false;
                    break;
                default:
                    break;
            }
        }
        return visible;
    }
}
