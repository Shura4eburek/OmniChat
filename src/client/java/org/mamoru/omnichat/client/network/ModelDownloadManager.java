package org.mamoru.omnichat.client.network;

import net.fabricmc.fabric.api.client.networking.v1.ClientPlayNetworking;
import org.mamoru.omnichat.client.config.OmnichatConfig;
import org.mamoru.omnichat.network.ModelDownloadRequestC2SPayload;
import org.mamoru.omnichat.network.ModelFileChunkS2CPayload;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.function.Consumer;

public class ModelDownloadManager {
    private static final Logger LOGGER = LoggerFactory.getLogger("OmniChat");
    private static final ModelDownloadManager INSTANCE = new ModelDownloadManager();

    private final Map<String, Map<String, ByteArrayOutputStream>> pendingDownloads = new ConcurrentHashMap<>();
    private final Map<String, DownloadProgress> progressMap = new ConcurrentHashMap<>();
    private Consumer<String> onDownloadComplete;

    private ModelDownloadManager() {}

    public static ModelDownloadManager getInstance() {
        return INSTANCE;
    }

    public void setOnDownloadComplete(Consumer<String> callback) {
        this.onDownloadComplete = callback;
    }

    public void requestDownload(String modelName) {
        if (progressMap.containsKey(modelName)) {
            LOGGER.info("Model '{}' download already in progress", modelName);
            return;
        }
        progressMap.put(modelName, new DownloadProgress());
        pendingDownloads.put(modelName, new ConcurrentHashMap<>());
        ClientPlayNetworking.send(new ModelDownloadRequestC2SPayload(modelName));
        LOGGER.info("Requested download of model '{}'", modelName);
    }

    public boolean isDownloading(String modelName) {
        return progressMap.containsKey(modelName);
    }

    /**
     * Returns download progress as 0.0-1.0, or -1 if not downloading.
     */
    public float getProgress(String modelName) {
        DownloadProgress progress = progressMap.get(modelName);
        if (progress == null) return -1f;
        if (progress.totalBytes <= 0) return 0f;
        return (float) progress.receivedBytes / progress.totalBytes;
    }

    /**
     * Returns a snapshot of all active downloads and their progress (0.0-1.0).
     */
    public Map<String, Float> getActiveDownloads() {
        Map<String, Float> result = new java.util.HashMap<>();
        progressMap.forEach((name, progress) -> {
            float pct = progress.totalBytes > 0 ? (float) progress.receivedBytes / progress.totalBytes : 0f;
            result.put(name, pct);
        });
        return result;
    }

    public void onChunkReceived(ModelFileChunkS2CPayload payload) {
        String modelName = payload.modelName();
        Map<String, ByteArrayOutputStream> fileMap = pendingDownloads.get(modelName);
        if (fileMap == null) {
            LOGGER.warn("Received chunk for unexpected model '{}'", modelName);
            return;
        }

        // Update progress
        DownloadProgress progress = progressMap.get(modelName);
        if (progress != null) {
            progress.totalBytes = payload.totalBytes();
            progress.receivedBytes += payload.data().length;
        }

        ByteArrayOutputStream stream = fileMap.computeIfAbsent(payload.fileName(), k -> new ByteArrayOutputStream());
        if (payload.data().length > 0) {
            stream.write(payload.data(), 0, payload.data().length);
        }

        if (payload.lastFile() && payload.lastChunk()) {
            saveModel(modelName, fileMap);
            pendingDownloads.remove(modelName);
            progressMap.remove(modelName);
        }
    }

    private void saveModel(String modelName, Map<String, ByteArrayOutputStream> fileMap) {
        Path modelDir = OmnichatConfig.getModelsDir().resolve(modelName);
        try {
            Files.createDirectories(modelDir);
            for (Map.Entry<String, ByteArrayOutputStream> entry : fileMap.entrySet()) {
                Path filePath = modelDir.resolve(entry.getKey());
                Files.createDirectories(filePath.getParent());
                Files.write(filePath, entry.getValue().toByteArray());
            }
            LOGGER.info("Model '{}' saved ({} files)", modelName, fileMap.size());
            if (onDownloadComplete != null) {
                onDownloadComplete.accept(modelName);
            }
        } catch (IOException e) {
            LOGGER.error("Failed to save model '{}'", modelName, e);
        }
    }

    public void clear() {
        pendingDownloads.clear();
        progressMap.clear();
    }

    private static class DownloadProgress {
        volatile long totalBytes;
        volatile long receivedBytes;
    }
}
