package org.mamoru.omnichat.client.network;

import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientTickEvents;
import net.fabricmc.fabric.api.client.networking.v1.ClientPlayNetworking;
import net.minecraft.client.MinecraftClient;
import net.minecraft.text.Text;
import net.minecraft.util.Formatting;
import org.mamoru.omnichat.client.config.OmnichatConfig;
import org.mamoru.omnichat.network.ModelDownloadRequestC2SPayload;
import org.mamoru.omnichat.network.ModelDownloadStatusS2CPayload;
import org.mamoru.omnichat.network.ModelFileChunkS2CPayload;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.ArrayDeque;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.function.Consumer;

/**
 * Downloads models from the server one at a time. Chunks arrive on the client thread and
 * are handed to a single background thread that streams them into
 * {@code config/omnichat/downloads/<name>.part/}; when the last chunk is written the
 * directory is moved into {@code models/<name>} in one rename, so a model folder is either
 * complete or absent.
 */
public class ModelDownloadManager {
    private static final Logger LOGGER = LoggerFactory.getLogger("OmniChat");
    private static final ModelDownloadManager INSTANCE = new ModelDownloadManager();

    // No QUEUED/chunk/failure reply to a request: the server dropped it (e.g. unknown model)
    private static final long ACK_TIMEOUT_MS = 15_000;
    // Gap between chunks of a started transfer. Waiting in the server queue has no limit:
    // the server answers every queued request with chunks or a failure.
    private static final long STALL_TIMEOUT_MS = 30_000;
    // Server drops requests closer than 250 ms; keep a margin after a quick failure
    private static final long REQUEST_SPACING_MS = 400;

    private final ExecutorService diskExecutor = Executors.newSingleThreadExecutor(r -> {
        Thread t = new Thread(r, "OmniChat-ModelDownload");
        t.setDaemon(true);
        return t;
    });

    // All fields below are guarded by this
    // modelName -> state, in request order (current download first)
    private final Map<String, Download> downloads = new LinkedHashMap<>();
    private final ArrayDeque<String> queuedRequests = new ArrayDeque<>();
    private Download current;
    private long lastRequestSentAt;
    private volatile Consumer<String> onDownloadComplete;

    private ModelDownloadManager() {
        ClientTickEvents.END_CLIENT_TICK.register(client -> tick());
    }

    public static ModelDownloadManager getInstance() {
        return INSTANCE;
    }

    /** Called on the download thread right after a model was installed. */
    public void setOnDownloadComplete(Consumer<String> callback) {
        this.onDownloadComplete = callback;
    }

    public synchronized void requestDownload(String modelName) {
        if (downloads.containsKey(modelName)) {
            LOGGER.info("Model '{}' download already in progress", modelName);
            return;
        }
        Path modelDir = OmnichatConfig.resolveModelDir(modelName);
        if (modelDir == null) {
            LOGGER.error("Not downloading model '{}': invalid name", modelName);
            return;
        }
        Path partDir = getDownloadsDir().resolve(modelDir.getFileName() + ".part");
        downloads.put(modelName, new Download(modelName, modelDir, partDir));
        queuedRequests.add(modelName);
        sendNextRequest();
    }

    private synchronized void sendNextRequest() {
        if (current != null || queuedRequests.isEmpty()) return;
        long now = System.currentTimeMillis();
        if (now - lastRequestSentAt < REQUEST_SPACING_MS) return; // retried from tick()
        if (!ClientNetworkHandler.canSend(ModelDownloadRequestC2SPayload.ID)) return;

        String modelName = queuedRequests.poll();
        current = downloads.get(modelName);
        current.lastActivity = now;
        lastRequestSentAt = now;
        ClientPlayNetworking.send(new ModelDownloadRequestC2SPayload(modelName));
        LOGGER.info("Requested download of model '{}'", modelName);
    }

    private synchronized void tick() {
        Download d = current;
        if (d != null) {
            long idle = System.currentTimeMillis() - d.lastActivity;
            if (!d.acknowledged && idle > ACK_TIMEOUT_MS) {
                fail(d, "no response from server");
            } else if (d.started && !d.installing && idle > STALL_TIMEOUT_MS) {
                fail(d, "transfer stalled");
            }
        }
        sendNextRequest();
    }

    /**
     * Returns a snapshot of all downloads in request order: progress 0.0-1.0 once data
     * flows, or -1 while the request is still waiting (locally or in the server queue).
     */
    public synchronized Map<String, Float> getActiveDownloads() {
        Map<String, Float> result = new LinkedHashMap<>();
        downloads.forEach((name, d) -> result.put(name,
                !d.started ? -1f : d.totalBytes > 0 ? (float) d.receivedBytes / d.totalBytes : 0f));
        return result;
    }

