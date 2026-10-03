package org.mamoru.omnichat.client.ui;

import org.junit.jupiter.api.Test;
import org.mamoru.omnichat.client.tts.ModelRepair.Health;
import org.mamoru.omnichat.client.tts.ModelRepair.Status;

import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class ModelHealthViewTest {
    static final Health OK = new Health(Status.OK, "", "", List.of());
    static final Health AUTO = new Health(Status.FIXABLE, "missing 'voice' metadata (espeak voice)", "ru", List.of("en-us", "ru"));
    static final Health PICK = new Health(Status.FIXABLE, "missing 'voice' metadata (espeak voice)", "", List.of("de", "en-us", "ru"));
    static final Health ONE = new Health(Status.FIXABLE, "missing voice", "", List.of("ru"));
    static final Health NONE = new Health(Status.FIXABLE, "missing voice", "", List.of());
    static final Health BAD = new Health(Status.INCOMPATIBLE, "missing 'n_speakers' metadata", "", List.of());

    @Test
    void badgeOnlyForInstalledProblemModels() {
        assertEquals(ModelHealthView.Badge.NONE, ModelHealthView.badge(VoiceCatalog.State.INSTALLED, null));
        assertEquals(ModelHealthView.Badge.NONE, ModelHealthView.badge(VoiceCatalog.State.INSTALLED, OK));
        assertEquals(ModelHealthView.Badge.WARN, ModelHealthView.badge(VoiceCatalog.State.INSTALLED, AUTO));
        assertEquals(ModelHealthView.Badge.ERROR, ModelHealthView.badge(VoiceCatalog.State.INSTALLED, BAD));
        assertEquals(ModelHealthView.Badge.NONE, ModelHealthView.badge(VoiceCatalog.State.DOWNLOADING, BAD));
        assertEquals(ModelHealthView.Badge.NONE, ModelHealthView.badge(VoiceCatalog.State.REMOTE, AUTO));
    }

    @Test
    void statusKeys() {
        assertNull(ModelHealthView.statusKey(null));
        assertNull(ModelHealthView.statusKey(OK));
        assertEquals("omnichat.ui.voice.needs_fix", ModelHealthView.statusKey(AUTO));
        assertEquals("omnichat.ui.voice.incompatible_model", ModelHealthView.statusKey(BAD));
    }

    @Test
    void onlyHealthyOrUncheckedInstalledVoicesCanBeActivated() {
        assertTrue(ModelHealthView.canActivate(VoiceCatalog.State.INSTALLED, null));
        assertTrue(ModelHealthView.canActivate(VoiceCatalog.State.INSTALLED, OK));
        assertFalse(ModelHealthView.canActivate(VoiceCatalog.State.INSTALLED, AUTO));
        assertFalse(ModelHealthView.canActivate(VoiceCatalog.State.INSTALLED, BAD));
        assertFalse(ModelHealthView.canActivate(VoiceCatalog.State.REMOTE, OK));
    }

    @Test
    void fixModes() {
        assertEquals(ModelHealthView.Fix.NONE, ModelHealthView.fixMode(null));
        assertEquals(ModelHealthView.Fix.NONE, ModelHealthView.fixMode(OK));
        assertEquals(ModelHealthView.Fix.NONE, ModelHealthView.fixMode(BAD));
        assertEquals(ModelHealthView.Fix.BUTTON, ModelHealthView.fixMode(AUTO));
        assertEquals(ModelHealthView.Fix.BUTTON, ModelHealthView.fixMode(ONE));
        assertEquals(ModelHealthView.Fix.PICKER, ModelHealthView.fixMode(PICK));
        assertEquals(ModelHealthView.Fix.NONE, ModelHealthView.fixMode(NONE));
        assertEquals("ru", ModelHealthView.autoVoice(AUTO));
        assertEquals("ru", ModelHealthView.autoVoice(ONE));
        assertEquals("", ModelHealthView.autoVoice(PICK));
    }

    @Test
    void initialPickerIndex() {
        List<String> v = List.of("de", "en-us", "ru");
        assertEquals(2, ModelHealthView.initialVoiceIndex(v, "ru", "en"));   // remembered choice wins
        assertEquals(2, ModelHealthView.initialVoiceIndex(v, null, "RU"));   // model language
        assertEquals(1, ModelHealthView.initialVoiceIndex(v, null, "en"));   // en -> en-us
        assertEquals(1, ModelHealthView.initialVoiceIndex(v, "xx", "Русский")); // unknown -> en-us
        assertEquals(0, ModelHealthView.initialVoiceIndex(List.of("de", "fr"), null, "")); // else first
    }

    @Test
    void signatureToken() {
        assertEquals("?", ModelHealthView.token(null));
        assertEquals("OK", ModelHealthView.token(OK));
        assertEquals("FIXABLE", ModelHealthView.token(AUTO));
    }
}
