package org.mamoru.omnichat.client.tts;

public interface ITtsEngine {
    float[] generate(String text, int speakerId, float speed);
    int getSampleRate();
    void release();
}
