package org.mamoru.omnichat.util;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Stream;

/**
 * Single source of truth for what a model directory contains: its type, which
 * {@code .onnx} file is the model, and whether every file the type needs is present.
 */
public final class ModelScanner {
    private static final Logger LOGGER = LoggerFactory.getLogger("OmniChat");
    private static final String PREFERRED_MODEL_FILE = "model.onnx";

    /** Model layouts the client knows how to load. */
    public enum ModelType {
        /** sherpa-onnx VITS: {@code .onnx} + {@code tokens.txt}. */
        SHERPA_VITS(List.of("tokens.txt")),
        /** GLaDOS / TeraTTS g2p-vits: {@code .onnx} + {@code config.json} + {@code dictionary.txt}. */
        GLADOS(List.of("config.json", "dictionary.txt"));

        private final List<String> requiredFiles;

        ModelType(List<String> requiredFiles) {
            this.requiredFiles = requiredFiles;
        }

        public List<String> requiredFiles() {
            return requiredFiles;
        }
    }

    private ModelScanner() {}

    /** GLaDOS models are recognised by their pronunciation dictionary. */
    public static ModelType detectType(Path modelDir) {
        return Files.exists(modelDir.resolve("dictionary.txt")) ? ModelType.GLADOS : ModelType.SHERPA_VITS;
    }

    /**
     * Picks the model file deterministically: {@code model.onnx} if present, otherwise the only
     * {@code .onnx} in the directory. Logs the chosen file.
     *
     * @throws IllegalStateException if there is no candidate or the choice is ambiguous
     */
    public static Path resolveOnnxModel(Path modelDir) {
        List<Path> candidates = listOnnxFiles(modelDir);
        Path chosen = pickOnnxModel(candidates);
        if (chosen == null) {
            if (candidates.isEmpty()) {
                throw new IllegalStateException("No .onnx model file found in " + modelDir);
            }
            throw new IllegalStateException("Ambiguous model files in " + modelDir + ": "
                    + candidates.stream().map(p -> p.getFileName().toString()).toList()
                    + " (rename the one to use to " + PREFERRED_MODEL_FILE + " or remove the others)");
        }
        LOGGER.info("Using model file '{}' from '{}'", chosen.getFileName(), modelDir.getFileName());
        return chosen;
    }

    /** Files required by the directory's model type that are missing (empty if complete). */
    public static List<String> missingFiles(Path modelDir) {
        List<String> missing = new ArrayList<>();
        for (String name : detectType(modelDir).requiredFiles()) {
            if (!Files.isRegularFile(modelDir.resolve(name))) {
                missing.add(name);
            }
        }
        return missing;
    }

    /**
     * Throws a descriptive exception if the directory is not a loadable model of its type.
     */
    public static void requireComplete(Path modelDir) {
        List<String> missing = missingFiles(modelDir);
        if (!missing.isEmpty()) {
            throw new IllegalStateException("Model in " + modelDir + " (" + detectType(modelDir)
                    + ") is incomplete, missing: " + missing);
        }
    }

    public static List<String> scanModels(Path modelsDir) {
        List<String> models = new ArrayList<>();
        if (!Files.isDirectory(modelsDir)) {
            return models;
        }
        try (Stream<Path> dirs = Files.list(modelsDir)) {
            // Dot-prefixed dirs are temporary (omnivoice ".<name>.installing", ".<name>.old-*"), never models.
            dirs.filter(Files::isDirectory)
                    .filter(dir -> !dir.getFileName().toString().startsWith("."))
                    .sorted()
                    .filter(ModelScanner::isUsableModelDir)
                    .forEach(dir -> models.add(dir.getFileName().toString()));
        } catch (IOException e) {
            LOGGER.error("Failed to list models", e);
        }
        return models;
    }

    private static boolean isUsableModelDir(Path dir) {
        List<Path> candidates;
        try {
            candidates = listOnnxFiles(dir);
        } catch (IllegalStateException e) {
            LOGGER.warn("Skipping model dir '{}': {}", dir.getFileName(), e.getMessage());
            return false;
        }
        if (candidates.isEmpty()) {
            return false;
        }
        String name = dir.getFileName().toString();
        if (pickOnnxModel(candidates) == null) {
            LOGGER.warn("Skipping model '{}': several .onnx files and no {} ({})", name, PREFERRED_MODEL_FILE,
                    candidates.stream().map(p -> p.getFileName().toString()).toList());
            return false;
        }
        List<String> missing = missingFiles(dir);
        if (!missing.isEmpty()) {
            LOGGER.warn("Skipping incomplete model '{}' ({}): missing {}", name, detectType(dir), missing);
            return false;
        }
        return true;
    }

    private static Path pickOnnxModel(List<Path> candidates) {
        for (Path p : candidates) {
            if (p.getFileName().toString().equals(PREFERRED_MODEL_FILE)) {
                return p;
            }
        }
        return candidates.size() == 1 ? candidates.get(0) : null;
    }

    private static List<Path> listOnnxFiles(Path modelDir) {
        try (Stream<Path> files = Files.list(modelDir)) {
            return files.filter(Files::isRegularFile)
                    .filter(p -> p.getFileName().toString().endsWith(".onnx"))
                    .sorted()
                    .toList();
        } catch (IOException e) {
            throw new IllegalStateException("Failed to scan model directory: " + modelDir, e);
        }
    }
}
