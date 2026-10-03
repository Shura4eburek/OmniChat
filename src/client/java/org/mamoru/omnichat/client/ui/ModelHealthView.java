package org.mamoru.omnichat.client.ui;

import org.mamoru.omnichat.client.tts.ModelRepair.Health;
import org.mamoru.omnichat.client.tts.ModelRepair.Status;

import java.util.List;
import java.util.Locale;

/** Pure mapping from a model's health to what the Voice tab shows. {@code null} health = check pending. */
public final class ModelHealthView {
    public enum Badge { NONE, WARN, ERROR }

    /** How the card offers a repair: none, one button with a known language, or a language picker + button. */
    public enum Fix { NONE, BUTTON, PICKER }

    private ModelHealthView() {
    }

    public static Badge badge(VoiceCatalog.State state, Health h) {
        if (state != VoiceCatalog.State.INSTALLED || h == null) return Badge.NONE;
        return switch (h.status()) {
            case OK -> Badge.NONE;
            case FIXABLE -> Badge.WARN;
            case INCOMPATIBLE -> Badge.ERROR;
        };
    }

    /** Translation key for the status line (takes the reason as %s), or null when there is nothing to report. */
    public static String statusKey(Health h) {
        if (h == null || h.status() == Status.OK) return null;
        return h.status() == Status.FIXABLE ? "omnichat.ui.voice.needs_fix" : "omnichat.ui.voice.incompatible_model";
    }

    /** A known-broken model is never made active (the engine would refuse it and fall back). */
    public static boolean canActivate(VoiceCatalog.State state, Health h) {
        return state == VoiceCatalog.State.INSTALLED && (h == null || h.status() == Status.OK);
    }

    /** The language to fix with without asking: the piper json's voice, or the only espeak voice there is. */
    public static String autoVoice(Health h) {
        if (h == null || h.status() != Status.FIXABLE) return "";
        if (!h.suggestedVoice().isBlank()) return h.suggestedVoice();
        return h.voices().size() == 1 ? h.voices().get(0) : "";
    }

    public static Fix fixMode(Health h) {
        if (h == null || h.status() != Status.FIXABLE) return Fix.NONE;
        if (!autoVoice(h).isBlank()) return Fix.BUTTON;
        return h.voices().size() >= 2 ? Fix.PICKER : Fix.NONE;
    }

    /** Picker start: the remembered choice, else the model's language, else en-us, else the first voice. */
    public static int initialVoiceIndex(List<String> voices, String chosen, String language) {
        if (chosen != null && voices.contains(chosen)) return voices.indexOf(chosen);
        String lang = language == null ? "" : language.trim().toLowerCase(Locale.ROOT);
        if (!lang.isEmpty()) {
            for (int i = 0; i < voices.size(); i++) {
                String v = voices.get(i).toLowerCase(Locale.ROOT);
                if (v.equals(lang) || v.startsWith(lang + "-")) return i;
            }
        }
        int en = voices.indexOf("en-us");
        return Math.max(0, en);
    }

    /** Part of the Voice tab's rebuild signature. */
    public static String token(Health h) {
        return h == null ? "?" : h.status().name();
    }
}
