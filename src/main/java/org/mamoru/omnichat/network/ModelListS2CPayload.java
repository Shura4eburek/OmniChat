package org.mamoru.omnichat.network;

import net.minecraft.network.RegistryByteBuf;
import net.minecraft.network.codec.PacketCodec;
import net.minecraft.network.codec.PacketCodecs;
import net.minecraft.network.packet.CustomPayload;
import net.minecraft.util.Identifier;

import java.util.List;

public record ModelListS2CPayload(List<String> models) implements CustomPayload {
    public static final Id<ModelListS2CPayload> ID =
            new Id<>(Identifier.of("omnichat", "model_list"));

    public static final PacketCodec<RegistryByteBuf, ModelListS2CPayload> CODEC =
            PacketCodec.tuple(
                    PacketCodecs.STRING.collect(PacketCodecs.toList()),
                    ModelListS2CPayload::models,
                    ModelListS2CPayload::new
            );

    @Override
    public Id<? extends CustomPayload> getId() {
        return ID;
    }
}
