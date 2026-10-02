package org.mamoru.omnichat.client.config;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import net.fabricmc.loader.api.FabricLoader;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.mamoru.omnichat.util.ModelScanner;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.InvalidPathException;
import java.nio.file.Path;
import java.util.List;

public class OmnichatConfig {
    private static final Logger LOGGER = LoggerFactory.getLogger("OmniChat");
    private static final Gson GSON = new GsonBuilder().setPrettyPrinting().create();

    private boolean enabled = true;
    private boolean readOwnMessages = false;
    private String modelPath = "default";
    private int speakerId = 0;
    private float speed = 1.0f;
    private float volume = 1.0f;
    private boolean robotEffect = false;
    private int maxQueueSize = 10;
    private boolean showChatBubbles = true;
    private float bubbleTextSpeed = 30.0f;
    // Per message type (see ChatPipeline): /msg whispers, /me emotes, /teammsg team messages
    private boolean speakWhispers = true;
    private boolean bubbleWhispers = true;
    private boolean speakEmotes = true;
    private boolean bubbleEmotes = true;
    private boolean speakTeamMessages = true;
    private boolean bubbleTeamMessages = true;

    public static Path getConfigDir() {
        return FabricLoader.getInstance().getConfigDir().resolve("omnichat");
    }

    public static Path getModelsDir() {
        return getConfigDir().resolve("models");
    }

    /**
     * Directory of a model whose name came from the server, or null if the name isn't a single
     * plain directory name inside the models dir (absolute paths, "..", separators).
     */
    public static Path resolveModelDir(String modelName) {
        Path dir = resolveInside(getModelsDir(), modelName);
        return dir != null && dir.getParent().equals(getModelsDir().toAbsolutePath().normalize()) ? dir : null;
    }

    /** {@code base.resolve(relative)}, or null if the result would leave {@code base}. */
    public static Path resolveInside(Path base, String relative) {
        if (relative == null || relative.isEmpty()) return null;
        Path root = base.toAbsolutePath().normalize();
        try {
            Path resolved = root.resolve(relative).normalize();
            return resolved.startsWith(root) && !resolved.equals(root) ? resolved : null;
        } catch (InvalidPathException e) {
            return null;
        }
    }

    public static Path getConfigFile() {
        return getConfigDir().resolve("config.json");
    }

    public static OmnichatConfig load() {
        Path configFile = getConfigFile();
        OmnichatConfig config;

        if (Files.exists(configFile)) {
            try {
                String json = Files.readString(configFile);
                config = GSON.fromJson(json, OmnichatConfig.class);
                if (config == null) {
                    config = new OmnichatConfig();
                }
            } catch (Exception e) {
                LOGGER.error("Failed to load config, using defaults", e);
                config = new OmnichatConfig();
            }
        } else {
            config = new OmnichatConfig();
        }

        config.validate();
        config.ensureDirectories();
        config.save(); // writes corrected values back
        return config;
    }

    public static final float MIN_SPEED = 0.5f, MAX_SPEED = 2.0f;
    public static final float MAX_VOLUME = 2.0f;
    public static final float MAX_BUBBLE_TEXT_SPEED = 100.0f;

    /**
     * Replaces nulls and clamps hand-edited or corrupted values into the ranges the UI and the
     * engines accept (e.g. maxQueueSize <= 0 would crash the playback worker at startup).
     */
    private void validate() {
        if (modelPath == null || modelPath.isBlank()) {
            LOGGER.warn("Config: modelPath is empty, using 'default'");
            modelPath = "default";
        }
        if (speakerId < 0) {
            LOGGER.warn("Config: speakerId {} is negative, using 0", speakerId);
            speakerId = 0;
        }
        if (maxQueueSize < 1) {
            LOGGER.warn("Config: maxQueueSize {} must be at least 1, using 10", maxQueueSize);
            maxQueueSize = 10;
        }
        speed = clamp("speed", speed, MIN_SPEED, MAX_SPEED, 1.0f);
        volume = clamp("volume", volume, 0.0f, MAX_VOLUME, 1.0f);
        bubbleTextSpeed = clamp("bubbleTextSpeed", bubbleTextSpeed, 0.0f, MAX_BUBBLE_TEXT_SPEED, 30.0f);
    }

