package org.mamoru.omnichat.client.ui;

import org.mamoru.omnichat.client.config.OmnichatConfig;
import org.mamoru.omnichat.client.tts.ModelRepair;
import org.mamoru.omnichat.client.tts.ModelRepair.Health;
import org.mamoru.omnichat.util.ModelScanner;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.Executor;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicLong;
import java.util.function.Function;
import java.util.function.LongSupplier;

/**
 * Background {@link ModelRepair#check} results per installed model, re-checked when the model's .onnx
 * file changes (mtime, looked at no more than every {@link #RECHECK_NANOS} per model, so the render
 * thread doesn't stat files every frame). {@link #get} never blocks: it returns null while pending;
 * a model whose folder is missing gets an INCOMPATIBLE (READ_ERROR) result.
 * The Voice tab notices new results through its periodic rebuild signature, not a callback.
 */
public final class ModelHealthCache {
    static final long RECHECK_NANOS = 2_000_000_000L;

    public static final ModelHealthCache INSTANCE = new ModelHealthCache(OmnichatConfig::resolveModelDir,
            ModelRepair::check, Executors.newSingleThreadExecutor(r -> {
                Thread t = new Thread(r, "OmniChat-Model-Check");
                t.setDaemon(true);
                return t;
            }), System::nanoTime);

    // A model whose folder can't be found: settled, so the tab doesn't show "checking" forever
    private static final Health MISSING = new Health(ModelRepair.Status.INCOMPATIBLE, ModelRepair.Reason.READ_ERROR,
            "model folder not found", "", java.util.List.of());

    private static final class Result {
        final Health health;
        final Path onnx;
        final long mtime;
        final boolean missing;
        volatile long verifiedAt;

        Result(Health health, Path onnx, long mtime, boolean missing, long verifiedAt) {
            this.health = health;
            this.onnx = onnx;
            this.mtime = mtime;
            this.missing = missing;
            this.verifiedAt = verifiedAt;
        }
    }

    private final Function<String, Path> resolver;
    private final Function<Path, Health> checker;
    private final Executor executor;
    private final LongSupplier clock;
    private final Map<String, Result> results = new ConcurrentHashMap<>();
    // model -> token of the check in flight; invalidate/clear drop it so a stale check can't store
    private final Map<String, Object> pending = new ConcurrentHashMap<>();

    ModelHealthCache(Function<String, Path> resolver, Function<Path, Health> checker, Executor executor, LongSupplier clock) {
        this.resolver = resolver;
        this.checker = checker;
        this.executor = executor;
        this.clock = clock;
    }

    /** Cached health, or null while the check is pending (one is started if needed). Any thread. */
    public Health get(String model) {
        Result r = results.get(model);
        if (r != null) {
            long now = clock.getAsLong();
            if (now - r.verifiedAt < RECHECK_NANOS) return r.health;
            if (r.missing ? !exists(resolver.apply(model)) : r.onnx == null || mtime(r.onnx) == r.mtime) {
                r.verifiedAt = now;
                return r.health;
            }
            results.remove(model, r);
        }
        Path dir = resolver.apply(model);
        if (!exists(dir)) {
            results.put(model, new Result(MISSING, null, 0, true, clock.getAsLong()));
            return MISSING;
        }
        Object token = new Object();
        if (pending.putIfAbsent(model, token) == null) {
            executor.execute(() -> run(model, dir, token));
        }
        return null;
    }

    private void run(String model, Path dir, Object token) {
        Path onnx = onnxOf(dir);
        long mtime = mtime(onnx);
        Health h;
        try {
            h = checker.apply(dir);
        } catch (RuntimeException | Error e) {
            pending.remove(model, token); // let a later get() retry
            throw e;
        }
        // Store only if this check wasn't invalidated meanwhile (compute is atomic per model)
        pending.computeIfPresent(model, (m, t) -> {
            if (t != token) return t;
            results.put(model, new Result(h, onnx, mtime, false, clock.getAsLong()));
            return null;
        });
    }

    /** The model's files changed: forget its result and any check in flight for it. Other models are kept. */
    public void invalidate(String model) {
        pending.remove(model);
        results.remove(model);
    }

    /** Disconnect: forget everything (the next server may ship other models). */
    public void clear() {
        pending.clear();
        results.clear();
    }

    private static boolean exists(Path dir) {
        return dir != null && Files.isDirectory(dir);
    }

    private static Path onnxOf(Path dir) {
        try {
            if (ModelScanner.detectType(dir) == ModelScanner.ModelType.GLADOS) return null;
            return ModelScanner.resolveOnnxModel(dir);
        } catch (RuntimeException e) {
            return null;
        }
    }

    private static long mtime(Path file) {
        if (file == null) return 0;
        try {
            return Files.getLastModifiedTime(file).toMillis();
        } catch (IOException e) {
            return -1;
        }
    }
}
