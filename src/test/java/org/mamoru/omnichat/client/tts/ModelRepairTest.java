package org.mamoru.omnichat.client.tts;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class ModelRepairTest {
    @TempDir Path dir;

    private static void varint(ByteArrayOutputStream out, long v) {
        while ((v & ~0x7FL) != 0) {
            out.write((int) ((v & 0x7F) | 0x80));
            v >>>= 7;
        }
        out.write((int) v);
    }

    private static void field(ByteArrayOutputStream out, int n, byte[] p) {
        varint(out, ((long) n << 3) | 2);
        varint(out, p.length);
        out.writeBytes(p);
    }

    static byte[] model(String... kv) {
        ByteArrayOutputStream m = new ByteArrayOutputStream();
        varint(m, 1 << 3);
        varint(m, 8);
        field(m, 7, new byte[1000]);
        for (int i = 0; i < kv.length; i += 2) {
            ByteArrayOutputStream e = new ByteArrayOutputStream();
            field(e, 1, kv[i].getBytes(StandardCharsets.UTF_8));
            field(e, 2, kv[i + 1].getBytes(StandardCharsets.UTF_8));
            field(m, 14, e.toByteArray());
        }
        return m.toByteArray();
    }

    private Path write(String name, byte[] data) throws IOException {
        Path p = dir.resolve(name);
        Files.write(p, data);
        return p;
    }

    private void espeak(String... dicts) throws IOException {
        Path e = Files.createDirectories(dir.resolve("espeak-ng-data"));
        for (String d : dicts) Files.write(e.resolve(d), new byte[]{1});
    }

    @Test
    void appendEntriesRoundTripsAndKeepsExisting() {
        byte[] base = model("n_speakers", "1", "comment", "piper");
        Map<String, String> add = new LinkedHashMap<>();
        add.put("voice", "ru");
        add.put("has_espeak", "1");
        Map<String, String> meta = OnnxMetadata.parse(OnnxMetadata.appendEntries(base, add));
        assertEquals(Map.of("n_speakers", "1", "comment", "piper", "voice", "ru", "has_espeak", "1"), meta);
    }

    @Test
    void okForCompletePiperModel() throws IOException {
        write("m.onnx", model("n_speakers", "1", "comment", "piper", "voice", "ru"));
        ModelRepair.Health h = ModelRepair.check(dir);
        assertEquals(ModelRepair.Status.OK, h.status());
        assertEquals("", h.problem());
    }

    @Test
    void fixableWithSuggestionFromJson() throws IOException {
        write("m.onnx", model("n_speakers", "1", "comment", "piper"));
        write("m.onnx.json", "{\"espeak\":{\"voice\":\"ru\"}}".getBytes(StandardCharsets.UTF_8));
        espeak("ru_dict", "en_dict");
        ModelRepair.Health h = ModelRepair.check(dir);
        assertEquals(ModelRepair.Status.FIXABLE, h.status());
        assertEquals("ru", h.suggestedVoice());
        assertEquals(List.of("en-us", "ru"), h.voices());
    }

    @Test
    void fixableWithoutJsonListsVoices() throws IOException {
        write("m.onnx", model("n_speakers", "1", "comment", "piper"));
        espeak("ru_dict", "de_dict", "en_dict", "readme.txt");
        ModelRepair.Health h = ModelRepair.check(dir);
        assertEquals(ModelRepair.Status.FIXABLE, h.status());
        assertEquals("", h.suggestedVoice());
        assertEquals(List.of("de", "en-us", "ru"), h.voices());
    }

    @Test
    void incompatibleWithoutNSpeakers() throws IOException {
        write("m.onnx", model("comment", "piper"));
        ModelRepair.Health h = ModelRepair.check(dir);
        assertEquals(ModelRepair.Status.INCOMPATIBLE, h.status());
        assertTrue(h.problem().contains("n_speakers"));
    }

    @Test
    void incompatibleWhenNoOnnxAndNeverThrows() {
        assertEquals(ModelRepair.Status.INCOMPATIBLE, ModelRepair.check(dir).status());
    }

    @Test
    void gladosTypeIsOk() throws IOException {
        write("model.onnx", model());
        write("dictionary.txt", new byte[0]);
        assertEquals(ModelRepair.Status.OK, ModelRepair.check(dir).status());
    }

    @Test
    void applyRepairsKeepsBackupAndAddsHasEspeak() throws IOException {
        byte[] original = model("n_speakers", "1", "comment", "piper");
        Path onnx = write("m.onnx", original);
        espeak("ru_dict");
        ModelRepair.apply(dir, "ru");
        Path bak = dir.resolve("m.onnx.bak");
        assertArrayEquals(original, Files.readAllBytes(bak));
        Map<String, String> meta = OnnxMetadata.parse(Files.readAllBytes(onnx));
        assertEquals("ru", meta.get("voice"));
        assertEquals("1", meta.get("has_espeak"));
        assertEquals(ModelRepair.Status.OK, ModelRepair.check(dir).status());

        // second apply on a repaired model: no-op, original .bak untouched
        byte[] repaired = Files.readAllBytes(onnx);
        ModelRepair.apply(dir, "en-us");
        assertArrayEquals(repaired, Files.readAllBytes(onnx));
        assertArrayEquals(original, Files.readAllBytes(bak));
        assertFalse(Files.exists(dir.resolve("m.onnx.tmp")));
    }

    @Test
    void secondRealApplyKeepsOriginalBak() throws IOException {
        byte[] original = model("n_speakers", "1", "comment", "piper");
        Path onnx = write("m.onnx", original);
        ModelRepair.apply(dir, "ru");
        // model replaced by another broken one; .bak must still be the very first original
        Files.write(onnx, model("n_speakers", "1", "comment", "piper", "x", "y"));
        ModelRepair.apply(dir, "de");
        assertArrayEquals(original, Files.readAllBytes(dir.resolve("m.onnx.bak")));
        assertEquals("de", OnnxMetadata.parse(Files.readAllBytes(onnx)).get("voice"));
    }

    @Test
    void noHasEspeakWithoutDataDir() throws IOException {
        Path onnx = write("m.onnx", model("n_speakers", "1", "comment", "piper"));
        ModelRepair.apply(dir, "ru");
        assertFalse(OnnxMetadata.parse(Files.readAllBytes(onnx)).containsKey("has_espeak"));
    }

    @Test
    void existingHasEspeakIsNotDuplicated() throws IOException {
        espeak("ru_dict");
        byte[] b = model("n_speakers", "1", "comment", "piper", "has_espeak", "1");
        Path onnx = write("m.onnx", b);
        ModelRepair.apply(dir, "ru");
        byte[] out = Files.readAllBytes(onnx);
        int voiceOnly = OnnxMetadata.appendEntries(new byte[0], Map.of("voice", "ru")).length;
        assertEquals(b.length + voiceOnly, out.length);
    }

    @Test
    void applyOnHealthyModelIsNoOpWithoutBackup() throws IOException {
        byte[] b = model("n_speakers", "1", "comment", "piper", "voice", "ru", "has_espeak", "1");
        Path onnx = write("m.onnx", b);
        ModelRepair.apply(dir, "en-us");
        assertArrayEquals(b, Files.readAllBytes(onnx));
        assertFalse(Files.exists(dir.resolve("m.onnx.bak")));
    }

    @Test
    void blankVoiceRejected() throws IOException {
        write("m.onnx", model("n_speakers", "1"));
        assertThrows(IOException.class, () -> ModelRepair.apply(dir, " "));
    }
}
