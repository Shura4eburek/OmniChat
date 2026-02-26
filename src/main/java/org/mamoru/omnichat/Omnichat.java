package org.mamoru.omnichat;

import net.fabricmc.api.ModInitializer;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerLifecycleEvents;
import net.fabricmc.fabric.api.networking.v1.PayloadTypeRegistry;
import net.fabricmc.fabric.api.networking.v1.ServerPlayConnectionEvents;
import org.mamoru.omnichat.network.*;
import org.mamoru.omnichat.server.ModelFileServer;
import org.mamoru.omnichat.server.ServerNetworkHandler;
import org.mamoru.omnichat.server.VoiceRegistry;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.nio.file.Path;

public class Omnichat implements ModInitializer {
    private static final Logger LOGGER = LoggerFactory.getLogger("OmniChat");

    private static VoiceRegistry voiceRegistry;
    private static ServerNetworkHandler networkHandler;

    @Override
    public void onInitialize() {
        // Register payload types
        // S2C
        PayloadTypeRegistry.playS2C().register(ModelListS2CPayload.ID, ModelListS2CPayload.CODEC);
        PayloadTypeRegistry.playS2C().register(VoiceInfoS2CPayload.ID, VoiceInfoS2CPayload.CODEC);
        PayloadTypeRegistry.playS2C().register(VoiceMapS2CPayload.ID, VoiceMapS2CPayload.CODEC);
        PayloadTypeRegistry.playS2C().register(ModelFileChunkS2CPayload.ID, ModelFileChunkS2CPayload.CODEC);
        PayloadTypeRegistry.playS2C().register(TypingIndicatorS2CPayload.ID, TypingIndicatorS2CPayload.CODEC);
        // C2S
        PayloadTypeRegistry.playC2S().register(VoiceSelectionC2SPayload.ID, VoiceSelectionC2SPayload.CODEC);
        PayloadTypeRegistry.playC2S().register(ModelDownloadRequestC2SPayload.ID, ModelDownloadRequestC2SPayload.CODEC);
        PayloadTypeRegistry.playC2S().register(TypingIndicatorC2SPayload.ID, TypingIndicatorC2SPayload.CODEC);

        ServerLifecycleEvents.SERVER_STARTED.register(server -> {
            Path configDir = server.getRunDirectory().resolve("config").resolve("omnichat");
            voiceRegistry = new VoiceRegistry(configDir);
            ModelFileServer fileServer = new ModelFileServer(voiceRegistry.getModelsDir());
            networkHandler = new ServerNetworkHandler(voiceRegistry, fileServer, server);
            networkHandler.registerHandlers();
            LOGGER.info("OmniChat server initialized with {} models", voiceRegistry.getAvailableModels().size());
        });

        ServerPlayConnectionEvents.JOIN.register((handler, sender, server) -> {
            if (networkHandler != null) {
                networkHandler.onPlayerJoin(handler.getPlayer());
            }
        });

        LOGGER.info("OmniChat mod loaded");
    }

    public static VoiceRegistry getVoiceRegistry() {
        return voiceRegistry;
    }
}
