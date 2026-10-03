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
import java.util.function.Consumer;
import java.util.function.Function;

/**
 * Background {@link ModelRepair#check} results per installed model, keyed by model name and invalidated
 * when the model's .onnx file changes (mtime). {@link #get} never blocks: it returns null while pending.
 */
public final class ModelHealthCache {
    public static final ModelHealthCache INSTANCE = new ModelHealthCache(OmnichatConfig::resolveModelDir,
            ModelRepair::check, Executors.newSingleThreadExecutor(r -> {
                Thread t = new Thread(r, "OmniChat-Model-Check");
                t.setDaemon(true);
                return t;
            }));

    private record Result(Health health, Path onnx, long mtime) {
    }

    private final Function<String, Path> resolver;
    private final Function<Path, Health> checker;
    private final Executor executor;
    private final Map<String, Result> results = new ConcurrentHashMap<>();
    private final Map<String, Long> pending = new ConcurrentHashMap<>();
    // Bumped by invalidate/clear: a check started before that must not store its (stale) result
    private final AtomicLong generation = new AtomicLong();
    private volatile Consumer<String> listener = m -> {
    };

    ModelHealthCache(Function<String, Path> resolver, Function<Path, Health> checker, Executor executor) {
        this.resolver = resolver;
        this.checker = checker;
        this.executor = executor;
    }

    /** Called on the checking thread with the model name whenever a new result is stored. */
    public void setListener(Consumer<String> listener) {
        this.listener = listener;
    }

    /** Cached health, or null while the check is pending (one is started if needed). Any thread. */
    public Health get(String model) {
        Result r = results.get(model);
        if (r != null && fresh(r)) return r.health();
        if (r != null) results.remove(model, r);
        Path dir = resolver.apply(model);
        if (dir == null || !Files.isDirectory(dir)) return null;
        long gen = generation.get();
        if (pending.putIfAbsent(model, gen) == null) {
            executor.execute(() -> run(model, dir, gen));
        }
        return null;
    }

    private void run(String model, Path dir, long gen) {
        boolean stored = false;
        try {
            Path onnx = onnxOf(dir);
            long mtime = mtime(onnx);
            Health h = checker.apply(dir);
            if (generation.get() == gen) {
                results.put(model, new Result(h, onnx, mtime));
                stored = true;
            }
        } finally {
            pending.remove(model, gen);
        }
        if (stored) listener.accept(model);
    }

    public void invalidate(String model) {
        generation.incrementAndGet();
        results.remove(model);
        pending.remove(model);
    }

    /** Disconnect: forget everything (the next server may ship other models). */
    public void clear() {
        generation.incrementAndGet();
        results.clear();
        pending.clear();
    }

    private static boolean fresh(Result r) {
        return r.onnx() == null || mtime(r.onnx()) == r.mtime();
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
