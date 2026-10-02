package org.mamoru.omnichat.server;

import net.fabricmc.fabric.api.networking.v1.ServerPlayNetworking;
import net.minecraft.network.packet.CustomPayload;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.network.ServerPlayerEntity;
import org.mamoru.omnichat.network.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.*;
import java.util.function.Supplier;

public class ServerNetworkHandler {
    private static final Logger LOGGER = LoggerFactory.getLogger("OmniChat");

    private final VoiceRegistry registry;
    private final ModelFileServer fileServer;
    private final MinecraftServer server;
    private final Map<UUID, Long> lastVoiceSelection = new HashMap<>();

    /** Minimum interval between accepted voice selections from one player. */
    private static final long VOICE_SELECTION_COOLDOWN_MS = 1000;

    public ServerNetworkHandler(VoiceRegistry registry, ModelFileServer fileServer, MinecraftServer server) {
        this.registry = registry;
        this.fileServer = fileServer;
        this.server = server;
    }

    /**
     * Registers the C2S receivers. Call ONCE from onInitialize: Fabric's global receiver
     * registry is static and outlives a server, so per-server handlers would go stale.
     * The receivers delegate to whatever handler {@code current} returns (null when no server runs).
     */
    public static void registerReceivers(Supplier<ServerNetworkHandler> current) {
        ServerPlayNetworking.registerGlobalReceiver(VoiceSelectionC2SPayload.ID, (payload, context) -> {
            ServerNetworkHandler handler = current.get();
            if (handler != null) handler.onVoiceSelection(payload, context);
        });
        ServerPlayNetworking.registerGlobalReceiver(ModelDownloadRequestC2SPayload.ID, (payload, context) -> {
            ServerNetworkHandler handler = current.get();
            if (handler != null) handler.onModelDownloadRequest(payload, context);
        });
        ServerPlayNetworking.registerGlobalReceiver(TypingIndicatorC2SPayload.ID, (payload, context) -> {
            ServerNetworkHandler handler = current.get();
            if (handler != null) handler.onTypingIndicator(payload, context);
        });
    }

    private void onVoiceSelection(VoiceSelectionC2SPayload payload, ServerPlayNetworking.Context context) {
        ServerPlayerEntity player = context.player();
        String modelName = payload.modelName();
        int speakerId = payload.speakerId();

        long now = System.currentTimeMillis();
        Long last = lastVoiceSelection.get(player.getUuid());
        if (last != null && now - last < VOICE_SELECTION_COOLDOWN_MS) {
            return;
        }
        lastVoiceSelection.put(player.getUuid(), now);

        if (speakerId < 0) {
            LOGGER.warn("Player {} selected invalid speaker {}", player.getName().getString(), speakerId);
            return;
        }
        if (!registry.isValidModel(modelName)) {
            LOGGER.warn("Player {} selected invalid model '{}'", player.getName().getString(), modelName);
            return;
        }

        if (!registry.setVoice(player.getUuid(), modelName, speakerId)) {
            return; // unchanged: no save, no broadcast
        }
        LOGGER.info("Player {} selected voice: {} (speaker {})", player.getName().getString(), modelName, speakerId);

        // Broadcast to all players
        broadcast(new VoiceInfoS2CPayload(player.getUuid(), modelName, speakerId), null);
    }

    private void onModelDownloadRequest(ModelDownloadRequestC2SPayload payload, ServerPlayNetworking.Context context) {
        ServerPlayerEntity player = context.player();
        String modelName = payload.modelName();

        if (!registry.isValidModel(modelName)) {
            LOGGER.warn("Player {} requested invalid model '{}'", player.getName().getString(), modelName);
            return;
        }

        // queued and logged by the file server; requests are rate-limited there
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

        // Tell players already online about the joiner's stored voice
        VoiceChoice choice = registry.getVoice(player.getUuid());
        if (choice != null) {
            broadcast(new VoiceInfoS2CPayload(player.getUuid(), choice.modelName(), choice.speakerId()), player);
        }
    }

    public void onPlayerLeave(ServerPlayerEntity player) {
        lastVoiceSelection.remove(player.getUuid());
        // Let remaining players drop the cached voice
        broadcast(new VoiceRemoveS2CPayload(player.getUuid()), player);
    }

    private void broadcast(CustomPayload payload, ServerPlayerEntity exclude) {
        for (ServerPlayerEntity p : server.getPlayerManager().getPlayerList()) {
            if (p != exclude && ServerPlayNetworking.canSend(p, payload.getId())) {
                ServerPlayNetworking.send(p, payload);
            }
        }
    }
}
