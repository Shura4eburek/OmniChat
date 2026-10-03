package org.mamoru.omnichat.util;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ModelScannerTest {
    private static void voice(Path dir) throws IOException {
        Files.createDirectories(dir);
        Files.write(dir.resolve(dir.getFileName().toString().replace(".", "") + ".onnx"), new byte[]{1});
        Files.writeString(dir.resolve("tokens.txt"), "_ 0\n");
    }

    @Test
    void skipsDotPrefixedTemporaryDirs(@TempDir Path models) throws IOException {
        voice(models.resolve("glados"));
        voice(models.resolve(".glados.installing"));
        voice(models.resolve(".glados.old-1a2b3c4d"));
        assertEquals(List.of("glados"), ModelScanner.scanModels(models));
    }
}
