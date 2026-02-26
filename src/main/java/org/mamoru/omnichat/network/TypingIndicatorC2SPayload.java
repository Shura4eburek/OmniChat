package org.mamoru.omnichat.network;

import net.minecraft.network.RegistryByteBuf;
import net.minecraft.network.codec.PacketCodec;
import net.minecraft.network.codec.PacketCodecs;
import net.minecraft.network.packet.CustomPayload;
import net.minecraft.util.Identifier;

public record TypingIndicatorC2SPayload(boolean typing) implements CustomPayload {
    public static final Id<TypingIndicatorC2SPayload> ID =
            new Id<>(Identifier.of("omnichat", "typing_indicator_c2s"));

    public static final PacketCodec<RegistryByteBuf, TypingIndicatorC2SPayload> CODEC =
            PacketCodec.tuple(
                    PacketCodecs.BOOLEAN, TypingIndicatorC2SPayload::typing,
                    TypingIndicatorC2SPayload::new
            );

    @Override
    public Id<? extends CustomPayload> getId() {
        return ID;
    }
}
