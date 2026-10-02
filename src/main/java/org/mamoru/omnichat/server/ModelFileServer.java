package org.mamoru.omnichat.server;

import net.fabricmc.fabric.api.event.lifecycle.v1.ServerLifecycleEvents;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerTickEvents;
import net.fabricmc.fabric.api.networking.v1.ServerPlayConnectionEvents;
import net.fabricmc.fabric.api.networking.v1.ServerPlayNetworking;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.network.ServerPlayerEntity;
import org.mamoru.omnichat.network.ModelDownloadStatusS2CPayload;
import org.mamoru.omnichat.network.ModelFileChunkS2CPayload;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayDeque;
import java.util.HashMap;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;

/**
 * Sends model files to players, paced by the server tick. State is static because the
 * tick/disconnect listeners can only be registered once, while a new instance is created
 * on every server start.
 */
public class ModelFileServer {
    private static final Logger LOGGER = LoggerFactory.getLogger("OmniChat");

    // 2 x 32 KB per tick at 20 TPS ~ 1.3 MB/s per player: a 144 MB model takes ~2 min,
    // but Netty never holds more than a few ticks of data and keep-alives get through.
    private static final int CHUNKS_PER_TICK = 2;
    // Global cap on simultaneous transfers (~2.6 MB/s server upload at most)
    private static final int MAX_ACTIVE_TRANSFERS = 2;
    // Waiting requests per player; enough for "Download All" of every model
    private static final int MAX_QUEUED_PER_PLAYER = 8;
    // Requests faster than this are dropped (a legit client asks again only after a download completes)
    private static final long REQUEST_COOLDOWN_MS = 250;

    private record Request(String modelName, Path modelDir, String playerName) {}

    // All state below is guarded by the class lock
    private static final Map<UUID, ArrayDeque<Request>> queues = new LinkedHashMap<>();
    private static final Map<UUID, ModelTransfer> active = new LinkedHashMap<>();
    private static final Map<UUID, Long> lastRequest = new HashMap<>();

    private final Path modelsDir;

    public ModelFileServer(Path modelsDir) {
        this.modelsDir = modelsDir;
    }

    /** Registers the tick/disconnect/stop listeners. Call once from mod init. */
    public static void register() {
        ServerTickEvents.END_SERVER_TICK.register(ModelFileServer::tick);
        ServerPlayConnectionEvents.DISCONNECT.register((handler, server) -> cancel(handler.getPlayer().getUuid()));
        ServerLifecycleEvents.SERVER_STOPPED.register(server -> reset());
    }

    public void sendModel(ServerPlayerEntity player, String modelName) {
        Path modelDir = modelsDir.resolve(modelName);
        if (!modelDir.normalize().startsWith(modelsDir.normalize())) {
            LOGGER.warn("Path traversal attempt from {} for model '{}'", player.getName().getString(), modelName);
            reject(player, modelName, "invalid model name");
            return;
        }

        // the registry is scanned once, so the folder may have been removed since
        if (!Files.isDirectory(modelDir)) {
            LOGGER.warn("Model '{}' not found for download request from {}", modelName, player.getName().getString());
            reject(player, modelName, "model not found on server");
            return;
        }

        enqueue(player, new Request(modelName, modelDir, player.getName().getString()));
    }

    /** Tells the client its request for {@code modelName} was refused or aborted. */
    public static void reject(ServerPlayerEntity player, String modelName, String reason) {
        if (player.isDisconnected()) return;
        sendStatus(player, ModelDownloadStatusS2CPayload.failed(modelName, reason));
    }

    private static void sendStatus(ServerPlayerEntity player, ModelDownloadStatusS2CPayload payload) {
        if (ServerPlayNetworking.canSend(player, ModelDownloadStatusS2CPayload.ID)) {
            ServerPlayNetworking.send(player, payload);
        }
    }

