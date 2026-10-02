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

    /** Below this level the limiter is transparent; above it peaks are compressed smoothly. */
    private static final float LIMITER_THRESHOLD = 0.9f;

    /**
     * Converts float PCM to little-endian int16, applying {@code volume} as gain (0..2).
     * Instead of hard-clipping at full scale (which audibly distorts speech when volume
     * is above 1), peaks over {@link #LIMITER_THRESHOLD} go through a tanh soft knee that
     * approaches but never exceeds 1.0. Samples below the threshold are scaled linearly.
     */
    public static byte[] floatPcmToInt16(float[] samples, float volume) {
        byte[] bytes = new byte[samples.length * 2];
        for (int i = 0; i < samples.length; i++) {
            float val = softLimit(samples[i] * volume);
            short s = (short) (val * Short.MAX_VALUE);
            // little-endian
            bytes[i * 2] = (byte) (s & 0xFF);
            bytes[i * 2 + 1] = (byte) ((s >> 8) & 0xFF);
        }
        return bytes;
    }

    static float softLimit(float x) {
        if (Float.isNaN(x)) return 0f;
        float abs = Math.abs(x);
        if (abs <= LIMITER_THRESHOLD) return x;
        float headroom = 1.0f - LIMITER_THRESHOLD;
        float limited = LIMITER_THRESHOLD + headroom * (float) Math.tanh((abs - LIMITER_THRESHOLD) / headroom);
        return Math.copySign(Math.min(limited, 1.0f), x);
    }
}
