package org.mamoru.omnichat.server;

import org.mamoru.omnichat.network.VoiceChoice;
import org.mamoru.omnichat.util.ModelScanner;

import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import java.util.UUID;

public class VoiceRegistry {
    private final Path modelsDir;
    private final VoiceStorage storage;
    // Immutable snapshot, swapped whole by refreshModels() (e.g. from /omnichat reload)
    private volatile List<String> availableModels = List.of();

    public VoiceRegistry(Path configDir) {
        this.modelsDir = configDir.resolve("models");
        this.storage = new VoiceStorage(configDir);
        refreshModels();
    }

    public void refreshModels() {
        this.availableModels = List.copyOf(ModelScanner.scanModels(modelsDir));
    }

    public List<String> getAvailableModels() {
        return availableModels;
    }

    public Path getModelsDir() {
        return modelsDir;
    }

    /** @return false if the stored choice was already identical */
    public boolean setVoice(UUID playerUuid, String modelName, int speakerId) {
        return storage.setVoice(playerUuid, new VoiceChoice(modelName, speakerId));
    }

    /** Flushes pending voice choices and stops the background writer. */
    public void close() {
        storage.close();
    }

    /** Stored voice, or null if none or its model is no longer installed on this server. */
    public VoiceChoice getVoice(UUID playerUuid) {
        VoiceChoice choice = storage.getVoice(playerUuid);
        return choice != null && isValidModel(choice.modelName()) ? choice : null;
    }

    public Map<UUID, VoiceChoice> getOnlineVoices(Iterable<UUID> onlinePlayers) {
        Map<UUID, VoiceChoice> map = new java.util.HashMap<>();
        for (UUID uuid : onlinePlayers) {
            VoiceChoice choice = getVoice(uuid);
            if (choice != null) {
                map.put(uuid, choice);
            }
        }
        return map;
    }

    public boolean isValidModel(String modelName) {
        return availableModels.contains(modelName);
    }
}