    private static synchronized void enqueue(ServerPlayerEntity player, Request request) {
        UUID playerId = player.getUuid();
        long now = System.currentTimeMillis();
        Long last = lastRequest.put(playerId, now);
        if (last != null && now - last < REQUEST_COOLDOWN_MS) {
            LOGGER.debug("Dropped model request '{}' from {}: too frequent", request.modelName(), request.playerName());
            reject(player, request.modelName(), "too many requests, try again");
            return;
        }

        ArrayDeque<Request> queue = queues.computeIfAbsent(playerId, k -> new ArrayDeque<>());
        ModelTransfer current = active.get(playerId);
        if (current != null && current.modelName.equals(request.modelName())) {
            // The client only re-asks for a model it gave up on (timeout/error), so it has
            // dropped the partial data: restart from the first byte instead of resuming mid-file.
            current.close();
            active.remove(playerId);
            queue.addFirst(request);
            sendStatus(player, ModelDownloadStatusS2CPayload.queued(request.modelName()));
            LOGGER.info("Restarting model '{}' transfer to {}", request.modelName(), request.playerName());
            return;
        }
        if (queue.stream().anyMatch(r -> r.modelName().equals(request.modelName()))) {
            sendStatus(player, ModelDownloadStatusS2CPayload.queued(request.modelName()));
            return;
        }
        if (queue.size() >= MAX_QUEUED_PER_PLAYER) {
            LOGGER.warn("Rejected model request '{}' from {}: queue full", request.modelName(), request.playerName());
            reject(player, request.modelName(), "download queue full");
            return;
        }
        queue.add(request);
        sendStatus(player, ModelDownloadStatusS2CPayload.queued(request.modelName()));
        LOGGER.info("Player {} requested download of model '{}'", request.playerName(), request.modelName());
    }

    private static synchronized void tick(MinecraftServer server) {
        startWaitingTransfers(server);

        Iterator<ModelTransfer> it = active.values().iterator();
        while (it.hasNext()) {
            ModelTransfer transfer = it.next();
            ServerPlayerEntity player = server.getPlayerManager().getPlayer(transfer.playerId);
            if (player == null || player.isDisconnected()
                    || !ServerPlayNetworking.canSend(player, ModelFileChunkS2CPayload.ID)) {
                transfer.close();
                it.remove();
                continue;
            }
            try {
                if (transfer.sendChunks(player, CHUNKS_PER_TICK)) {
                    LOGGER.info("Sent model '{}' ({} files, {} bytes) to {}",
                            transfer.modelName, transfer.fileCount(), transfer.totalBytes, transfer.playerName);
                    transfer.close();
                    it.remove();
                }
            } catch (IOException | RuntimeException e) {
                // runs on the server thread: never let a bad file escape the tick
                LOGGER.error("Failed to send model '{}' to {}", transfer.modelName, transfer.playerName, e);
                transfer.close();
                it.remove();
                reject(player, transfer.modelName, "server read error");
            }
        }
    }

    // Fills free slots round-robin: one transfer per player, MAX_ACTIVE_TRANSFERS overall
    private static void startWaitingTransfers(MinecraftServer server) {
        Iterator<Map.Entry<UUID, ArrayDeque<Request>>> it = queues.entrySet().iterator();
        Map<UUID, ArrayDeque<Request>> served = new LinkedHashMap<>();
        while (it.hasNext() && active.size() < MAX_ACTIVE_TRANSFERS) {
            Map.Entry<UUID, ArrayDeque<Request>> entry = it.next();
            UUID playerId = entry.getKey();
            if (active.containsKey(playerId)) continue;

            ServerPlayerEntity player = server.getPlayerManager().getPlayer(playerId);
            if (player == null || player.isDisconnected()) {
                it.remove();
                continue;
            }

            Request request = entry.getValue().poll();
            if (request != null) {
                try {
                    active.put(playerId, new ModelTransfer(playerId, request.playerName(), request.modelName(), request.modelDir()));
                } catch (ModelTransfer.RefusedException e) {
                    LOGGER.warn("Refused model '{}' for {}: {}", request.modelName(), request.playerName(), e.getMessage());
                    reject(player, request.modelName(), e.getMessage());
                } catch (IOException | RuntimeException e) {
                    LOGGER.error("Failed to send model '{}' to {}", request.modelName(), request.playerName(), e);
                    reject(player, request.modelName(), "server read error");
                }
            }
            // Move served players to the back so others get the next free slot
            it.remove();
            if (!entry.getValue().isEmpty()) {
                served.put(playerId, entry.getValue());
            }
        }
        queues.putAll(served);
    }

    private static synchronized void cancel(UUID playerId) {
        ModelTransfer transfer = active.remove(playerId);
        if (transfer != null) {
            transfer.close();
            LOGGER.info("Cancelled model '{}' transfer to {}", transfer.modelName, transfer.playerName);
        }
        queues.remove(playerId);
        lastRequest.remove(playerId);
    }

    private static synchronized void reset() {
        active.values().forEach(ModelTransfer::close);
        active.clear();
        queues.clear();
        lastRequest.clear();
    }
}
