package org.mamoru.omnichat.server;

import net.fabricmc.fabric.api.networking.v1.ServerPlayNetworking;
import net.minecraft.server.network.ServerPlayerEntity;
import org.mamoru.omnichat.network.ModelFileChunkS2CPayload;

import java.io.Closeable;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.UUID;
import java.util.stream.Stream;

/**
 * Streaming state of one model being sent to one player. Files are read chunk by chunk
 * from an open stream, never loaded whole.
 */
final class ModelTransfer implements Closeable {
    private static final int CHUNK_SIZE = 32 * 1024; // 32 KB

    final UUID playerId;
    final String playerName;
    final String modelName;
    private final Path modelDir;
    private final List<Path> files;
    final long totalBytes;

    private int fileIdx;
    private InputStream in;
    private long fileSize;
    private int offset;

    /** The model can't be sent as is (empty folder, oversized file); the message goes to the client. */
    static final class RefusedException extends IOException {
        RefusedException(String message) {
            super(message);
        }
    }

    ModelTransfer(UUID playerId, String playerName, String modelName, Path modelDir) throws IOException {
        this.playerId = playerId;
        this.playerName = playerName;
        this.modelName = modelName;
        this.modelDir = modelDir;
        try (Stream<Path> stream = Files.walk(modelDir)) {
            this.files = stream.filter(Files::isRegularFile).toList();
        }
        if (files.isEmpty()) {
            throw new RefusedException("model folder is empty");
        }
        long total = 0;
        for (Path file : files) {
            long size = Files.size(file);
            // the chunk offset is an int (VarInt) and the client checks it per file
            if (size > Integer.MAX_VALUE) {
                throw new RefusedException("file too large: " + modelDir.relativize(file));
            }
            total += size;
        }
        this.totalBytes = total;
    }

    int fileCount() {
        return files.size();
    }

    /**
     * Sends up to {@code maxChunks} chunks. Returns true once the whole model has been sent.
     */
    boolean sendChunks(ServerPlayerEntity player, int maxChunks) throws IOException {
        for (int i = 0; i < maxChunks && fileIdx < files.size(); i++) {
            Path file = files.get(fileIdx);
            if (in == null) {
                in = Files.newInputStream(file);
                fileSize = Files.size(file);
                offset = 0;
            }

            byte[] chunk = in.readNBytes(CHUNK_SIZE);
            boolean lastChunk = chunk.length < CHUNK_SIZE || offset + chunk.length >= fileSize;
            boolean lastFile = lastChunk && fileIdx == files.size() - 1;
            String relativePath = modelDir.relativize(file).toString().replace('\\', '/');

            ServerPlayNetworking.send(player,
                    new ModelFileChunkS2CPayload(modelName, relativePath, offset, chunk, lastChunk, lastFile, totalBytes));
            offset += chunk.length;

            if (lastChunk) {
                in.close();
                in = null;
                fileIdx++;
            }
        }
        return fileIdx >= files.size();
    }

    @Override
    public void close() {
        if (in != null) {
            try {
                in.close();
            } catch (IOException ignored) {
            }
            in = null;
        }
    }
}
