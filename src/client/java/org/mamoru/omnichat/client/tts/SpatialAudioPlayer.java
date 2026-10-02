package org.mamoru.omnichat.client.tts;

import net.minecraft.client.MinecraftClient;
import net.minecraft.client.render.Camera;
import net.minecraft.entity.player.PlayerEntity;
import net.minecraft.util.math.Vec3d;
import org.lwjgl.openal.AL10;
import org.lwjgl.openal.AL11;
import org.lwjgl.openal.ALC10;
import org.mamoru.omnichat.client.HearingRange;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.ArrayDeque;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;
import java.util.UUID;
import java.util.function.BooleanSupplier;

/**
 * Plays TTS clips on raw OpenAL sources in Minecraft's AL context.
 * <p>
 * Clips are serialized per sender (a new clip waits until the previous one stops) and the
 * number of simultaneously playing sources is capped. All state is guarded by {@link #LOCK}
 * because the sound-engine shutdown hook ({@link #onSoundEngineClosing()}) may run off the
 * render thread.
 */
public class SpatialAudioPlayer {
    private static final Logger LOGGER = LoggerFactory.getLogger("OmniChat");

    /** Linear attenuation reaches silence here, matching the chat hearing range. */
    private static final float MAX_DISTANCE = (float) HearingRange.BLOCKS;
    private static final float REFERENCE_DISTANCE = 4.0f;
    /** Sources are only force-stopped well beyond the point where they are already silent. */
    private static final double STOP_DISTANCE = HearingRange.BLOCKS * 2.0;

    /** Global cap on simultaneously playing TTS sources (vanilla shares the same AL source pool). */
    private static final int MAX_ACTIVE_SOURCES = 8;
    /** Clips waiting behind the currently playing one, per sender; oldest are dropped beyond this. */
    private static final int MAX_PENDING_PER_SENDER = 3;

    /** Queue key for non-positional (mono) playback. */
    private static final UUID MONO_KEY = new UUID(0L, 0L);

    private static final Object LOCK = new Object();
    private static final Map<UUID, ActiveSource> playing = new LinkedHashMap<>();
    private static final Map<UUID, ArrayDeque<Clip>> pending = new LinkedHashMap<>();

    private record ActiveSource(int sourceId, int bufferId, UUID senderUuid) {}

    /** {@code senderUuid == null} means mono playback. */
    private record Clip(byte[] pcm, int sampleRate, UUID senderUuid, BooleanSupplier active) {}

    public static void playSpatial(byte[] pcm, int sampleRate, UUID senderUuid) {
        playSpatial(pcm, sampleRate, senderUuid, () -> true);
    }

    /** {@code active} is checked on the render thread, so nothing starts after the caller shut down. */
    public static void playSpatial(byte[] pcm, int sampleRate, UUID senderUuid, BooleanSupplier active) {
        submit(new Clip(pcm, sampleRate, senderUuid, active), senderUuid);
    }

    public static void playMono(byte[] pcm, int sampleRate) {
        playMono(pcm, sampleRate, () -> true);
    }

    public static void playMono(byte[] pcm, int sampleRate, BooleanSupplier active) {
        submit(new Clip(pcm, sampleRate, null, active), MONO_KEY);
    }

    private static void submit(Clip clip, UUID key) {
        MinecraftClient.getInstance().execute(() -> {
            if (!clip.active().getAsBoolean()) return;
            synchronized (LOCK) {
                try {
                    reapStopped();
                    ArrayDeque<Clip> queue = pending.computeIfAbsent(key, k -> new ArrayDeque<>());
                    queue.addLast(clip);
                    while (queue.size() > MAX_PENDING_PER_SENDER) {
                        queue.pollFirst();
                        LOGGER.warn("TTS queue full for one sender, dropped oldest pending clip");
                    }
                    startPending();
                } catch (Exception e) {
                    LOGGER.error("Failed to queue TTS audio", e);
                }
            }
        });
    }

    public static void tick() {
        synchronized (LOCK) {
            if (playing.isEmpty() && pending.isEmpty()) return;
            try {
                reapStopped();
                updatePositions();
                startPending();
            } catch (Exception e) {
                LOGGER.error("TTS audio tick failed", e);
            }
        }
    }

    public static void cleanupAll() {
        MinecraftClient.getInstance().execute(() -> {
            synchronized (LOCK) {
                pending.clear();
                releaseAll();
            }
        });
    }