    public synchronized void onStatusReceived(ModelDownloadStatusS2CPayload payload) {
        Download d = current;
        if (d == null || !d.modelName.equals(payload.modelName())) {
            LOGGER.debug("Ignoring status {} for model '{}' that isn't downloading", payload.status(), payload.modelName());
            return;
        }
        switch (payload.status()) {
            case QUEUED -> {
                d.acknowledged = true;
                d.lastActivity = System.currentTimeMillis();
            }
            case FAILED -> fail(d, payload.reason().isEmpty() ? "refused by server" : payload.reason());
        }
    }

    public synchronized void onChunkReceived(ModelFileChunkS2CPayload payload) {
        Download d = current;
        if (d == null || !d.modelName.equals(payload.modelName())) {
            // tail of a transfer this client already gave up on
            LOGGER.debug("Ignoring chunk for model '{}' that isn't downloading", payload.modelName());
            return;
        }
        if (d.installing) {
            fail(d, "unexpected data after the last file");
            return;
        }

        String fileName = payload.fileName();
        if (!fileName.equals(d.currentFile)) {
            // a new file must start at 0, after the previous one ended, and never repeat
            if (d.currentFile != null || payload.offset() != 0 || !d.seenFiles.add(fileName)) {
                fail(d, "out-of-order data for '" + fileName + "'");
                return;
            }
            // names come from the server: never let them point outside the download dir
            if (OmnichatConfig.resolveInside(d.partDir, fileName) == null) {
                LOGGER.error("Rejected model '{}': invalid file name '{}' from server", d.modelName, fileName);
                fail(d, "invalid file name from server");
                return;
            }
            d.currentFile = fileName;
            d.expectedOffset = 0;
        } else if (payload.offset() != d.expectedOffset) {
            fail(d, "out-of-order data for '" + fileName + "'");
            return;
        }

        byte[] data = payload.data();
        d.started = true;
        d.acknowledged = true;
        d.lastActivity = System.currentTimeMillis();
        d.totalBytes = payload.totalBytes();
        d.receivedBytes += data.length;
        d.expectedOffset += data.length;
        boolean lastChunk = payload.lastChunk();
        if (lastChunk) d.currentFile = null;

        diskExecutor.execute(() -> writeChunk(d, fileName, data, lastChunk));

        if (payload.lastFile() && lastChunk) {
            d.installing = true;
            diskExecutor.execute(() -> install(d));
        }
    }

    // ---- download thread ----

    private void writeChunk(Download d, String fileName, byte[] data, boolean lastChunk) {
        if (d.aborted) return;
        try {
            if (d.channel == null) {
                if (!d.partDirReady) {
                    deleteRecursively(d.partDir); // leftover from a crash or an earlier failure
                    Files.createDirectories(d.partDir);
                    d.partDirReady = true;
                }
                Path file = OmnichatConfig.resolveInside(d.partDir, fileName);
                Files.createDirectories(file.getParent());
                d.channel = FileChannel.open(file, StandardOpenOption.CREATE, StandardOpenOption.WRITE,
                        StandardOpenOption.TRUNCATE_EXISTING);
            }
            ByteBuffer buf = ByteBuffer.wrap(data);
            while (buf.hasRemaining()) {
                d.channel.write(buf);
            }
            d.bytesWritten += data.length;
            if (lastChunk) {
                d.channel.force(true);
                d.channel.close();
                d.channel = null;
            }
        } catch (IOException | RuntimeException e) {
            LOGGER.error("Failed to write model '{}' file '{}'", d.modelName, fileName, e);
            abortOnDiskThread(d, "disk write error: " + e.getMessage());
        }
    }

