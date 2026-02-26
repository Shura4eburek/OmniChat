package org.mamoru.omnichat.client.tts;

public final class AudioUtils {

    private AudioUtils() {
    }

    public static void applyRobotEffect(float[] samples, int sampleRate) {
        // Ring modulation — metallic tone
        for (int i = 0; i < samples.length; i++) {
            samples[i] *= (float) Math.sin(2.0 * Math.PI * 40.0 * i / sampleRate);
        }
        // Bitcrusher — quantize to 8 levels
        for (int i = 0; i < samples.length; i++) {
            samples[i] = Math.round(samples[i] * 8.0f) / 8.0f;
        }
        // Downsample — sample-and-hold with factor 4
        for (int i = 0; i < samples.length; i += 4) {
            float held = samples[i];
            for (int j = 1; j < 4 && i + j < samples.length; j++) {
                samples[i + j] = held;
            }
        }
    }

    public static byte[] floatPcmToInt16(float[] samples, float volume) {
        byte[] bytes = new byte[samples.length * 2];
        for (int i = 0; i < samples.length; i++) {
            float val = samples[i] * volume;
            val = Math.max(-1.0f, Math.min(1.0f, val));
            short s = (short) (val * Short.MAX_VALUE);
            // little-endian
            bytes[i * 2] = (byte) (s & 0xFF);
            bytes[i * 2 + 1] = (byte) ((s >> 8) & 0xFF);
        }
        return bytes;
    }
}
