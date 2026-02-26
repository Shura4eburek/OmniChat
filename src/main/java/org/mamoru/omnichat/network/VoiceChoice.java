package org.mamoru.omnichat.network;

import net.minecraft.network.codec.PacketCodec;
import net.minecraft.network.codec.PacketCodecs;
import net.minecraft.network.PacketByteBuf;

public record VoiceChoice(String modelName, int speakerId) {
    public static final PacketCodec<PacketByteBuf, VoiceChoice> CODEC = PacketCodec.tuple(
            PacketCodecs.STRING, VoiceChoice::modelName,
            PacketCodecs.VAR_INT, VoiceChoice::speakerId,
            VoiceChoice::new
    );
}
