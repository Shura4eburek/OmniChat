package org.mamoru.omnichat.client.chat;

import com.mojang.authlib.GameProfile;
import net.fabricmc.fabric.api.client.message.v1.ClientReceiveMessageEvents;
import net.minecraft.client.MinecraftClient;
import net.minecraft.client.world.ClientWorld;
import net.minecraft.entity.player.PlayerEntity;
import net.minecraft.network.message.MessageType;
import net.minecraft.network.message.SignedMessage;
import net.minecraft.text.Text;
import org.mamoru.omnichat.client.OmnichatClient;
import org.mamoru.omnichat.client.config.OmnichatConfig;
import org.mamoru.omnichat.client.network.VoiceCache;
import org.mamoru.omnichat.client.tts.TtsPlaybackWorker;
import org.mamoru.omnichat.client.tts.TtsRequest;
import org.mamoru.omnichat.network.VoiceChoice;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.time.Instant;
import java.util.UUID;

public class ChatMessageHandler {
    private static final Logger LOGGER = LoggerFactory.getLogger("OmniChat");
    private static final double MAX_DISTANCE = 100.0;

    private final OmnichatConfig config;

    public ChatMessageHandler(OmnichatConfig config) {
        this.config = config;
    }

    public void register() {
        ClientReceiveMessageEvents.CHAT.register(this::onChatMessage);
        LOGGER.info("Chat message handler registered");
    }

    private void onChatMessage(Text message, SignedMessage signedMessage, GameProfile sender, MessageType.Parameters params, Instant receptionTimestamp) {
        if (!config.isEnabled()) {
            return;
        }

        TtsPlaybackWorker worker = OmnichatClient.getWorker();
        if (worker == null) {
            return;
        }

        if (!config.isReadOwnMessages() && sender != null) {
            MinecraftClient client = MinecraftClient.getInstance();
            if (client.player != null && sender.id().equals(client.player.getUuid())) {
                return;
            }
        }

        String text;
        if (signedMessage != null) {
            text = signedMessage.getContent().getString();
        } else {
            text = message.getString();
        }
        if (text.isEmpty()) {
            return;
        }

        UUID senderUuid = null;
        if (sender != null) {
            MinecraftClient client = MinecraftClient.getInstance();
            ClientWorld world = client.world;
            if (world != null && client.player != null) {
                PlayerEntity senderEntity = world.getPlayerByUuid(sender.id());
                if (senderEntity != null) {
                    double distance = client.player.getEntityPos().distanceTo(senderEntity.getEntityPos());
                    if (distance > MAX_DISTANCE) {
                        return;
                    }
                    senderUuid = sender.id();
                } else {
                    return;
                }
            }
        }

        // Lookup voice from server cache
        String modelName = null;
        int speakerId = -1;
        if (senderUuid != null) {
            VoiceChoice voice = VoiceCache.getInstance().getVoice(senderUuid);
            if (voice != null) {
                modelName = voice.modelName();
                speakerId = voice.speakerId();
            }
        }

        LOGGER.debug("Enqueuing TTS for message: {}", text);
        worker.enqueue(new TtsRequest(text, senderUuid, modelName, speakerId));
    }
}
