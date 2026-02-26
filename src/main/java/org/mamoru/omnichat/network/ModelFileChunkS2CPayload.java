package org.mamoru.omnichat.network;

import net.minecraft.network.RegistryByteBuf;
import net.minecraft.network.codec.PacketCodec;
import net.minecraft.network.packet.CustomPayload;
import net.minecraft.util.Identifier;

public record ModelFileChunkS2CPayload(
        String modelName,
        String fileName,
        int offset,
        byte[] data,
        boolean lastChunk,
        boolean lastFile,
        long totalBytes
) implements CustomPayload {
    public static final Id<ModelFileChunkS2CPayload> ID =
            new Id<>(Identifier.of("omnichat", "model_file_chunk"));

    public static final PacketCodec<RegistryByteBuf, ModelFileChunkS2CPayload> CODEC =
            new PacketCodec<>() {
                @Override
                public ModelFileChunkS2CPayload decode(RegistryByteBuf buf) {
                    String modelName = buf.readString();
                    String fileName = buf.readString();
                    int offset = buf.readVarInt();
                    byte[] data = buf.readByteArray();
                    boolean lastChunk = buf.readBoolean();
                    boolean lastFile = buf.readBoolean();
                    long totalBytes = buf.readLong();
                    return new ModelFileChunkS2CPayload(modelName, fileName, offset, data, lastChunk, lastFile, totalBytes);
                }

                @Override
                public void encode(RegistryByteBuf buf, ModelFileChunkS2CPayload payload) {
                    buf.writeString(payload.modelName);
                    buf.writeString(payload.fileName);
                    buf.writeVarInt(payload.offset);
                    buf.writeByteArray(payload.data);
                    buf.writeBoolean(payload.lastChunk);
                    buf.writeBoolean(payload.lastFile);
                    buf.writeLong(payload.totalBytes);
                }
            };

    @Override
    public Id<? extends CustomPayload> getId() {
        return ID;
    }
}
