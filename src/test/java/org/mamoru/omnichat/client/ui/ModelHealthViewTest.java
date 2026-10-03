package org.mamoru.omnichat.client.ui;

import org.junit.jupiter.api.Test;
import org.mamoru.omnichat.client.tts.ModelRepair;
import org.mamoru.omnichat.client.tts.ModelRepair.Health;
import org.mamoru.omnichat.client.tts.ModelRepair.Reason;
import org.mamoru.omnichat.client.tts.ModelRepair.Status;

import java.io.IOException;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class ModelHealthViewTest {
    static final Health OK = new Health(Status.OK, Reason.NONE, "", "", List.of());
    static final Health AUTO = new Health(Status.FIXABLE, Reason.MISSING_VOICE, "missing voice", "ru", List.of("en-us", "ru"));
    static final Health PICK = new Health(Status.FIXABLE, Reason.MISSING_VOICE, "missing voice", "", List.of("de", "en-us", "ru"));
    static final Health ONE = new Health(Status.FIXABLE, Reason.MISSING_VOICE, "missing voice", "", List.of("ru"));
    static final Health NONE = new Health(Status.FIXABLE, Reason.MISSING_VOICE, "missing voice", "", List.of());
    static final Health BAD = new Health(Status.INCOMPATIBLE, Reason.NOT_VITS, "missing 'n_speakers' metadata", "", List.of());

    @Test
    void badgeOnlyForInstalledProblemModels() {
        assertEquals(ModelHealthView.Badge.NONE, ModelHealthView.badge(VoiceCatalog.State.INSTALLED, null));
        assertEquals(ModelHealthView.Badge.NONE, ModelHealthView.badge(VoiceCatalog.State.INSTALLED, OK));
        assertEquals(ModelHealthView.Badge.WARN, ModelHealthView.badge(VoiceCatalog.State.INSTALLED, AUTO));
        assertEquals(ModelHealthView.Badge.ERROR, ModelHealthView.badge(VoiceCatalog.State.INSTALLED, BAD));
        assertEquals(ModelHealthView.Badge.ERROR, ModelHealthView.badge(VoiceCatalog.State.INSTALLED, NONE), "no way to fix");
        assertEquals(ModelHealthView.Badge.NONE, ModelHealthView.badge(VoiceCatalog.State.DOWNLOADING, BAD));
        assertEquals(ModelHealthView.Badge.NONE, ModelHealthView.badge(VoiceCatalog.State.REMOTE, AUTO));
    }

    @Test
    void statusKeys() {
        assertEquals("omnichat.ui.voice.checking", ModelHealthView.statusKey(null));
        assertNull(ModelHealthView.statusKey(OK));
        assertEquals("omnichat.ui.voice.needs_fix", ModelHealthView.statusKey(AUTO));
        assertEquals("omnichat.ui.voice.needs_fix", ModelHealthView.statusKey(PICK));
        assertEquals("omnichat.ui.voice.incompatible_model", ModelHealthView.statusKey(BAD));
        assertEquals("omnichat.ui.voice.incompatible_model", ModelHealthView.statusKey(NONE));
    }

    @Test
    void reasonKeys() {
        assertEquals("omnichat.reason.missing_voice", ModelHealthView.reasonKey(Reason.MISSING_VOICE));
        assertEquals("omnichat.reason.not_vits", ModelHealthView.reasonKey(Reason.NOT_VITS));
        assertEquals("omnichat.reason.read_error", ModelHealthView.reasonKey(Reason.READ_ERROR));
        assertEquals("omnichat.reason.too_large", ModelHealthView.reasonKey(Reason.TOO_LARGE));
    }

    @Test
    void repairFailureKeys() {
        assertEquals("omnichat.repair_error.in_use",
                ModelHealthView.failureKey(new ModelRepair.RepairException(ModelRepair.Failure.IN_USE, "x", null)));
        assertEquals("omnichat.repair_error.incompatible",
                ModelHealthView.failureKey(new ModelRepair.RepairException(ModelRepair.Failure.INCOMPATIBLE, "x", null)));
        assertEquals("omnichat.repair_error.verify",
                ModelHealthView.failureKey(new ModelRepair.RepairException(ModelRepair.Failure.VERIFY_FAILED, "x", null)));
        assertEquals("omnichat.repair_error.generic",
                ModelHealthView.failureKey(new ModelRepair.RepairException(ModelRepair.Failure.OTHER, "x", null)));
        assertEquals("omnichat.repair_error.generic", ModelHealthView.failureKey(new IOException("disk full")));
        assertEquals("omnichat.repair_error.generic", ModelHealthView.failureKey(new IllegalStateException()));
    }

    @Test
    void onlyCheckedHealthyInstalledVoicesCanBeActivated() {
        assertFalse(ModelHealthView.canActivate(VoiceCatalog.State.INSTALLED, null), "pending: select only");
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
        assertEquals(2, ModelHealthView.initialVoiceIndex(v, "ru", "en"));
        assertEquals(2, ModelHealthView.initialVoiceIndex(v, null, "RU"));
        assertEquals(1, ModelHealthView.initialVoiceIndex(v, null, "en"));
        assertEquals(1, ModelHealthView.initialVoiceIndex(v, "xx", "Russian"));
        assertEquals(0, ModelHealthView.initialVoiceIndex(List.of("de", "fr"), null, ""));
    }

    @Test
    void signatureToken() {
        assertEquals("?", ModelHealthView.token(null));
        assertEquals("OK", ModelHealthView.token(OK));
        assertEquals("FIXABLE", ModelHealthView.token(AUTO));
    }
}
