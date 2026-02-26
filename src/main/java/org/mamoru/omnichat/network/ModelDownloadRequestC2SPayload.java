package org.mamoru.omnichat.network;

import net.minecraft.network.RegistryByteBuf;
import net.minecraft.network.codec.PacketCodec;
import net.minecraft.network.codec.PacketCodecs;
import net.minecraft.network.packet.CustomPayload;
import net.minecraft.util.Identifier;

public record ModelDownloadRequestC2SPayload(String modelName) implements CustomPayload {
    public static final Id<ModelDownloadRequestC2SPayload> ID =
            new Id<>(Identifier.of("omnichat", "model_download_request"));

    public static final PacketCodec<RegistryByteBuf, ModelDownloadRequestC2SPayload> CODEC =
            PacketCodec.tuple(
                    PacketCodecs.STRING, ModelDownloadRequestC2SPayload::modelName,
                    ModelDownloadRequestC2SPayload::new
            );

    @Override
    public Id<? extends CustomPayload> getId() {
        return ID;
    }
}
