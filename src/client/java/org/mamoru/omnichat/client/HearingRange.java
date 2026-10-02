package org.mamoru.omnichat.client;

/**
 * How far a player's chat can be heard and seen. Shared by the TTS filter, the spatial audio
 * attenuation and the chat bubble renderer so they never disagree.
 */
public final class HearingRange {
    /** Beyond this distance (blocks) messages are neither spoken nor bubbled. */
    public static final double BLOCKS = 40.0;

    private HearingRange() {
    }
}
