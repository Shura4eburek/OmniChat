package org.mamoru.omnichat.network;

import net.minecraft.network.PacketByteBuf;
import net.minecraft.network.RegistryByteBuf;
import net.minecraft.network.codec.PacketCodec;
import net.minecraft.network.packet.CustomPayload;
import net.minecraft.util.Identifier;

import java.util.HashMap;
import java.util.Map;
import java.util.UUID;

public record VoiceMapS2CPayload(Map<UUID, VoiceChoice> voices) implements CustomPayload {
    public static final Id<VoiceMapS2CPayload> ID =
            new Id<>(Identifier.of("omnichat", "voice_map"));

    public static final PacketCodec<RegistryByteBuf, VoiceMapS2CPayload> CODEC =
            new PacketCodec<>() {
                @Override
                public VoiceMapS2CPayload decode(RegistryByteBuf buf) {
                    int size = buf.readVarInt();
                    Map<UUID, VoiceChoice> map = new HashMap<>(size);
                    for (int i = 0; i < size; i++) {
                        UUID uuid = buf.readUuid();
                        VoiceChoice choice = VoiceChoice.CODEC.decode(buf);
                        map.put(uuid, choice);
                    }
                    return new VoiceMapS2CPayload(map);
                }

                @Override
                public void encode(RegistryByteBuf buf, VoiceMapS2CPayload payload) {
                    buf.writeVarInt(payload.voices.size());
                    payload.voices.forEach((uuid, choice) -> {
                        buf.writeUuid(uuid);
                        VoiceChoice.CODEC.encode(buf, choice);
                    });
                }
            };

    @Override
    public Id<? extends CustomPayload> getId() {
        return ID;
    }
}
