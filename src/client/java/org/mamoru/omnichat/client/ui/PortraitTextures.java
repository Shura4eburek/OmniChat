package org.mamoru.omnichat.client.ui;

import net.minecraft.client.MinecraftClient;
import net.minecraft.client.texture.NativeImage;
import net.minecraft.client.texture.NativeImageBackedTexture;
import net.minecraft.util.Identifier;
import org.mamoru.omnichat.voice.VoiceMeta;
import org.mamoru.omnichat.voice.VoiceMetaReader;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.util.Arrays;
import java.util.HashMap;
import java.util.HexFormat;
import java.util.Map;

/** Uploads voice portraits (from portrait.png or generated) as GUI textures. Render thread only. */
public final class PortraitTextures {
    private static final Logger LOGGER = LoggerFactory.getLogger("OmniChat");
    private static final Map<String, Identifier> BY_KEY = new HashMap<>();
    private static final Map<Identifier, Integer> SIZES = new HashMap<>();

    private PortraitTextures() {
    }

    public static Identifier get(VoiceMeta meta) {
        String key = meta.model() + ":" + Arrays.hashCode(meta.portrait());
        Identifier id = BY_KEY.get(key);
        if (id != null) return id;
        NativeImage image = decode(meta);
        id = Identifier.of("omnichat", "portrait/" + HexFormat.of().toHexDigits(key.hashCode()));
        MinecraftClient.getInstance().getTextureManager()
                .registerTexture(id, new NativeImageBackedTexture(() -> "omnichat portrait " + meta.model(), image));
        BY_KEY.put(key, id);
        SIZES.put(id, image.getWidth());
        return id;
    }

    public static int sizeOf(Identifier id) {
        return SIZES.getOrDefault(id, PortraitGenerator.SIZE);
    }

    /** Frees all portrait textures (disconnect, catalog change). */
    public static void clear() {
        var tm = MinecraftClient.getInstance().getTextureManager();
        for (Identifier id : BY_KEY.values()) tm.destroyTexture(id);
        BY_KEY.clear();
        SIZES.clear();
    }

    private static NativeImage decode(VoiceMeta meta) {
        if (meta.portrait().length > 0 && !VoiceMetaReader.isValidPortrait(meta.portrait())) {
            LOGGER.warn("Bad portrait for voice '{}', using a generated one: not a 16x16/32x32 PNG", meta.model());
        } else if (meta.portrait().length > 0) {
            try {
                return NativeImage.read(meta.portrait());
            } catch (IOException | RuntimeException e) {
                LOGGER.warn("Bad portrait for voice '{}', using a generated one: {}", meta.model(), e.toString());
            }
        }
        int[] px = PortraitGenerator.generate(meta.model());
        NativeImage img = new NativeImage(PortraitGenerator.SIZE, PortraitGenerator.SIZE, false);
        for (int y = 0; y < PortraitGenerator.SIZE; y++) {
            for (int x = 0; x < PortraitGenerator.SIZE; x++) {
                img.setColorArgb(x, y, px[y * PortraitGenerator.SIZE + x]);
            }
        }
        return img;
    }
}
