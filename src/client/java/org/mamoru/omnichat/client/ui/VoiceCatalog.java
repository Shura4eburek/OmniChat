package org.mamoru.omnichat.client.ui;

import net.minecraft.client.MinecraftClient;
import org.mamoru.omnichat.client.config.OmnichatConfig;
import org.mamoru.omnichat.client.network.ModelDownloadManager;
import org.mamoru.omnichat.client.network.VoiceCache;
import org.mamoru.omnichat.voice.VoiceMeta;
import org.mamoru.omnichat.voice.VoiceMetaReader;

import java.nio.file.Path;
import java.util.*;

/** Everything the Voice tab shows: server voices, local-only voices and their download state. */
public final class VoiceCatalog {
    public enum State { INSTALLED, REMOTE, DOWNLOADING, FAILED }

    public record Entry(VoiceMeta meta, State state, float progress, String failure, boolean onServer) {
    }

    private VoiceCatalog() {
    }

    public static List<Entry> build(List<VoiceMeta> server, List<VoiceMeta> local,
                                    Map<String, Float> downloads, Map<String, String> failures) {
        Map<String, VoiceMeta> localByModel = new LinkedHashMap<>();
        for (VoiceMeta m : local) localByModel.put(m.model(), m);

        List<Entry> out = new ArrayList<>();
        Set<String> seen = new HashSet<>();
        for (VoiceMeta s : server) {
            if (!seen.add(s.model())) continue;
            VoiceMeta l = localByModel.get(s.model());
            out.add(entry(l != null ? l : s, l != null, downloads, failures, true));
        }
        List<String> localOnly = new ArrayList<>();
        for (String model : localByModel.keySet()) {
            if (!seen.contains(model)) localOnly.add(model);
        }
        Collections.sort(localOnly);
        for (String model : localOnly) {
            out.add(entry(localByModel.get(model), true, downloads, failures, false));
        }
        return out;
    }

    private static Entry entry(VoiceMeta meta, boolean installed, Map<String, Float> downloads,
                               Map<String, String> failures, boolean onServer) {
        Float progress = downloads.get(meta.model());
        if (progress != null) return new Entry(meta, State.DOWNLOADING, progress, "", onServer);
        if (installed) return new Entry(meta, State.INSTALLED, 1f, "", onServer);
        String failure = failures.get(meta.model());
        if (failure != null) return new Entry(meta, State.FAILED, 0f, failure, onServer);
        return new Entry(meta, State.REMOTE, 0f, "", onServer);
    }

    public static String selectOrFallback(List<Entry> entries, String selected, String configured) {
        if (entries.isEmpty()) return null;
        if (contains(entries, selected)) return selected;
        if (contains(entries, configured)) return configured;
        return entries.get(0).meta().model();
    }

    private static boolean contains(List<Entry> entries, String model) {
        if (model == null) return false;
        for (Entry e : entries) {
            if (e.meta().model().equals(model)) return true;
        }
        return false;
    }

    // Local metadata is read once per model (folder size walks hundreds of files); see invalidateLocal
    private static final Map<String, VoiceMeta> LOCAL_CACHE = new HashMap<>();

    /** Live catalog from the client's real sources. Render thread. */
    public static List<Entry> current() {
        List<VoiceMeta> local = new ArrayList<>();
        for (String model : OmnichatConfig.listAvailableModels()) {
            Path dir = OmnichatConfig.resolveModelDir(model);
            if (dir != null) local.add(LOCAL_CACHE.computeIfAbsent(model, m -> VoiceMetaReader.read(dir, m)));
        }
        ModelDownloadManager downloads = ModelDownloadManager.getInstance();
        return build(VoiceCache.getInstance().getCatalog(), local, downloads.getActiveDownloads(), downloads.getFailures());
    }

    /** Forget cached local metadata (a model was installed or replaced). Any thread. */
    public static void invalidateLocal(String model) {
        MinecraftClient.getInstance().execute(() -> LOCAL_CACHE.remove(model));
    }

    /**
     * What the Voice tab shows, without array identity: used to decide whether to rebuild.
     * (VoiceMeta holds a byte[], so record equality would never match.)
     */
    public static List<String> signature(List<Entry> entries) {
        List<String> out = new ArrayList<>(entries.size());
        for (Entry e : entries) {
            out.add(e.meta().model() + "|" + e.meta().name() + "|" + e.state() + "|"
                    + Math.round(e.progress() * 100) + "|" + e.failure() + "|" + e.onServer());
        }
        return out;
    }
}
