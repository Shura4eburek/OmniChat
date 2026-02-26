package org.mamoru.omnichat.client.tts;

import org.mamoru.omnichat.client.OmnichatClient;
import org.mamoru.omnichat.client.config.OmnichatConfig;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;

public class TtsPlaybackWorker {
    private static final Logger LOGGER = LoggerFactory.getLogger("OmniChat");

    private final BlockingQueue<TtsRequest> queue;
    private final ITtsEngine defaultEngine;
    private final OmnichatConfig config;
    private final Thread workerThread;

    public TtsPlaybackWorker(ITtsEngine defaultEngine, OmnichatConfig config) {
        this.defaultEngine = defaultEngine;
        this.config = config;
        this.queue = new LinkedBlockingQueue<>(config.getMaxQueueSize());

        this.workerThread = new Thread(this::run, "OmniChat-TTS-Worker");
        this.workerThread.setDaemon(true);
    }

    public void start() {
        workerThread.start();
        LOGGER.info("TTS playback worker started");
    }

    public void shutdown() {
        workerThread.interrupt();
        queue.clear();
        SpatialAudioPlayer.cleanupAll();
        LOGGER.info("TTS playback worker stopped");
    }

    public void enqueue(TtsRequest request) {
        while (!queue.offer(request)) {
            queue.poll();
        }
    }

    private void run() {
        while (!Thread.currentThread().isInterrupted()) {
            try {
                TtsRequest request = queue.take();
                processMessage(request);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                break;
            } catch (Exception e) {
                LOGGER.error("Error processing TTS message", e);
            }
        }
    }

    private void processMessage(TtsRequest request) {
        // Pick the engine for the sender's model (falls back to default if unavailable)
        ITtsEngine engine = OmnichatClient.getEngineForModel(request.modelName());

        // Use speakerId from request (server voice) if available, otherwise fall back to config
        int speakerId = request.speakerId() >= 0 ? request.speakerId() : config.getSpeakerId();

        float[] samples = engine.generate(request.text(), speakerId, config.getSpeed());
        if (samples == null || samples.length == 0) {
            return;
        }

        if (config.isRobotEffect()) {
            AudioUtils.applyRobotEffect(samples, engine.getSampleRate());
        }

        byte[] pcmData = AudioUtils.floatPcmToInt16(samples, config.getVolume());

        if (request.senderUuid() != null) {
            SpatialAudioPlayer.playSpatial(pcmData, engine.getSampleRate(), request.senderUuid());
        } else {
            SpatialAudioPlayer.playMono(pcmData, engine.getSampleRate());
        }
    }
}
