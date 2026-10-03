package org.mamoru.omnichat.voice;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class VoiceMetaReaderTest {
    @TempDir Path dir;

    static byte[] png(int w, int h, int totalSize) {
        // PNG signature + IHDR chunk header + width/height, padded to totalSize
        ByteBuffer b = ByteBuffer.allocate(Math.max(totalSize, 24));
        b.put(new byte[]{(byte) 0x89, 'P', 'N', 'G', 0x0D, 0x0A, 0x1A, 0x0A});
        b.putInt(13).put(new byte[]{'I', 'H', 'D', 'R'}).putInt(w).putInt(h);
        return b.array();
    }

    @Test
    void missingFilesGiveBareMetaWithFolderSize() throws IOException {
        Files.write(dir.resolve("model.onnx"), new byte[1234]);
        VoiceMeta m = VoiceMetaReader.read(dir, "denis");
        assertEquals("denis", m.name());
        assertEquals("", m.description());
        assertEquals(0, m.portrait().length);
        assertEquals(1234, m.sizeBytes());
    }

    @Test
    void missingFolderGivesBareMetaWithZeroSize() {
        VoiceMeta m = VoiceMetaReader.read(dir.resolve("gone"), "ghost");
        assertEquals("ghost", m.name());
        assertEquals(0, m.sizeBytes());
        assertEquals(0, m.portrait().length);
    }

    @Test
    void readsAndTruncatesFields() throws IOException {
        String longName = "N".repeat(50);
        Files.writeString(dir.resolve("voice.json"),
                "{\"name\":\"" + longName + "\",\"description\":\"" + "d".repeat(300) + "\","
                        + "\"language\":\"ru-RU-extra\",\"gender\":\"male\",\"sample\":\"" + "s".repeat(200) + "\","
                        + "\"unknown\":42}", StandardCharsets.UTF_8);
        VoiceMeta m = VoiceMetaReader.read(dir, "denis");
        assertEquals(32, m.name().length());
        assertEquals(200, m.description().length());
        assertEquals(8, m.language().length());
        assertEquals(120, m.sample().length());
        assertEquals("male", m.gender());
    }

    @Test
    void brokenJsonFallsBack() throws IOException {
        Files.writeString(dir.resolve("voice.json"), "{ not json");
        assertEquals("denis", VoiceMetaReader.read(dir, "denis").name());
    }

    @Test
    void blankNameFallsBackToModel() throws IOException {
        Files.writeString(dir.resolve("voice.json"), "{\"name\":\"   \"}");
        assertEquals("denis", VoiceMetaReader.read(dir, "denis").name());
    }

    @Test
    void readsUtf8OnAnyPlatform() throws IOException {
        Files.write(dir.resolve("voice.json"), "{\"name\":\"Денис\"}".getBytes(StandardCharsets.UTF_8));
        assertEquals("Денис", VoiceMetaReader.read(dir, "denis").name());
    }

    @Test
    void acceptsValidPortraits() throws IOException {
        Files.write(dir.resolve("portrait.png"), png(16, 16, 300));
        assertEquals(300, VoiceMetaReader.read(dir, "denis").portrait().length);
        assertTrue(VoiceMetaReader.isValidPortrait(png(32, 32, 500)));
    }

    @Test
    void rejectsBadPortraits() {
        assertFalse(VoiceMetaReader.isValidPortrait(png(64, 64, 300)));      // wrong size
        assertFalse(VoiceMetaReader.isValidPortrait(png(16, 32, 300)));      // not square
        assertFalse(VoiceMetaReader.isValidPortrait(png(16, 16, 9000)));     // too big
        assertFalse(VoiceMetaReader.isValidPortrait("GIF89a....".getBytes())); // not png
        assertFalse(VoiceMetaReader.isValidPortrait(new byte[0]));
    }
}
