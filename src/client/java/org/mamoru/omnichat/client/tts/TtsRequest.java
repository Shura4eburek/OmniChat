package org.mamoru.omnichat.client.tts;

import org.jetbrains.annotations.Nullable;

import java.util.UUID;

public record TtsRequest(String text, @Nullable UUID senderUuid, @Nullable String modelName, int speakerId) {
}
