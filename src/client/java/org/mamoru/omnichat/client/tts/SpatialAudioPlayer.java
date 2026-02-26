package org.mamoru.omnichat.client.tts;

import net.minecraft.client.MinecraftClient;
import net.minecraft.entity.player.PlayerEntity;
import net.minecraft.util.math.Vec3d;
import org.lwjgl.openal.AL10;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.UUID;

public class SpatialAudioPlayer {
    private static final Logger LOGGER = LoggerFactory.getLogger("OmniChat");
    private static final float MAX_DISTANCE = 40.0f;
    private static final float REFERENCE_DISTANCE = 4.0f;

    private static final List<ActiveSource> activeSources = new ArrayList<>();

    private record ActiveSource(int sourceId, int bufferId, UUID senderUuid) {}

    public static void playSpatial(byte[] pcm, int sampleRate, UUID senderUuid) {
        MinecraftClient.getInstance().execute(() -> {
            try {
                cleanup();

                MinecraftClient client = MinecraftClient.getInstance();
                Vec3d pos = Vec3d.ZERO;
                if (client.world != null) {
                    PlayerEntity sender = client.world.getPlayerByUuid(senderUuid);
                    if (sender != null) {
                        pos = sender.getEntityPos();
                    }
                }

                int buffer = createBuffer(pcm, sampleRate);
                int source = AL10.alGenSources();

                AL10.alSourcei(source, AL10.AL_BUFFER, buffer);
                AL10.alSourcef(source, AL10.AL_REFERENCE_DISTANCE, REFERENCE_DISTANCE);
                AL10.alSourcef(source, AL10.AL_MAX_DISTANCE, MAX_DISTANCE);
                AL10.alSourcef(source, AL10.AL_ROLLOFF_FACTOR, 1.0f);
                AL10.alSourcei(source, AL10.AL_SOURCE_RELATIVE, AL10.AL_FALSE);
                AL10.alSource3f(source, AL10.AL_POSITION,
                        (float) pos.x, (float) pos.y, (float) pos.z);

                AL10.alSourcePlay(source);
                activeSources.add(new ActiveSource(source, buffer, senderUuid));
            } catch (Exception e) {
                LOGGER.error("Failed to play spatial audio", e);
            }
        });
    }

    public static void playMono(byte[] pcm, int sampleRate) {
        MinecraftClient.getInstance().execute(() -> {
            try {
                cleanup();
                int buffer = createBuffer(pcm, sampleRate);
                int source = AL10.alGenSources();

                AL10.alSourcei(source, AL10.AL_BUFFER, buffer);
                AL10.alSourcei(source, AL10.AL_SOURCE_RELATIVE, AL10.AL_TRUE);
                AL10.alSource3f(source, AL10.AL_POSITION, 0.0f, 0.0f, 0.0f);

                AL10.alSourcePlay(source);
                activeSources.add(new ActiveSource(source, buffer, null));
            } catch (Exception e) {
                LOGGER.error("Failed to play mono audio", e);
            }
        });
    }

    public static void tick() {
        MinecraftClient client = MinecraftClient.getInstance();
        if (client.world == null) return;

        Iterator<ActiveSource> it = activeSources.iterator();
        while (it.hasNext()) {
            ActiveSource active = it.next();
            int state = AL10.alGetSourcei(active.sourceId(), AL10.AL_SOURCE_STATE);
            if (state == AL10.AL_STOPPED) {
                AL10.alDeleteSources(active.sourceId());
                AL10.alDeleteBuffers(active.bufferId());
                it.remove();
                continue;
            }

            if (active.senderUuid() != null && client.player != null) {
                PlayerEntity player = client.world.getPlayerByUuid(active.senderUuid());
                if (player != null) {
                    Vec3d pos = player.getEntityPos();
                    double distance = client.player.getEntityPos().distanceTo(pos);
                    if (distance > MAX_DISTANCE) {
                        AL10.alSourceStop(active.sourceId());
                        AL10.alDeleteSources(active.sourceId());
                        AL10.alDeleteBuffers(active.bufferId());
                        it.remove();
                        continue;
                    }
                    AL10.alSource3f(active.sourceId(), AL10.AL_POSITION,
                            (float) pos.x, (float) pos.y, (float) pos.z);
                }
            }
        }
    }

    public static void cleanupAll() {
        MinecraftClient.getInstance().execute(() -> {
            for (ActiveSource active : activeSources) {
                AL10.alSourceStop(active.sourceId());
                AL10.alDeleteSources(active.sourceId());
                AL10.alDeleteBuffers(active.bufferId());
            }
            activeSources.clear();
        });
    }

    private static void cleanup() {
        Iterator<ActiveSource> it = activeSources.iterator();
        while (it.hasNext()) {
            ActiveSource active = it.next();
            int state = AL10.alGetSourcei(active.sourceId(), AL10.AL_SOURCE_STATE);
            if (state == AL10.AL_STOPPED) {
                AL10.alDeleteSources(active.sourceId());
                AL10.alDeleteBuffers(active.bufferId());
                it.remove();
            }
        }
    }

    private static int createBuffer(byte[] pcm, int sampleRate) {
        int buffer = AL10.alGenBuffers();
        ByteBuffer data = ByteBuffer.allocateDirect(pcm.length)
                .order(ByteOrder.nativeOrder())
                .put(pcm)
                .flip();
        AL10.alBufferData(buffer, AL10.AL_FORMAT_MONO16, data, sampleRate);
        return buffer;
    }
}
