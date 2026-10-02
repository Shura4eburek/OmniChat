package org.mamoru.omnichat.client.network;

import net.fabricmc.fabric.api.client.networking.v1.ClientPlayNetworking;
import org.mamoru.omnichat.client.OmnichatClient;
import org.mamoru.omnichat.client.chat.ChatBubbleManager;
import org.mamoru.omnichat.client.config.OmnichatConfig;
import org.mamoru.omnichat.network.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.List;

public class ClientNetworkHandler {
    private static final Logger LOGGER = LoggerFactory.getLogger("OmniChat");

    public static void registerHandlers() {
        ClientPlayNetworking.registerGlobalReceiver(ModelListS2CPayload.ID, ClientNetworkHandler::onModelList);
        ClientPlayNetworking.registerGlobalReceiver(VoiceInfoS2CPayload.ID, ClientNetworkHandler::onVoiceInfo);
        ClientPlayNetworking.registerGlobalReceiver(VoiceMapS2CPayload.ID, ClientNetworkHandler::onVoiceMap);
        ClientPlayNetworking.registerGlobalReceiver(ModelFileChunkS2CPayload.ID, ClientNetworkHandler::onModelFileChunk);
        ClientPlayNetworking.registerGlobalReceiver(ModelDownloadStatusS2CPayload.ID,
                (payload, context) -> ModelDownloadManager.getInstance().onStatusReceived(payload));
        ClientPlayNetworking.registerGlobalReceiver(TypingIndicatorS2CPayload.ID, ClientNetworkHandler::onTypingIndicator);
        ClientPlayNetworking.registerGlobalReceiver(VoiceRemoveS2CPayload.ID, ClientNetworkHandler::onVoiceRemove);
        LOGGER.info("Client network handlers registered");
    }

    private static void onModelList(ModelListS2CPayload payload, ClientPlayNetworking.Context context) {
        VoiceCache.getInstance().setServerModels(payload.models());
        LOGGER.info("Received server model list: {}", payload.models());
        syncVoiceSelection(payload.models());
    }

    /** Tells the server which voice this client has configured, so others hear the right one. */
    private static void syncVoiceSelection(List<String> serverModels) {
        OmnichatConfig config = OmnichatClient.getConfig();
        String model = config.getModelPath();
        if (!serverModels.contains(model) || !ClientPlayNetworking.canSend(VoiceSelectionC2SPayload.ID)) {
            return;
        }
        ClientPlayNetworking.send(new VoiceSelectionC2SPayload(model, config.getSpeakerId()));
        LOGGER.info("Sent configured voice to server: {} (speaker {})", model, config.getSpeakerId());
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

    private static void onVoiceRemove(VoiceRemoveS2CPayload payload, ClientPlayNetworking.Context context) {
        VoiceCache.getInstance().removeVoice(payload.playerUuid());
        LOGGER.debug("Voice removed: {}", payload.playerUuid());
    }
}