    /**
     * Called (via mixin) right before Minecraft's {@code SoundEngine} destroys its AL context,
     * e.g. on F3+T / resource reload, audio-device change or shutdown. The context is still
     * current here, so our sources and buffers are freed properly; afterwards no stale AL ids
     * remain that could alias vanilla's sources in the new context. Pending clips hold only PCM
     * and start again once the new context is up.
     */
    public static void onSoundEngineClosing() {
        synchronized (LOCK) {
            if (playing.isEmpty()) return;
            try {
                if (ALC10.alcGetCurrentContext() != 0L) {
                    releaseAll();
                    return;
                }
            } catch (Throwable t) {
                LOGGER.warn("Failed to release TTS sources before sound engine shutdown", t);
            }
            playing.clear();
        }
    }

    private static void startPending() {
        Iterator<Map.Entry<UUID, ArrayDeque<Clip>>> it = pending.entrySet().iterator();
        while (it.hasNext()) {
            Map.Entry<UUID, ArrayDeque<Clip>> entry = it.next();
            UUID key = entry.getKey();
            ArrayDeque<Clip> queue = entry.getValue();
            if (playing.containsKey(key)) continue;

            while (!queue.isEmpty() && playing.size() < MAX_ACTIVE_SOURCES) {
                Clip clip = queue.pollFirst();
                if (!clip.active().getAsBoolean()) continue;
                Vec3d pos = null;
                if (clip.senderUuid() != null) {
                    // Synthesis is async: the sender may have left, changed dimension or walked
                    // away since the message arrived. Never fall back to the origin or the camera.
                    pos = audiblePosition(clip.senderUuid());
                    if (pos == null) {
                        LOGGER.debug("Dropping TTS clip: sender gone or out of hearing range");
                        continue;
                    }
                }
                ActiveSource source = start(clip, pos);
                if (source != null) {
                    playing.put(key, source);
                    break;
                }
            }
            if (queue.isEmpty()) it.remove();
            if (playing.size() >= MAX_ACTIVE_SOURCES) return;
        }
    }

    /**
     * Creates buffer + source and starts playback. Returns null (with nothing leaked) on AL failure.
     * {@code pos} is the sender position for spatial clips and is ignored for mono ones.
     */
    private static ActiveSource start(Clip clip, Vec3d pos) {
        AL10.alGetError(); // clear stale state so the checks below report our own calls

        int buffer = AL10.alGenBuffers();
        if (failed("alGenBuffers")) return null;

        ByteBuffer data = ByteBuffer.allocateDirect(clip.pcm().length)
                .order(ByteOrder.nativeOrder())
                .put(clip.pcm())
                .flip();
        AL10.alBufferData(buffer, AL10.AL_FORMAT_MONO16, data, clip.sampleRate());
        if (failed("alBufferData")) {
            deleteQuietly(0, buffer);
            return null;
        }

        int source = AL10.alGenSources();
        if (failed("alGenSources")) {
            deleteQuietly(0, buffer);
            return null;
        }

        AL10.alSourcei(source, AL10.AL_BUFFER, buffer);
        boolean spatial = clip.senderUuid() != null;
        if (spatial) {
            // Same model as vanilla Source.setAttenuation (AL_SOURCE_DISTANCE_MODEL is enabled by
            // vanilla SoundEngine.init); clamped so it is full volume within REFERENCE_DISTANCE.
            AL10.alSourcei(source, AL11.AL_DISTANCE_MODEL, AL11.AL_LINEAR_DISTANCE_CLAMPED);
            AL10.alSourcef(source, AL10.AL_REFERENCE_DISTANCE, REFERENCE_DISTANCE);
            AL10.alSourcef(source, AL10.AL_MAX_DISTANCE, MAX_DISTANCE);
            AL10.alSourcef(source, AL10.AL_ROLLOFF_FACTOR, 1.0f);
            AL10.alSourcei(source, AL10.AL_SOURCE_RELATIVE, AL10.AL_FALSE);
            AL10.alSource3f(source, AL10.AL_POSITION, (float) pos.x, (float) pos.y, (float) pos.z);
        } else {
            // Like vanilla Source.disableAttenuation for relative sounds.
            AL10.alSourcei(source, AL11.AL_DISTANCE_MODEL, AL10.AL_NONE);
            AL10.alSourcei(source, AL10.AL_SOURCE_RELATIVE, AL10.AL_TRUE);
            AL10.alSource3f(source, AL10.AL_POSITION, 0.0f, 0.0f, 0.0f);
        }
        if (failed("source setup")) {
            deleteQuietly(source, buffer);
            return null;
        }

        AL10.alSourcePlay(source);
        if (failed("alSourcePlay")) {
            deleteQuietly(source, buffer);
            return null;
        }
        logStarted(source, clip.pcm(), clip.sampleRate(), spatial ? "spatial" : "mono");
        return new ActiveSource(source, buffer, clip.senderUuid());
    }

