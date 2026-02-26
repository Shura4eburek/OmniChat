package org.mamoru.omnichat.network;

import net.minecraft.network.RegistryByteBuf;
import net.minecraft.network.codec.PacketCodec;
import net.minecraft.network.codec.PacketCodecs;
import net.minecraft.network.packet.CustomPayload;
import net.minecraft.util.Identifier;

public record VoiceSelectionC2SPayload(String modelName, int speakerId) implements CustomPayload {
    public static final Id<VoiceSelectionC2SPayload> ID =
            new Id<>(Identifier.of("omnichat", "voice_selection"));

    public static final PacketCodec<RegistryByteBuf, VoiceSelectionC2SPayload> CODEC =
            PacketCodec.tuple(
                    PacketCodecs.STRING, VoiceSelectionC2SPayload::modelName,
                    PacketCodecs.VAR_INT, VoiceSelectionC2SPayload::speakerId,
                    VoiceSelectionC2SPayload::new
            );

    @Override
    public Id<? extends CustomPayload> getId() {
        return ID;
    }
}
