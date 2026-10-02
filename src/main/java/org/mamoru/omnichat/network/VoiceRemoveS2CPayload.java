package org.mamoru.omnichat.network;

import net.minecraft.network.RegistryByteBuf;
import net.minecraft.network.codec.PacketCodec;
import net.minecraft.network.packet.CustomPayload;
import net.minecraft.util.Identifier;
import net.minecraft.util.Uuids;

import java.util.UUID;

public record VoiceRemoveS2CPayload(UUID playerUuid) implements CustomPayload {
    public static final Id<VoiceRemoveS2CPayload> ID =
            new Id<>(Identifier.of("omnichat", "voice_remove"));

    public static final PacketCodec<RegistryByteBuf, VoiceRemoveS2CPayload> CODEC =
            PacketCodec.tuple(
                    Uuids.PACKET_CODEC, VoiceRemoveS2CPayload::playerUuid,
                    VoiceRemoveS2CPayload::new
            );

    @Override
    public Id<? extends CustomPayload> getId() {
        return ID;
    }
}
