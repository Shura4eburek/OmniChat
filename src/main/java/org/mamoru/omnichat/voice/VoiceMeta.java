package org.mamoru.omnichat.voice;

/**
 * Display metadata of a voice model. Strings are never null; {@code portrait} is a validated PNG
 * or an empty array (the client then generates a portrait).
 */
public record VoiceMeta(String model, String name, String description, String language,
                        String gender, String sample, long sizeBytes, byte[] portrait) {

    public static VoiceMeta bare(String model) {
        return new VoiceMeta(model, model, "", "", "", "", 0, new byte[0]);
    }
}
