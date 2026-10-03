package org.mamoru.omnichat.client.tts;

import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import org.mamoru.omnichat.util.ModelScanner;

import java.io.IOException;
import java.io.Reader;
import java.nio.file.AccessDeniedException;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.FileSystemException;
import java.nio.file.StandardOpenOption;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
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
            Map<String, String> meta = OnnxMetadata.parse(onnx);
            String problem = OnnxMetadata.vitsProblem(meta);
            if (problem == null) return new Health(Status.OK, "", "", List.of());
            if (!OnnxMetadata.missingVoiceOnly(meta)) return new Health(Status.INCOMPATIBLE, problem, "", List.of());
            String suggested = voiceFromPiperJson(onnx.resolveSibling(onnx.getFileName() + ".json"));
            return new Health(Status.FIXABLE, problem, suggested, espeakVoices(modelDir.resolve("espeak-ng-data")));
        } catch (OutOfMemoryError e) {
            return new Health(Status.INCOMPATIBLE, "out of memory while reading the model", "", List.of());
        } catch (IOException | RuntimeException e) {
            String msg = e.getMessage() == null ? e.getClass().getSimpleName() : e.getMessage();
            return new Health(Status.INCOMPATIBLE, msg, "", List.of());
        }
    }

    /**
     * Adds the missing {@code voice} (and {@code has_espeak=1} when espeak-ng-data exists and the key is
     * missing or blank) to the model. Blank existing entries are removed first so no duplicate remains.
     * Only a FIXABLE model is touched: an OK model is a no-op (no write, no .bak); an INCOMPATIBLE model
     * throws IOException with the reason. Keeps a {@code .bak} copy if none exists yet.
     */
    public static void apply(Path modelDir, String voice) throws IOException {
        if (voice == null || voice.isBlank()) throw new IOException("no espeak voice given");
        Health health = check(modelDir);
        if (health.status() == Status.OK) return;
        if (health.status() == Status.INCOMPATIBLE) throw new IOException("model can't be repaired: " + health.problem());
        Path onnx;
        try {
            onnx = ModelScanner.resolveOnnxModel(modelDir);
        } catch (IllegalStateException e) {
            throw new IOException(e.getMessage(), e);
        }
        Map<String, String> meta = OnnxMetadata.parse(onnx);
        Map<String, String> add = new LinkedHashMap<>();
        Set<String> blank = new HashSet<>();
        if (meta.getOrDefault("voice", "").isBlank()) {
            add.put("voice", voice.trim());
            if (meta.containsKey("voice")) blank.add("voice");
        }
        boolean espeakDir = Files.isDirectory(modelDir.resolve("espeak-ng-data"));
        if (espeakDir && meta.getOrDefault("has_espeak", "").isBlank()) {
            add.put("has_espeak", "1");
            if (meta.containsKey("has_espeak")) blank.add("has_espeak");
        }
        if (add.isEmpty()) return;

        Path bak = onnx.resolveSibling(onnx.getFileName() + ".bak");
        Path tmp = onnx.resolveSibling(onnx.getFileName() + ".tmp");
        Path bakTmp = onnx.resolveSibling(onnx.getFileName() + ".bak.tmp");
        try {
            if (!Files.exists(bak)) {
                copyContent(onnx, bakTmp);
                Files.move(bakTmp, bak);
            }
            if (blank.isEmpty()) {
                copyContent(onnx, tmp);
                Files.write(tmp, OnnxMetadata.appendEntries(new byte[0], add), StandardOpenOption.APPEND);
            } else {
                byte[] cleaned = OnnxMetadata.removeEntries(Files.readAllBytes(onnx), blank);
                Files.write(tmp, OnnxMetadata.appendEntries(cleaned, add));
            }
            try {
                Files.move(tmp, onnx, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
            } catch (AtomicMoveNotSupportedException e) {
                Files.move(tmp, onnx, StandardCopyOption.REPLACE_EXISTING);
            }
        } catch (AccessDeniedException e) {
            throw new IOException("model file is in use or read-only: " + onnx.getFileName(), e);
        } catch (FileSystemException e) {
            throw new IOException("model file is in use or can't be replaced: " + onnx.getFileName(), e);
        } finally {
            Files.deleteIfExists(tmp);
            Files.deleteIfExists(bakTmp);
        }
    }

    /** Copies bytes only: Files.copy(Path, Path) would carry a read-only attribute over to the copy. */
    private static void copyContent(Path from, Path to) throws IOException {
        try (java.io.OutputStream out = Files.newOutputStream(to)) {
            Files.copy(from, out);
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
