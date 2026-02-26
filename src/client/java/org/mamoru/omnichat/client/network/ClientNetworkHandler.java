package org.mamoru.omnichat.client.network;

import net.fabricmc.fabric.api.client.networking.v1.ClientPlayNetworking;
import org.mamoru.omnichat.client.chat.ChatBubbleManager;
import org.mamoru.omnichat.network.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class ClientNetworkHandler {
    private static final Logger LOGGER = LoggerFactory.getLogger("OmniChat");

    public static void registerHandlers() {
        ClientPlayNetworking.registerGlobalReceiver(ModelListS2CPayload.ID, ClientNetworkHandler::onModelList);
        ClientPlayNetworking.registerGlobalReceiver(VoiceInfoS2CPayload.ID, ClientNetworkHandler::onVoiceInfo);
        ClientPlayNetworking.registerGlobalReceiver(VoiceMapS2CPayload.ID, ClientNetworkHandler::onVoiceMap);
        ClientPlayNetworking.registerGlobalReceiver(ModelFileChunkS2CPayload.ID, ClientNetworkHandler::onModelFileChunk);
        ClientPlayNetworking.registerGlobalReceiver(TypingIndicatorS2CPayload.ID, ClientNetworkHandler::onTypingIndicator);
        LOGGER.info("Client network handlers registered");
    }

    private static void onModelList(ModelListS2CPayload payload, ClientPlayNetworking.Context context) {
        VoiceCache.getInstance().setServerModels(payload.models());
        LOGGER.info("Received server model list: {}", payload.models());
    }

    private static void onVoiceInfo(VoiceInfoS2CPayload payload, ClientPlayNetworking.Context context) {
        VoiceCache.getInstance().setVoice(payload.playerUuid(),
                new VoiceChoice(payload.modelName(), payload.speakerId()));
        LOGGER.debug("Voice update: {} -> {} (speaker {})",
                payload.playerUuid(), payload.modelName(), payload.speakerId());
    }

    private static void onVoiceMap(VoiceMapS2CPayload payload, ClientPlayNetworking.Context context) {
        VoiceCache.getInstance().setVoiceMap(payload.voices());
        LOGGER.info("Received voice map with {} entries", payload.voices().size());
    }

    private static void onModelFileChunk(ModelFileChunkS2CPayload payload, ClientPlayNetworking.Context context) {
        ModelDownloadManager.getInstance().onChunkReceived(payload);
    }

    private static void onTypingIndicator(TypingIndicatorS2CPayload payload, ClientPlayNetworking.Context context) {
        ChatBubbleManager.getInstance().setTyping(payload.playerUuid(), payload.typing());
    }
}