    private static float clamp(String name, float value, float min, float max, float fallback) {
        float result = Float.isNaN(value) ? fallback : Math.max(min, Math.min(max, value));
        if (result != value) {
            LOGGER.warn("Config: {} {} is out of range [{}, {}], using {}", name, value, min, max, result);
        }
        return result;
    }

    public void save() {
        try {
            Files.createDirectories(getConfigDir());
            Files.writeString(getConfigFile(), GSON.toJson(this));
        } catch (IOException e) {
            LOGGER.error("Failed to save config", e);
        }
    }

    private void ensureDirectories() {
        try {
            Files.createDirectories(getModelsDir());
        } catch (IOException e) {
            LOGGER.error("Failed to create config directories", e);
        }
    }

    public boolean isEnabled() {
        return enabled;
    }

    public boolean isReadOwnMessages() {
        return readOwnMessages;
    }

    public String getModelPath() {
        return modelPath;
    }

    public Path getResolvedModelDir() {
        return getModelsDir().resolve(modelPath);
    }

    public int getSpeakerId() {
        return speakerId;
    }

    public void setSpeakerId(int speakerId) {
        this.speakerId = Math.max(0, speakerId);
    }

    public float getSpeed() {
        return speed;
    }

    public float getVolume() {
        return volume;
    }

    public boolean isRobotEffect() {
        return robotEffect;
    }

    public int getMaxQueueSize() {
        return maxQueueSize;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public void setReadOwnMessages(boolean readOwnMessages) {
        this.readOwnMessages = readOwnMessages;
    }

    public void setModelPath(String modelPath) {
        this.modelPath = modelPath;
    }

    public void setSpeed(float speed) {
        this.speed = speed;
    }

    public void setVolume(float volume) {
        this.volume = volume;
    }

    public void setRobotEffect(boolean robotEffect) {
        this.robotEffect = robotEffect;
    }

    public boolean isShowChatBubbles() {
        return showChatBubbles;
    }

    public void setShowChatBubbles(boolean showChatBubbles) {
        this.showChatBubbles = showChatBubbles;
    }

    public float getBubbleTextSpeed() {
        return bubbleTextSpeed;
    }

    public void setBubbleTextSpeed(float bubbleTextSpeed) {
        this.bubbleTextSpeed = bubbleTextSpeed;
    }

    public static List<String> listAvailableModels() {
        return ModelScanner.scanModels(getModelsDir());
    }

    public boolean isSpeakWhispers() {
        return speakWhispers;
    }

    public void setSpeakWhispers(boolean speakWhispers) {
        this.speakWhispers = speakWhispers;
    }

    public boolean isBubbleWhispers() {
        return bubbleWhispers;
    }

    public void setBubbleWhispers(boolean bubbleWhispers) {
        this.bubbleWhispers = bubbleWhispers;
    }

    public boolean isSpeakEmotes() {
        return speakEmotes;
    }

    public void setSpeakEmotes(boolean speakEmotes) {
        this.speakEmotes = speakEmotes;
    }

    public boolean isBubbleEmotes() {
        return bubbleEmotes;
    }

    public void setBubbleEmotes(boolean bubbleEmotes) {
        this.bubbleEmotes = bubbleEmotes;
    }

    public boolean isSpeakTeamMessages() {
        return speakTeamMessages;
    }

    public void setSpeakTeamMessages(boolean speakTeamMessages) {
        this.speakTeamMessages = speakTeamMessages;
    }

    public boolean isBubbleTeamMessages() {
        return bubbleTeamMessages;
    }

    public void setBubbleTeamMessages(boolean bubbleTeamMessages) {
        this.bubbleTeamMessages = bubbleTeamMessages;
    }
}
