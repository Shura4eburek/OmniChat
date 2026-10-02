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

public class OmnichatClient implements ClientModInitializer {
    private static final Logger LOGGER = LoggerFactory.getLogger("OmniChat");

    private static OmnichatConfig config;
    // Engines are owned (cached and released) by the worker of each generation
    private static volatile TtsPlaybackWorker worker;
    private static ChatMessageHandler chatHandler;

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
        // Runs on whatever thread saved the model; the worker evicts on its own thread
        ModelDownloadManager.getInstance().setOnDownloadComplete(modelName -> {
            TtsPlaybackWorker current = worker;
            if (current != null) {
                current.evictModel(modelName);
            }
        });

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
        ITtsEngine engine;
        try {
            engine = createEngine(config);
        } catch (Exception | LinkageError e) {
            LOGGER.error("Failed to initialize TTS engine with model '{}': {}", config.getModelPath(), e.getMessage());
            engine = tryFallbackModel();
            if (engine == null) {
                LOGGER.error("No working TTS model found. TTS will be disabled.");
                return;
            }
        }

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
     * Loads a fresh engine for the given model name, or returns null if the model is
     * unavailable or fails to load (the caller then uses its default engine, uncached).
     */
    public static ITtsEngine loadEngineForModel(String name) {
        Path modelDir = OmnichatConfig.resolveModelDir(name);
        if (modelDir == null || !Files.isDirectory(modelDir)) {
            LOGGER.debug("Model '{}' not available locally, using default engine", name);
            return null;
        }
        try {
            LOGGER.info("Loading engine for model '{}'", name);
            return createEngineForModel(modelDir);
        } catch (Exception | LinkageError e) {
            LOGGER.warn("Failed to load engine for model '{}', using default: {}", name, e.toString());
            return null;
        }
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
            } catch (Exception | LinkageError e) {
                LOGGER.warn("Fallback model '{}' also failed: {}", model, e.getMessage());
            }
        }
        config.setModelPath(failedModel);
        config.save();
        return null;
    }

    public static void reinitializeTts() {
        LOGGER.info("Reinitializing TTS engine...");

        // The old worker releases its own engines once its thread leaves the loop
        TtsPlaybackWorker old = worker;
        worker = null;
        if (old != null) {
            old.shutdown();
        }

        if (!config.isEnabled()) {
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
