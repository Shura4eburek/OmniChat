package org.mamoru.omnichat.client.ui;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;

/**
 * Deterministic 16x16 "identicon" for voices without a portrait.png: a mirrored 8x14 mask inside a
 * 1-pixel frame, colored from the model name's hash in the HUD palette family.
 */
public final class PortraitGenerator {
    public static final int SIZE = 16;
    public static final int BACKGROUND = 0xFF15111A;

    private PortraitGenerator() {
    }

    public static int[] generate(String model) {
        byte[] h = hash(model);
        float hue = (h[0] & 0xFF) / 255f;
        int main = hsv(hue, 0.55f, 0.95f);
        int shade = hsv(hue, 0.65f, 0.60f);
        int accent = hsv((hue + 0.5f) % 1f, 0.45f, 1.0f);

        int[] px = new int[SIZE * SIZE];
        java.util.Arrays.fill(px, BACKGROUND);
        int bit = 0;
        for (int y = 1; y < SIZE - 1; y++) {
            for (int x = 1; x < SIZE / 2; x++) {
                boolean on = ((h[1 + (bit >> 3) % 31] >> (bit & 7)) & 1) == 1 || (x >= 5 && y >= 4 && y <= 11);
                bit++;
                if (!on) continue;
                int c = y < 6 ? main : (y > 11 ? shade : (x == 6 && y == 7 ? accent : main));
                px[y * SIZE + x] = c;
                px[y * SIZE + (SIZE - 1 - x)] = c;
            }
        }
        return px;
    }

    private static byte[] hash(String s) {
        try {
            return MessageDigest.getInstance("SHA-256").digest(s.getBytes(StandardCharsets.UTF_8));
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);
        }
    }

    private static int hsv(float h, float s, float v) {
        int rgb = java.awt.Color.HSBtoRGB(h, s, v);
        return 0xFF000000 | (rgb & 0xFFFFFF);
    }
}
