package org.mamoru.omnichat.client.tts;

import org.mamoru.omnichat.client.config.OmnichatConfig;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.stream.Stream;

/**
 * Number of speakers of a locally installed model, for the settings screen's speaker selector.
 * The sherpa-onnx Java API (1.12.4) has no getNumSpeakers(), so the count is read from the VITS
 * model's ONNX metadata ("n_speakers", the same key TtsEngine validates) without loading natives.
 * GLaDOS models (dictionary.txt) are single-speaker.
 */
public final class SpeakerCounts {
    private static final Logger LOGGER = LoggerFactory.getLogger("OmniChat");
    private static final byte[] KEY = "n_speakers".getBytes(StandardCharsets.US_ASCII);

    private static final Map<String, Integer> CACHE = new ConcurrentHashMap<>();
    private static final Map<String, Boolean> PENDING = new ConcurrentHashMap<>();
    private static final ExecutorService READER = Executors.newSingleThreadExecutor(r -> {
        Thread t = new Thread(r, "OmniChat-Speaker-Count");
        t.setDaemon(true);
        return t;
    });

    private SpeakerCounts() {}

    /**
     * @return the cached speaker count (>= 1), or 0 if it isn't known yet; in that case the model
     *         file is read in the background and {@code onLoaded} runs (on that thread) when done.
     *         Models that aren't installed locally stay unknown.
     */
    public static int get(String modelName, Runnable onLoaded) {
        Integer cached = CACHE.get(modelName);
        if (cached != null) return cached;
        Path dir = OmnichatConfig.resolveModelDir(modelName);
        if (dir == null || !Files.isDirectory(dir)) return 0;
        if (PENDING.putIfAbsent(modelName, Boolean.TRUE) == null) {
            READER.execute(() -> {
                try {
                    CACHE.put(modelName, read(dir));
                } finally {
                    PENDING.remove(modelName);
                }
                onLoaded.run();
            });
        }
        return 0;
    }

    private static int read(Path dir) {
        if (Files.exists(dir.resolve("dictionary.txt"))) return 1;
        try (Stream<Path> files = Files.list(dir)) {
            Path model = files.filter(p -> p.getFileName().toString().endsWith(".onnx")).findFirst().orElse(null);
            return model == null ? 1 : parse(Files.readAllBytes(model));
        } catch (IOException | RuntimeException | OutOfMemoryError e) {
            LOGGER.warn("Failed to read speaker count of model in '{}': {}", dir.getFileName(), e.toString());
            return 1;
        }
    }

    /**
     * Finds the metadata entry {@code key="n_speakers"} and parses its value. In the protobuf
     * encoding the key bytes are followed by the value field: tag 0x12, a length byte, ASCII digits.
     */
    static int parse(byte[] data) {
        outer:
        for (int i = 0; i + KEY.length + 2 < data.length; i++) {
            for (int j = 0; j < KEY.length; j++) {
                if (data[i + j] != KEY[j]) continue outer;
            }
            int p = i + KEY.length;
            int len = data[p + 1];
            if (data[p] != 0x12 || len < 1 || len > 9 || p + 2 + len > data.length) continue;
            int n = 0;
            for (int k = 0; k < len; k++) {
                byte b = data[p + 2 + k];
                if (b < '0' || b > '9') continue outer;
                n = n * 10 + (b - '0');
            }
            return Math.max(1, n);
        }
        return 1;
    }
}
