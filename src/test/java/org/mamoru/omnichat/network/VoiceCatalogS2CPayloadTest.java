package org.mamoru.omnichat.network;

import io.netty.buffer.Unpooled;
import net.minecraft.network.RegistryByteBuf;
import net.minecraft.registry.DynamicRegistryManager;
import org.junit.jupiter.api.Test;
import org.mamoru.omnichat.voice.VoiceMeta;

import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class VoiceCatalogS2CPayloadTest {
    private static VoiceCatalogS2CPayload roundTrip(VoiceCatalogS2CPayload p) {
        RegistryByteBuf buf = new RegistryByteBuf(Unpooled.buffer(), DynamicRegistryManager.EMPTY);
        VoiceCatalogS2CPayload.CODEC.encode(buf, p);
        return VoiceCatalogS2CPayload.CODEC.decode(buf);
    }

    @Test
    void roundTripsAllFields() {
        VoiceMeta m = new VoiceMeta("denis", "Денис", "Спокойный", "ru", "male", "Привет", 81_146_850L, new byte[]{1, 2, 3});
        VoiceMeta out = roundTrip(new VoiceCatalogS2CPayload(List.of(m, VoiceMeta.bare("irina")))).voices().get(0);
        assertEquals("denis", out.model());
        assertEquals("Денис", out.name());
        assertEquals("Спокойный", out.description());
        assertEquals("ru", out.language());
        assertEquals("male", out.gender());
        assertEquals("Привет", out.sample());
        assertEquals(81_146_850L, out.sizeBytes());
        assertArrayEquals(new byte[]{1, 2, 3}, out.portrait());
    }

    @Test
    void capsEntriesOnEncode() {
        List<VoiceMeta> many = new ArrayList<>();
        for (int i = 0; i < 100; i++) many.add(VoiceMeta.bare("m" + i));
        assertEquals(VoiceCatalogS2CPayload.MAX_ENTRIES, roundTrip(new VoiceCatalogS2CPayload(many)).voices().size());
    }
}