    // pcm is 16-bit mono, so 2 bytes per sample
    private static void logStarted(int source, byte[] pcm, int sampleRate, String kind) {
        double seconds = pcm.length / 2.0 / sampleRate;
        int state = AL10.alGetSourcei(source, AL10.AL_SOURCE_STATE);
        if (state == AL10.AL_PLAYING) {
            LOGGER.info("TTS playing ({}): {}s", kind, String.format(Locale.ROOT, "%.1f", seconds));
        } else {
            LOGGER.warn("TTS source not playing ({}): AL state {}, error {}", kind, state, AL10.alGetError());
        }
    }

    /** Removes sources that finished, or whose id is no longer valid (state query errors). */
    private static void reapStopped() {
        Iterator<ActiveSource> it = playing.values().iterator();
        while (it.hasNext()) {
            ActiveSource active = it.next();
            int state = AL10.alGetSourcei(active.sourceId(), AL10.AL_SOURCE_STATE);
            int error = AL10.alGetError();
            if (error != AL10.AL_NO_ERROR || (state != AL10.AL_PLAYING && state != AL10.AL_PAUSED)) {
                deleteQuietly(active.sourceId(), active.bufferId());
                it.remove();
            }
        }
    }

    private static void updatePositions() {
        MinecraftClient client = MinecraftClient.getInstance();
        if (client.world == null) return;
        Vec3d listener = listenerPosition();

        Iterator<ActiveSource> it = playing.values().iterator();
        while (it.hasNext()) {
            ActiveSource active = it.next();
            if (active.senderUuid() == null) continue;
            Vec3d pos = senderPosition(active.senderUuid());
            // Sender unloaded, left or changed dimension: its frozen position is meaningless now
            if (pos == null || (listener != null && listener.distanceTo(pos) > STOP_DISTANCE)) {
                AL10.alSourceStop(active.sourceId());
                deleteQuietly(active.sourceId(), active.bufferId());
                it.remove();
                continue;
            }
            AL10.alSource3f(active.sourceId(), AL10.AL_POSITION,
                    (float) pos.x, (float) pos.y, (float) pos.z);
        }
        AL10.alGetError();
    }

    /** Sender position if the sender is loaded and within hearing range of the listener, else null. */
    private static Vec3d audiblePosition(UUID senderUuid) {
        Vec3d pos = senderPosition(senderUuid);
        if (pos == null) return null;
        Vec3d listener = listenerPosition();
        if (listener == null || listener.distanceTo(pos) > HearingRange.BLOCKS) return null;
        return pos;
    }

    private static Vec3d senderPosition(UUID senderUuid) {
        MinecraftClient client = MinecraftClient.getInstance();
        if (client.world == null) return null;
        PlayerEntity sender = client.world.getPlayerByUuid(senderUuid);
        return sender != null ? sender.getEntityPos() : null;
    }

    /** The OpenAL listener follows the camera, not the player entity (third person, spectator). */
    private static Vec3d listenerPosition() {
        MinecraftClient client = MinecraftClient.getInstance();
        if (client.gameRenderer != null) {
            Camera camera = client.gameRenderer.getCamera();
            if (camera != null && camera.isReady()) return camera.getCameraPos();
        }
        return client.player != null ? client.player.getEntityPos() : null;
    }

    private static void releaseAll() {
        for (ActiveSource active : playing.values()) {
            AL10.alSourceStop(active.sourceId());
            deleteQuietly(active.sourceId(), active.bufferId());
        }
        playing.clear();
    }

    /** Deletes source then buffer (0 = skip) and swallows the resulting AL error state. */
    private static void deleteQuietly(int source, int buffer) {
        if (source != 0) AL10.alDeleteSources(source);
        if (buffer != 0) AL10.alDeleteBuffers(buffer);
        AL10.alGetError();
    }

    private static boolean failed(String op) {
        int error = AL10.alGetError();
        if (error == AL10.AL_NO_ERROR) return false;
        LOGGER.warn("TTS OpenAL {} failed: error 0x{}", op, Integer.toHexString(error));
        return true;
    }
}
