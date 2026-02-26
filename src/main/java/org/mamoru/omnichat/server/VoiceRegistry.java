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
    private List<String> availableModels;

    public VoiceRegistry(Path configDir) {
        this.modelsDir = configDir.resolve("models");
        this.storage = new VoiceStorage(configDir);
        refreshModels();
    }

    public void refreshModels() {
        this.availableModels = ModelScanner.scanModels(modelsDir);
    }

    public List<String> getAvailableModels() {
        return availableModels;
    }

    public Path getModelsDir() {
        return modelsDir;
    }

    public void setVoice(UUID playerUuid, String modelName, int speakerId) {
        storage.setVoice(playerUuid, new VoiceChoice(modelName, speakerId));
    }

    public VoiceChoice getVoice(UUID playerUuid) {
        return storage.getVoice(playerUuid);
    }

    public Map<UUID, VoiceChoice> getOnlineVoices(Iterable<UUID> onlinePlayers) {
        Map<UUID, VoiceChoice> map = new java.util.HashMap<>();
        for (UUID uuid : onlinePlayers) {
            VoiceChoice choice = storage.getVoice(uuid);
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
