package org.mamoru.omnichat.server;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.reflect.TypeToken;
import org.mamoru.omnichat.network.VoiceChoice;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.lang.reflect.Type;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ScheduledThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * Persists voice choices to voice_choices.json. Writes are coalesced (at most one per
 * {@link #FLUSH_DELAY_SECONDS}), run on a background thread, and go through a temp file
 * plus atomic move so a crash never leaves a truncated file behind.
 */
public class VoiceStorage {
    private static final Logger LOGGER = LoggerFactory.getLogger("OmniChat");
    private static final Gson GSON = new GsonBuilder().setPrettyPrinting().create();
    private static final Type MAP_TYPE = new TypeToken<Map<String, StoredVoice>>() {}.getType();
    private static final long FLUSH_DELAY_SECONDS = 5;

    private final Path filePath;
    private final Path tempPath;
    private final Map<UUID, VoiceChoice> choices = new ConcurrentHashMap<>();
    private final AtomicBoolean flushScheduled = new AtomicBoolean(false);
    private final Object writeLock = new Object();
    private final ScheduledThreadPoolExecutor executor = new ScheduledThreadPoolExecutor(1, r -> {
        Thread t = new Thread(r, "OmniChat-VoiceStorage");
        t.setDaemon(true);
        return t;
    });
    private volatile boolean dirty = false;

    public VoiceStorage(Path configDir) {
        this.filePath = configDir.resolve("voice_choices.json");
        this.tempPath = configDir.resolve("voice_choices.json.tmp");
        // On close, drop the pending delayed flush; close() flushes synchronously instead
        executor.setExecuteExistingDelayedTasksAfterShutdownPolicy(false);
        load();
    }

    private void load() {
        if (!Files.exists(filePath)) return;
        try {
            String json = Files.readString(filePath);
            Map<String, StoredVoice> raw = GSON.fromJson(json, MAP_TYPE);
            if (raw != null) {
                raw.forEach((key, val) -> {
                    if (val == null || val.modelName == null || val.speakerId < 0) return;
                    try {
                        choices.put(UUID.fromString(key), new VoiceChoice(val.modelName, val.speakerId));
                    } catch (IllegalArgumentException ignored) {}
                });
            }
        } catch (Exception e) {
            LOGGER.error("Failed to load voice_choices.json, moving it aside", e);
            backupCorrupted();
        }
    }

    /** Keep the unreadable file so the next save cannot destroy the only copy. */
    private void backupCorrupted() {
        Path backup = filePath.resolveSibling("voice_choices.json." + System.currentTimeMillis() + ".bak");
        try {
            Files.move(filePath, backup, StandardCopyOption.REPLACE_EXISTING);
            LOGGER.warn("Corrupted voice_choices.json saved as {}", backup.getFileName());
        } catch (IOException e) {
            LOGGER.error("Failed to back up corrupted voice_choices.json", e);
        }
    }

    /**
     * Stores the choice and schedules a coalesced background save.
     * @return false if the player already had exactly this choice (nothing changed)
     */
    public boolean setVoice(UUID playerUuid, VoiceChoice choice) {
        VoiceChoice previous = choices.put(playerUuid, choice);
        if (Objects.equals(previous, choice)) return false;
        dirty = true;
        scheduleFlush();
        return true;
    }

    private void scheduleFlush() {
        if (executor.isShutdown()) return;
        if (flushScheduled.compareAndSet(false, true)) {
            try {
                executor.schedule(() -> {
                    flushScheduled.set(false);
                    flush();
                }, FLUSH_DELAY_SECONDS, TimeUnit.SECONDS);
            } catch (RejectedExecutionException e) {
                flushScheduled.set(false);
            }
        }
    }

    /** Writes pending changes now, on the calling thread. */
    public void flush() {
        synchronized (writeLock) {
            if (!dirty) return;
            dirty = false;
            Map<String, StoredVoice> raw = new HashMap<>();
            choices.forEach((uuid, choice) ->
                    raw.put(uuid.toString(), new StoredVoice(choice.modelName(), choice.speakerId())));
            try {
                Files.createDirectories(filePath.getParent());
                Files.writeString(tempPath, GSON.toJson(raw));
                try {
                    Files.move(tempPath, filePath, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
                } catch (AtomicMoveNotSupportedException e) {
                    Files.move(tempPath, filePath, StandardCopyOption.REPLACE_EXISTING);
                }
            } catch (IOException e) {
                dirty = true;
                LOGGER.error("Failed to save voice_choices.json", e);
            }
        }
    }

    /** Stops the background writer and flushes whatever is still pending. */
    public void close() {
        // shutdown (not shutdownNow): an in-progress write must not be interrupted mid-file
        executor.shutdown();
        try {
            executor.awaitTermination(5, TimeUnit.SECONDS);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
        flush();
    }

    public VoiceChoice getVoice(UUID playerUuid) {
        return choices.get(playerUuid);
    }

    public Map<UUID, VoiceChoice> getAllChoices() {
        return Map.copyOf(choices);
    }

    private record StoredVoice(String modelName, int speakerId) {}
}
