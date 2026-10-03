package org.mamoru.omnichat.client.ui;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.mamoru.omnichat.client.tts.ModelRepair.Health;
import org.mamoru.omnichat.client.tts.ModelRepair.Reason;
import org.mamoru.omnichat.client.tts.ModelRepair.Status;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.FileTime;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

import static org.junit.jupiter.api.Assertions.*;

class ModelHealthCacheTest {
    @TempDir
    Path root;

    final List<Runnable> queued = new ArrayList<>();
    final AtomicInteger checks = new AtomicInteger();
    final AtomicLong clock = new AtomicLong(1_000_000_000L);

    ModelHealthCache cache() {
        return new ModelHealthCache(m -> {
            Path d = root.resolve(m);
            return Files.isDirectory(d) ? d : null;
        }, dir -> {
            checks.incrementAndGet();
            return new Health(Status.FIXABLE, Reason.MISSING_VOICE, "p", "ru", List.of());
        }, queued::add, clock::get);
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

    void bumpMtime(Path d) throws Exception {
        Path f = d.resolve("m.onnx");
        Files.setLastModifiedTime(f, FileTime.fromMillis(Files.getLastModifiedTime(f).toMillis() + 5000));
    }

    @Test
    void pendingThenCached() throws Exception {
        model("a");
        ModelHealthCache c = cache();
        assertNull(c.get("a"));
        assertNull(c.get("a"));
        assertEquals(1, queued.size(), "one check per model while pending");
        runQueued();
        assertEquals(Status.FIXABLE, c.get("a").status());
        c.get("a");
        assertTrue(queued.isEmpty());
        assertEquals(1, checks.get());
    }

    @Test
    void missingModelSettlesOnReadError() throws Exception {
        ModelHealthCache c = cache();
        Health h = c.get("nope");
        assertNotNull(h, "never pending forever");
        assertEquals(Status.INCOMPATIBLE, h.status());
        assertEquals(Reason.READ_ERROR, h.reason());
        assertSame(h, c.get("nope"), "cached");
        assertTrue(queued.isEmpty());
        // The folder shows up later: after the re-check interval it gets a real check
        model("nope");
        assertSame(h, c.get("nope"));
        clock.addAndGet(ModelHealthCache.RECHECK_NANOS + 1);
        assertNull(c.get("nope"));
        runQueued();
        assertEquals(Status.FIXABLE, c.get("nope").status());
    }

    @Test
    void mtimeIsOnlyRecheckedAfterTheInterval() throws Exception {
        Path d = model("a");
        ModelHealthCache c = cache();
        c.get("a");
        runQueued();
        bumpMtime(d);
        assertNotNull(c.get("a"), "within the interval the file isn't looked at");
        clock.addAndGet(ModelHealthCache.RECHECK_NANOS + 1);
        assertNull(c.get("a"), "changed file -> re-check");
        runQueued();
        assertNotNull(c.get("a"));
        assertEquals(2, checks.get());
    }

    @Test
    void unchangedFileStaysCachedAfterTheInterval() throws Exception {
        model("a");
        ModelHealthCache c = cache();
        c.get("a");
        runQueued();
        clock.addAndGet(ModelHealthCache.RECHECK_NANOS + 1);
        assertNotNull(c.get("a"));
        assertTrue(queued.isEmpty());
    }

    @Test
    void invalidateOnlyDropsThatModel() throws Exception {
        model("a");
        model("b");
        ModelHealthCache c = cache();
        c.get("a");
        c.get("b");
        c.invalidate("a"); // a's in-flight check is stale, b's is not
        runQueued();
        assertNull(c.get("a"), "stale in-flight result must not be stored");
        assertNotNull(c.get("b"), "other models keep their in-flight result");
        runQueued();
        assertNotNull(c.get("a"));
    }

    @Test
    void clearDropsEverythingInFlight() throws Exception {
        model("a");
        ModelHealthCache c = cache();
        c.get("a");
        c.clear();
        runQueued();
        assertNull(c.get("a"));
        runQueued();
        assertNotNull(c.get("a"));
    }
}
