package org.mamoru.omnichat.server;

import net.fabricmc.fabric.api.event.lifecycle.v1.ServerTickEvents;
import net.fabricmc.fabric.api.networking.v1.ServerPlayNetworking;
import net.minecraft.network.packet.CustomPayload;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.network.ServerPlayerEntity;
import net.minecraft.text.Text;
import net.minecraft.util.Formatting;
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
    // Selections that arrived inside the cooldown: the latest one wins and is applied when it ends
    private final Map<UUID, VoiceSelectionC2SPayload> pendingVoiceSelection = new HashMap<>();

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
        ServerTickEvents.END_SERVER_TICK.register(server -> {
            ServerNetworkHandler handler = current.get();
            if (handler != null) handler.flushPendingVoiceSelections();
        });
    }

    private void onVoiceSelection(VoiceSelectionC2SPayload payload, ServerPlayNetworking.Context context) {
        ServerPlayerEntity player = context.player();
        long now = System.currentTimeMillis();
        Long last = lastVoiceSelection.get(player.getUuid());
        if (last != null && now - last < VOICE_SELECTION_COOLDOWN_MS) {
            pendingVoiceSelection.put(player.getUuid(), payload);
            return;
        }
        applyVoiceSelection(player, payload, now);
    }

    private void flushPendingVoiceSelections() {
        if (pendingVoiceSelection.isEmpty()) return;
        long now = System.currentTimeMillis();
        Iterator<Map.Entry<UUID, VoiceSelectionC2SPayload>> it = pendingVoiceSelection.entrySet().iterator();
        while (it.hasNext()) {
            Map.Entry<UUID, VoiceSelectionC2SPayload> entry = it.next();
            Long last = lastVoiceSelection.get(entry.getKey());
            if (last != null && now - last < VOICE_SELECTION_COOLDOWN_MS) continue;
            it.remove();
            ServerPlayerEntity player = server.getPlayerManager().getPlayer(entry.getKey());
            if (player != null) {
                applyVoiceSelection(player, entry.getValue(), now);
            }
        }
    }

    private void applyVoiceSelection(ServerPlayerEntity player, VoiceSelectionC2SPayload payload, long now) {
        String modelName = payload.modelName();
        int speakerId = payload.speakerId();
        lastVoiceSelection.put(player.getUuid(), now);

        if (speakerId < 0) {
            LOGGER.warn("Player {} selected invalid speaker {}", player.getName().getString(), speakerId);
            rejectSelection(player, "invalid speaker " + speakerId);
            return;
        }
        if (!registry.isValidModel(modelName)) {
            LOGGER.warn("Player {} selected invalid model '{}'", player.getName().getString(), modelName);
            rejectSelection(player, "model '" + modelName + "' is not installed on this server");
            return;
        }

        if (!registry.setVoice(player.getUuid(), modelName, speakerId)) {
            return; // unchanged: no save, no broadcast
        }
        LOGGER.info("Player {} selected voice: {} (speaker {})", player.getName().getString(), modelName, speakerId);

        // Broadcast to all players
        broadcast(new VoiceInfoS2CPayload(player.getUuid(), modelName, speakerId), null);
    }

    /** Tells the player why their voice wasn't applied instead of failing silently. */
    private static void rejectSelection(ServerPlayerEntity player, String reason) {
        player.sendMessage(Text.literal("[OmniChat] Voice not applied: " + reason).formatted(Formatting.RED), false);
    }

    private void onModelDownloadRequest(ModelDownloadRequestC2SPayload payload, ServerPlayNetworking.Context context) {
        ServerPlayerEntity player = context.player();
        String modelName = payload.modelName();

        if (!registry.isValidModel(modelName)) {
            LOGGER.warn("Player {} requested invalid model '{}'", player.getName().getString(), modelName);
            ModelFileServer.reject(player, modelName, "unknown model");
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

    /**
     * Rescans the models directory and re-sends the model list and the (filtered) voice map to
     * everyone online, so added models become selectable and removed ones stop being used.
     * Runs on the server thread (from /omnichat reload).
     * @return the number of models now available
     */
    public int reloadModels() {
        registry.refreshModels();
        List<String> models = registry.getAvailableModels();
        List<ServerPlayerEntity> players = server.getPlayerManager().getPlayerList();
        List<UUID> onlineUuids = new ArrayList<>();
        for (ServerPlayerEntity p : players) {
            onlineUuids.add(p.getUuid());
        }
        // Sent even when empty: the client replaces its whole map, dropping voices of removed models
        VoiceMapS2CPayload voices = new VoiceMapS2CPayload(registry.getOnlineVoices(onlineUuids));
        broadcast(voices, null);
        // Model list last: clients answer it by re-sending their configured voice
        broadcast(new ModelListS2CPayload(models), null);
        LOGGER.info("Reloaded OmniChat models: {}", models);
        return models.size();
    }

    public void onPlayerLeave(ServerPlayerEntity player) {
        lastVoiceSelection.remove(player.getUuid());
        pendingVoiceSelection.remove(player.getUuid());
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
