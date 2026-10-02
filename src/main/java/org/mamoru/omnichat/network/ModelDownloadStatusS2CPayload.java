package org.mamoru.omnichat.network;

import net.minecraft.network.RegistryByteBuf;
import net.minecraft.network.codec.PacketCodec;
import net.minecraft.network.packet.CustomPayload;
import net.minecraft.util.Identifier;

/**
 * Server-side state of a model download request that isn't carried by the chunks themselves:
 * QUEUED acknowledges the request (it may wait behind other transfers), FAILED means the
 * server refused or aborted it and will send nothing more for it.
 */
public record ModelDownloadStatusS2CPayload(String modelName, Status status, String reason) implements CustomPayload {
    public enum Status { QUEUED, FAILED }

    public static final Id<ModelDownloadStatusS2CPayload> ID =
            new Id<>(Identifier.of("omnichat", "model_download_status"));

    public static final PacketCodec<RegistryByteBuf, ModelDownloadStatusS2CPayload> CODEC =
            new PacketCodec<>() {
                @Override
                public ModelDownloadStatusS2CPayload decode(RegistryByteBuf buf) {
                    String modelName = buf.readString();
                    int ordinal = buf.readVarInt();
                    Status[] values = Status.values();
                    // unknown status from a newer server: treat as failure rather than hang
                    Status status = ordinal >= 0 && ordinal < values.length ? values[ordinal] : Status.FAILED;
                    String reason = buf.readString();
                    return new ModelDownloadStatusS2CPayload(modelName, status, reason);
                }

                @Override
                public void encode(RegistryByteBuf buf, ModelDownloadStatusS2CPayload payload) {
                    buf.writeString(payload.modelName);
                    buf.writeVarInt(payload.status.ordinal());
                    buf.writeString(payload.reason);
                }
            };

    public static ModelDownloadStatusS2CPayload queued(String modelName) {
        return new ModelDownloadStatusS2CPayload(modelName, Status.QUEUED, "");
    }

    public static ModelDownloadStatusS2CPayload failed(String modelName, String reason) {
        return new ModelDownloadStatusS2CPayload(modelName, Status.FAILED, reason);
    }

    @Override
    public Id<? extends CustomPayload> getId() {
        return ID;
    }
}
