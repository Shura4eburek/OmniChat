package org.mamoru.omnichat.client.tts;

/** RMS levels over PCM by playback time, for the preview oscilloscope. */
public final class WaveformMeter {
    private static final int WINDOW_MS = 50;
    private final float[] samples;
    private final int sampleRate;

    public WaveformMeter(float[] samples, int sampleRate) {
        this.samples = samples;
        this.sampleRate = sampleRate;
    }

    public float level(long elapsedMillis) {
        int end = (int) Math.min(samples.length, elapsedMillis * sampleRate / 1000);
        int start = Math.max(0, end - WINDOW_MS * sampleRate / 1000);
        if (end <= start) return 0f;
        double sum = 0;
        for (int i = start; i < end; i++) {
            float v = Math.clamp(samples[i], -1f, 1f);
            sum += v * v;
        }
        return (float) Math.min(1.0, Math.sqrt(sum / (end - start)));
    }

    public float[] bars(long elapsedMillis, int count) {
        float[] out = new float[count];
        for (int i = 0; i < count; i++) out[i] = level(elapsedMillis - (long) (count - 1 - i) * 30);
        return out;
    }

    public boolean finished(long elapsedMillis) {
        return elapsedMillis * sampleRate / 1000 > samples.length;
    }
}
