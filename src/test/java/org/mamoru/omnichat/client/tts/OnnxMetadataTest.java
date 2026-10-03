package org.mamoru.omnichat.client.tts;

import org.junit.jupiter.api.Test;

import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class OnnxMetadataTest {
    private static void varint(ByteArrayOutputStream out, long v) {
        while ((v & ~0x7FL) != 0) {
            out.write((int) ((v & 0x7F) | 0x80));
            v >>>= 7;
        }
        out.write((int) v);
    }

    private static void field(ByteArrayOutputStream out, int number, byte[] payload) {
        varint(out, ((long) number << 3) | 2);
        varint(out, payload.length);
        out.writeBytes(payload);
    }

    private static byte[] entry(String key, String value) {
        ByteArrayOutputStream e = new ByteArrayOutputStream();
        field(e, 1, key.getBytes(StandardCharsets.UTF_8));
        field(e, 2, value.getBytes(StandardCharsets.UTF_8));
        return e.toByteArray();
    }

    /** ModelProto with ir_version (varint field 1), a large "graph" (field 7) and metadata_props (field 14). */
    private static byte[] model(String... kv) {
        ByteArrayOutputStream m = new ByteArrayOutputStream();
        varint(m, (1 << 3)); // ir_version, wire type 0
        varint(m, 8);
        field(m, 7, new byte[70_000]); // stand-in for the graph: must be skipped, not scanned
        for (int i = 0; i < kv.length; i += 2) field(m, 14, entry(kv[i], kv[i + 1]));
        return m.toByteArray();
    }

    @Test
    void readsMetadataProps() {
        Map<String, String> meta = OnnxMetadata.parse(model("n_speakers", "1", "comment", "piper", "voice", "ru"));
        assertEquals(Map.of("n_speakers", "1", "comment", "piper", "voice", "ru"), meta);
    }

    @Test
    void ignoresKeysInsideOtherFields() {
        // "voice" bytes inside the graph payload must not count as metadata
        ByteArrayOutputStream m = new ByteArrayOutputStream();
        field(m, 7, entry("voice", "ru"));
        field(m, 14, entry("n_speakers", "1"));
        assertEquals(Map.of("n_speakers", "1"), OnnxMetadata.parse(m.toByteArray()));
    }

    @Test
    void truncatedOrGarbageGivesWhatWasRead() {
        byte[] full = model("n_speakers", "1", "voice", "ru");
        byte[] cut = java.util.Arrays.copyOf(full, full.length - 3);
        assertEquals(Map.of("n_speakers", "1"), OnnxMetadata.parse(cut));
        assertTrue(OnnxMetadata.parse(new byte[]{(byte) 0xFF, (byte) 0xFF, 0x01}).isEmpty());
        assertTrue(OnnxMetadata.parse(new byte[0]).isEmpty());
    }

    @Test
    void piperWithoutVoiceIsRejected() {
        assertEquals("missing 'voice' metadata (espeak voice)",
                OnnxMetadata.vitsProblem(Map.of("n_speakers", "1", "comment", "piper", "language", "ru")));
        assertNull(OnnxMetadata.vitsProblem(Map.of("n_speakers", "1", "comment", "piper", "voice", "ru")));
        assertEquals("missing 'n_speakers' metadata", OnnxMetadata.vitsProblem(Map.of("comment", "piper", "voice", "ru")));
        assertNull(OnnxMetadata.vitsProblem(Map.of("n_speakers", "4", "comment", "coqui")));
    }
}
