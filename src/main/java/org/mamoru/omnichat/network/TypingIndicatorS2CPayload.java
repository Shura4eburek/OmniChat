package org.mamoru.omnichat.network;

import net.minecraft.network.RegistryByteBuf;
import net.minecraft.network.codec.PacketCodec;
import net.minecraft.network.codec.PacketCodecs;
import net.minecraft.network.packet.CustomPayload;
import net.minecraft.util.Identifier;
import net.minecraft.util.Uuids;

import java.util.UUID;

public record TypingIndicatorS2CPayload(UUID playerUuid, boolean typing) implements CustomPayload {
    public static final Id<TypingIndicatorS2CPayload> ID =
            new Id<>(Identifier.of("omnichat", "typing_indicator_s2c"));

    public static final PacketCodec<RegistryByteBuf, TypingIndicatorS2CPayload> CODEC =
            PacketCodec.tuple(
                    Uuids.PACKET_CODEC, TypingIndicatorS2CPayload::playerUuid,
                    PacketCodecs.BOOLEAN, TypingIndicatorS2CPayload::typing,
                    TypingIndicatorS2CPayload::new
            );

    @Override
    public Id<? extends CustomPayload> getId() {
        return ID;
    }
}
