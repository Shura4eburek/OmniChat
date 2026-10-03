package org.mamoru.omnichat.network;

import net.minecraft.network.RegistryByteBuf;
import net.minecraft.network.codec.PacketCodec;
import net.minecraft.network.codec.PacketCodecs;
import net.minecraft.network.packet.CustomPayload;
import net.minecraft.util.Identifier;

/**
 * Handshake, registered in both directions. The client sends its version on join; the server
 * answers with its own and only starts sending OmniChat payloads when the two match.
 * Never change this codec: it is how mismatched versions recognise each other.
 * 2: VoiceCatalogS2CPayload replaces ModelListS2CPayload.
 */
public record ProtocolVersionPayload(int version) implements CustomPayload {
    /** Bump whenever any OmniChat payload codec or the handshake flow changes. */
    public static final int PROTOCOL_VERSION = 2;

    public static final Id<ProtocolVersionPayload> ID =
            new Id<>(Identifier.of("omnichat", "protocol_version"));

    public static final PacketCodec<RegistryByteBuf, ProtocolVersionPayload> CODEC =
            PacketCodec.tuple(
                    PacketCodecs.VAR_INT, ProtocolVersionPayload::version,
                    ProtocolVersionPayload::new
            );

    @Override
    public Id<? extends CustomPayload> getId() {
        return ID;
    }
}
