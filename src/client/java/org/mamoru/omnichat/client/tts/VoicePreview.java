package org.mamoru.omnichat.client.tts;

import net.minecraft.client.MinecraftClient;
import org.mamoru.omnichat.client.OmnichatClient;
import org.mamoru.omnichat.client.config.OmnichatConfig;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Synthesizes a short sample with a given voice and plays it non-positionally. */
public final class VoicePreview {
    private static final Logger LOGGER = LoggerFactory.getLogger("OmniChat");
    private static final ExecutorService EXECUTOR = Executors.newSingleThreadExecutor(r -> {
        Thread t = new Thread(r, "OmniChat-Preview");
        t.setDaemon(true);
        return t;
    });
    private static final PreviewTickets TICKETS = new PreviewTickets();

    private static volatile String loadingModel;
    private static volatile String playingModel;
    private static volatile WaveformMeter meter;
    private static volatile long startedAt;

    private VoicePreview() {
    }

    public static void play(String model, String sampleText) {
        int ticket = TICKETS.next();
        loadingModel = model;
        playingModel = null;
        meter = null;
        EXECUTOR.execute(() -> {
            ITtsEngine engine = null;
            try {
                if (!TICKETS.isCurrent(ticket)) return;
                engine = TtsService.loadEngineForModel(model);
                if (engine == null || !TICKETS.isCurrent(ticket)) return;
                OmnichatConfig config = OmnichatClient.getConfig();
                float[] samples = engine.generate(sampleText, Math.max(0, config.getSpeakerId()), config.getSpeed());
                if (samples == null || samples.length == 0 || !TICKETS.isCurrent(ticket)) return;
                byte[] pcm = AudioUtils.floatPcmToInt16(samples, config.getVolume());
                int rate = engine.getSampleRate();
                MinecraftClient.getInstance().execute(() -> {
                    if (!TICKETS.isCurrent(ticket)) return;
                    meter = new WaveformMeter(samples, rate);
                    startedAt = System.currentTimeMillis();
                    playingModel = model;
                    SpatialAudioPlayer.playMono(pcm, rate, () -> TICKETS.isCurrent(ticket));
                });
            } catch (Exception | LinkageError e) {
                LOGGER.warn("Voice preview of '{}' failed: {}", model, e.toString());
            } finally {
                if (TICKETS.isCurrent(ticket)) loadingModel = null;
                if (engine != null) engine.release();
            }
        });
    }

    /** Invalidates any pending or playing preview (closing the screen, switching voice). */
    public static void stop() {
        TICKETS.next();
        loadingModel = null;
        playingModel = null;
        meter = null;
    }

    public static boolean isLoading(String model) {
        return model != null && model.equals(loadingModel);
    }

    public static String playingModel() {
        WaveformMeter m = meter;
        if (m != null && m.finished(System.currentTimeMillis() - startedAt)) {
            playingModel = null;
            meter = null;
        }
        return playingModel;
    }

    public static float[] bars(int count) {
        WaveformMeter m = meter;
        return m == null ? new float[count] : m.bars(System.currentTimeMillis() - startedAt, count);
    }
}
