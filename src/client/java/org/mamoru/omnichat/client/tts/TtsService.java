package org.mamoru.omnichat.client.tts;

import net.minecraft.client.MinecraftClient;
import net.minecraft.text.Text;
import org.mamoru.omnichat.client.config.OmnichatConfig;
import org.mamoru.omnichat.client.ui.HudTheme;
import org.mamoru.omnichat.client.ui.HudToast;
import org.mamoru.omnichat.util.ModelScanner;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Owns the TTS playback worker (which in turn owns its engines). Engines are built on a
 * background loader thread and the new worker is published only once it is running, so the
 * render thread never blocks on model loading and a failed load leaves no dead worker behind.
 */
public class TtsService {
    private static final Logger LOGGER = LoggerFactory.getLogger("OmniChat");

    private final OmnichatConfig config;
    private final ExecutorService loader = Executors.newSingleThreadExecutor(r -> {
        Thread t = new Thread(r, "OmniChat-TTS-Loader");
        t.setDaemon(true);
        return t;
    });

    private volatile TtsPlaybackWorker worker;
    // Guarded by this: bumped on every rebuild so a superseded load discards its result
    private int generation;
    private boolean loading;
    // Settings the current/pending worker was built for; other settings are read live
    private BuildKey builtFor;
    // Model the running default engine actually uses (differs from config on fallback)
    private String activeModel;

    private record BuildKey(boolean enabled, String modelPath, int maxQueueSize) {
        static BuildKey of(OmnichatConfig config) {
            return new BuildKey(config.isEnabled(), config.getModelPath(), config.getMaxQueueSize());
        }
    }

    public TtsService(OmnichatConfig config) {
        this.config = config;
    }

    public TtsPlaybackWorker getWorker() {
        return worker;
    }

    public void start() {
        rebuild();
    }

    /**
     * Called after settings were saved. Rebuilds only if a setting the engine/worker is built
     * from changed, or TTS is enabled but has no worker (e.g. a previous load failed).
     * Volume, speed, speaker and robot effect are read live by the worker.
     */
    public synchronized void applySettings() {
        boolean changed = !BuildKey.of(config).equals(builtFor);
        boolean dead = config.isEnabled() && worker == null && !loading;
        if (changed || dead) {
            rebuild();
        }
    }

    /** A model finished downloading: drop its stale cached engine, retry if it was the one we lacked. */
    public synchronized void onModelDownloaded(String modelName) {
        TtsPlaybackWorker current = worker;
        if (current != null) {
            current.evictModel(modelName);
        }
        if (config.isEnabled() && modelName.equals(config.getModelPath())
                && !loading && !modelName.equals(activeModel)) {
            LOGGER.info("Configured model '{}' is now available, reloading TTS", modelName);
            rebuild();
        }
    }

    /** Drops queued and playing speech from the previous server; the worker itself keeps running. */
    public void onDisconnect() {
        TtsPlaybackWorker current = worker;
        if (current != null) {
            current.clearQueue();
        }
        SpatialAudioPlayer.cleanupAll();
    }

    public synchronized void shutdown() {
        generation++;
        TtsPlaybackWorker old = worker;
        worker = null;
        activeModel = null;
        loader.shutdownNow();
        if (old != null) {
            old.shutdown();
        }
    }

    private synchronized void rebuild() {
        int gen = ++generation;
        builtFor = BuildKey.of(config);
        boolean enabled = builtFor.enabled();
        String model = builtFor.modelPath();

        // Unpublish now so no new messages go to the old worker; stop it off the render thread
        TtsPlaybackWorker old = worker;
        worker = null;
        activeModel = null;
        loading = enabled;

        loader.execute(() -> {
            if (old != null) {
                LOGGER.info("Reinitializing TTS engine...");
                old.shutdown();
            }
            if (!enabled) {
                LOGGER.info("OmniChat TTS disabled");
                return;
            }
            if (!isCurrent(gen)) return;
            load(gen, model);
        });
    }

    private void load(int gen, String model) {
        String usedModel = model;
        ITtsEngine engine = createDefaultEngine(model);
        if (engine == null) {
            usedModel = null;
            for (String candidate : OmnichatConfig.listAvailableModels()) {
                if (candidate.equals(model)) continue;
                if (!isCurrent(gen)) return;
                LOGGER.info("Trying fallback model: {}", candidate);
                engine = createDefaultEngine(candidate);
                if (engine != null) {
                    usedModel = candidate;
                    break;
                }
            }
        }

        if (engine == null) {
            LOGGER.error("No working TTS model found. TTS will be disabled.");
            synchronized (this) {
                if (gen == generation) loading = false;
            }
            notifyUser(Text.translatable("omnichat.toast.tts_disabled"), Text.translatable("omnichat.toast.tts_disabled.desc", model));
            return;
        }

        // Fallback stays in memory only: the user's configured model is never overwritten
        TtsPlaybackWorker created = new TtsPlaybackWorker(engine, usedModel, config);
        synchronized (this) {
            if (gen != generation) {
                engine.release();
                return;
            }
            created.start();
            worker = created;
            activeModel = usedModel;
            loading = false;
        }
        if (!usedModel.equals(model)) {
            LOGGER.warn("Using fallback TTS model '{}' instead of '{}'", usedModel, model);
            notifyUser(Text.translatable("omnichat.toast.tts_fallback"), Text.translatable("omnichat.toast.tts_fallback.desc", usedModel, model));
        } else {
            LOGGER.info("TTS engine ready (model '{}')", usedModel);
        }
    }

    private synchronized boolean isCurrent(int gen) {
        return gen == generation;
    }

    private static ITtsEngine createDefaultEngine(String model) {
        Path modelDir = OmnichatConfig.resolveModelDir(model);
        if (modelDir == null || !Files.isDirectory(modelDir)) {
            LOGGER.error("Failed to initialize TTS engine with model '{}': model directory not found", model);
            return null;
        }
        try {
            return createEngineForModel(modelDir);
        } catch (Exception | LinkageError e) {
            LOGGER.error("Failed to initialize TTS engine with model '{}': {}", model, e.getMessage());
            return null;
        }
    }

    static ITtsEngine createEngineForModel(Path modelDir) {
        ModelScanner.requireComplete(modelDir);
        if (ModelScanner.detectType(modelDir) == ModelScanner.ModelType.GLADOS) {
            LOGGER.info("Detected GLaDOS-type model in '{}'", modelDir.getFileName());
            return GladosTtsEngine.create(modelDir);
        }
        return TtsEngine.create(modelDir);
    }

    /**
     * Loads a fresh engine for the given model name, or returns null if the model is
     * unavailable or fails to load (the caller then uses its default engine, uncached).
     */
    static ITtsEngine loadEngineForModel(String name) {
        Path modelDir = OmnichatConfig.resolveModelDir(name);
        if (modelDir == null || !Files.isDirectory(modelDir)) {
            LOGGER.debug("Model '{}' not available locally, using default engine", name);
            return null;
        }
        try {
            LOGGER.info("Loading engine for model '{}'", name);
            return createEngineForModel(modelDir);
        } catch (Exception | LinkageError e) {
            LOGGER.warn("Failed to load engine for model '{}', using default: {}", name, e.toString());
            return null;
        }
    }

    private static void notifyUser(Text title, Text description) {
        HudToast.show(title, description, HudTheme.WARN);
    }
}
