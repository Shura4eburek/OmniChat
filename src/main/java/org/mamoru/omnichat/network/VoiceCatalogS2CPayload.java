package org.mamoru.omnichat.network;

import net.minecraft.network.RegistryByteBuf;
import net.minecraft.network.codec.PacketCodec;
import net.minecraft.network.packet.CustomPayload;
import net.minecraft.util.Identifier;
import org.mamoru.omnichat.voice.VoiceMeta;
import org.mamoru.omnichat.voice.VoiceMetaReader;

import java.util.ArrayList;
import java.util.List;

/** Server → client: every voice the server offers, with display metadata. Replaces the bare model list. */
public record VoiceCatalogS2CPayload(List<VoiceMeta> voices) implements CustomPayload {
    public static final Id<VoiceCatalogS2CPayload> ID = new Id<>(Identifier.of("omnichat", "voice_catalog"));
    public static final int MAX_ENTRIES = 64;

    public static final PacketCodec<RegistryByteBuf, VoiceCatalogS2CPayload> CODEC = PacketCodec.of(
            (payload, buf) -> {
                List<VoiceMeta> voices = payload.voices();
                int n = Math.min(voices.size(), MAX_ENTRIES);
                buf.writeVarInt(n);
                for (int i = 0; i < n; i++) {
                    VoiceMeta m = voices.get(i);
                    buf.writeString(m.model());
                    buf.writeString(m.name());
                    buf.writeString(m.description());
                    buf.writeString(m.language());
                    buf.writeString(m.gender());
                    buf.writeString(m.sample());
                    buf.writeVarLong(m.sizeBytes());
                    buf.writeByteArray(m.portrait());
                }
            },
            buf -> {
                int n = Math.min(buf.readVarInt(), MAX_ENTRIES);
                List<VoiceMeta> voices = new ArrayList<>(n);
                for (int i = 0; i < n; i++) {
                    voices.add(new VoiceMeta(buf.readString(), buf.readString(VoiceMetaReader.MAX_NAME * 4),
                            buf.readString(VoiceMetaReader.MAX_DESCRIPTION * 4), buf.readString(64),
                            buf.readString(64), buf.readString(VoiceMetaReader.MAX_SAMPLE * 4),
                            buf.readVarLong(), buf.readByteArray(VoiceMetaReader.MAX_PORTRAIT_BYTES)));
                }
                return new VoiceCatalogS2CPayload(List.copyOf(voices));
            });

    @Override
    public Id<? extends CustomPayload> getId() {
        return ID;
    }
}
