package org.mamoru.omnichat.server;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.reflect.TypeToken;
import org.mamoru.omnichat.network.VoiceChoice;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.lang.reflect.Type;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

public class VoiceStorage {
    private static final Logger LOGGER = LoggerFactory.getLogger("OmniChat");
    private static final Gson GSON = new GsonBuilder().setPrettyPrinting().create();
    private static final Type MAP_TYPE = new TypeToken<Map<String, StoredVoice>>() {}.getType();

    private final Path filePath;
    private final Map<UUID, VoiceChoice> choices = new ConcurrentHashMap<>();

    public VoiceStorage(Path configDir) {
        this.filePath = configDir.resolve("voice_choices.json");
        load();
    }

    private void load() {
        if (!Files.exists(filePath)) return;
        try {
            String json = Files.readString(filePath);
            Map<String, StoredVoice> raw = GSON.fromJson(json, MAP_TYPE);
            if (raw != null) {
                raw.forEach((key, val) -> {
                    try {
                        choices.put(UUID.fromString(key), new VoiceChoice(val.modelName, val.speakerId));
                    } catch (IllegalArgumentException ignored) {}
                });
            }
        } catch (Exception e) {
            LOGGER.error("Failed to load voice_choices.json", e);
        }
    }

    public void save() {
        try {
            Files.createDirectories(filePath.getParent());
            Map<String, StoredVoice> raw = new java.util.HashMap<>();
            choices.forEach((uuid, choice) ->
                    raw.put(uuid.toString(), new StoredVoice(choice.modelName(), choice.speakerId())));
            Files.writeString(filePath, GSON.toJson(raw));
        } catch (IOException e) {
            LOGGER.error("Failed to save voice_choices.json", e);
        }
    }

    public void setVoice(UUID playerUuid, VoiceChoice choice) {
        choices.put(playerUuid, choice);
        save();
    }

    public VoiceChoice getVoice(UUID playerUuid) {
        return choices.get(playerUuid);
    }

    public Map<UUID, VoiceChoice> getAllChoices() {
        return Map.copyOf(choices);
    }

    private record StoredVoice(String modelName, int speakerId) {}
}
