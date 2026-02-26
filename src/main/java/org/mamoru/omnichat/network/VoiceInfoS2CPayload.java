package org.mamoru.omnichat.network;

import net.minecraft.network.RegistryByteBuf;
import net.minecraft.network.codec.PacketCodec;
import net.minecraft.network.codec.PacketCodecs;
import net.minecraft.network.packet.CustomPayload;
import net.minecraft.util.Identifier;
import net.minecraft.util.Uuids;

import java.util.UUID;

public record VoiceInfoS2CPayload(UUID playerUuid, String modelName, int speakerId) implements CustomPayload {
    public static final Id<VoiceInfoS2CPayload> ID =
            new Id<>(Identifier.of("omnichat", "voice_info"));

    public static final PacketCodec<RegistryByteBuf, VoiceInfoS2CPayload> CODEC =
            PacketCodec.tuple(
                    Uuids.PACKET_CODEC, VoiceInfoS2CPayload::playerUuid,
                    PacketCodecs.STRING, VoiceInfoS2CPayload::modelName,
                    PacketCodecs.VAR_INT, VoiceInfoS2CPayload::speakerId,
                    VoiceInfoS2CPayload::new
            );

    @Override
    public Id<? extends CustomPayload> getId() {
        return ID;
    }
}
