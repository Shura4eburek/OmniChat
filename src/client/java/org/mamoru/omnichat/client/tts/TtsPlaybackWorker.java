package org.mamoru.omnichat.client.tts;

import org.mamoru.omnichat.client.config.OmnichatConfig;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.Collections;
import java.util.HashMap;
import java.util.IdentityHashMap;
import java.util.Map;
import java.util.Queue;
import java.util.Set;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.LinkedBlockingQueue;

/**
 * Owns its engines: they are created, used and released only on the worker thread,
 * so native generate() and release() never overlap.
 */
public class TtsPlaybackWorker {
    private static final Logger LOGGER = LoggerFactory.getLogger("OmniChat");
    private static final long SHUTDOWN_JOIN_MS = 2000;

    private final BlockingQueue<TtsRequest> queue;
    private final ITtsEngine defaultEngine;
    private final String defaultModelName;
    private final OmnichatConfig config;
    private final Thread workerThread;
    // Non-default engines loaded by this worker; touched only on the worker thread
    private final Map<String, ITtsEngine> engines = new HashMap<>();
    private final Queue<String> pendingEvictions = new ConcurrentLinkedQueue<>();
    private volatile boolean running = true;
    // Bumped by clearQueue (disconnect): a clip synthesized before it is dropped, not played in the menu
    private volatile int epoch;

    /** @param defaultModelName the model {@code defaultEngine} was built from (may be a fallback) */
    public TtsPlaybackWorker(ITtsEngine defaultEngine, String defaultModelName, OmnichatConfig config) {
        this.defaultEngine = defaultEngine;
        this.defaultModelName = defaultModelName;
        this.config = config;
        this.queue = new LinkedBlockingQueue<>(config.getMaxQueueSize());

        this.workerThread = new Thread(this::run, "OmniChat-TTS-Worker");
        this.workerThread.setDaemon(true);
    }

    public void start() {
        workerThread.start();
        LOGGER.info("TTS playback worker started");
    }

    /**
     * Stops the worker and waits briefly for it. Engines are released by the worker thread
     * itself once it leaves its loop, so a generate() still running past the timeout is safe.
     */
    public void shutdown() {
        running = false;
        workerThread.interrupt();
        queue.clear();
        try {
            workerThread.join(SHUTDOWN_JOIN_MS);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
        if (workerThread.isAlive()) {
            LOGGER.warn("TTS worker still busy after {} ms; it will release its engines when done", SHUTDOWN_JOIN_MS);
        }
        SpatialAudioPlayer.cleanupAll();
        LOGGER.info("TTS playback worker stopped");
    }

    public void enqueue(TtsRequest request) {
        if (!running) return;
        while (!queue.offer(request)) {
            queue.poll();
        }
    }

    /** Drops pending requests without stopping the worker (e.g. on disconnect). */
    public void clearQueue() {
        epoch++;
        queue.clear();
    }

    /** Drops the cached engine for a model (e.g. it was just re-downloaded). Safe from any thread. */
    public void evictModel(String modelName) {
        pendingEvictions.add(modelName);
    }

    private void run() {
        try {
            while (running && !Thread.currentThread().isInterrupted()) {
                try {
                    TtsRequest request = queue.take();
                    processEvictions();
                    processMessage(request);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    break;
                } catch (Exception | LinkageError e) {
                    LOGGER.error("Error processing TTS message", e);
                }
            }
        } finally {
            releaseEngines();
        }
    }

    private void processMessage(TtsRequest request) {
        int startEpoch = epoch;
        // Pick the engine for the sender's model (falls back to default if unavailable)
        ITtsEngine engine = getEngine(request.modelName());

        // Use speakerId from request (server voice) if available, otherwise fall back to config
        int speakerId = request.speakerId() >= 0 ? request.speakerId() : config.getSpeakerId();

        String modelLabel = request.modelName() != null ? request.modelName() : "default";
        long start = System.nanoTime();
        float[] samples = engine.generate(request.text(), speakerId, config.getSpeed());
        if (!running || epoch != startEpoch) return;
        if (samples == null || samples.length == 0) {
            LOGGER.warn("TTS generated no audio for {} chars (model '{}', speaker {})",
                    request.text().length(), modelLabel, speakerId);
            return;
        }
        // message text itself is not logged: chat can be private
        LOGGER.info("TTS generated {} chars in {} ms (model '{}', speaker {})",
                request.text().length(), (System.nanoTime() - start) / 1_000_000, modelLabel, speakerId);

        if (config.isRobotEffect()) {
            AudioUtils.applyRobotEffect(samples, engine.getSampleRate());
        }

        byte[] pcmData = AudioUtils.floatPcmToInt16(samples, config.getVolume());

        if (request.senderUuid() != null) {
            SpatialAudioPlayer.playSpatial(pcmData, engine.getSampleRate(), request.senderUuid(), () -> running && epoch == startEpoch);
        } else {
            SpatialAudioPlayer.playMono(pcmData, engine.getSampleRate(), () -> running && epoch == startEpoch);
        }
    }

    /** Only successfully loaded engines are cached, so a missing model is retried next time. */
    private ITtsEngine getEngine(String modelName) {
        if (modelName == null || modelName.equals(defaultModelName)) {
            return defaultEngine;
        }
        ITtsEngine cached = engines.get(modelName);
        if (cached != null) {
            return cached;
        }
        ITtsEngine loaded = TtsService.loadEngineForModel(modelName);
        if (loaded == null) {
            return defaultEngine;
        }
        engines.put(modelName, loaded);
        return loaded;
    }

    private void processEvictions() {
        String modelName;
        while ((modelName = pendingEvictions.poll()) != null) {
            ITtsEngine evicted = engines.remove(modelName);
            if (evicted != null && evicted != defaultEngine) {
                LOGGER.info("Model '{}' was updated, reloading its engine on next use", modelName);
                evicted.release();
            }
        }
    }

    private void releaseEngines() {
        Set<ITtsEngine> unique = Collections.newSetFromMap(new IdentityHashMap<>());
        unique.add(defaultEngine);
        unique.addAll(engines.values());
        engines.clear();
        for (ITtsEngine engine : unique) {
            try {
                engine.release();
            } catch (RuntimeException | LinkageError e) {
                LOGGER.error("Failed to release TTS engine", e);
            }
        }
    }
}
