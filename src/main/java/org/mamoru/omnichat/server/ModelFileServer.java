package org.mamoru.omnichat.server;

import net.fabricmc.fabric.api.networking.v1.ServerPlayNetworking;
import net.minecraft.server.network.ServerPlayerEntity;
import org.mamoru.omnichat.network.ModelFileChunkS2CPayload;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

public class ModelFileServer {
    private static final Logger LOGGER = LoggerFactory.getLogger("OmniChat");
    private static final int CHUNK_SIZE = 32 * 1024; // 32 KB

    private final Path modelsDir;

    public ModelFileServer(Path modelsDir) {
        this.modelsDir = modelsDir;
    }

    public void sendModel(ServerPlayerEntity player, String modelName) {
        Path modelDir = modelsDir.resolve(modelName);
        if (!Files.isDirectory(modelDir)) {
            LOGGER.warn("Model '{}' not found for download request from {}", modelName, player.getName().getString());
            return;
        }

        if (!modelDir.normalize().startsWith(modelsDir.normalize())) {
            LOGGER.warn("Path traversal attempt from {} for model '{}'", player.getName().getString(), modelName);
            return;
        }

        Thread.startVirtualThread(() -> {
            try {
                sendModelFiles(player, modelName, modelDir);
            } catch (IOException e) {
                LOGGER.error("Failed to send model '{}' to {}", modelName, player.getName().getString(), e);
            }
        });
    }

    private void sendModelFiles(ServerPlayerEntity player, String modelName, Path modelDir) throws IOException {
        List<Path> files;
        try (Stream<Path> stream = Files.walk(modelDir)) {
            files = stream.filter(Files::isRegularFile).toList();
        }

        // Calculate total size of all files
        long totalBytes = 0;
        for (Path file : files) {
            totalBytes += Files.size(file);
        }

        for (int fileIdx = 0; fileIdx < files.size(); fileIdx++) {
            Path file = files.get(fileIdx);
            boolean isLastFile = (fileIdx == files.size() - 1);
            String relativePath = modelDir.relativize(file).toString().replace('\\', '/');

            byte[] content = Files.readAllBytes(file);
            int offset = 0;

            while (offset < content.length) {
                int end = Math.min(offset + CHUNK_SIZE, content.length);
                byte[] chunk = new byte[end - offset];
                System.arraycopy(content, offset, chunk, 0, chunk.length);

                boolean lastChunk = (end >= content.length);
                boolean lastFile = lastChunk && isLastFile;

                ServerPlayNetworking.send(player,
                        new ModelFileChunkS2CPayload(modelName, relativePath, offset, chunk, lastChunk, lastFile, totalBytes));

                offset = end;
            }

            if (content.length == 0) {
                ServerPlayNetworking.send(player,
                        new ModelFileChunkS2CPayload(modelName, relativePath, 0, new byte[0], true, isLastFile, totalBytes));
            }
        }

        LOGGER.info("Sent model '{}' ({} files, {} bytes) to {}", modelName, files.size(), totalBytes, player.getName().getString());
    }
}
