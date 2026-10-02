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

    // Typing indicator: players whose typing=true was last broadcast, plus a per-player
    // throttle (toggles inside the cooldown collapse into one pending state, flushed on tick)
    private final Set<UUID> typingBroadcast = new HashSet<>();
    private final Map<UUID, Long> lastTypingBroadcast = new HashMap<>();
    private final Map<UUID, Boolean> pendingTyping = new HashMap<>();

    /** Minimum interval between typing-state broadcasts for one player. */
    private static final long TYPING_COOLDOWN_MS = 500;

    /** Players whose client completed the handshake with a matching protocol version. */
    private final Set<UUID> compatible = new HashSet<>();

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
        ServerPlayNetworking.registerGlobalReceiver(ProtocolVersionPayload.ID, (payload, context) -> {
            ServerNetworkHandler handler = current.get();
            if (handler != null) handler.onProtocolVersion(payload, context);
        });
        ServerPlayNetworking.registerGlobalReceiver(VoiceSelectionC2SPayload.ID, (payload, context) -> {
            ServerNetworkHandler handler = current.get();
            if (handler != null && handler.isCompatible(context.player())) handler.onVoiceSelection(payload, context);
        });
        ServerPlayNetworking.registerGlobalReceiver(ModelDownloadRequestC2SPayload.ID, (payload, context) -> {
            ServerNetworkHandler handler = current.get();
            if (handler != null && handler.isCompatible(context.player())) handler.onModelDownloadRequest(payload, context);
        });
        ServerPlayNetworking.registerGlobalReceiver(TypingIndicatorC2SPayload.ID, (payload, context) -> {
            ServerNetworkHandler handler = current.get();
            if (handler != null && handler.isCompatible(context.player())) handler.onTypingIndicator(payload, context);
        });
        ServerTickEvents.END_SERVER_TICK.register(server -> {
            ServerNetworkHandler handler = current.get();
            if (handler != null) {
                handler.flushPendingVoiceSelections();
                handler.flushPendingTyping();
            }
        });
    }

    private boolean isCompatible(ServerPlayerEntity player) {
        return compatible.contains(player.getUuid());
    }

    /** Client handshake: always answer with our version, then sync state only if they match. */
    private void onProtocolVersion(ProtocolVersionPayload payload, ServerPlayNetworking.Context context) {
        ServerPlayerEntity player = context.player();
        if (ServerPlayNetworking.canSend(player, ProtocolVersionPayload.ID)) {
            ServerPlayNetworking.send(player, new ProtocolVersionPayload(ProtocolVersionPayload.PROTOCOL_VERSION));
        }
        if (payload.version() != ProtocolVersionPayload.PROTOCOL_VERSION) {
            compatible.remove(player.getUuid());
            LOGGER.warn("Player {} uses OmniChat protocol {}, server uses {}: OmniChat features disabled for them",
                    player.getName().getString(), payload.version(), ProtocolVersionPayload.PROTOCOL_VERSION);
            return;
        }
        if (compatible.add(player.getUuid())) {
            sendInitialState(player);
        }
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
        UUID uuid = player.getUuid();
        boolean typing = payload.typing();
        if (typing == typingBroadcast.contains(uuid)) {
            pendingTyping.remove(uuid); // repeat, or a toggle that cancels a pending one
            return;
        }
        Long last = lastTypingBroadcast.get(uuid);
        long now = System.currentTimeMillis();
        if (last != null && now - last < TYPING_COOLDOWN_MS) {
            pendingTyping.put(uuid, typing);
            return;
        }
        applyTyping(player, typing, now);
    }

    private void flushPendingTyping() {
        if (pendingTyping.isEmpty()) return;
        long now = System.currentTimeMillis();
        Iterator<Map.Entry<UUID, Boolean>> it = pendingTyping.entrySet().iterator();
        while (it.hasNext()) {
            Map.Entry<UUID, Boolean> entry = it.next();
            Long last = lastTypingBroadcast.get(entry.getKey());
            if (last != null && now - last < TYPING_COOLDOWN_MS) continue;
            it.remove();
            ServerPlayerEntity player = server.getPlayerManager().getPlayer(entry.getKey());
            if (player != null) {
                applyTyping(player, entry.getValue(), now);
            }
        }
    }

    private void applyTyping(ServerPlayerEntity player, boolean typing, long now) {
        UUID uuid = player.getUuid();
        if (typing ? !typingBroadcast.add(uuid) : !typingBroadcast.remove(uuid)) return;
        lastTypingBroadcast.put(uuid, now);
        broadcast(new TypingIndicatorS2CPayload(uuid, typing), player);
    }

    public void onPlayerJoin(ServerPlayerEntity player) {
        // Model list and voice map wait for the client's handshake (onProtocolVersion).
        // A client with OmniChat channels but no handshake channel runs a pre-versioning build.
        if (!ServerPlayNetworking.canSend(player, ProtocolVersionPayload.ID)
                && ServerPlayNetworking.canSend(player, ModelListS2CPayload.ID)) {
            LOGGER.warn("Player {} uses an outdated OmniChat version: OmniChat features disabled for them",
                    player.getName().getString());
            player.sendMessage(Text.literal("[OmniChat] Your OmniChat version doesn't match the server's; "
                    + "voice sync is disabled here. Update the mod to use it.").formatted(Formatting.YELLOW), false);
        }

        // Tell players already online about the joiner's stored voice
        VoiceChoice choice = registry.getVoice(player.getUuid());
        if (choice != null) {
            broadcast(new VoiceInfoS2CPayload(player.getUuid(), choice.modelName(), choice.speakerId()), player);
        }
    }

    /** Model list and voice map of everyone online, sent once the handshake succeeds. */
    private void sendInitialState(ServerPlayerEntity player) {
        if (ServerPlayNetworking.canSend(player, ModelListS2CPayload.ID)) {
            ServerPlayNetworking.send(player, new ModelListS2CPayload(registry.getAvailableModels()));
        }

        List<UUID> onlineUuids = new ArrayList<>();
        for (ServerPlayerEntity p : server.getPlayerManager().getPlayerList()) {
            onlineUuids.add(p.getUuid());
        }
        Map<UUID, VoiceChoice> voices = registry.getOnlineVoices(onlineUuids);
        if (!voices.isEmpty() && ServerPlayNetworking.canSend(player, VoiceMapS2CPayload.ID)) {
            ServerPlayNetworking.send(player, new VoiceMapS2CPayload(voices));
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
        compatible.remove(player.getUuid());
        lastVoiceSelection.remove(player.getUuid());
        pendingVoiceSelection.remove(player.getUuid());
        // The client's own typing=false is lost on crash/kick/timeout; clear "..." for everyone else
        pendingTyping.remove(player.getUuid());
        lastTypingBroadcast.remove(player.getUuid());
        if (typingBroadcast.remove(player.getUuid())) {
            broadcast(new TypingIndicatorS2CPayload(player.getUuid(), false), player);
        }
        // Let remaining players drop the cached voice
        broadcast(new VoiceRemoveS2CPayload(player.getUuid()), player);
    }

    private void broadcast(CustomPayload payload, ServerPlayerEntity exclude) {
        for (ServerPlayerEntity p : server.getPlayerManager().getPlayerList()) {
            if (p != exclude && isCompatible(p) && ServerPlayNetworking.canSend(p, payload.getId())) {
                ServerPlayNetworking.send(p, payload);
            }
        }
    }
}
