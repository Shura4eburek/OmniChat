package org.mamoru.omnichat.client;

import net.fabricmc.api.ClientModInitializer;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientLifecycleEvents;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientTickEvents;
import net.fabricmc.fabric.api.client.networking.v1.ClientPlayConnectionEvents;
import net.minecraft.client.MinecraftClient;
import org.mamoru.omnichat.client.chat.ChatBubbleManager;
import org.mamoru.omnichat.client.chat.ChatBubbleRenderer;
import org.mamoru.omnichat.client.chat.ChatMessageHandler;
import org.mamoru.omnichat.client.chat.ChatPipeline;
import org.mamoru.omnichat.client.config.OmnichatConfig;
import org.mamoru.omnichat.client.network.ClientNetworkHandler;
import org.mamoru.omnichat.client.network.ModelDownloadManager;
import org.mamoru.omnichat.client.network.VoiceCache;
import org.mamoru.omnichat.client.screen.DownloadProgressHud;
import org.mamoru.omnichat.client.tts.SpatialAudioPlayer;
import org.mamoru.omnichat.client.tts.TtsPlaybackWorker;
import org.mamoru.omnichat.client.tts.TtsService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;


public class OmnichatClient implements ClientModInitializer {
    private static final Logger LOGGER = LoggerFactory.getLogger("OmniChat");

    private static OmnichatConfig config;
    private static TtsService tts;
    private static ChatMessageHandler chatHandler;

    @Override
    public void onInitializeClient() {
        LOGGER.info("OmniChat initializing...");

        config = OmnichatConfig.load();
        // Engine loading runs on a background thread; TTS becomes available once it is ready
        tts = new TtsService(config);

        OmnichatKeybinds.register();
        ClientTickEvents.END_CLIENT_TICK.register(client -> {
            SpatialAudioPlayer.tick();
            ChatBubbleManager.getInstance().tick();
        });
        ChatBubbleRenderer.register();

        // Register chat bubble listener (independent of TTS)
        ChatPipeline.register();

        // Register client network handlers and HUD
        ClientNetworkHandler.registerHandlers();
        DownloadProgressHud.register();
        // Runs on whatever thread saved the model; the worker evicts on its own thread
        ModelDownloadManager.getInstance().setOnDownloadComplete(modelName -> tts.onModelDownloaded(modelName));

        // Clean up on disconnect
        ClientPlayConnectionEvents.DISCONNECT.register((handler, client) -> {
            VoiceCache.getInstance().clear();
            ModelDownloadManager.getInstance().clear();
            ChatBubbleManager.getInstance().clear();
            tts.onDisconnect();
        });
        ClientLifecycleEvents.CLIENT_STOPPING.register(client -> tts.shutdown());

        // The handler checks config.isEnabled() itself, so it can be registered once up front
        chatHandler = new ChatMessageHandler(config);
        chatHandler.register();

        if (config.isEnabled()) {
            tts.start();
        } else {
            LOGGER.info("OmniChat is disabled in config");
        }

        LOGGER.info("OmniChat initialized successfully");
    }

    public static OmnichatConfig getConfig() {
        return config;
    }

    public static TtsService getTts() {
        return tts;
    }

    public static TtsPlaybackWorker getWorker() {
        return tts != null ? tts.getWorker() : null;
    }
}
