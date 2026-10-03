package org.mamoru.omnichat.client.ui;

import org.junit.jupiter.api.Test;
import org.mamoru.omnichat.voice.VoiceMeta;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class VoiceCatalogTest {
    static VoiceMeta m(String model) {
        return VoiceMeta.bare(model);
    }

    @Test
    void emptySourcesGiveEmptyCatalog() {
        assertTrue(VoiceCatalog.build(List.of(), List.of(), Map.of(), Map.of()).isEmpty());
        assertNull(VoiceCatalog.selectOrFallback(List.of(), "x", "default"));
    }

    @Test
    void mergesStates() {
        List<VoiceCatalog.Entry> e = VoiceCatalog.build(
                List.of(m("denis"), m("ruslan"), m("dmitri"), m("irina")),
                List.of(m("denis"), m("mine")),
                Map.of("ruslan", 0.42f, "dmitri", -1f),
                Map.of("irina", "queue full"));
        assertEquals(List.of("denis", "ruslan", "dmitri", "irina", "mine"),
                e.stream().map(x -> x.meta().model()).toList());
        assertEquals(VoiceCatalog.State.INSTALLED, e.get(0).state());
        assertEquals(VoiceCatalog.State.DOWNLOADING, e.get(1).state());
        assertEquals(0.42f, e.get(1).progress());
        assertEquals(-1f, e.get(2).progress());
        assertEquals(VoiceCatalog.State.FAILED, e.get(3).state());
        assertEquals("queue full", e.get(3).failure());
        assertEquals(VoiceCatalog.State.INSTALLED, e.get(4).state());
        assertFalse(e.get(4).onServer());
    }

    @Test
    void downloadedModelBecomesInstalled() {
        var before = VoiceCatalog.build(List.of(m("ruslan")), List.of(), Map.of("ruslan", 0.9f), Map.of());
        var after = VoiceCatalog.build(List.of(m("ruslan")), List.of(m("ruslan")), Map.of(), Map.of());
        assertEquals(VoiceCatalog.State.DOWNLOADING, before.get(0).state());
        assertEquals(VoiceCatalog.State.INSTALLED, after.get(0).state());
    }

    @Test
    void localMetadataWinsForInstalledVoices() {
        VoiceMeta server = new VoiceMeta("denis", "Server Denis", "", "", "", "", 1, new byte[0]);
        VoiceMeta local = new VoiceMeta("denis", "Local Denis", "", "", "", "", 1, new byte[0]);
        assertEquals("Local Denis", VoiceCatalog.build(List.of(server), List.of(local), Map.of(), Map.of())
                .get(0).meta().name());
    }

    @Test
    void signatureIgnoresPortraitArrayIdentity() {
        VoiceMeta a = new VoiceMeta("denis", "D", "", "", "", "", 1, new byte[]{1, 2});
        VoiceMeta b = new VoiceMeta("denis", "D", "", "", "", "", 1, new byte[]{1, 2});
        var x = VoiceCatalog.build(List.of(a), List.of(), Map.of(), Map.of());
        var y = VoiceCatalog.build(List.of(b), List.of(), Map.of(), Map.of());
        assertNotEquals(x, y); // record equality compares arrays by identity
        assertEquals(VoiceCatalog.signature(x), VoiceCatalog.signature(y));
        var z = VoiceCatalog.build(List.of(b), List.of(), Map.of("denis", 0.5f), Map.of());
        assertNotEquals(VoiceCatalog.signature(x), VoiceCatalog.signature(z));
    }

    @Test
    void signatureIgnoresDownloadProgress() {
        // Progress is drawn live; a rebuild per percent would drop focus and slider drags
        VoiceMeta a = new VoiceMeta("denis", "D", "", "", "", "", 1, new byte[0]);
        var x = VoiceCatalog.build(List.of(a), List.of(), Map.of("denis", 0.1f), Map.of());
        var y = VoiceCatalog.build(List.of(a), List.of(), Map.of("denis", 0.9f), Map.of());
        assertEquals(VoiceCatalog.signature(x), VoiceCatalog.signature(y));
    }

    @Test
    void selectionFallsBackWhenVoiceRemoved() {
        var e = VoiceCatalog.build(List.of(m("denis"), m("irina")), List.of(), Map.of(), Map.of());
        assertEquals("irina", VoiceCatalog.selectOrFallback(e, "irina", "denis"));
        assertEquals("denis", VoiceCatalog.selectOrFallback(e, "gone", "denis"));
        assertEquals("denis", VoiceCatalog.selectOrFallback(e, "gone", "also-gone"));
    }
}
