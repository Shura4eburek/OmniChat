package org.mamoru.omnichat.server;

import net.fabricmc.fabric.api.networking.v1.ServerPlayNetworking;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.network.ServerPlayerEntity;
import org.mamoru.omnichat.network.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.*;

public class ServerNetworkHandler {
    private static final Logger LOGGER = LoggerFactory.getLogger("OmniChat");

    private final VoiceRegistry registry;
    private final ModelFileServer fileServer;
    private final MinecraftServer server;

    public ServerNetworkHandler(VoiceRegistry registry, ModelFileServer fileServer, MinecraftServer server) {
        this.registry = registry;
        this.fileServer = fileServer;
        this.server = server;
    }

    public void registerHandlers() {
        ServerPlayNetworking.registerGlobalReceiver(VoiceSelectionC2SPayload.ID, this::onVoiceSelection);
        ServerPlayNetworking.registerGlobalReceiver(ModelDownloadRequestC2SPayload.ID, this::onModelDownloadRequest);
        ServerPlayNetworking.registerGlobalReceiver(TypingIndicatorC2SPayload.ID, this::onTypingIndicator);
    }

    private void onVoiceSelection(VoiceSelectionC2SPayload payload, ServerPlayNetworking.Context context) {
        ServerPlayerEntity player = context.player();
        String modelName = payload.modelName();
        int speakerId = payload.speakerId();

        if (!registry.isValidModel(modelName)) {
            LOGGER.warn("Player {} selected invalid model '{}'", player.getName().getString(), modelName);
            return;
        }

        registry.setVoice(player.getUuid(), modelName, speakerId);
        LOGGER.info("Player {} selected voice: {} (speaker {})", player.getName().getString(), modelName, speakerId);

        // Broadcast to all players
        VoiceInfoS2CPayload broadcast = new VoiceInfoS2CPayload(player.getUuid(), modelName, speakerId);
        for (ServerPlayerEntity p : server.getPlayerManager().getPlayerList()) {
            ServerPlayNetworking.send(p, broadcast);
        }
    }

    private void onModelDownloadRequest(ModelDownloadRequestC2SPayload payload, ServerPlayNetworking.Context context) {
        ServerPlayerEntity player = context.player();
        String modelName = payload.modelName();

        if (!registry.isValidModel(modelName)) {
            LOGGER.warn("Player {} requested invalid model '{}'", player.getName().getString(), modelName);
            return;
        }

        LOGGER.info("Player {} requested download of model '{}'", player.getName().getString(), modelName);
        fileServer.sendModel(player, modelName);
    }

    private void onTypingIndicator(TypingIndicatorC2SPayload payload, ServerPlayNetworking.Context context) {
        ServerPlayerEntity player = context.player();
        TypingIndicatorS2CPayload broadcast = new TypingIndicatorS2CPayload(player.getUuid(), payload.typing());
        for (ServerPlayerEntity p : server.getPlayerManager().getPlayerList()) {
            if (p != player) {
                ServerPlayNetworking.send(p, broadcast);
            }
        }
    }

    public void onPlayerJoin(ServerPlayerEntity player) {
        // Send model list
        ServerPlayNetworking.send(player, new ModelListS2CPayload(registry.getAvailableModels()));

        // Send voice map of all online players
        List<UUID> onlineUuids = new ArrayList<>();
        for (ServerPlayerEntity p : server.getPlayerManager().getPlayerList()) {
            onlineUuids.add(p.getUuid());
        }
        Map<UUID, VoiceChoice> voices = registry.getOnlineVoices(onlineUuids);
        if (!voices.isEmpty()) {
            ServerPlayNetworking.send(player, new VoiceMapS2CPayload(voices));
        }
    }
}
