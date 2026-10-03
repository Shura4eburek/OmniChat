package org.mamoru.omnichat.voice;

import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

/** Reads optional {@code voice.json} and {@code portrait.png} from a model folder. Never throws. */
public final class VoiceMetaReader {
    private static final Logger LOGGER = LoggerFactory.getLogger("OmniChat");

    public static final int MAX_NAME = 32;
    public static final int MAX_DESCRIPTION = 200;
    public static final int MAX_SAMPLE = 120;
    public static final int MAX_LANGUAGE = 8;
    public static final int MAX_PORTRAIT_BYTES = 8192;

    private static final byte[] PNG_SIGNATURE = {(byte) 0x89, 'P', 'N', 'G', 0x0D, 0x0A, 0x1A, 0x0A};

    private VoiceMetaReader() {
    }

    public static VoiceMeta read(Path modelDir, String model) {
        String name = model, description = "", language = "", gender = "", sample = "";
        Path json = modelDir.resolve("voice.json");
        if (Files.isRegularFile(json)) {
            try {
                // Always UTF-8: the platform default on Windows would mangle Cyrillic
                JsonObject o = JsonParser.parseString(Files.readString(json, StandardCharsets.UTF_8)).getAsJsonObject();
                String n = str(o, "name", MAX_NAME);
                if (!n.isBlank()) name = n;
                description = str(o, "description", MAX_DESCRIPTION);
                language = str(o, "language", MAX_LANGUAGE);
                gender = str(o, "gender", 16);
                sample = str(o, "sample", MAX_SAMPLE);
            } catch (IOException | RuntimeException e) {
                LOGGER.warn("Ignoring invalid voice.json of model '{}': {}", model, e.toString());
            }
        }
        byte[] portrait = new byte[0];
        Path png = modelDir.resolve("portrait.png");
        if (Files.isRegularFile(png)) {
            try {
                if (Files.size(png) <= MAX_PORTRAIT_BYTES) {
                    byte[] data = Files.readAllBytes(png);
                    if (isValidPortrait(data)) portrait = data;
                }
                if (portrait.length == 0) {
                    LOGGER.warn("Ignoring portrait.png of model '{}': must be a 16x16 or 32x32 PNG up to {} bytes",
                            model, MAX_PORTRAIT_BYTES);
                }
            } catch (IOException e) {
                LOGGER.warn("Failed to read portrait.png of model '{}': {}", model, e.toString());
            }
        }
        return new VoiceMeta(model, name, description, language, gender, sample, folderSize(modelDir), portrait);
    }

    /** PNG signature, IHDR first, square 16x16 or 32x32, at most {@link #MAX_PORTRAIT_BYTES}. */
    public static boolean isValidPortrait(byte[] png) {
        if (png == null || png.length < 24 || png.length > MAX_PORTRAIT_BYTES) return false;
        for (int i = 0; i < PNG_SIGNATURE.length; i++) {
            if (png[i] != PNG_SIGNATURE[i]) return false;
        }
        if (png[12] != 'I' || png[13] != 'H' || png[14] != 'D' || png[15] != 'R') return false;
        int w = readInt(png, 16), h = readInt(png, 20);
        return w == h && (w == 16 || w == 32);
    }

    private static int readInt(byte[] b, int off) {
        return ((b[off] & 0xFF) << 24) | ((b[off + 1] & 0xFF) << 16) | ((b[off + 2] & 0xFF) << 8) | (b[off + 3] & 0xFF);
    }

    private static String str(JsonObject o, String key, int max) {
        JsonElement e = o.get(key);
        if (e == null || !e.isJsonPrimitive()) return "";
        String s = e.getAsString().strip();
        return s.length() > max ? s.substring(0, max) : s;
    }

    private static long folderSize(Path dir) {
        try (Stream<Path> files = Files.walk(dir)) {
            return files.filter(Files::isRegularFile).mapToLong(p -> {
                try {
                    return Files.size(p);
                } catch (IOException e) {
                    return 0;
                }
            }).sum();
        } catch (IOException e) {
            return 0;
        }
    }
}
