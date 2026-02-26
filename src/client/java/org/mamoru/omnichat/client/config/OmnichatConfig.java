package org.mamoru.omnichat.client.config;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import net.fabricmc.loader.api.FabricLoader;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.mamoru.omnichat.util.ModelScanner;

import java.io.IOException;
import java.nio.file.Files;
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

    public static Path getConfigDir() {
        return FabricLoader.getInstance().getConfigDir().resolve("omnichat");
    }

    public static Path getModelsDir() {
        return getConfigDir().resolve("models");
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

        config.ensureDirectories();
        config.save();
        return config;
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
}
