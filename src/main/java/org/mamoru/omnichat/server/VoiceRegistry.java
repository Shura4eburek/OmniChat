package org.mamoru.omnichat.server;

import org.mamoru.omnichat.network.VoiceChoice;
import org.mamoru.omnichat.util.ModelScanner;
import org.mamoru.omnichat.voice.VoiceMeta;
import org.mamoru.omnichat.voice.VoiceMetaReader;

import java.nio.file.Path;
import java.util.ArrayList;
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

    // Immutable snapshot, swapped whole by refreshModels() together with availableModels
    private volatile List<VoiceMeta> catalog = List.of();

    public void refreshModels() {
        List<String> models = List.copyOf(ModelScanner.scanModels(modelsDir));
        List<VoiceMeta> metas = new ArrayList<>(models.size());
        for (String model : models) {
            metas.add(VoiceMetaReader.read(modelsDir.resolve(model), model));
        }
        this.availableModels = models;
        this.catalog = List.copyOf(metas);
    }

    public List<VoiceMeta> getCatalog() {
        return catalog;
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