    private void install(Download d) {
        if (d.aborted) return;
        try {
            if (d.bytesWritten != d.totalBytes) {
                throw new IOException("size mismatch: got " + d.bytesWritten + " of " + d.totalBytes + " bytes");
            }
            Files.createDirectories(d.modelDir.getParent());
            Path backup = null;
            if (Files.exists(d.modelDir)) {
                // replacing an existing model: move it aside first so the swap can be undone
                backup = getDownloadsDir().resolve(d.modelDir.getFileName() + ".old");
                deleteRecursively(backup);
                move(d.modelDir, backup);
            }
            try {
                move(d.partDir, d.modelDir);
            } catch (IOException e) {
                if (backup != null) {
                    try {
                        move(backup, d.modelDir);
                    } catch (IOException restoreError) {
                        e.addSuppressed(restoreError);
                    }
                }
                throw e;
            }
            if (backup != null) {
                try {
                    deleteRecursively(backup);
                } catch (IOException e) {
                    LOGGER.warn("Could not delete previous copy of model '{}' at {}", d.modelName, backup, e);
                }
            }
        } catch (IOException | RuntimeException e) {
            LOGGER.error("Failed to install model '{}'", d.modelName, e);
            abortOnDiskThread(d, "install failed: " + e.getMessage());
            return;
        }

        LOGGER.info("Model '{}' installed ({} files, {} bytes)", d.modelName, d.seenFiles.size(), d.bytesWritten);
        Consumer<String> callback = onDownloadComplete;
        if (callback != null) {
            try {
                callback.accept(d.modelName);
            } catch (RuntimeException e) {
                LOGGER.error("Download-complete callback failed for model '{}'", d.modelName, e);
            }
        }
        MinecraftClient.getInstance().execute(() -> finish(d));
    }

    private void abortOnDiskThread(Download d, String reason) {
        d.aborted = true;
        cleanup(d);
        MinecraftClient.getInstance().execute(() -> {
            synchronized (this) {
                fail(d, reason);
            }
        });
    }

    /** Closes the open file and removes the partial download. Runs on the download thread. */
    private void cleanup(Download d) {
        if (d.channel != null) {
            try {
                d.channel.close();
            } catch (IOException ignored) {
            }
            d.channel = null;
        }
        try {
            deleteRecursively(d.partDir);
        } catch (IOException e) {
            LOGGER.warn("Could not delete partial download {}", d.partDir, e);
        }
    }

    // ---- state transitions (client thread, under lock) ----

    private synchronized void finish(Download d) {
        downloads.remove(d.modelName, d);
        if (current == d) current = null;
        sendNextRequest();
    }

    private void fail(Download d, String reason) {
        if (downloads.get(d.modelName) != d) return; // already finished, failed or cleared
        downloads.remove(d.modelName);
        if (current == d) current = null;
        queuedRequests.remove(d.modelName);
        d.aborted = true;
        diskExecutor.execute(() -> cleanup(d));

        LOGGER.warn("Download of model '{}' failed: {}", d.modelName, reason);
        MinecraftClient client = MinecraftClient.getInstance();
        if (client.player != null) {
            client.player.sendMessage(Text.literal("[OmniChat] Model '" + d.modelName + "' download failed: " + reason)
                    .formatted(Formatting.RED), false);
        }
        sendNextRequest();
    }

    public synchronized void clear() {
        for (Download d : downloads.values()) {
            d.aborted = true;
            diskExecutor.execute(() -> cleanup(d));
        }
        downloads.clear();
        queuedRequests.clear();
        current = null;
    }

    // ---- file helpers ----

    private static Path getDownloadsDir() {
        return OmnichatConfig.getConfigDir().resolve("downloads").toAbsolutePath().normalize();
    }

    private static void move(Path from, Path to) throws IOException {
        try {
            Files.move(from, to, StandardCopyOption.ATOMIC_MOVE);
        } catch (AtomicMoveNotSupportedException e) {
            Files.move(from, to);
        }
    }

    private static void deleteRecursively(Path dir) throws IOException {
        if (!Files.exists(dir)) return;
        Files.walkFileTree(dir, new SimpleFileVisitor<>() {
            @Override
            public FileVisitResult visitFile(Path file, BasicFileAttributes attrs) throws IOException {
                Files.delete(file);
                return FileVisitResult.CONTINUE;
            }

            @Override
            public FileVisitResult postVisitDirectory(Path d, IOException exc) throws IOException {
                if (exc != null) throw exc;
                Files.delete(d);
                return FileVisitResult.CONTINUE;
            }
        });
    }

    private static final class Download {
        final String modelName;
        final Path modelDir;
        final Path partDir;

        // client thread (under the manager lock)
        long lastActivity;
        boolean acknowledged;
        boolean started;
        boolean installing;
        long totalBytes;
        long receivedBytes;
        String currentFile;
        long expectedOffset;
        final Set<String> seenFiles = new HashSet<>();

        // set by either thread, read by the download thread
        volatile boolean aborted;

        // download thread only
        FileChannel channel;
        boolean partDirReady;
        long bytesWritten;

        Download(String modelName, Path modelDir, Path partDir) {
            this.modelName = modelName;
            this.modelDir = modelDir;
            this.partDir = partDir;
        }
    }
}
