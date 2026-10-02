package org.mamoru.omnichat.client.chat;

import com.mojang.authlib.GameProfile;
import net.fabricmc.fabric.api.client.message.v1.ClientReceiveMessageEvents;
import net.minecraft.client.MinecraftClient;
import net.minecraft.client.world.ClientWorld;
import net.minecraft.entity.player.PlayerEntity;
import net.minecraft.network.message.MessageType;
import net.minecraft.network.message.SignedMessage;
import net.minecraft.registry.entry.RegistryEntry;
import net.minecraft.text.Text;
import org.mamoru.omnichat.client.HearingRange;
import org.mamoru.omnichat.client.OmnichatClient;
import org.mamoru.omnichat.client.config.OmnichatConfig;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.time.Instant;
import java.util.UUID;

/**
 * The single CHAT listener. Filters each player chat message once (type, text, own message,
 * sender lookup, hearing range) and hands the result to TTS and to chat bubbles, so both
 * always agree on what was heard.
 */
public final class ChatPipeline {
    private static final Logger LOGGER = LoggerFactory.getLogger("OmniChat");

    private static boolean registered;
    // Set once TTS is up; null while TTS is disabled or failed to initialize
    private static volatile ChatMessageHandler ttsHandler;

    enum Category { CHAT, WHISPER, EMOTE, TEAM }

    private ChatPipeline() {
    }

    public static void register() {
        if (registered) return;
        registered = true;
        ClientReceiveMessageEvents.CHAT.register(ChatPipeline::onChatMessage);
    }

    static void setTtsHandler(ChatMessageHandler handler) {
        ttsHandler = handler;
    }

    private static void onChatMessage(Text message, SignedMessage signedMessage, GameProfile sender,
                                      MessageType.Parameters params, Instant receptionTimestamp) {
        OmnichatConfig config = OmnichatClient.getConfig();
        ChatMessageHandler tts = ttsHandler;
        Category category = classify(params);

        boolean speak = tts != null && config.isEnabled() && shouldSpeak(config, category);
        boolean bubble = config.isShowChatBubbles() && shouldBubble(config, category);
        if (!speak && !bubble) {
            return;
        }

        String text = signedMessage != null ? signedMessage.getContent().getString() : message.getString();
        if (text.isEmpty()) {
            return;
        }

        MinecraftClient client = MinecraftClient.getInstance();
        boolean own = sender != null && client.player != null && sender.id().equals(client.player.getUuid());

        // Sender position decides both spatial playback and the bubble; null means "not positional"
        UUID senderUuid = null;
        if (sender != null) {
            ClientWorld world = client.world;
            if (world != null && client.player != null) {
                PlayerEntity senderEntity = world.getPlayerByUuid(sender.id());
                if (senderEntity == null) {
                    LOGGER.debug("Dropping {} message from {}: sender not loaded", category, sender.id());
                    return;
                }
                double distance = client.player.getEntityPos().distanceTo(senderEntity.getEntityPos());
                if (distance > HearingRange.BLOCKS) {
                    LOGGER.debug("Dropping {} message from {}: {} blocks away (range {})",
                            category, sender.id(), (int) distance, (int) HearingRange.BLOCKS);
                    return;
                }
                senderUuid = sender.id();
            }
        }

        if (speak && (!own || config.isReadOwnMessages())) {
            tts.speak(text, senderUuid);
        }
        if (bubble && senderUuid != null && !own) {
            ChatBubbleManager.getInstance().addBubble(senderUuid, text);
        }
    }

    static Category classify(MessageType.Parameters params) {
        if (params == null) return Category.CHAT;
        RegistryEntry<MessageType> type = params.type();
        if (type.matchesKey(MessageType.MSG_COMMAND_INCOMING) || type.matchesKey(MessageType.MSG_COMMAND_OUTGOING)) {
            return Category.WHISPER;
        }
        if (type.matchesKey(MessageType.EMOTE_COMMAND)) {
            return Category.EMOTE;
        }
        if (type.matchesKey(MessageType.TEAM_MSG_COMMAND_INCOMING) || type.matchesKey(MessageType.TEAM_MSG_COMMAND_OUTGOING)) {
            return Category.TEAM;
        }
        // Plain chat, /say and server-defined types
        return Category.CHAT;
    }

    private static boolean shouldSpeak(OmnichatConfig config, Category category) {
        return switch (category) {
            case CHAT -> true;
            case WHISPER -> config.isSpeakWhispers();
            case EMOTE -> config.isSpeakEmotes();
            case TEAM -> config.isSpeakTeamMessages();
        };
    }

    private static boolean shouldBubble(OmnichatConfig config, Category category) {
        return switch (category) {
            case CHAT -> true;
            case WHISPER -> config.isBubbleWhispers();
            case EMOTE -> config.isBubbleEmotes();
            case TEAM -> config.isBubbleTeamMessages();
        };
    }
}
