package org.mamoru.omnichat.client.tts;

import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import org.mamoru.omnichat.util.ModelScanner;

import java.io.IOException;
import java.io.Reader;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Stream;

/** Checks a sherpa (VITS) model's ONNX metadata and repairs the missing espeak entries in place. */
public final class ModelRepair {
    public enum Status { OK, FIXABLE, INCOMPATIBLE }

    /**
     * @param problem        "" when OK
     * @param suggestedVoice "" when unknown
     * @param voices         sorted espeak voices available in the model's espeak-ng-data, may be empty
     */
    public record Health(Status status, String problem, String suggestedVoice, List<String> voices) {
    }

    private ModelRepair() {
    }

    /** Never throws: IO problems give INCOMPATIBLE with the reason. */
    public static Health check(Path modelDir) {
        try {
            if (ModelScanner.detectType(modelDir) == ModelScanner.ModelType.GLADOS) {
                return new Health(Status.OK, "", "", List.of());
            }
            Path onnx = ModelScanner.resolveOnnxModel(modelDir);
            Map<String, String> meta = OnnxMetadata.parse(Files.readAllBytes(onnx));
            String problem = OnnxMetadata.vitsProblem(meta);
            if (problem == null) return new Health(Status.OK, "", "", List.of());
            boolean voiceOnly = meta.containsKey("n_speakers") && problem.contains("'voice'");
            if (!voiceOnly) return new Health(Status.INCOMPATIBLE, problem, "", List.of());
            String suggested = voiceFromPiperJson(onnx.resolveSibling(onnx.getFileName() + ".json"));
            return new Health(Status.FIXABLE, problem, suggested, espeakVoices(modelDir.resolve("espeak-ng-data")));
        } catch (IOException | RuntimeException e) {
            String msg = e.getMessage() == null ? e.getClass().getSimpleName() : e.getMessage();
            return new Health(Status.INCOMPATIBLE, msg, "", List.of());
        }
    }

    /**
     * Appends the missing {@code voice} (and {@code has_espeak=1} when espeak-ng-data exists and the key
     * is missing) to the model. Keeps a {@code .bak} copy if none exists yet. A model with nothing to add
     * is left untouched (no-op, no .bak).
     */
    public static void apply(Path modelDir, String voice) throws IOException {
        if (voice == null || voice.isBlank()) throw new IOException("no espeak voice given");
        Path onnx;
        try {
            onnx = ModelScanner.resolveOnnxModel(modelDir);
        } catch (IllegalStateException e) {
            throw new IOException(e.getMessage(), e);
        }
        byte[] bytes = Files.readAllBytes(onnx);
        Map<String, String> meta = OnnxMetadata.parse(bytes);
        Map<String, String> add = new LinkedHashMap<>();
        if (meta.getOrDefault("voice", "").isBlank()) add.put("voice", voice.trim());
        if (!meta.containsKey("has_espeak") && Files.isDirectory(modelDir.resolve("espeak-ng-data"))) {
            add.put("has_espeak", "1");
        }
        if (add.isEmpty()) return;

        Path bak = onnx.resolveSibling(onnx.getFileName() + ".bak");
        if (!Files.exists(bak)) Files.copy(onnx, bak);
        Path tmp = onnx.resolveSibling(onnx.getFileName() + ".tmp");
        try {
            Files.write(tmp, OnnxMetadata.appendEntries(bytes, add));
            try {
                Files.move(tmp, onnx, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
            } catch (AtomicMoveNotSupportedException e) {
                Files.move(tmp, onnx, StandardCopyOption.REPLACE_EXISTING);
            }
        } finally {
            Files.deleteIfExists(tmp);
        }
    }

    /** {@code espeak.voice} of a piper {@code .onnx.json}, or "" if absent/unreadable. */
    public static String voiceFromPiperJson(Path onnxJson) {
        if (!Files.isRegularFile(onnxJson)) return "";
        try (Reader r = Files.newBufferedReader(onnxJson)) {
            JsonElement root = JsonParser.parseReader(r);
            if (!root.isJsonObject()) return "";
            JsonElement espeak = root.getAsJsonObject().get("espeak");
            if (espeak == null || !espeak.isJsonObject()) return "";
            JsonObject o = espeak.getAsJsonObject();
            JsonElement v = o.get("voice");
            return v != null && v.isJsonPrimitive() ? v.getAsString().trim() : "";
        } catch (IOException | RuntimeException e) {
            return "";
        }
    }

    /** Voice codes from {@code *_dict} file names: ru_dict -> ru, en_dict -> en-us, others -> prefix. Sorted. */
    public static List<String> espeakVoices(Path espeakDir) {
        if (!Files.isDirectory(espeakDir)) return List.of();
        try (Stream<Path> files = Files.list(espeakDir)) {
            List<String> out = new ArrayList<>();
            files.map(p -> p.getFileName().toString())
                    .filter(n -> n.endsWith("_dict") && n.length() > 5)
                    .forEach(n -> {
                        String code = n.substring(0, n.length() - 5);
                        out.add(code.equals("en") ? "en-us" : code);
                    });
            out.sort(null);
            return List.copyOf(out);
        } catch (IOException e) {
            return List.of();
        }
    }
}
