package org.mamoru.omnichat.client;

import com.mojang.authlib.GameProfile;
import net.fabricmc.api.ClientModInitializer;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientLifecycleEvents;
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
import org.mamoru.omnichat.client.tts.SpatialAudioPlayer;
import org.mamoru.omnichat.client.tts.TtsPlaybackWorker;
import org.mamoru.omnichat.client.tts.TtsService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.time.Instant;

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
        ClientReceiveMessageEvents.CHAT.register(OmnichatClient::onChatMessageForBubble);

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

    public static TtsService getTts() {
        return tts;
    }

    public static TtsPlaybackWorker getWorker() {
        return tts != null ? tts.getWorker() : null;
    }
}
