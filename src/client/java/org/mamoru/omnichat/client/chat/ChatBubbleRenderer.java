package org.mamoru.omnichat.client.chat;

import net.fabricmc.fabric.api.client.rendering.v1.world.WorldRenderEvents;
import net.minecraft.client.MinecraftClient;
import net.minecraft.client.font.TextRenderer;
import net.minecraft.client.render.LightmapTextureManager;
import net.minecraft.client.render.command.OrderedRenderCommandQueue;
import net.minecraft.client.render.state.CameraRenderState;
import net.minecraft.client.util.math.MatrixStack;
import net.minecraft.entity.player.PlayerEntity;
import net.minecraft.text.Text;
import net.minecraft.util.math.Vec3d;
import org.mamoru.omnichat.client.OmnichatClient;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

public class ChatBubbleRenderer {
    private static final double MAX_DISTANCE = 40.0;
    private static final int MAX_LINE_WIDTH = 200;
    private static final double LINE_HEIGHT = 0.25;

    public static void register() {
        WorldRenderEvents.AFTER_ENTITIES.register(context -> {
            if (!OmnichatClient.getConfig().isShowChatBubbles()) {
                return;
            }

            MinecraftClient client = MinecraftClient.getInstance();
            if (client.world == null || client.player == null) {
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
                String visibleText = bubble.getVisibleText();
                if (visibleText.isEmpty()) continue;

                renderBubble(client, matrices, commandQueue, cameraState, uuid, visibleText);
            }

            // Render typing indicators
            long time = System.currentTimeMillis();
            Set<UUID> typingPlayers = manager.getTypingPlayers();
            for (UUID uuid : typingPlayers) {
                if (manager.getActiveBubbles().containsKey(uuid)) continue;

                int dots = (int) ((time / 500) % 4);
                String typingText = ".".repeat(dots);
                if (typingText.isEmpty()) typingText = " ";

                renderBubble(client, matrices, commandQueue, cameraState, uuid, typingText);
            }
        });
    }

    private static List<String> wrapText(String text, TextRenderer textRenderer) {
        List<String> lines = new ArrayList<>();
        if (textRenderer.getWidth(text) <= MAX_LINE_WIDTH) {
            lines.add(text);
            return lines;
        }

        String[] words = text.split(" ");
        StringBuilder currentLine = new StringBuilder();

        for (String word : words) {
            if (currentLine.isEmpty()) {
                currentLine.append(word);
            } else {
                String test = currentLine + " " + word;
                if (textRenderer.getWidth(test) > MAX_LINE_WIDTH) {
                    lines.add(currentLine.toString());
                    currentLine = new StringBuilder(word);
                } else {
                    currentLine.append(" ").append(word);
                }
            }
        }
        if (!currentLine.isEmpty()) {
            lines.add(currentLine.toString());
        }

        return lines;
    }

    private static void renderBubble(MinecraftClient client, MatrixStack matrices,
                                      OrderedRenderCommandQueue commandQueue,
                                      CameraRenderState cameraState, UUID playerUuid,
                                      String text) {
        PlayerEntity player = client.world.getPlayerByUuid(playerUuid);
        if (player == null) return;
        if (player == client.player) return;

        Vec3d playerPos = player.getEntityPos();
        double squaredDist = client.player.getEntityPos().squaredDistanceTo(playerPos);
        if (squaredDist > MAX_DISTANCE * MAX_DISTANCE) return;

        List<String> lines = wrapText(text, client.textRenderer);

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
                    Text.literal(lines.get(i)), true,
                    LightmapTextureManager.MAX_LIGHT_COORDINATE,
                    squaredDist, cameraState);
        }

        matrices.pop();
    }
}
