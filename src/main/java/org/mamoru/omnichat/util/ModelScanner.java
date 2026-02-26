package org.mamoru.omnichat.util;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Stream;

public final class ModelScanner {
    private static final Logger LOGGER = LoggerFactory.getLogger("OmniChat");

    private ModelScanner() {}

    public static List<String> scanModels(Path modelsDir) {
        List<String> models = new ArrayList<>();
        if (!Files.isDirectory(modelsDir)) {
            return models;
        }
        try (Stream<Path> dirs = Files.list(modelsDir)) {
            dirs.filter(Files::isDirectory)
                    .filter(dir -> {
                        try (Stream<Path> files = Files.list(dir)) {
                            return files.anyMatch(f -> f.getFileName().toString().endsWith(".onnx"));
                        } catch (IOException e) {
                            return false;
                        }
                    })
                    .forEach(dir -> models.add(dir.getFileName().toString()));
        } catch (IOException e) {
            LOGGER.error("Failed to list models", e);
        }
        return models;
    }
}
