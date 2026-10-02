package org.mamoru.omnichat.client.chat;

import org.mamoru.omnichat.client.OmnichatClient;
import org.mamoru.omnichat.client.config.OmnichatConfig;
import org.mamoru.omnichat.client.network.VoiceCache;
import org.mamoru.omnichat.client.tts.TtsPlaybackWorker;
import org.mamoru.omnichat.client.tts.TtsRequest;
import org.mamoru.omnichat.network.VoiceChoice;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.UUID;

/**
 * TTS sink of the {@link ChatPipeline}: turns an already filtered chat message into a TTS
 * request with the sender's voice.
 */
public class ChatMessageHandler {
    private static final Logger LOGGER = LoggerFactory.getLogger("OmniChat");

    private final OmnichatConfig config;

    public ChatMessageHandler(OmnichatConfig config) {
        this.config = config;
    }

    public void register() {
        ChatPipeline.register();
        ChatPipeline.setTtsHandler(this);
        LOGGER.info("Chat message handler registered");
    }

    /**
     * @param senderUuid the in-range sender for spatial playback; the pipeline never passes null
     *                   (profileless messages are skipped), null would mean non-positional playback
     */
    void speak(String text, UUID senderUuid) {
        if (!config.isEnabled()) {
            return;
        }

        TtsPlaybackWorker worker = OmnichatClient.getWorker();
        if (worker == null) {
            return;
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

        LOGGER.debug("Enqueuing TTS for {} chars", text.length());
        worker.enqueue(new TtsRequest(text, senderUuid, modelName, speakerId));
    }
}
