package org.mamoru.omnichat.client.ui;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.mamoru.omnichat.client.tts.ModelRepair.Health;
import org.mamoru.omnichat.client.tts.ModelRepair.Status;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.FileTime;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.*;

class ModelHealthCacheTest {
    @TempDir
    Path root;

    final List<Runnable> queued = new ArrayList<>();
    final AtomicInteger checks = new AtomicInteger();
    final List<String> notified = new ArrayList<>();

    ModelHealthCache cache() {
        ModelHealthCache c = new ModelHealthCache(m -> {
            Path d = root.resolve(m);
            return Files.isDirectory(d) ? d : null;
        }, dir -> {
            checks.incrementAndGet();
            return new Health(Status.FIXABLE, "p", "ru", List.of());
        }, queued::add);
        c.setListener(notified::add);
        return c;
    }

    void runQueued() {
        List<Runnable> now = new ArrayList<>(queued);
        queued.clear();
        now.forEach(Runnable::run);
    }

    Path model(String name) throws Exception {
        Path d = Files.createDirectories(root.resolve(name));
        Files.write(d.resolve("m.onnx"), new byte[]{1});
        return d;
    }

    @Test
    void pendingThenCachedAndNotified() throws Exception {
        model("a");
        ModelHealthCache c = cache();
        assertNull(c.get("a"));
        assertNull(c.get("a"));
        assertEquals(1, queued.size(), "one check per model while pending");
        runQueued();
        assertEquals(Status.FIXABLE, c.get("a").status());
        assertEquals(List.of("a"), notified);
        c.get("a");
        assertTrue(queued.isEmpty());
        assertEquals(1, checks.get());
    }

    @Test
    void missingModelIsNotChecked() {
        ModelHealthCache c = cache();
        assertNull(c.get("nope"));
        assertTrue(queued.isEmpty());
    }

    @Test
    void changedOnnxMtimeRechecks() throws Exception {
        Path d = model("a");
        ModelHealthCache c = cache();
        c.get("a");
        runQueued();
        Files.setLastModifiedTime(d.resolve("m.onnx"), FileTime.fromMillis(Files.getLastModifiedTime(d.resolve("m.onnx")).toMillis() + 5000));
        assertNull(c.get("a"));
        runQueued();
        assertNotNull(c.get("a"));
        assertEquals(2, checks.get());
    }

    @Test
    void invalidateAndClearDropResultsAndInFlightChecks() throws Exception {
        model("a");
        ModelHealthCache c = cache();
        c.get("a");
        runQueued();
        c.invalidate("a");
        assertNull(c.get("a"));
        c.clear(); // the queued check now belongs to an old generation
        runQueued();
        assertNull(c.get("a"), "stale in-flight result must not be stored");
        runQueued();
        assertNotNull(c.get("a"));
    }
}
