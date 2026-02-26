package org.mamoru.omnichat.client;

import com.mojang.authlib.GameProfile;
import net.fabricmc.api.ClientModInitializer;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientTickEvents;
import net.fabricmc.fabric.api.client.message.v1.ClientReceiveMessageEvents;
import net.fabricmc.fabric.api.client.networking.v1.ClientPlayConnectionEvents;
import net.minecraft.client.MinecraftClient;
import net.minecraft.network.message.MessageType;
import net.minecraft.network.message.SignedMessage;
import net.minecraft.text.Text;
import org.mamoru.omnichat.client.chat.ChatBubbleManager;
import org.mamoru.omnichat.client.chat.ChatBubbleRenderer;
import org.mamoru.omnichat.client.chat.ChatMessageHandler;
import org.mamoru.omnichat.client.config.OmnichatConfig;
import org.mamoru.omnichat.client.network.ClientNetworkHandler;
import org.mamoru.omnichat.client.network.ModelDownloadManager;
import org.mamoru.omnichat.client.network.VoiceCache;
import org.mamoru.omnichat.client.screen.DownloadProgressHud;
import org.mamoru.omnichat.client.tts.GladosTtsEngine;
import org.mamoru.omnichat.client.tts.ITtsEngine;
import org.mamoru.omnichat.client.tts.TtsEngine;
import org.mamoru.omnichat.client.tts.SpatialAudioPlayer;
import org.mamoru.omnichat.client.tts.TtsPlaybackWorker;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public class OmnichatClient implements ClientModInitializer {
    private static final Logger LOGGER = LoggerFactory.getLogger("OmniChat");

    private static OmnichatConfig config;
    private static ITtsEngine engine;
    private static TtsPlaybackWorker worker;
    private static ChatMessageHandler chatHandler;
    private static final Map<String, ITtsEngine> engineCache = new ConcurrentHashMap<>();

    @Override
    public void onInitializeClient() {
        LOGGER.info("OmniChat initializing...");

        config = OmnichatConfig.load();

        OmnichatKeybinds.register();
        ClientTickEvents.END_CLIENT_TICK.register(client -> {
            SpatialAudioPlayer.tick();
            ChatBubbleManager.getInstance().tick();
        });
        ChatBubbleRenderer.register();

        // Register chat bubble listener (independent of TTS)
        ClientReceiveMessageEvents.CHAT.register(OmnichatClient::onChatMessageForBubble);

        // Register client network handlers and HUD
        ClientNetworkHandler.registerHandlers();
        DownloadProgressHud.register();

        // Clean up on disconnect
        ClientPlayConnectionEvents.DISCONNECT.register((handler, client) -> {
            VoiceCache.getInstance().clear();
            ModelDownloadManager.getInstance().clear();
            ChatBubbleManager.getInstance().clear();
        });

        if (!config.isEnabled()) {
            LOGGER.info("OmniChat is disabled in config");
            return;
        }

        initializeTts();

        LOGGER.info("OmniChat initialized successfully");
    }

    private static void initializeTts() {
        try {
            engine = createEngine(config);
        } catch (Exception e) {
            LOGGER.error("Failed to initialize TTS engine with model '{}': {}", config.getModelPath(), e.getMessage());
            engine = tryFallbackModel();
            if (engine == null) {
                LOGGER.error("No working TTS model found. TTS will be disabled.");
                return;
            }
        }

        // Cache the default engine
        engineCache.put(config.getModelPath(), engine);

        worker = new TtsPlaybackWorker(engine, config);
        worker.start();

        if (chatHandler == null) {
            chatHandler = new ChatMessageHandler(config);
            chatHandler.register();
        }
    }

    private static ITtsEngine createEngine(OmnichatConfig cfg) {
        return createEngineForModel(cfg.getResolvedModelDir());
    }

    static ITtsEngine createEngineForModel(Path modelDir) {
        if (Files.exists(modelDir.resolve("dictionary.txt"))) {
            LOGGER.info("Detected GLaDOS-type model in '{}'", modelDir.getFileName());
            return GladosTtsEngine.create(modelDir);
        }
        return TtsEngine.create(modelDir);
    }

    /**
     * Returns the engine for the given model name, loading and caching it if needed.
     * Falls back to the default engine if the model is unavailable.
     */
    public static ITtsEngine getEngineForModel(String modelName) {
        if (modelName == null || modelName.equals(config.getModelPath())) {
            return engine;
        }

        return engineCache.computeIfAbsent(modelName, name -> {
            Path modelDir = OmnichatConfig.getModelsDir().resolve(name);
            if (!Files.isDirectory(modelDir)) {
                LOGGER.debug("Model '{}' not available locally, using default engine", name);
                return engine;
            }
            try {
                LOGGER.info("Loading engine for model '{}'", name);
                return createEngineForModel(modelDir);
            } catch (Exception e) {
                LOGGER.warn("Failed to load engine for model '{}', using default: {}", name, e.getMessage());
                return engine;
            }
        });
    }

    private static ITtsEngine tryFallbackModel() {
        String failedModel = config.getModelPath();
        List<String> models = OmnichatConfig.listAvailableModels();
        for (String model : models) {
            if (model.equals(failedModel)) continue;
            LOGGER.info("Trying fallback model: {}", model);
            config.setModelPath(model);
            config.save();
            try {
                return createEngine(config);
            } catch (Exception e) {
                LOGGER.warn("Fallback model '{}' also failed: {}", model, e.getMessage());
            }
        }
        config.setModelPath(failedModel);
        config.save();
        return null;
    }

    public static void reinitializeTts() {
        LOGGER.info("Reinitializing TTS engine...");

        if (worker != null) {
            worker.shutdown();
        }
        // Release all cached engines
        for (ITtsEngine cached : engineCache.values()) {
            cached.release();
        }
        engineCache.clear();
        engine = null;

        if (!config.isEnabled()) {
            worker = null;
            LOGGER.info("OmniChat TTS disabled");
            return;
        }

        initializeTts();
        LOGGER.info("TTS engine reinitialized");
    }

    private static void onChatMessageForBubble(Text message, SignedMessage signedMessage,
                                                   GameProfile sender, MessageType.Parameters params,
                                                   Instant receptionTimestamp) {
        if (!config.isShowChatBubbles() || sender == null) return;

        MinecraftClient client = MinecraftClient.getInstance();
        if (client.world == null || client.player == null) return;

        // Skip own messages
        if (sender.id().equals(client.player.getUuid())) return;

        // Check player exists in world
        if (client.world.getPlayerByUuid(sender.id()) == null) return;

        String text;
        if (signedMessage != null) {
            text = signedMessage.getContent().getString();
        } else {
            text = message.getString();
        }
        if (!text.isEmpty()) {
            ChatBubbleManager.getInstance().addBubble(sender.id(), text);
        }
    }

    public static OmnichatConfig getConfig() {
        return config;
    }

    public static TtsPlaybackWorker getWorker() {
        return worker;
    }
}
