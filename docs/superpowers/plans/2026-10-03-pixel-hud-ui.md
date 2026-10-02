# Pixel HUD UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the vanilla-widget settings screen and all OmniChat pop-ups with one teal "tactical HUD" pixel interface, backed by per-voice metadata (`voice.json` + `portrait.png`) streamed from the server.

**Architecture:** Pure, unit-tested logic (metadata parsing, catalog state, layout math, portrait generation, waveform RMS) sits underneath a small set of custom widgets (`client/ui/widget/*`, all extending vanilla `ClickableWidget`/`SliderWidget`). `OmnichatScreen` composes header, `TabBar`, the active tab and a hint footer inside a panel whose size is computed by `HudLayout`. The server sends a `VoiceCatalogS2CPayload` (protocol v2) instead of the bare model list.

**Tech Stack:** Java 21, Fabric Loader 0.18.4, Fabric API 0.141.3+1.21.11, Minecraft 1.21.11 (Yarn 1.21.11+build.4), Loom 1.15, Gson, JUnit 5 (new).

**Spec:** `docs/superpowers/specs/2026-10-03-pixel-hud-ui-design.md`

## Global Constraints

- Accent `#35E0C8`; dim accent = accent at 45 % alpha (`0x7335E0C8`); panel bg `0xDB0A080C` (#0A080C @ ~86 %); tile bg `0xFF15111A`; text `0xFFD9D4DC`; muted `0xFF9A93A0`; ok `0xFF59E36B`; warn `0xFFFFCF4A`.
- Vanilla font only. Frames 1 px, corner brackets 2 px (GUI pixels).
- Panel size `min(screenW − 16, 420) × min(screenH − 16, 260)` in scaled GUI pixels, centered.
- Must fit at 854×480 window with the largest GUI scale Minecraft allows there (2) — and every other valid scale for 854×480, 1280×720, 1920×1080.
- `voice.json` limits: `name` ≤ 32, `description` ≤ 200, `sample` ≤ 120, `language` ≤ 8 chars; unknown fields ignored.
- `portrait.png`: PNG, exactly 16×16 or 32×32, ≤ 8192 bytes.
- `VoiceCatalogS2CPayload`: ≤ 64 entries; `ProtocolVersionPayload.PROTOCOL_VERSION = 2`.
- No `Text.literal` for user-facing UI strings — use `Text.translatable` with keys in both `en_us.json` and `ru_ru.json`.
- No new runtime dependencies for players. JUnit is test-only.
- Mixins use `@Inject`, never `@Overwrite`. Client code stays in `src/client`, common code in `src/main`.
- Never log chat text. Keep the existing log lines `TTS generated`, `TTS playing`, `TTS playback worker started`, `TTS engine ready` (smoke test greps them).
- Build: `./gradlew build`; after editing jar-related parts of `build.gradle` use `./gradlew clean build`.

## Review Focus

1. **Very long or wide voice names** (e.g. 32 × "Ш") — tile captions and card titles must be ellipsized to fit, never overflow the panel. Test: `HudTextTest.ellipsizesLongNames` (Task 6).
2. **Zero voices** (vanilla server, empty `models/`) — the Voice tab must show an empty-state line instead of a blank grid or a crash. Test: `VoiceCatalogTest.emptySourcesGiveEmptyCatalog` (Task 5) + empty-state rendering step (Task 9).
3. **Download finishes / server reload while the screen is open** — tile states and selection must update live; a selected voice that disappeared falls back to the configured model. Tests: `VoiceCatalogTest.downloadedModelBecomesInstalled`, `VoiceCatalogTest.selectionFallsBackWhenVoiceRemoved`, `VoiceCatalogTest.signatureIgnoresPortraitArrayIdentity` (Task 5).
4. **Preview spam** (rapid right-clicks on several voices) — only the most recent preview may play; earlier syntheses finishing late are dropped. Test: `PreviewTicketsTest.staleTicketIsRejected` (Task 8).
5. **Cyrillic and other UTF-8 in `voice.json`** on Windows (default charset cp1251) — must be read as UTF-8. Test: `VoiceMetaReaderTest.readsUtf8OnAnyPlatform` (Task 2).

---

## File Structure

| Path | Responsibility |
|---|---|
| `build.gradle` | + JUnit 5, test source set sees `client` classes |
| `src/main/java/org/mamoru/omnichat/voice/VoiceMeta.java` | Immutable voice metadata record (common) |
| `src/main/java/org/mamoru/omnichat/voice/VoiceMetaReader.java` | Reads/validates `voice.json` + `portrait.png` + folder size |
| `src/main/java/org/mamoru/omnichat/network/VoiceCatalogS2CPayload.java` | Catalog payload + codec (replaces `ModelListS2CPayload`) |
| `src/main/java/org/mamoru/omnichat/network/ProtocolVersionPayload.java` | Bump to 2 |
| `src/main/java/org/mamoru/omnichat/server/VoiceRegistry.java` | Holds catalog snapshot |
| `src/main/java/org/mamoru/omnichat/server/ServerNetworkHandler.java` | Sends catalog instead of model list |
| `src/main/java/org/mamoru/omnichat/Omnichat.java` | Registers catalog payload |
| `src/client/java/org/mamoru/omnichat/client/network/VoiceCache.java` | Stores server catalog |
| `src/client/java/org/mamoru/omnichat/client/network/ClientNetworkHandler.java` | Receives catalog |
| `src/client/java/org/mamoru/omnichat/client/network/ModelDownloadManager.java` | + `getFailure(model)`, toast hooks |
| `src/client/java/org/mamoru/omnichat/client/ui/HudTheme.java` | Palette + drawing primitives |
| `src/client/java/org/mamoru/omnichat/client/ui/HudLayout.java` | Pure layout math (panel/header/tabs/body/footer/grid/detail rects) |
| `src/client/java/org/mamoru/omnichat/client/ui/HudText.java` | Pure text fitting (ellipsize, wrap) |
| `src/client/java/org/mamoru/omnichat/client/ui/PortraitGenerator.java` | Pure deterministic 16×16 ARGB portrait |
| `src/client/java/org/mamoru/omnichat/client/ui/PortraitTextures.java` | Uploads portraits as textures, frees them |
| `src/client/java/org/mamoru/omnichat/client/ui/VoiceCatalog.java` | Pure merge of server + local + download state → `VoiceEntry` list |
| `src/client/java/org/mamoru/omnichat/client/ui/widget/HudButton.java` | Button |
| `src/client/java/org/mamoru/omnichat/client/ui/widget/HudToggle.java` | On/off row |
| `src/client/java/org/mamoru/omnichat/client/ui/widget/HudSlider.java` | Slider row |
| `src/client/java/org/mamoru/omnichat/client/ui/widget/TabBar.java` | Tabs |
| `src/client/java/org/mamoru/omnichat/client/ui/widget/VoiceTile.java` | Portrait tile + badge |
| `src/client/java/org/mamoru/omnichat/client/ui/widget/StatusLine.java` | Status row (draw helper, not focusable) |
| `src/client/java/org/mamoru/omnichat/client/ui/screen/HudTab.java` | Tab interface |
| `src/client/java/org/mamoru/omnichat/client/ui/screen/OmnichatScreen.java` | The screen |
| `src/client/java/org/mamoru/omnichat/client/ui/screen/VoiceTab.java` | Grid + detail card |
| `src/client/java/org/mamoru/omnichat/client/ui/screen/AudioTab.java` | Audio settings |
| `src/client/java/org/mamoru/omnichat/client/ui/screen/BubblesTab.java` | Bubble settings |
| `src/client/java/org/mamoru/omnichat/client/ui/HudToast.java` | HUD-style toast |
| `src/client/java/org/mamoru/omnichat/client/screen/DownloadProgressHud.java` | Restyled |
| `src/client/java/org/mamoru/omnichat/client/tts/WaveformMeter.java` | Pure RMS-at-time over PCM |
| `src/client/java/org/mamoru/omnichat/client/tts/PreviewTickets.java` | Pure "latest request wins" counter |
| `src/client/java/org/mamoru/omnichat/client/tts/VoicePreview.java` | Synthesizes + plays a sample |
| `src/client/java/org/mamoru/omnichat/client/OmnichatKeybinds.java` | Opens `OmnichatScreen` |
| `src/client/java/org/mamoru/omnichat/client/screen/OmnichatSettingsScreen.java` | **Deleted** |
| `src/main/resources/assets/omnichat/lang/en_us.json`, `ru_ru.json` | All UI strings |
| `scripts/smoke.sh` | + UI screenshot step |
| `README.md` | «Оформление голосов» section |
| `src/test/java/...` | Unit tests (paths in each task) |

---

### Task 1: Test infrastructure

**Files:**
- Modify: `build.gradle`
- Create: `src/test/java/org/mamoru/omnichat/SanityTest.java`

**Interfaces:**
- Produces: `./gradlew test` runs JUnit 5 tests that can see `main` and `client` classes.

- [ ] **Step 1: Add JUnit and wire the test source set**

In `build.gradle`, inside `dependencies { ... }` add:

```groovy
    testImplementation platform('org.junit:junit-bom:5.11.3')
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
```

After the `dependencies` block add:

```groovy
// Unit tests cover pure logic in both source sets (no game launch)
sourceSets {
    test {
        compileClasspath += sourceSets.client.output + sourceSets.client.compileClasspath
        runtimeClasspath += sourceSets.client.output + sourceSets.client.runtimeClasspath
    }
}

test {
    useJUnitPlatform()
}
```

- [ ] **Step 2: Write a sanity test**

`src/test/java/org/mamoru/omnichat/SanityTest.java`:

```java
package org.mamoru.omnichat;

import org.junit.jupiter.api.Test;
import org.mamoru.omnichat.client.HearingRange;

import static org.junit.jupiter.api.Assertions.assertEquals;

class SanityTest {
    @Test
    void seesClientClasses() {
        assertEquals(40.0, HearingRange.BLOCKS);
    }
}
```

- [ ] **Step 3: Run**

Run: `./gradlew test`
Expected: `BUILD SUCCESSFUL`, 1 test passed (`build/reports/tests/test/index.html`).

- [ ] **Step 4: Commit**

```bash
git add build.gradle src/test
git commit -m "test: add junit 5 with access to client classes"
```

---

### Task 2: Voice metadata model and reader (common)

**Files:**
- Create: `src/main/java/org/mamoru/omnichat/voice/VoiceMeta.java`
- Create: `src/main/java/org/mamoru/omnichat/voice/VoiceMetaReader.java`
- Test: `src/test/java/org/mamoru/omnichat/voice/VoiceMetaReaderTest.java`

**Interfaces:**
- Produces:
  - `record VoiceMeta(String model, String name, String description, String language, String gender, String sample, long sizeBytes, byte[] portrait)` — `name` never null/empty (falls back to `model`); other strings `""` when absent; `portrait` empty array when absent/invalid.
  - `static VoiceMeta VoiceMeta.bare(String model)` — no metadata, size 0.
  - `static VoiceMeta VoiceMetaReader.read(Path modelDir, String model)` — never throws.
  - `static boolean VoiceMetaReader.isValidPortrait(byte[] png)`.
  - Constants `VoiceMetaReader.MAX_NAME=32, MAX_DESCRIPTION=200, MAX_SAMPLE=120, MAX_LANGUAGE=8, MAX_PORTRAIT_BYTES=8192`.

- [ ] **Step 1: Write the failing tests**

```java
package org.mamoru.omnichat.voice;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class VoiceMetaReaderTest {
    @TempDir Path dir;

    static byte[] png(int w, int h, int totalSize) {
        // PNG signature + IHDR chunk header + width/height, padded to totalSize
        ByteBuffer b = ByteBuffer.allocate(Math.max(totalSize, 24));
        b.put(new byte[]{(byte) 0x89, 'P', 'N', 'G', 0x0D, 0x0A, 0x1A, 0x0A});
        b.putInt(13).put(new byte[]{'I', 'H', 'D', 'R'}).putInt(w).putInt(h);
        return b.array();
    }

    @Test
    void missingFilesGiveBareMetaWithFolderSize() throws IOException {
        Files.write(dir.resolve("model.onnx"), new byte[1234]);
        VoiceMeta m = VoiceMetaReader.read(dir, "denis");
        assertEquals("denis", m.name());
        assertEquals("", m.description());
        assertEquals(0, m.portrait().length);
        assertEquals(1234, m.sizeBytes());
    }

    @Test
    void readsAndTruncatesFields() throws IOException {
        String longName = "N".repeat(50);
        Files.writeString(dir.resolve("voice.json"),
                "{\"name\":\"" + longName + "\",\"description\":\"" + "d".repeat(300) + "\","
                        + "\"language\":\"ru-RU-extra\",\"gender\":\"male\",\"sample\":\"" + "s".repeat(200) + "\","
                        + "\"unknown\":42}", StandardCharsets.UTF_8);
        VoiceMeta m = VoiceMetaReader.read(dir, "denis");
        assertEquals(32, m.name().length());
        assertEquals(200, m.description().length());
        assertEquals(8, m.language().length());
        assertEquals(120, m.sample().length());
        assertEquals("male", m.gender());
    }

    @Test
    void brokenJsonFallsBack() throws IOException {
        Files.writeString(dir.resolve("voice.json"), "{ not json");
        assertEquals("denis", VoiceMetaReader.read(dir, "denis").name());
    }

    @Test
    void blankNameFallsBackToModel() throws IOException {
        Files.writeString(dir.resolve("voice.json"), "{\"name\":\"   \"}");
        assertEquals("denis", VoiceMetaReader.read(dir, "denis").name());
    }

    @Test
    void readsUtf8OnAnyPlatform() throws IOException {
        Files.write(dir.resolve("voice.json"), "{\"name\":\"Денис\"}".getBytes(StandardCharsets.UTF_8));
        assertEquals("Денис", VoiceMetaReader.read(dir, "denis").name());
    }

    @Test
    void acceptsValidPortraits() throws IOException {
        Files.write(dir.resolve("portrait.png"), png(16, 16, 300));
        assertEquals(300, VoiceMetaReader.read(dir, "denis").portrait().length);
        assertTrue(VoiceMetaReader.isValidPortrait(png(32, 32, 500)));
    }

    @Test
    void rejectsBadPortraits() {
        assertFalse(VoiceMetaReader.isValidPortrait(png(64, 64, 300)));      // wrong size
        assertFalse(VoiceMetaReader.isValidPortrait(png(16, 32, 300)));      // not square
        assertFalse(VoiceMetaReader.isValidPortrait(png(16, 16, 9000)));     // too big
        assertFalse(VoiceMetaReader.isValidPortrait("GIF89a....".getBytes())); // not png
        assertFalse(VoiceMetaReader.isValidPortrait(new byte[0]));
    }
}
```

- [ ] **Step 2: Run to see it fail**

Run: `./gradlew test --tests '*VoiceMetaReaderTest*'`
Expected: compilation FAIL — `VoiceMetaReader` / `VoiceMeta` not found.

- [ ] **Step 3: Implement**

`VoiceMeta.java`:

```java
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
```

`VoiceMetaReader.java`:

```java
package org.mamoru.omnichat.voice;

import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

/** Reads optional {@code voice.json} and {@code portrait.png} from a model folder. Never throws. */
public final class VoiceMetaReader {
    private static final Logger LOGGER = LoggerFactory.getLogger("OmniChat");

    public static final int MAX_NAME = 32;
    public static final int MAX_DESCRIPTION = 200;
    public static final int MAX_SAMPLE = 120;
    public static final int MAX_LANGUAGE = 8;
    public static final int MAX_PORTRAIT_BYTES = 8192;

    private static final byte[] PNG_SIGNATURE = {(byte) 0x89, 'P', 'N', 'G', 0x0D, 0x0A, 0x1A, 0x0A};

    private VoiceMetaReader() {
    }

    public static VoiceMeta read(Path modelDir, String model) {
        String name = model, description = "", language = "", gender = "", sample = "";
        Path json = modelDir.resolve("voice.json");
        if (Files.isRegularFile(json)) {
            try {
                // Always UTF-8: the platform default on Windows would mangle Cyrillic
                JsonObject o = JsonParser.parseString(Files.readString(json, StandardCharsets.UTF_8)).getAsJsonObject();
                String n = str(o, "name", MAX_NAME);
                if (!n.isBlank()) name = n;
                description = str(o, "description", MAX_DESCRIPTION);
                language = str(o, "language", MAX_LANGUAGE);
                gender = str(o, "gender", 16);
                sample = str(o, "sample", MAX_SAMPLE);
            } catch (IOException | RuntimeException e) {
                LOGGER.warn("Ignoring invalid voice.json of model '{}': {}", model, e.toString());
            }
        }
        byte[] portrait = new byte[0];
        Path png = modelDir.resolve("portrait.png");
        if (Files.isRegularFile(png)) {
            try {
                if (Files.size(png) <= MAX_PORTRAIT_BYTES) {
                    byte[] data = Files.readAllBytes(png);
                    if (isValidPortrait(data)) portrait = data;
                }
                if (portrait.length == 0) {
                    LOGGER.warn("Ignoring portrait.png of model '{}': must be a 16x16 or 32x32 PNG up to {} bytes",
                            model, MAX_PORTRAIT_BYTES);
                }
            } catch (IOException e) {
                LOGGER.warn("Failed to read portrait.png of model '{}': {}", model, e.toString());
            }
        }
        return new VoiceMeta(model, name, description, language, gender, sample, folderSize(modelDir), portrait);
    }

    /** PNG signature, IHDR first, square 16x16 or 32x32, at most {@link #MAX_PORTRAIT_BYTES}. */
    public static boolean isValidPortrait(byte[] png) {
        if (png == null || png.length < 24 || png.length > MAX_PORTRAIT_BYTES) return false;
        for (int i = 0; i < PNG_SIGNATURE.length; i++) {
            if (png[i] != PNG_SIGNATURE[i]) return false;
        }
        if (png[12] != 'I' || png[13] != 'H' || png[14] != 'D' || png[15] != 'R') return false;
        int w = readInt(png, 16), h = readInt(png, 20);
        return w == h && (w == 16 || w == 32);
    }

    private static int readInt(byte[] b, int off) {
        return ((b[off] & 0xFF) << 24) | ((b[off + 1] & 0xFF) << 16) | ((b[off + 2] & 0xFF) << 8) | (b[off + 3] & 0xFF);
    }

    private static String str(JsonObject o, String key, int max) {
        JsonElement e = o.get(key);
        if (e == null || !e.isJsonPrimitive()) return "";
        String s = e.getAsString().strip();
        return s.length() > max ? s.substring(0, max) : s;
    }

    private static long folderSize(Path dir) {
        try (Stream<Path> files = Files.walk(dir)) {
            return files.filter(Files::isRegularFile).mapToLong(p -> {
                try {
                    return Files.size(p);
                } catch (IOException e) {
                    return 0;
                }
            }).sum();
        } catch (IOException e) {
            return 0;
        }
    }
}
```

- [ ] **Step 4: Run tests**

Run: `./gradlew test --tests '*VoiceMetaReaderTest*'`
Expected: 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/main/java/org/mamoru/omnichat/voice src/test/java/org/mamoru/omnichat/voice
git commit -m "feat(voice): read voice.json and portrait.png metadata"
```

---

### Task 3: Catalog payload, protocol v2, server sends catalog

**Files:**
- Create: `src/main/java/org/mamoru/omnichat/network/VoiceCatalogS2CPayload.java`
- Delete: `src/main/java/org/mamoru/omnichat/network/ModelListS2CPayload.java`
- Modify: `src/main/java/org/mamoru/omnichat/network/ProtocolVersionPayload.java` (`PROTOCOL_VERSION = 2`)
- Modify: `src/main/java/org/mamoru/omnichat/Omnichat.java` (payload registration line for `ModelListS2CPayload` → `VoiceCatalogS2CPayload`)
- Modify: `src/main/java/org/mamoru/omnichat/server/VoiceRegistry.java`
- Modify: `src/main/java/org/mamoru/omnichat/server/ServerNetworkHandler.java` (`onPlayerJoin`, `sendInitialState`, `reloadModels`)
- Modify: `src/client/java/org/mamoru/omnichat/client/network/VoiceCache.java`
- Modify: `src/client/java/org/mamoru/omnichat/client/network/ClientNetworkHandler.java` (`onModelList` → `onCatalog`)
- Test: `src/test/java/org/mamoru/omnichat/network/VoiceCatalogS2CPayloadTest.java`

**Interfaces:**
- Consumes: `VoiceMeta`, `VoiceMetaReader.read` (Task 2).
- Produces:
  - `record VoiceCatalogS2CPayload(List<VoiceMeta> voices)`, `ID = omnichat:voice_catalog`, `CODEC` (`PacketCodec<RegistryByteBuf, …>`), `MAX_ENTRIES = 64`.
  - `VoiceRegistry.getCatalog(): List<VoiceMeta>` (same order as `getAvailableModels()`).
  - `VoiceCache.setCatalog(List<VoiceMeta>)`, `VoiceCache.getCatalog(): List<VoiceMeta>`; `getServerModels()` keeps working (derived from catalog).

- [ ] **Step 1: Write the failing codec test**

```java
package org.mamoru.omnichat.network;

import io.netty.buffer.Unpooled;
import net.minecraft.network.RegistryByteBuf;
import net.minecraft.registry.DynamicRegistryManager;
import org.junit.jupiter.api.Test;
import org.mamoru.omnichat.voice.VoiceMeta;

import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class VoiceCatalogS2CPayloadTest {
    private static VoiceCatalogS2CPayload roundTrip(VoiceCatalogS2CPayload p) {
        RegistryByteBuf buf = new RegistryByteBuf(Unpooled.buffer(), DynamicRegistryManager.EMPTY);
        VoiceCatalogS2CPayload.CODEC.encode(buf, p);
        return VoiceCatalogS2CPayload.CODEC.decode(buf);
    }

    @Test
    void roundTripsAllFields() {
        VoiceMeta m = new VoiceMeta("denis", "Денис", "Спокойный", "ru", "male", "Привет", 81_146_850L, new byte[]{1, 2, 3});
        VoiceMeta out = roundTrip(new VoiceCatalogS2CPayload(List.of(m, VoiceMeta.bare("irina")))).voices().get(0);
        assertEquals("denis", out.model());
        assertEquals("Денис", out.name());
        assertEquals("Спокойный", out.description());
        assertEquals("ru", out.language());
        assertEquals("male", out.gender());
        assertEquals("Привет", out.sample());
        assertEquals(81_146_850L, out.sizeBytes());
        assertArrayEquals(new byte[]{1, 2, 3}, out.portrait());
    }

    @Test
    void capsEntriesOnEncode() {
        List<VoiceMeta> many = new ArrayList<>();
        for (int i = 0; i < 100; i++) many.add(VoiceMeta.bare("m" + i));
        assertEquals(VoiceCatalogS2CPayload.MAX_ENTRIES, roundTrip(new VoiceCatalogS2CPayload(many)).voices().size());
    }
}
```

- [ ] **Step 2: Run to see it fail**

Run: `./gradlew test --tests '*VoiceCatalogS2CPayloadTest*'`
Expected: compilation FAIL — `VoiceCatalogS2CPayload` not found. (If `DynamicRegistryManager.EMPTY` triggers a bootstrap error, replace it with `null` — `RegistryByteBuf` only uses it for registry-backed codecs, which this payload doesn't use.)

- [ ] **Step 3: Implement the payload**

```java
package org.mamoru.omnichat.network;

import net.minecraft.network.RegistryByteBuf;
import net.minecraft.network.codec.PacketCodec;
import net.minecraft.network.packet.CustomPayload;
import net.minecraft.util.Identifier;
import org.mamoru.omnichat.voice.VoiceMeta;
import org.mamoru.omnichat.voice.VoiceMetaReader;

import java.util.ArrayList;
import java.util.List;

/** Server → client: every voice the server offers, with display metadata. Replaces the bare model list. */
public record VoiceCatalogS2CPayload(List<VoiceMeta> voices) implements CustomPayload {
    public static final Id<VoiceCatalogS2CPayload> ID = new Id<>(Identifier.of("omnichat", "voice_catalog"));
    public static final int MAX_ENTRIES = 64;

    public static final PacketCodec<RegistryByteBuf, VoiceCatalogS2CPayload> CODEC = PacketCodec.of(
            (payload, buf) -> {
                List<VoiceMeta> voices = payload.voices();
                int n = Math.min(voices.size(), MAX_ENTRIES);
                buf.writeVarInt(n);
                for (int i = 0; i < n; i++) {
                    VoiceMeta m = voices.get(i);
                    buf.writeString(m.model());
                    buf.writeString(m.name());
                    buf.writeString(m.description());
                    buf.writeString(m.language());
                    buf.writeString(m.gender());
                    buf.writeString(m.sample());
                    buf.writeVarLong(m.sizeBytes());
                    buf.writeByteArray(m.portrait());
                }
            },
            buf -> {
                int n = Math.min(buf.readVarInt(), MAX_ENTRIES);
                List<VoiceMeta> voices = new ArrayList<>(n);
                for (int i = 0; i < n; i++) {
                    voices.add(new VoiceMeta(buf.readString(), buf.readString(VoiceMetaReader.MAX_NAME * 4),
                            buf.readString(VoiceMetaReader.MAX_DESCRIPTION * 4), buf.readString(64),
                            buf.readString(64), buf.readString(VoiceMetaReader.MAX_SAMPLE * 4),
                            buf.readVarLong(), buf.readByteArray(VoiceMetaReader.MAX_PORTRAIT_BYTES)));
                }
                return new VoiceCatalogS2CPayload(List.copyOf(voices));
            });

    @Override
    public Id<? extends CustomPayload> getId() {
        return ID;
    }
}
```

- [ ] **Step 4: Run the codec test**

Run: `./gradlew test --tests '*VoiceCatalogS2CPayloadTest*'`
Expected: 2 tests PASS.

- [ ] **Step 5: Server side**

`ProtocolVersionPayload.java`: change `PROTOCOL_VERSION = 1` to `PROTOCOL_VERSION = 2` and add to its javadoc: `2: VoiceCatalogS2CPayload replaces ModelListS2CPayload.`

`VoiceRegistry.java`: add a catalog snapshot refreshed with the model list.

```java
    // Immutable snapshot, swapped whole by refreshModels() together with availableModels
    private volatile List<VoiceMeta> catalog = List.of();

    public void refreshModels() {
        List<String> models = List.copyOf(ModelScanner.scanModels(modelsDir));
        List<VoiceMeta> metas = new ArrayList<>(models.size());
        for (String model : models) {
            metas.add(VoiceMetaReader.read(modelsDir.resolve(model), model));
        }
        this.availableModels = models;
        this.catalog = List.copyOf(metas);
    }

    public List<VoiceMeta> getCatalog() {
        return catalog;
    }
```

(Imports: `java.util.ArrayList`, `org.mamoru.omnichat.voice.VoiceMeta`, `org.mamoru.omnichat.voice.VoiceMetaReader`.)

`ServerNetworkHandler.java`: replace every `ModelListS2CPayload` use.
- In `onPlayerJoin`: `ServerPlayNetworking.canSend(player, ModelListS2CPayload.ID)` → `ServerPlayNetworking.canSend(player, VoiceCatalogS2CPayload.ID)`.
- In `sendInitialState`:

```java
        if (ServerPlayNetworking.canSend(player, VoiceCatalogS2CPayload.ID)) {
            ServerPlayNetworking.send(player, new VoiceCatalogS2CPayload(registry.getCatalog()));
        }
```

- In `reloadModels`: `broadcast(new ModelListS2CPayload(models), null);` → `broadcast(new VoiceCatalogS2CPayload(registry.getCatalog()), null);` and the comment above it → `// Catalog last: clients answer it by re-sending their configured voice`.

`Omnichat.java`: `PayloadTypeRegistry.playS2C().register(ModelListS2CPayload.ID, ModelListS2CPayload.CODEC);` → `PayloadTypeRegistry.playS2C().register(VoiceCatalogS2CPayload.ID, VoiceCatalogS2CPayload.CODEC);`

Delete `ModelListS2CPayload.java`.

- [ ] **Step 6: Client side**

`VoiceCache.java`: replace the `serverModels` field and its two methods with:

```java
    private volatile List<VoiceMeta> catalog = List.of();

    public void setCatalog(List<VoiceMeta> voices) {
        this.catalog = List.copyOf(voices);
    }

    public List<VoiceMeta> getCatalog() {
        return catalog;
    }

    public List<String> getServerModels() {
        return catalog.stream().map(VoiceMeta::model).toList();
    }
```

In `clear()` set `catalog = List.of();` instead of clearing `serverModels`. `isConnectedToOmnichatServer()` → `return !catalog.isEmpty();`.

`ClientNetworkHandler.java`: `receive(ModelListS2CPayload.ID, ClientNetworkHandler::onModelList);` → `receive(VoiceCatalogS2CPayload.ID, ClientNetworkHandler::onCatalog);` and:

```java
    private static void onCatalog(VoiceCatalogS2CPayload payload, ClientPlayNetworking.Context context) {
        VoiceCache.getInstance().setCatalog(payload.voices());
        List<String> models = VoiceCache.getInstance().getServerModels();
        LOGGER.info("Received server model list: {}", models);
        syncVoiceSelection(models);
    }
```

(The log line text is unchanged so `scripts/smoke.sh` keeps matching it.)

- [ ] **Step 7: Build + smoke**

Run: `./gradlew build` → `BUILD SUCCESSFUL`, all tests pass.
Run: `scripts/smoke.sh` → exit 0; `grep "protocol 2 matches" run/smoke/listener/logs/latest.log` finds a line.

- [ ] **Step 8: Commit**

```bash
git add -A src/main src/client src/test
git commit -m "feat(network): send a voice catalog with metadata (protocol 2)"
```

---

### Task 4: Portrait generator

**Files:**
- Create: `src/client/java/org/mamoru/omnichat/client/ui/PortraitGenerator.java`
- Test: `src/test/java/org/mamoru/omnichat/client/ui/PortraitGeneratorTest.java`

**Interfaces:**
- Produces: `static int[] PortraitGenerator.generate(String model)` — 16×16 = 256 ARGB ints, row-major, deterministic, horizontally symmetric, background `0xFF15111A`.

- [ ] **Step 1: Failing tests**

```java
package org.mamoru.omnichat.client.ui;

import org.junit.jupiter.api.Test;

import java.util.Arrays;

import static org.junit.jupiter.api.Assertions.*;

class PortraitGeneratorTest {
    @Test
    void isDeterministic() {
        assertArrayEquals(PortraitGenerator.generate("denis"), PortraitGenerator.generate("denis"));
    }

    @Test
    void differsBetweenNames() {
        assertFalse(Arrays.equals(PortraitGenerator.generate("denis"), PortraitGenerator.generate("irina")));
    }

    @Test
    void isSymmetricAndFilled() {
        int[] p = PortraitGenerator.generate("glados");
        assertEquals(256, p.length);
        int filled = 0;
        for (int y = 0; y < 16; y++) {
            for (int x = 0; x < 16; x++) {
                assertEquals(p[y * 16 + x], p[y * 16 + (15 - x)], "symmetry at " + x + "," + y);
                if (p[y * 16 + x] != PortraitGenerator.BACKGROUND) filled++;
            }
        }
        assertTrue(filled > 40, "portrait too empty: " + filled);
    }
}
```

- [ ] **Step 2: Run** — `./gradlew test --tests '*PortraitGeneratorTest*'` → FAIL (class missing).

- [ ] **Step 3: Implement**

```java
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
```

- [ ] **Step 4: Run** — `./gradlew test --tests '*PortraitGeneratorTest*'` → 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/client/java/org/mamoru/omnichat/client/ui/PortraitGenerator.java src/test/java/org/mamoru/omnichat/client/ui/PortraitGeneratorTest.java
git commit -m "feat(ui): generate fallback voice portraits"
```

---

### Task 5: Voice catalog (client state merge)

**Files:**
- Create: `src/client/java/org/mamoru/omnichat/client/ui/VoiceCatalog.java`
- Modify: `src/client/java/org/mamoru/omnichat/client/network/ModelDownloadManager.java` (record last failure per model)
- Test: `src/test/java/org/mamoru/omnichat/client/ui/VoiceCatalogTest.java`

**Interfaces:**
- Consumes: `VoiceMeta` (Task 2), `VoiceCache.getCatalog()` (Task 3), `ModelDownloadManager.getActiveDownloads()` (existing: `Map<String, Float>`, `-1` = queued).
- Produces:
  - `enum VoiceCatalog.State { INSTALLED, REMOTE, DOWNLOADING, FAILED }`
  - `record VoiceCatalog.Entry(VoiceMeta meta, State state, float progress, String failure, boolean onServer)` — `progress` in 0..1 or `-1` (queued); `failure` `""` unless FAILED.
  - `static List<Entry> VoiceCatalog.build(List<VoiceMeta> server, List<VoiceMeta> local, Map<String, Float> downloads, Map<String, String> failures)` — pure; server order first, then local-only voices sorted by model; local metadata wins over server metadata for installed voices.
  - `static String VoiceCatalog.selectOrFallback(List<Entry> entries, String selected, String configured)` — returns `selected` if still present, else `configured` if present, else first model, else `null`.
  - `static List<Entry> VoiceCatalog.current()` — wires real sources (client only, render thread); local metadata cached per model.
  - `static void VoiceCatalog.invalidateLocal(String model)` — drop cached local metadata (call after an install).
  - `static List<String> VoiceCatalog.signature(List<Entry>)` — change detection without `byte[]` identity.
  - `ModelDownloadManager.getFailures(): Map<String, String>` (copy) — set on failure, cleared on new request for that model.

- [ ] **Step 1: Failing tests**

```java
package org.mamoru.omnichat.client.ui;

import org.junit.jupiter.api.Test;
import org.mamoru.omnichat.voice.VoiceMeta;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class VoiceCatalogTest {
    static VoiceMeta m(String model) {
        return VoiceMeta.bare(model);
    }

    @Test
    void emptySourcesGiveEmptyCatalog() {
        assertTrue(VoiceCatalog.build(List.of(), List.of(), Map.of(), Map.of()).isEmpty());
        assertNull(VoiceCatalog.selectOrFallback(List.of(), "x", "default"));
    }

    @Test
    void mergesStates() {
        List<VoiceCatalog.Entry> e = VoiceCatalog.build(
                List.of(m("denis"), m("ruslan"), m("dmitri"), m("irina")),
                List.of(m("denis"), m("mine")),
                Map.of("ruslan", 0.42f, "dmitri", -1f),
                Map.of("irina", "queue full"));
        assertEquals(List.of("denis", "ruslan", "dmitri", "irina", "mine"),
                e.stream().map(x -> x.meta().model()).toList());
        assertEquals(VoiceCatalog.State.INSTALLED, e.get(0).state());
        assertEquals(VoiceCatalog.State.DOWNLOADING, e.get(1).state());
        assertEquals(0.42f, e.get(1).progress());
        assertEquals(-1f, e.get(2).progress());
        assertEquals(VoiceCatalog.State.FAILED, e.get(3).state());
        assertEquals("queue full", e.get(3).failure());
        assertEquals(VoiceCatalog.State.INSTALLED, e.get(4).state());
        assertFalse(e.get(4).onServer());
    }

    @Test
    void downloadedModelBecomesInstalled() {
        var before = VoiceCatalog.build(List.of(m("ruslan")), List.of(), Map.of("ruslan", 0.9f), Map.of());
        var after = VoiceCatalog.build(List.of(m("ruslan")), List.of(m("ruslan")), Map.of(), Map.of());
        assertEquals(VoiceCatalog.State.DOWNLOADING, before.get(0).state());
        assertEquals(VoiceCatalog.State.INSTALLED, after.get(0).state());
    }

    @Test
    void localMetadataWinsForInstalledVoices() {
        VoiceMeta server = new VoiceMeta("denis", "Server Denis", "", "", "", "", 1, new byte[0]);
        VoiceMeta local = new VoiceMeta("denis", "Local Denis", "", "", "", "", 1, new byte[0]);
        assertEquals("Local Denis", VoiceCatalog.build(List.of(server), List.of(local), Map.of(), Map.of())
                .get(0).meta().name());
    }

    @Test
    void signatureIgnoresPortraitArrayIdentity() {
        VoiceMeta a = new VoiceMeta("denis", "D", "", "", "", "", 1, new byte[]{1, 2});
        VoiceMeta b = new VoiceMeta("denis", "D", "", "", "", "", 1, new byte[]{1, 2});
        var x = VoiceCatalog.build(List.of(a), List.of(), Map.of(), Map.of());
        var y = VoiceCatalog.build(List.of(b), List.of(), Map.of(), Map.of());
        assertNotEquals(x, y); // record equality compares arrays by identity
        assertEquals(VoiceCatalog.signature(x), VoiceCatalog.signature(y));
        var z = VoiceCatalog.build(List.of(b), List.of(), Map.of("denis", 0.5f), Map.of());
        assertNotEquals(VoiceCatalog.signature(x), VoiceCatalog.signature(z));
    }

    @Test
    void selectionFallsBackWhenVoiceRemoved() {
        var e = VoiceCatalog.build(List.of(m("denis"), m("irina")), List.of(), Map.of(), Map.of());
        assertEquals("irina", VoiceCatalog.selectOrFallback(e, "irina", "denis"));
        assertEquals("denis", VoiceCatalog.selectOrFallback(e, "gone", "denis"));
        assertEquals("denis", VoiceCatalog.selectOrFallback(e, "gone", "also-gone"));
    }
}
```

- [ ] **Step 2: Run** — `./gradlew test --tests '*VoiceCatalogTest*'` → FAIL (class missing).

- [ ] **Step 3: Implement `VoiceCatalog`**

```java
package org.mamoru.omnichat.client.ui;

import net.minecraft.client.MinecraftClient;
import org.mamoru.omnichat.client.config.OmnichatConfig;
import org.mamoru.omnichat.client.network.ModelDownloadManager;
import org.mamoru.omnichat.client.network.VoiceCache;
import org.mamoru.omnichat.voice.VoiceMeta;
import org.mamoru.omnichat.voice.VoiceMetaReader;

import java.nio.file.Path;
import java.util.*;

/** Everything the Voice tab shows: server voices, local-only voices and their download state. */
public final class VoiceCatalog {
    public enum State { INSTALLED, REMOTE, DOWNLOADING, FAILED }

    public record Entry(VoiceMeta meta, State state, float progress, String failure, boolean onServer) {
    }

    private VoiceCatalog() {
    }

    public static List<Entry> build(List<VoiceMeta> server, List<VoiceMeta> local,
                                    Map<String, Float> downloads, Map<String, String> failures) {
        Map<String, VoiceMeta> localByModel = new LinkedHashMap<>();
        for (VoiceMeta m : local) localByModel.put(m.model(), m);

        List<Entry> out = new ArrayList<>();
        Set<String> seen = new HashSet<>();
        for (VoiceMeta s : server) {
            if (!seen.add(s.model())) continue;
            VoiceMeta l = localByModel.get(s.model());
            out.add(entry(l != null ? l : s, l != null, downloads, failures, true));
        }
        List<String> localOnly = new ArrayList<>();
        for (String model : localByModel.keySet()) {
            if (!seen.contains(model)) localOnly.add(model);
        }
        Collections.sort(localOnly);
        for (String model : localOnly) {
            out.add(entry(localByModel.get(model), true, downloads, failures, false));
        }
        return out;
    }

    private static Entry entry(VoiceMeta meta, boolean installed, Map<String, Float> downloads,
                               Map<String, String> failures, boolean onServer) {
        Float progress = downloads.get(meta.model());
        if (progress != null) return new Entry(meta, State.DOWNLOADING, progress, "", onServer);
        if (installed) return new Entry(meta, State.INSTALLED, 1f, "", onServer);
        String failure = failures.get(meta.model());
        if (failure != null) return new Entry(meta, State.FAILED, 0f, failure, onServer);
        return new Entry(meta, State.REMOTE, 0f, "", onServer);
    }

    public static String selectOrFallback(List<Entry> entries, String selected, String configured) {
        if (entries.isEmpty()) return null;
        if (contains(entries, selected)) return selected;
        if (contains(entries, configured)) return configured;
        return entries.get(0).meta().model();
    }

    private static boolean contains(List<Entry> entries, String model) {
        if (model == null) return false;
        for (Entry e : entries) {
            if (e.meta().model().equals(model)) return true;
        }
        return false;
    }

    // Local metadata is read once per model (folder size walks hundreds of files); see invalidateLocal
    private static final Map<String, VoiceMeta> LOCAL_CACHE = new HashMap<>();

    /** Live catalog from the client's real sources. Render thread. */
    public static List<Entry> current() {
        List<VoiceMeta> local = new ArrayList<>();
        for (String model : OmnichatConfig.listAvailableModels()) {
            Path dir = OmnichatConfig.resolveModelDir(model);
            if (dir != null) local.add(LOCAL_CACHE.computeIfAbsent(model, m -> VoiceMetaReader.read(dir, m)));
        }
        ModelDownloadManager downloads = ModelDownloadManager.getInstance();
        return build(VoiceCache.getInstance().getCatalog(), local, downloads.getActiveDownloads(), downloads.getFailures());
    }

    /** Forget cached local metadata (a model was installed or replaced). Any thread. */
    public static void invalidateLocal(String model) {
        MinecraftClient.getInstance().execute(() -> LOCAL_CACHE.remove(model));
    }

    /**
     * What the Voice tab shows, without array identity: used to decide whether to rebuild.
     * (VoiceMeta holds a byte[], so record equality would never match.)
     */
    public static List<String> signature(List<Entry> entries) {
        List<String> out = new ArrayList<>(entries.size());
        for (Entry e : entries) {
            out.add(e.meta().model() + "|" + e.meta().name() + "|" + e.state() + "|"
                    + Math.round(e.progress() * 100) + "|" + e.failure() + "|" + e.onServer());
        }
        return out;
    }
}
```

- [ ] **Step 4: `ModelDownloadManager` failures**

Add field `private final Map<String, String> failures = new HashMap<>();` and method:

```java
    /** Last failure reason per model since its last request (shown on the voice card). */
    public synchronized Map<String, String> getFailures() {
        return Map.copyOf(failures);
    }
```

In `requestDownload(String modelName)` (at its start, after the name validation) add `failures.remove(modelName);`. In the method that logs `"Download of model '{}' failed: {}"` (around line 325) add `failures.put(d.modelName, reason);` right after the log line. In `clear()` add `failures.clear();`.

- [ ] **Step 5: Run** — `./gradlew test --tests '*VoiceCatalogTest*'` → 6 PASS; `./gradlew compileClientJava` → OK.

- [ ] **Step 6: Commit**

```bash
git add src/client/java/org/mamoru/omnichat/client/ui/VoiceCatalog.java src/client/java/org/mamoru/omnichat/client/network/ModelDownloadManager.java src/test/java/org/mamoru/omnichat/client/ui/VoiceCatalogTest.java
git commit -m "feat(ui): merge server, local and download state into a voice catalog"
```

---

### Task 6: Theme, layout math, text fitting

**Files:**
- Create: `src/client/java/org/mamoru/omnichat/client/ui/HudLayout.java`
- Create: `src/client/java/org/mamoru/omnichat/client/ui/HudText.java`
- Create: `src/client/java/org/mamoru/omnichat/client/ui/HudTheme.java`
- Test: `src/test/java/org/mamoru/omnichat/client/ui/HudLayoutTest.java`, `HudTextTest.java`

**Interfaces:**
- Produces:
  - `record HudLayout.Rect(int x, int y, int w, int h)` with `right()`, `bottom()`, `contains(Rect)`.
  - `record HudLayout(Rect panel, Rect header, Rect tabs, Rect body, Rect footer, Rect grid, Rect detail, int columns)`; `static HudLayout compute(int screenW, int screenH)`; constants `MAX_W=420, MAX_H=260, MARGIN=8, HEADER_H=26, TABS_H=14, FOOTER_H=14, TILE=30, TILE_GAP=4, PAD=6`.
  - `static int HudLayout.maxGuiScale(int windowW, int windowH)` — mirrors Minecraft: largest `s` with `windowW / s >= 320 && windowH / s >= 240` (≥ 1).
  - `static String HudText.ellipsize(String s, int maxWidth, ToIntFunction<String> width)`; `static List<String> HudText.wrap(String s, int maxWidth, int maxLines, ToIntFunction<String> width)`.
  - `HudTheme` constants `ACCENT, ACCENT_DIM, BG, TILE_BG, TEXT, MUTED, OK, WARN` and static draw methods `frame(DrawContext, Rect)`, `frame(DrawContext, int x, int y, int w, int h, int color)`, `divider(DrawContext, int x, int y, int w)`, `spacedTitle(DrawContext, TextRenderer, String, int x, int y, int color)`, `text(DrawContext, TextRenderer, Text, int x, int y, int color)`.

- [ ] **Step 1: Failing tests**

```java
package org.mamoru.omnichat.client.ui;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class HudLayoutTest {
    private static final int[][] WINDOWS = {{854, 480}, {1280, 720}, {1920, 1080}};

    @Test
    void maxGuiScaleMatchesMinecraft() {
        assertEquals(2, HudLayout.maxGuiScale(854, 480));
        assertEquals(3, HudLayout.maxGuiScale(1280, 720));
        assertEquals(4, HudLayout.maxGuiScale(1920, 1080));
    }

    @Test
    void everyRectFitsOnEveryValidScale() {
        for (int[] win : WINDOWS) {
            for (int s = 1; s <= HudLayout.maxGuiScale(win[0], win[1]); s++) {
                int w = (int) Math.ceil(win[0] / (double) s), h = (int) Math.ceil(win[1] / (double) s);
                HudLayout l = HudLayout.compute(w, h);
                HudLayout.Rect screen = new HudLayout.Rect(0, 0, w, h);
                String at = win[0] + "x" + win[1] + "@" + s;
                assertTrue(screen.contains(l.panel()), "panel " + at);
                for (HudLayout.Rect r : new HudLayout.Rect[]{l.header(), l.tabs(), l.body(), l.footer(), l.grid(), l.detail()}) {
                    assertTrue(l.panel().contains(r), r + " outside panel " + at);
                    assertTrue(r.w() > 0 && r.h() > 0, "empty rect " + r + " " + at);
                }
                assertTrue(l.columns() >= 2, "columns " + at);
                assertTrue(l.detail().w() >= 120, "detail too narrow " + at);
                assertTrue(l.body().h() >= 140, "body too short " + at);
            }
        }
    }

    @Test
    void panelIsCappedAndCentered() {
        HudLayout l = HudLayout.compute(1920, 1080);
        assertEquals(HudLayout.MAX_W, l.panel().w());
        assertEquals(HudLayout.MAX_H, l.panel().h());
        assertEquals((1920 - HudLayout.MAX_W) / 2, l.panel().x());
    }
}
```

```java
package org.mamoru.omnichat.client.ui;

import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.function.ToIntFunction;

import static org.junit.jupiter.api.Assertions.*;

class HudTextTest {
    // 6 px per char, like most vanilla glyphs
    static final ToIntFunction<String> W = s -> s.length() * 6;

    @Test
    void keepsShortText() {
        assertEquals("Denis", HudText.ellipsize("Denis", 100, W));
    }

    @Test
    void ellipsizesLongNames() {
        String out = HudText.ellipsize("Ш".repeat(32), 60, W);
        assertTrue(out.endsWith("…"));
        assertTrue(W.applyAsInt(out) <= 60);
    }

    @Test
    void wrapsAndLimitsLines() {
        List<String> lines = HudText.wrap("one two three four five six seven", 30, 2, W);
        assertEquals(2, lines.size());
        assertTrue(lines.get(1).endsWith("…"));
        for (String l : lines) assertTrue(W.applyAsInt(l) <= 30);
    }

    @Test
    void wrapsUnbreakableWords() {
        List<String> lines = HudText.wrap("x".repeat(40), 60, 3, W);
        assertEquals(3, lines.size());
        for (String l : lines) assertTrue(W.applyAsInt(l) <= 60);
    }
}
```

- [ ] **Step 2: Run** — `./gradlew test --tests '*HudLayoutTest*' --tests '*HudTextTest*'` → FAIL (classes missing).

- [ ] **Step 3: Implement `HudLayout`**

```java
package org.mamoru.omnichat.client.ui;

/** Pure layout math for OmnichatScreen, in scaled GUI pixels. */
public record HudLayout(Rect panel, Rect header, Rect tabs, Rect body, Rect footer,
                        Rect grid, Rect detail, int columns) {
    public static final int MAX_W = 420, MAX_H = 260, MARGIN = 8;
    public static final int HEADER_H = 26, TABS_H = 14, FOOTER_H = 14, PAD = 6;
    public static final int TILE = 30, TILE_GAP = 4;

    public record Rect(int x, int y, int w, int h) {
        public int right() {
            return x + w;
        }

        public int bottom() {
            return y + h;
        }

        public boolean contains(Rect o) {
            return o.x >= x && o.y >= y && o.right() <= right() && o.bottom() <= bottom();
        }
    }

    public static HudLayout compute(int screenW, int screenH) {
        int w = Math.min(screenW - 2 * MARGIN, MAX_W);
        int h = Math.min(screenH - 2 * MARGIN, MAX_H);
        Rect panel = new Rect((screenW - w) / 2, (screenH - h) / 2, w, h);
        int ix = panel.x() + PAD, iw = w - 2 * PAD;
        Rect header = new Rect(ix, panel.y() + PAD, iw, HEADER_H);
        Rect tabs = new Rect(ix, header.bottom() + 2, iw, TABS_H);
        Rect footer = new Rect(ix, panel.bottom() - PAD - FOOTER_H, iw, FOOTER_H);
        int bodyY = tabs.bottom() + 4;
        Rect body = new Rect(ix, bodyY, iw, footer.y() - 2 - bodyY);

        // Grid takes ~42% of the width (at least 2 tiles), the detail card the rest
        int gridW = Math.max(2 * TILE + TILE_GAP, (int) (iw * 0.42));
        int columns = Math.max(2, (gridW + TILE_GAP) / (TILE + TILE_GAP));
        gridW = columns * TILE + (columns - 1) * TILE_GAP;
        Rect grid = new Rect(ix, body.y(), gridW, body.h());
        Rect detail = new Rect(grid.right() + PAD + 1, body.y(), body.right() - grid.right() - PAD - 1, body.h());
        return new HudLayout(panel, header, tabs, body, footer, grid, detail, columns);
    }

    /** Largest GUI scale Minecraft offers for this window (its 320x240 minimum). */
    public static int maxGuiScale(int windowW, int windowH) {
        int s = 1;
        while (windowW / (s + 1) >= 320 && windowH / (s + 1) >= 240) s++;
        return s;
    }
}
```

- [ ] **Step 4: Implement `HudText`**

```java
package org.mamoru.omnichat.client.ui;

import java.util.ArrayList;
import java.util.List;
import java.util.function.ToIntFunction;

/** Pure text fitting; the width function is TextRenderer::getWidth in game, a stub in tests. */
public final class HudText {
    public static final String ELLIPSIS = "…";

    private HudText() {
    }

    public static String ellipsize(String s, int maxWidth, ToIntFunction<String> width) {
        if (width.applyAsInt(s) <= maxWidth) return s;
        int end = s.length();
        while (end > 0 && width.applyAsInt(s.substring(0, end) + ELLIPSIS) > maxWidth) end--;
        return s.substring(0, end) + ELLIPSIS;
    }

    public static List<String> wrap(String s, int maxWidth, int maxLines, ToIntFunction<String> width) {
        List<String> lines = new ArrayList<>();
        StringBuilder line = new StringBuilder();
        for (String word : s.split(" ")) {
            String candidate = line.isEmpty() ? word : line + " " + word;
            if (width.applyAsInt(candidate) <= maxWidth) {
                line.setLength(0);
                line.append(candidate);
                continue;
            }
            if (!line.isEmpty()) {
                lines.add(line.toString());
                line.setLength(0);
            }
            // A word wider than the line is split by characters
            String rest = word;
            while (width.applyAsInt(rest) > maxWidth) {
                int cut = rest.length();
                while (cut > 1 && width.applyAsInt(rest.substring(0, cut)) > maxWidth) cut--;
                lines.add(rest.substring(0, cut));
                rest = rest.substring(cut);
            }
            line.append(rest);
        }
        if (!line.isEmpty()) lines.add(line.toString());
        if (lines.size() > maxLines) {
            List<String> cut = new ArrayList<>(lines.subList(0, maxLines));
            cut.set(maxLines - 1, ellipsize(cut.get(maxLines - 1) + ELLIPSIS, maxWidth, width));
            return cut;
        }
        return lines;
    }
}
```

- [ ] **Step 5: Implement `HudTheme`**

```java
package org.mamoru.omnichat.client.ui;

import net.minecraft.client.font.TextRenderer;
import net.minecraft.client.gui.DrawContext;
import net.minecraft.text.Text;

/** HUD palette and drawing primitives (see spec "Визуальный стиль"). */
public final class HudTheme {
    public static final int ACCENT = 0xFF35E0C8;
    public static final int ACCENT_DIM = 0x7335E0C8;
    public static final int BG = 0xDB0A080C;
    public static final int TILE_BG = 0xFF15111A;
    public static final int TEXT = 0xFFD9D4DC;
    public static final int MUTED = 0xFF9A93A0;
    public static final int OK = 0xFF59E36B;
    public static final int WARN = 0xFFFFCF4A;
    public static final int ERROR = 0xFFFF5A5A;
    private static final int BRACKET = 6;

    private HudTheme() {
    }

    /** Panel: background, 1 px accent border, 2 px corner brackets top-left and bottom-right. */
    public static void frame(DrawContext ctx, HudLayout.Rect r) {
        ctx.fill(r.x(), r.y(), r.right(), r.bottom(), BG);
        ctx.drawStrokedRectangle(r.x(), r.y(), r.w(), r.h(), ACCENT);
        ctx.fill(r.x() - 2, r.y() - 2, r.x() + BRACKET, r.y(), ACCENT);
        ctx.fill(r.x() - 2, r.y() - 2, r.x(), r.y() + BRACKET, ACCENT);
        ctx.fill(r.right() - BRACKET, r.bottom(), r.right() + 2, r.bottom() + 2, ACCENT);
        ctx.fill(r.right(), r.bottom() - BRACKET, r.right() + 2, r.bottom() + 2, ACCENT);
    }

    /** Thin 1 px outline (tiles, inputs). */
    public static void frame(DrawContext ctx, int x, int y, int w, int h, int color) {
        ctx.drawStrokedRectangle(x, y, w, h, color);
    }

    public static void divider(DrawContext ctx, int x, int y, int w) {
        ctx.fill(x, y, x + w, y + 1, ACCENT_DIM);
    }

    /** Letter-spaced caps title, like "O M N I C H A T". */
    public static void spacedTitle(DrawContext ctx, TextRenderer tr, String s, int x, int y, int color) {
        int cx = x;
        for (int i = 0; i < s.length(); i++) {
            String ch = String.valueOf(s.charAt(i));
            ctx.drawText(tr, ch, cx, y, color, false);
            cx += tr.getWidth(ch) + 3;
        }
    }

    public static void text(DrawContext ctx, TextRenderer tr, Text t, int x, int y, int color) {
        ctx.drawText(tr, t, x, y, color, false);
    }
}
```

- [ ] **Step 6: Run** — `./gradlew test --tests '*HudLayoutTest*' --tests '*HudTextTest*'` → 7 PASS; `./gradlew compileClientJava` → OK. If `everyRectFitsOnEveryValidScale` fails on `body too short` at 1280x720@3 or 1920x1080@4, lower `HEADER_H` to 22 and re-run (that's the only knob; keep `MAX_W/MAX_H`).

- [ ] **Step 7: Commit**

```bash
git add src/client/java/org/mamoru/omnichat/client/ui/HudLayout.java src/client/java/org/mamoru/omnichat/client/ui/HudText.java src/client/java/org/mamoru/omnichat/client/ui/HudTheme.java src/test/java/org/mamoru/omnichat/client/ui/HudLayoutTest.java src/test/java/org/mamoru/omnichat/client/ui/HudTextTest.java
git commit -m "feat(ui): add hud theme, adaptive layout and text fitting"
```

---

### Task 7: Widgets and portrait textures

**Files:**
- Create: `src/client/java/org/mamoru/omnichat/client/ui/PortraitTextures.java`
- Create: `src/client/java/org/mamoru/omnichat/client/ui/widget/HudButton.java`, `HudToggle.java`, `HudSlider.java`, `TabBar.java`, `VoiceTile.java`, `StatusLine.java`

**Interfaces:**
- Consumes: `HudTheme`, `HudText` (Task 6), `PortraitGenerator` (Task 4), `VoiceCatalog.Entry/State` (Task 5), `VoiceMeta` (Task 2).
- Produces:
  - `PortraitTextures.get(VoiceMeta meta): Identifier` (16×16 or 32×32 texture, cached per model + portrait hash); `PortraitTextures.clear()`; `static int PortraitTextures.sizeOf(Identifier)`.
  - `new HudButton(int x, int y, int w, int h, Text label, Runnable onPress)`.
  - `new HudToggle(int x, int y, int w, Text label, boolean value, Consumer<Boolean> onChange)` (height 14).
  - `new HudSlider(int x, int y, int w, Text label, double min, double max, double value, double step, DoubleFunction<Text> format, DoubleConsumer onChange)` (height 14).
  - `new TabBar(int x, int y, int w, List<Text> labels, int active, IntConsumer onSelect)` (height 14).
  - `new VoiceTile(int x, int y, VoiceCatalog.Entry entry, boolean selected, boolean active, Consumer<String> onSelect, Consumer<String> onPreview)` (size `HudLayout.TILE`).
  - `StatusLine.draw(DrawContext, TextRenderer, int x, int y, int w, Text left, Text right, int rightColor)`.

These are rendering classes: verified by `./gradlew compileClientJava` and visually in Task 9/11, not unit tests.

- [ ] **Step 1: `PortraitTextures`**

```java
package org.mamoru.omnichat.client.ui;

import net.minecraft.client.MinecraftClient;
import net.minecraft.client.texture.NativeImage;
import net.minecraft.client.texture.NativeImageBackedTexture;
import net.minecraft.util.Identifier;
import org.mamoru.omnichat.voice.VoiceMeta;
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
        if (meta.portrait().length > 0) {
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
```

Verify the two `NativeImage` calls exist with the JDK javap (path `C:\Program Files\Java\jdk-25\bin\javap.exe`, jar `.gradle/loom-cache/minecraftMaven/net/minecraft/minecraft-clientOnly-*/…yarn…v2.jar`, class `net.minecraft.client.texture.NativeImage`): `read(byte[])` and `setColorArgb(int,int,int)`. If `read(byte[])` is missing use `NativeImage.read(new java.io.ByteArrayInputStream(bytes))`; if `setColorArgb` is missing use `setColor(x, y, abgr)` with `abgr = (argb & 0xFF00FF00) | ((argb & 0xFF) << 16) | ((argb >> 16) & 0xFF)`.

- [ ] **Step 2: `HudButton`**

```java
package org.mamoru.omnichat.client.ui.widget;

import net.minecraft.client.MinecraftClient;
import net.minecraft.client.gui.Click;
import net.minecraft.client.gui.DrawContext;
import net.minecraft.client.gui.screen.narration.NarrationMessageBuilder;
import net.minecraft.client.gui.widget.ClickableWidget;
import net.minecraft.client.input.KeyInput;
import net.minecraft.text.Text;
import org.mamoru.omnichat.client.ui.HudText;
import org.mamoru.omnichat.client.ui.HudTheme;

public class HudButton extends ClickableWidget {
    private final Runnable onPress;

    public HudButton(int x, int y, int w, int h, Text label, Runnable onPress) {
        super(x, y, w, h, label);
        this.onPress = onPress;
    }

    @Override
    protected void renderWidget(DrawContext ctx, int mouseX, int mouseY, float delta) {
        var tr = MinecraftClient.getInstance().textRenderer;
        boolean hot = active && (isHovered() || isFocused());
        ctx.fill(getX(), getY(), getX() + width, getY() + height, hot ? 0x3335E0C8 : 0x22000000);
        HudTheme.frame(ctx, getX(), getY(), width, height, active ? (hot ? HudTheme.ACCENT : HudTheme.ACCENT_DIM) : 0x33FFFFFF);
        String label = HudText.ellipsize(getMessage().getString(), width - 6, tr::getWidth);
        int color = active ? (hot ? HudTheme.ACCENT : HudTheme.TEXT) : HudTheme.MUTED;
        ctx.drawText(tr, label, getX() + (width - tr.getWidth(label)) / 2, getY() + (height - 8) / 2, color, false);
    }

    @Override
    public void onClick(Click click, boolean doubled) {
        onPress.run();
    }

    @Override
    public boolean keyPressed(KeyInput input) {
        if (active && visible && input.isEnterOrSpace()) {
            playDownSound(MinecraftClient.getInstance().getSoundManager());
            onPress.run();
            return true;
        }
        return false;
    }

    @Override
    protected void appendClickableNarrations(NarrationMessageBuilder builder) {
        appendDefaultNarrations(builder);
    }
}
```

- [ ] **Step 3: `HudToggle`**

```java
package org.mamoru.omnichat.client.ui.widget;

import net.minecraft.client.MinecraftClient;
import net.minecraft.client.gui.Click;
import net.minecraft.client.gui.DrawContext;
import net.minecraft.client.gui.screen.narration.NarrationMessageBuilder;
import net.minecraft.client.gui.widget.ClickableWidget;
import net.minecraft.client.input.KeyInput;
import net.minecraft.screen.ScreenTexts;
import net.minecraft.text.Text;
import org.mamoru.omnichat.client.ui.HudText;
import org.mamoru.omnichat.client.ui.HudTheme;

import java.util.function.Consumer;

/** "Label ........ [■ ]" row; click or Enter flips it. */
public class HudToggle extends ClickableWidget {
    public static final int HEIGHT = 14;
    private final Text label;
    private final Consumer<Boolean> onChange;
    private boolean value;

    public HudToggle(int x, int y, int w, Text label, boolean value, Consumer<Boolean> onChange) {
        super(x, y, w, HEIGHT, label);
        this.label = label;
        this.value = value;
        this.onChange = onChange;
        updateMessage();
    }

    private void updateMessage() {
        setMessage(ScreenTexts.composeToggleText(label, value));
    }

    private void flip() {
        value = !value;
        updateMessage();
        onChange.accept(value);
    }

    @Override
    protected void renderWidget(DrawContext ctx, int mouseX, int mouseY, float delta) {
        var tr = MinecraftClient.getInstance().textRenderer;
        boolean hot = isHovered() || isFocused();
        int sw = 18, sx = getX() + width - sw;
        String text = HudText.ellipsize(label.getString(), width - sw - 6, tr::getWidth);
        ctx.drawText(tr, text, getX(), getY() + 3, hot ? HudTheme.ACCENT : HudTheme.TEXT, false);
        HudTheme.frame(ctx, sx, getY() + 2, sw, 10, hot ? HudTheme.ACCENT : HudTheme.ACCENT_DIM);
        int kx = value ? sx + sw - 8 : sx + 2;
        ctx.fill(kx, getY() + 4, kx + 6, getY() + 10, value ? HudTheme.ACCENT : HudTheme.MUTED);
    }

    @Override
    public void onClick(Click click, boolean doubled) {
        flip();
    }

    @Override
    public boolean keyPressed(KeyInput input) {
        if (active && visible && input.isEnterOrSpace()) {
            playDownSound(MinecraftClient.getInstance().getSoundManager());
            flip();
            return true;
        }
        return false;
    }

    @Override
    protected void appendClickableNarrations(NarrationMessageBuilder builder) {
        appendDefaultNarrations(builder);
    }
}
```

- [ ] **Step 4: `HudSlider`** (reuses vanilla drag/keyboard behaviour; only the look changes)

```java
package org.mamoru.omnichat.client.ui.widget;

import net.minecraft.client.MinecraftClient;
import net.minecraft.client.gui.DrawContext;
import net.minecraft.client.gui.widget.SliderWidget;
import net.minecraft.text.Text;
import org.mamoru.omnichat.client.ui.HudTheme;

import java.util.function.DoubleConsumer;
import java.util.function.DoubleFunction;

/** "Label  value  [====|-----]" row with snapping to {@code step}. */
public class HudSlider extends SliderWidget {
    public static final int HEIGHT = 14;
    private final Text label;
    private final double min, max, step;
    private final DoubleFunction<Text> format;
    private final DoubleConsumer onChange;

    public HudSlider(int x, int y, int w, Text label, double min, double max, double value, double step,
                     DoubleFunction<Text> format, DoubleConsumer onChange) {
        super(x, y, w, HEIGHT, Text.empty(), (Math.clamp(value, min, max) - min) / (max - min));
        this.label = label;
        this.min = min;
        this.max = max;
        this.step = step;
        this.format = format;
        this.onChange = onChange;
        updateMessage();
    }

    public double current() {
        double v = min + value * (max - min);
        return step > 0 ? Math.round(v / step) * step : v;
    }

    @Override
    protected void updateMessage() {
        setMessage(Text.empty().append(label).append(": ").append(format.apply(current())));
    }

    @Override
    protected void applyValue() {
        onChange.accept(current());
    }

    @Override
    public void renderWidget(DrawContext ctx, int mouseX, int mouseY, float delta) {
        var tr = MinecraftClient.getInstance().textRenderer;
        boolean hot = isHovered() || isFocused();
        int labelW = width / 2;
        ctx.drawText(tr, label, getX(), getY() + 3, hot ? HudTheme.ACCENT : HudTheme.TEXT, false);
        Text v = format.apply(current());
        ctx.drawText(tr, v, getX() + labelW - tr.getWidth(v) - 4, getY() + 3, HudTheme.MUTED, false);
        int bx = getX() + labelW, bw = width - labelW, by = getY() + 6;
        ctx.fill(bx, by, bx + bw, by + 2, 0xFF2A2430);
        int fill = (int) (value * bw);
        ctx.fill(bx, by, bx + fill, by + 2, HudTheme.ACCENT);
        int kx = Math.min(bx + fill, bx + bw - 3);
        ctx.fill(kx, getY() + 2, kx + 3, getY() + 12, hot ? 0xFFFFFFFF : HudTheme.TEXT);
    }
}
```

- [ ] **Step 5: `TabBar`**

```java
package org.mamoru.omnichat.client.ui.widget;

import net.minecraft.client.MinecraftClient;
import net.minecraft.client.gui.Click;
import net.minecraft.client.gui.DrawContext;
import net.minecraft.client.gui.screen.narration.NarrationMessageBuilder;
import net.minecraft.client.gui.widget.ClickableWidget;
import net.minecraft.client.input.KeyInput;
import net.minecraft.text.Text;
import org.mamoru.omnichat.client.ui.HudTheme;

import java.util.List;
import java.util.function.IntConsumer;

/** Row of tabs. Left/Right when focused, or 1..9 handled by the screen. */
public class TabBar extends ClickableWidget {
    public static final int HEIGHT = 14;
    private final List<Text> labels;
    private final IntConsumer onSelect;
    private final int active;

    public TabBar(int x, int y, int w, List<Text> labels, int active, IntConsumer onSelect) {
        super(x, y, w, HEIGHT, labels.get(active));
        this.labels = labels;
        this.active = active;
        this.onSelect = onSelect;
    }

    private int tabX(int i) {
        var tr = MinecraftClient.getInstance().textRenderer;
        int x = getX();
        for (int j = 0; j < i; j++) x += tr.getWidth(labels.get(j)) + 14;
        return x;
    }

    @Override
    protected void renderWidget(DrawContext ctx, int mouseX, int mouseY, float delta) {
        var tr = MinecraftClient.getInstance().textRenderer;
        for (int i = 0; i < labels.size(); i++) {
            int x = tabX(i), w = tr.getWidth(labels.get(i)) + 12;
            boolean on = i == active;
            boolean hover = mouseX >= x && mouseX < x + w && mouseY >= getY() && mouseY < getY() + HEIGHT;
            if (on) ctx.fill(x, getY(), x + w, getY() + HEIGHT, 0x1435E0C8);
            HudTheme.frame(ctx, x, getY(), w, HEIGHT, on ? HudTheme.ACCENT : HudTheme.ACCENT_DIM);
            ctx.drawText(tr, labels.get(i), x + 6, getY() + 3, on || hover ? HudTheme.ACCENT : HudTheme.MUTED, false);
        }
        if (isFocused()) ctx.fill(tabX(active), getY() + HEIGHT, tabX(active) + 8, getY() + HEIGHT + 1, HudTheme.ACCENT);
    }

    @Override
    public void onClick(Click click, boolean doubled) {
        var tr = MinecraftClient.getInstance().textRenderer;
        for (int i = 0; i < labels.size(); i++) {
            int x = tabX(i), w = tr.getWidth(labels.get(i)) + 12;
            if (click.x() >= x && click.x() < x + w && i != active) onSelect.accept(i);
        }
    }

    @Override
    public boolean keyPressed(KeyInput input) {
        if (input.isLeft() && active > 0) {
            onSelect.accept(active - 1);
            return true;
        }
        if (input.isRight() && active < labels.size() - 1) {
            onSelect.accept(active + 1);
            return true;
        }
        return false;
    }

    @Override
    protected void appendClickableNarrations(NarrationMessageBuilder builder) {
        appendDefaultNarrations(builder);
    }
}
```

- [ ] **Step 6: `VoiceTile`**

```java
package org.mamoru.omnichat.client.ui.widget;

import net.minecraft.client.MinecraftClient;
import net.minecraft.client.gl.RenderPipelines;
import net.minecraft.client.gui.Click;
import net.minecraft.client.gui.DrawContext;
import net.minecraft.client.gui.screen.narration.NarrationMessageBuilder;
import net.minecraft.client.gui.widget.ClickableWidget;
import net.minecraft.client.input.KeyInput;
import net.minecraft.client.input.MouseInput;
import net.minecraft.text.Text;
import net.minecraft.util.Identifier;
import org.mamoru.omnichat.client.ui.HudLayout;
import org.mamoru.omnichat.client.ui.HudTheme;
import org.mamoru.omnichat.client.ui.PortraitTextures;
import org.mamoru.omnichat.client.ui.VoiceCatalog;

import java.util.function.Consumer;

/** Portrait tile. LMB/Enter selects, RMB previews. Badge: ✓ active, ↓ remote, % downloading, ! failed. */
public class VoiceTile extends ClickableWidget {
    private final VoiceCatalog.Entry entry;
    private final boolean selected, activeVoice;
    private final Consumer<String> onSelect, onPreview;

    public VoiceTile(int x, int y, VoiceCatalog.Entry entry, boolean selected, boolean activeVoice,
                     Consumer<String> onSelect, Consumer<String> onPreview) {
        super(x, y, HudLayout.TILE, HudLayout.TILE, Text.literal(entry.meta().name()));
        this.entry = entry;
        this.selected = selected;
        this.activeVoice = activeVoice;
        this.onSelect = onSelect;
        this.onPreview = onPreview;
    }

    @Override
    protected void renderWidget(DrawContext ctx, int mouseX, int mouseY, float delta) {
        int x = getX(), y = getY(), s = HudLayout.TILE;
        ctx.fill(x, y, x + s, y + s, HudTheme.TILE_BG);
        Identifier portrait = PortraitTextures.get(entry.meta());
        int size = PortraitTextures.sizeOf(portrait);
        ctx.drawTexture(RenderPipelines.GUI_TEXTURED, portrait, x + 3, y + 3, 0, 0, s - 6, s - 6, size, size, size, size);
        if (entry.state() == VoiceCatalog.State.REMOTE || entry.state() == VoiceCatalog.State.FAILED) {
            ctx.fill(x + 3, y + 3, x + s - 3, y + s - 3, 0x88000000); // dim what isn't installed
        }
        boolean hot = isHovered() || isFocused();
        int border = selected ? HudTheme.ACCENT : hot ? 0xCC35E0C8 : HudTheme.ACCENT_DIM;
        HudTheme.frame(ctx, x, y, s, s, border);
        if (selected) HudTheme.frame(ctx, x - 1, y - 1, s + 2, s + 2, HudTheme.ACCENT);
        drawBadge(ctx, x + s, y + s);
    }

    private void drawBadge(DrawContext ctx, int right, int bottom) {
        String text;
        int color;
        switch (entry.state()) {
            case DOWNLOADING -> {
                text = entry.progress() < 0 ? "…" : Math.round(entry.progress() * 100) + "%";
                color = HudTheme.WARN;
            }
            case REMOTE -> { text = "↓"; color = HudTheme.WARN; }
            case FAILED -> { text = "!"; color = HudTheme.ERROR; }
            default -> {
                if (!activeVoice) return;
                text = "✓";
                color = HudTheme.ACCENT;
            }
        }
        var tr = MinecraftClient.getInstance().textRenderer;
        int w = tr.getWidth(text) + 3;
        ctx.fill(right - w, bottom - 10, right, bottom, 0xFF0A080C);
        HudTheme.frame(ctx, right - w, bottom - 10, w, 10, color);
        ctx.drawText(tr, text, right - w + 2, bottom - 9, color, false);
    }

    @Override
    protected boolean isValidClickButton(MouseInput input) {
        return input.button() == 0 || input.button() == 1;
    }

    @Override
    public void onClick(Click click, boolean doubled) {
        if (click.button() == 1) onPreview.accept(entry.meta().model());
        else onSelect.accept(entry.meta().model());
    }

    @Override
    public boolean keyPressed(KeyInput input) {
        if (active && visible && input.isEnterOrSpace()) {
            playDownSound(MinecraftClient.getInstance().getSoundManager());
            onSelect.accept(entry.meta().model());
            return true;
        }
        return false;
    }

    @Override
    protected void appendClickableNarrations(NarrationMessageBuilder builder) {
        appendDefaultNarrations(builder);
    }
}
```

- [ ] **Step 7: `StatusLine`**

```java
package org.mamoru.omnichat.client.ui.widget;

import net.minecraft.client.font.TextRenderer;
import net.minecraft.client.gui.DrawContext;
import net.minecraft.text.Text;
import org.mamoru.omnichat.client.ui.HudTheme;

/** Divider + "left ........ right" status row. Not focusable, just drawn. */
public final class StatusLine {
    public static final int HEIGHT = 12;

    private StatusLine() {
    }

    public static void draw(DrawContext ctx, TextRenderer tr, int x, int y, int w, Text left, Text right, int rightColor) {
        HudTheme.divider(ctx, x, y, w);
        ctx.drawText(tr, left, x, y + 3, HudTheme.TEXT, false);
        ctx.drawText(tr, right, x + w - tr.getWidth(right), y + 3, rightColor, false);
    }
}
```

- [ ] **Step 8: Compile**

Run: `./gradlew compileClientJava`
Expected: `BUILD SUCCESSFUL`. Fix any signature mismatch by checking the exact method with javap (path in Step 1).

- [ ] **Step 9: Commit**

```bash
git add src/client/java/org/mamoru/omnichat/client/ui
git commit -m "feat(ui): add hud widgets and portrait textures"
```

---

### Task 8: Voice preview with live waveform

**Files:**
- Create: `src/client/java/org/mamoru/omnichat/client/tts/WaveformMeter.java`
- Create: `src/client/java/org/mamoru/omnichat/client/tts/PreviewTickets.java`
- Create: `src/client/java/org/mamoru/omnichat/client/tts/VoicePreview.java`
- Test: `src/test/java/org/mamoru/omnichat/client/tts/WaveformMeterTest.java`, `PreviewTicketsTest.java`

**Interfaces:**
- Consumes: `TtsService.loadEngineForModel(String)` (existing, package-private static in `client.tts`), `AudioUtils.floatPcmToInt16(float[], float)`, `SpatialAudioPlayer.playMono(byte[], int, BooleanSupplier)`, `OmnichatConfig`.
- Produces:
  - `WaveformMeter(float[] samples, int sampleRate)`; `float level(long elapsedMillis)` → RMS 0..1 over a 50 ms window ending at that time; `float[] bars(long elapsedMillis, int count)` → `count` levels spaced 30 ms apart, newest last; `boolean finished(long elapsedMillis)`.
  - `PreviewTickets`: `int next()`, `boolean isCurrent(int ticket)`.
  - `VoicePreview.play(String model, String sampleText)`; `VoicePreview.stop()`; `VoicePreview.playingModel(): String` (null if none); `VoicePreview.bars(int count): float[]` (zeros if idle); `VoicePreview.isLoading(String model)`.

- [ ] **Step 1: Failing tests**

```java
package org.mamoru.omnichat.client.tts;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class WaveformMeterTest {
    @Test
    void silenceThenTone() {
        int sr = 1000;
        float[] s = new float[sr]; // 1 s
        for (int i = 500; i < 1000; i++) s[i] = (i % 2 == 0) ? 0.5f : -0.5f;
        WaveformMeter m = new WaveformMeter(s, sr);
        assertEquals(0f, m.level(200), 1e-6);
        assertEquals(0.5f, m.level(800), 1e-3);
        assertFalse(m.finished(900));
        assertTrue(m.finished(1001));
    }

    @Test
    void barsHaveRequestedCountAndRange() {
        float[] s = new float[2000];
        java.util.Arrays.fill(s, 2f); // over-range input is clamped
        float[] bars = new WaveformMeter(s, 1000).bars(1500, 9);
        assertEquals(9, bars.length);
        for (float b : bars) assertTrue(b >= 0f && b <= 1f);
    }
}
```

```java
package org.mamoru.omnichat.client.tts;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class PreviewTicketsTest {
    @Test
    void staleTicketIsRejected() {
        PreviewTickets t = new PreviewTickets();
        int a = t.next();
        int b = t.next();
        assertFalse(t.isCurrent(a));
        assertTrue(t.isCurrent(b));
    }
}
```

- [ ] **Step 2: Run** — `./gradlew test --tests '*WaveformMeterTest*' --tests '*PreviewTicketsTest*'` → FAIL.

- [ ] **Step 3: Implement the pure parts**

```java
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
```

```java
package org.mamoru.omnichat.client.tts;

import java.util.concurrent.atomic.AtomicInteger;

/** "Latest request wins": a preview finishing after a newer one was requested is dropped. */
public final class PreviewTickets {
    private final AtomicInteger current = new AtomicInteger();

    public int next() {
        return current.incrementAndGet();
    }

    public boolean isCurrent(int ticket) {
        return current.get() == ticket;
    }
}
```

- [ ] **Step 4: Run** — same command → 3 PASS.

- [ ] **Step 5: `VoicePreview`**

```java
package org.mamoru.omnichat.client.tts;

import net.minecraft.client.MinecraftClient;
import org.mamoru.omnichat.client.OmnichatClient;
import org.mamoru.omnichat.client.config.OmnichatConfig;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Synthesizes a short sample with a given voice and plays it non-positionally. */
public final class VoicePreview {
    private static final Logger LOGGER = LoggerFactory.getLogger("OmniChat");
    private static final ExecutorService EXECUTOR = Executors.newSingleThreadExecutor(r -> {
        Thread t = new Thread(r, "OmniChat-Preview");
        t.setDaemon(true);
        return t;
    });
    private static final PreviewTickets TICKETS = new PreviewTickets();

    private static volatile String loadingModel;
    private static volatile String playingModel;
    private static volatile WaveformMeter meter;
    private static volatile long startedAt;

    private VoicePreview() {
    }

    public static void play(String model, String sampleText) {
        int ticket = TICKETS.next();
        loadingModel = model;
        playingModel = null;
        meter = null;
        EXECUTOR.execute(() -> {
            ITtsEngine engine = null;
            try {
                if (!TICKETS.isCurrent(ticket)) return;
                engine = TtsService.loadEngineForModel(model);
                if (engine == null || !TICKETS.isCurrent(ticket)) return;
                OmnichatConfig config = OmnichatClient.getConfig();
                float[] samples = engine.generate(sampleText, Math.max(0, config.getSpeakerId()), config.getSpeed());
                if (samples == null || samples.length == 0 || !TICKETS.isCurrent(ticket)) return;
                byte[] pcm = AudioUtils.floatPcmToInt16(samples, config.getVolume());
                int rate = engine.getSampleRate();
                MinecraftClient.getInstance().execute(() -> {
                    if (!TICKETS.isCurrent(ticket)) return;
                    meter = new WaveformMeter(samples, rate);
                    startedAt = System.currentTimeMillis();
                    playingModel = model;
                    SpatialAudioPlayer.playMono(pcm, rate, () -> TICKETS.isCurrent(ticket));
                });
            } catch (Exception | LinkageError e) {
                LOGGER.warn("Voice preview of '{}' failed: {}", model, e.toString());
            } finally {
                if (TICKETS.isCurrent(ticket)) loadingModel = null;
                if (engine != null) engine.release();
            }
        });
    }

    /** Invalidates any pending or playing preview (closing the screen, switching voice). */
    public static void stop() {
        TICKETS.next();
        loadingModel = null;
        playingModel = null;
        meter = null;
    }

    public static boolean isLoading(String model) {
        return model != null && model.equals(loadingModel);
    }

    public static String playingModel() {
        WaveformMeter m = meter;
        if (m != null && m.finished(System.currentTimeMillis() - startedAt)) {
            playingModel = null;
            meter = null;
        }
        return playingModel;
    }

    public static float[] bars(int count) {
        WaveformMeter m = meter;
        return m == null ? new float[count] : m.bars(System.currentTimeMillis() - startedAt, count);
    }
}
```

Note: `SpatialAudioPlayer.playMono` queues mono clips on a shared mono queue (one at a time); a stale preview is skipped because its `active` supplier returns false. Ensure `TtsService.loadEngineForModel` is accessible from the same package (it is `static`, package-private, in `org.mamoru.omnichat.client.tts`).

- [ ] **Step 6: Compile** — `./gradlew compileClientJava` → OK.

- [ ] **Step 7: Commit**

```bash
git add src/client/java/org/mamoru/omnichat/client/tts/WaveformMeter.java src/client/java/org/mamoru/omnichat/client/tts/PreviewTickets.java src/client/java/org/mamoru/omnichat/client/tts/VoicePreview.java src/test/java/org/mamoru/omnichat/client/tts
git commit -m "feat(tts): preview a voice with a live waveform"
```

---

### Task 9: OmnichatScreen and the three tabs

**Files:**
- Create: `src/client/java/org/mamoru/omnichat/client/ui/screen/HudTab.java`, `OmnichatScreen.java`, `VoiceTab.java`, `AudioTab.java`, `BubblesTab.java`
- Modify: `src/client/java/org/mamoru/omnichat/client/OmnichatKeybinds.java`
- Delete: `src/client/java/org/mamoru/omnichat/client/screen/OmnichatSettingsScreen.java`
- Modify: `src/main/resources/assets/omnichat/lang/en_us.json`, `ru_ru.json`

**Interfaces:**
- Consumes: everything from Tasks 2–8; `OmnichatClient.getConfig()`, `OmnichatClient.getTts().applySettings()`, `ClientNetworkHandler.canSend(id)`, `VoiceSelectionC2SPayload`, `ModelDownloadManager.requestDownload(String)`, `SpeakerCounts.get(String, Runnable)`.
- Produces:
  - `interface HudTab { void init(OmnichatScreen screen, HudLayout layout); void render(DrawContext ctx, int mouseX, int mouseY, float delta, HudLayout layout); Text hints(); default void tick() {} default boolean mouseScrolled(double mx, double my, double v) { return false; } }`
  - `OmnichatScreen(Screen parent)`; `public <T extends Element & Drawable & Selectable> T add(T widget)`; `public void rebuild()`; `public static final int TAB_VOICE=0, TAB_AUDIO=1, TAB_BUBBLES=2`.

- [ ] **Step 1: Lang keys**

Add to `en_us.json` (keep existing keys):

```json
  "omnichat.ui.title": "OMNICHAT",
  "omnichat.ui.subtitle": "Voices for your chat",
  "omnichat.ui.tab.voice": "VOICE",
  "omnichat.ui.tab.audio": "AUDIO",
  "omnichat.ui.tab.bubbles": "BUBBLES",
  "omnichat.ui.hints.voice": "LMB select · RMB preview · 1-3 tabs · O close",
  "omnichat.ui.hints.settings": "Changes apply instantly · 1-3 tabs · O close",
  "omnichat.ui.voices.empty": "No voices. Put models into config/omnichat/models or join an OmniChat server.",
  "omnichat.ui.voice.installed": "Installed",
  "omnichat.ui.voice.active": "Active",
  "omnichat.ui.voice.remote": "On server, not downloaded",
  "omnichat.ui.voice.queued": "Queued",
  "omnichat.ui.voice.downloading": "Downloading %s%%",
  "omnichat.ui.voice.failed": "Download failed: %s",
  "omnichat.ui.voice.download": "Download · %s",
  "omnichat.ui.voice.retry": "Retry download",
  "omnichat.ui.voice.preview_hint": "RMB: listen",
  "omnichat.ui.voice.preview_remote": "Download to listen",
  "omnichat.ui.voice.speaker": "Speaker",
  "omnichat.ui.voice.local_only": "Local only",
  "omnichat.ui.voice.incompatible": "Server runs another OmniChat version: local voices only",
  "omnichat.ui.voice.default_sample": "Hello! This is how I sound.",
  "omnichat.ui.audio.enabled": "Voice chat",
  "omnichat.ui.audio.volume": "Volume",
  "omnichat.ui.audio.speed": "Speed",
  "omnichat.ui.audio.robot": "Robot effect",
  "omnichat.ui.audio.own": "Read my messages",
  "omnichat.ui.audio.whispers": "Speak whispers",
  "omnichat.ui.audio.emotes": "Speak /me",
  "omnichat.ui.audio.team": "Speak team chat",
  "omnichat.ui.bubbles.enabled": "Chat bubbles",
  "omnichat.ui.bubbles.speed": "Text speed",
  "omnichat.ui.bubbles.instant": "instant",
  "omnichat.ui.bubbles.whispers": "Bubble whispers",
  "omnichat.ui.bubbles.emotes": "Bubble /me",
  "omnichat.ui.bubbles.team": "Bubble team chat",
  "omnichat.ui.bubbles.typing": "Show that I'm typing"
```

Add the same keys to `ru_ru.json` with:

```json
  "omnichat.ui.title": "OMNICHAT",
  "omnichat.ui.subtitle": "Голоса для твоего чата",
  "omnichat.ui.tab.voice": "ГОЛОС",
  "omnichat.ui.tab.audio": "ЗВУК",
  "omnichat.ui.tab.bubbles": "ОБЛАЧКА",
  "omnichat.ui.hints.voice": "ЛКМ выбрать · ПКМ прослушать · 1-3 вкладки · O закрыть",
  "omnichat.ui.hints.settings": "Применяется сразу · 1-3 вкладки · O закрыть",
  "omnichat.ui.voices.empty": "Голосов нет. Положи модели в config/omnichat/models или зайди на сервер с OmniChat.",
  "omnichat.ui.voice.installed": "Установлен",
  "omnichat.ui.voice.active": "Выбран",
  "omnichat.ui.voice.remote": "Есть на сервере, не скачан",
  "omnichat.ui.voice.queued": "В очереди",
  "omnichat.ui.voice.downloading": "Скачивается %s%%",
  "omnichat.ui.voice.failed": "Загрузка не удалась: %s",
  "omnichat.ui.voice.download": "Скачать · %s",
  "omnichat.ui.voice.retry": "Скачать снова",
  "omnichat.ui.voice.preview_hint": "ПКМ: прослушать",
  "omnichat.ui.voice.preview_remote": "Скачай, чтобы прослушать",
  "omnichat.ui.voice.speaker": "Спикер",
  "omnichat.ui.voice.local_only": "Только локально",
  "omnichat.ui.voice.incompatible": "У сервера другая версия OmniChat: только локальные голоса",
  "omnichat.ui.voice.default_sample": "Привет! Вот так я звучу.",
  "omnichat.ui.audio.enabled": "Озвучка чата",
  "omnichat.ui.audio.volume": "Громкость",
  "omnichat.ui.audio.speed": "Скорость",
  "omnichat.ui.audio.robot": "Эффект робота",
  "omnichat.ui.audio.own": "Озвучивать мои сообщения",
  "omnichat.ui.audio.whispers": "Озвучивать шёпот",
  "omnichat.ui.audio.emotes": "Озвучивать /me",
  "omnichat.ui.audio.team": "Озвучивать командный чат",
  "omnichat.ui.bubbles.enabled": "Облачка чата",
  "omnichat.ui.bubbles.speed": "Скорость текста",
  "omnichat.ui.bubbles.instant": "сразу",
  "omnichat.ui.bubbles.whispers": "Облачка для шёпота",
  "omnichat.ui.bubbles.emotes": "Облачка для /me",
  "omnichat.ui.bubbles.team": "Облачка для командного чата",
  "omnichat.ui.bubbles.typing": "Показывать, что я печатаю"
```

- [ ] **Step 2: `HudTab`**

```java
package org.mamoru.omnichat.client.ui.screen;

import net.minecraft.client.gui.DrawContext;
import net.minecraft.text.Text;
import org.mamoru.omnichat.client.ui.HudLayout;

/** One tab of OmnichatScreen: adds its widgets in init, draws extra decoration in render. */
public interface HudTab {
    void init(OmnichatScreen screen, HudLayout layout);

    void render(DrawContext ctx, int mouseX, int mouseY, float delta, HudLayout layout);

    Text hints();

    default void tick() {
    }

    default boolean mouseScrolled(double mouseX, double mouseY, double vertical) {
        return false;
    }
}
```

- [ ] **Step 3: `OmnichatScreen`**

```java
package org.mamoru.omnichat.client.ui.screen;

import net.minecraft.client.gui.Drawable;
import net.minecraft.client.gui.DrawContext;
import net.minecraft.client.gui.Element;
import net.minecraft.client.gui.Selectable;
import net.minecraft.client.gui.screen.Screen;
import net.minecraft.client.input.KeyInput;
import net.minecraft.text.Text;
import org.lwjgl.glfw.GLFW;
import org.mamoru.omnichat.client.OmnichatClient;
import org.mamoru.omnichat.client.tts.VoicePreview;
import org.mamoru.omnichat.client.ui.HudLayout;
import org.mamoru.omnichat.client.ui.HudTheme;
import org.mamoru.omnichat.client.ui.widget.TabBar;

import java.util.List;

/** The OmniChat HUD: header, tabs, active tab, hint footer, inside an adaptive panel. */
public class OmnichatScreen extends Screen {
    public static final int TAB_VOICE = 0, TAB_AUDIO = 1, TAB_BUBBLES = 2;
    private static int lastTab = TAB_VOICE;

    private final Screen parent;
    private final HudTab[] tabs = {new VoiceTab(), new AudioTab(), new BubblesTab()};
    private HudLayout layout;
    private long openedAt;

    public OmnichatScreen(Screen parent) {
        super(Text.translatable("omnichat.ui.title"));
        this.parent = parent;
    }

    @Override
    protected void init() {
        if (openedAt == 0) openedAt = System.currentTimeMillis();
        layout = HudLayout.compute(width, height);
        addDrawableChild(new TabBar(layout.tabs().x(), layout.tabs().y(), layout.tabs().w(), List.of(
                Text.translatable("omnichat.ui.tab.voice"),
                Text.translatable("omnichat.ui.tab.audio"),
                Text.translatable("omnichat.ui.tab.bubbles")), lastTab, this::selectTab));
        tabs[lastTab].init(this, layout);
    }

    public <T extends Element & Drawable & Selectable> T add(T widget) {
        return addDrawableChild(widget);
    }

    public void rebuild() {
        clearAndInit();
    }

    private void selectTab(int tab) {
        if (tab == lastTab || tab < 0 || tab >= tabs.length) return;
        lastTab = tab;
        rebuild();
    }

    @Override
    public void renderBackground(DrawContext ctx, int mouseX, int mouseY, float delta) {
        // No blur: the world stays visible behind the HUD, like the reference
        ctx.fill(0, 0, width, height, 0x55000000);
    }

    @Override
    public void render(DrawContext ctx, int mouseX, int mouseY, float delta) {
        float fade = Math.min(1f, (System.currentTimeMillis() - openedAt) / 150f);
        HudTheme.frame(ctx, layout.panel());
        var h = layout.header();
        ctx.fill(h.x(), h.y(), h.x() + 20, h.y() + 20, 0x22000000);
        HudTheme.frame(ctx, h.x(), h.y(), 20, 20, HudTheme.ACCENT);
        ctx.drawText(textRenderer, "OC", h.x() + 4, h.y() + 6, HudTheme.ACCENT, false);
        HudTheme.spacedTitle(ctx, textRenderer, Text.translatable("omnichat.ui.title").getString(), h.x() + 26, h.y() + 1, HudTheme.ACCENT);
        boolean cursor = (System.currentTimeMillis() / 500) % 2 == 0;
        ctx.drawText(textRenderer, Text.translatable("omnichat.ui.subtitle").getString() + (cursor ? " _" : ""),
                h.x() + 26, h.y() + 12, HudTheme.MUTED, false);
        HudTheme.divider(ctx, h.x(), h.bottom(), h.w());

        tabs[lastTab].render(ctx, mouseX, mouseY, delta, layout);
        super.render(ctx, mouseX, mouseY, delta);

        var f = layout.footer();
        HudTheme.divider(ctx, f.x(), f.y(), f.w());
        Text hints = tabs[lastTab].hints();
        ctx.drawText(textRenderer, hints, f.x() + (f.w() - textRenderer.getWidth(hints)) / 2, f.y() + 4, HudTheme.MUTED, false);
        if (fade < 1f) ctx.fill(0, 0, width, height, ((int) ((1f - fade) * 255) << 24) | 0x0A080C);
    }

    @Override
    public void tick() {
        tabs[lastTab].tick();
    }

    @Override
    public boolean mouseScrolled(double mouseX, double mouseY, double horizontal, double vertical) {
        return tabs[lastTab].mouseScrolled(mouseX, mouseY, vertical) || super.mouseScrolled(mouseX, mouseY, horizontal, vertical);
    }

    @Override
    public boolean keyPressed(KeyInput input) {
        int key = input.key();
        if (key >= GLFW.GLFW_KEY_1 && key <= GLFW.GLFW_KEY_3) {
            selectTab(key - GLFW.GLFW_KEY_1);
            return true;
        }
        if (key == GLFW.GLFW_KEY_O) {
            close();
            return true;
        }
        return super.keyPressed(input);
    }

    @Override
    public boolean shouldPause() {
        return false;
    }

    @Override
    public void removed() {
        VoicePreview.stop();
        OmnichatClient.getConfig().save();
    }

    @Override
    public void close() {
        client.setScreen(parent);
    }
}
```

- [ ] **Step 4: `AudioTab` and `BubblesTab`** (rows flow into a second column when the body is short)

```java
package org.mamoru.omnichat.client.ui.screen;

import net.minecraft.client.gui.DrawContext;
import net.minecraft.client.gui.widget.ClickableWidget;
import net.minecraft.text.Text;
import org.mamoru.omnichat.client.OmnichatClient;
import org.mamoru.omnichat.client.config.OmnichatConfig;
import org.mamoru.omnichat.client.ui.HudLayout;
import org.mamoru.omnichat.client.ui.widget.HudSlider;
import org.mamoru.omnichat.client.ui.widget.HudToggle;

import java.util.ArrayList;
import java.util.List;
import java.util.function.Function;

public class AudioTab implements HudTab {
    static final int ROW = 18;

    /** Lays rows top-to-bottom, wrapping into a second column if the body is too short. */
    static void layoutRows(OmnichatScreen screen, HudLayout l, List<Function<int[], ClickableWidget>> rows) {
        var b = l.body();
        int perColumn = Math.max(1, b.h() / ROW);
        int columns = rows.size() > perColumn ? 2 : 1;
        int colW = (b.w() - (columns - 1) * 12) / columns;
        for (int i = 0; i < rows.size(); i++) {
            int col = i / perColumn, row = i % perColumn;
            screen.add(rows.get(i).apply(new int[]{b.x() + col * (colW + 12), b.y() + row * ROW, colW}));
        }
    }

    @Override
    public void init(OmnichatScreen screen, HudLayout l) {
        OmnichatConfig c = OmnichatClient.getConfig();
        List<Function<int[], ClickableWidget>> rows = new ArrayList<>();
        rows.add(p -> new HudToggle(p[0], p[1], p[2], Text.translatable("omnichat.ui.audio.enabled"), c.isEnabled(), v -> {
            c.setEnabled(v);
            OmnichatClient.getTts().applySettings();
        }));
        rows.add(p -> new HudSlider(p[0], p[1], p[2], Text.translatable("omnichat.ui.audio.volume"), 0, 2, c.getVolume(), 0.05,
                v -> Text.literal(Math.round(v * 100) + "%"), v -> c.setVolume((float) v)));
        rows.add(p -> new HudSlider(p[0], p[1], p[2], Text.translatable("omnichat.ui.audio.speed"), 0.5, 2, c.getSpeed(), 0.05,
                v -> Text.literal(String.format("%.2fx", v)), v -> c.setSpeed((float) v)));
        rows.add(p -> new HudToggle(p[0], p[1], p[2], Text.translatable("omnichat.ui.audio.robot"), c.isRobotEffect(), c::setRobotEffect));
        rows.add(p -> new HudToggle(p[0], p[1], p[2], Text.translatable("omnichat.ui.audio.own"), c.isReadOwnMessages(), c::setReadOwnMessages));
        rows.add(p -> new HudToggle(p[0], p[1], p[2], Text.translatable("omnichat.ui.audio.whispers"), c.isSpeakWhispers(), c::setSpeakWhispers));
        rows.add(p -> new HudToggle(p[0], p[1], p[2], Text.translatable("omnichat.ui.audio.emotes"), c.isSpeakEmotes(), c::setSpeakEmotes));
        rows.add(p -> new HudToggle(p[0], p[1], p[2], Text.translatable("omnichat.ui.audio.team"), c.isSpeakTeamMessages(), c::setSpeakTeamMessages));
        layoutRows(screen, l, rows);
    }

    @Override
    public void render(DrawContext ctx, int mouseX, int mouseY, float delta, HudLayout layout) {
    }

    @Override
    public Text hints() {
        return Text.translatable("omnichat.ui.hints.settings");
    }
}
```

`Text.literal` above formats numbers only (not translatable copy) — allowed.

```java
package org.mamoru.omnichat.client.ui.screen;

import net.minecraft.client.gui.DrawContext;
import net.minecraft.client.gui.widget.ClickableWidget;
import net.minecraft.text.Text;
import org.mamoru.omnichat.client.OmnichatClient;
import org.mamoru.omnichat.client.config.OmnichatConfig;
import org.mamoru.omnichat.client.ui.HudLayout;
import org.mamoru.omnichat.client.ui.widget.HudSlider;
import org.mamoru.omnichat.client.ui.widget.HudToggle;

import java.util.ArrayList;
import java.util.List;
import java.util.function.Function;

public class BubblesTab implements HudTab {
    @Override
    public void init(OmnichatScreen screen, HudLayout l) {
        OmnichatConfig c = OmnichatClient.getConfig();
        List<Function<int[], ClickableWidget>> rows = new ArrayList<>();
        rows.add(p -> new HudToggle(p[0], p[1], p[2], Text.translatable("omnichat.ui.bubbles.enabled"), c.isShowChatBubbles(), c::setShowChatBubbles));
        rows.add(p -> new HudSlider(p[0], p[1], p[2], Text.translatable("omnichat.ui.bubbles.speed"), 0, 100, c.getBubbleTextSpeed(), 5,
                v -> v <= 0 ? Text.translatable("omnichat.ui.bubbles.instant") : Text.literal(Math.round(v) + "/s"),
                v -> c.setBubbleTextSpeed((float) v)));
        rows.add(p -> new HudToggle(p[0], p[1], p[2], Text.translatable("omnichat.ui.bubbles.whispers"), c.isBubbleWhispers(), c::setBubbleWhispers));
        rows.add(p -> new HudToggle(p[0], p[1], p[2], Text.translatable("omnichat.ui.bubbles.emotes"), c.isBubbleEmotes(), c::setBubbleEmotes));
        rows.add(p -> new HudToggle(p[0], p[1], p[2], Text.translatable("omnichat.ui.bubbles.team"), c.isBubbleTeamMessages(), c::setBubbleTeamMessages));
        rows.add(p -> new HudToggle(p[0], p[1], p[2], Text.translatable("omnichat.ui.bubbles.typing"), c.isSendTypingIndicator(), c::setSendTypingIndicator));
        AudioTab.layoutRows(screen, l, rows);
    }

    @Override
    public void render(DrawContext ctx, int mouseX, int mouseY, float delta, HudLayout layout) {
    }

    @Override
    public Text hints() {
        return Text.translatable("omnichat.ui.hints.settings");
    }
}
```

- [ ] **Step 5: `VoiceTab`**

```java
package org.mamoru.omnichat.client.ui.screen;

import net.fabricmc.fabric.api.client.networking.v1.ClientPlayNetworking;
import net.minecraft.client.MinecraftClient;
import net.minecraft.client.gl.RenderPipelines;
import net.minecraft.client.gui.DrawContext;
import net.minecraft.text.Text;
import net.minecraft.util.Identifier;
import org.mamoru.omnichat.client.OmnichatClient;
import org.mamoru.omnichat.client.config.OmnichatConfig;
import org.mamoru.omnichat.client.network.ClientNetworkHandler;
import org.mamoru.omnichat.client.network.ModelDownloadManager;
import org.mamoru.omnichat.client.network.VoiceCache;
import org.mamoru.omnichat.client.tts.SpeakerCounts;
import org.mamoru.omnichat.client.tts.VoicePreview;
import org.mamoru.omnichat.client.ui.*;
import org.mamoru.omnichat.client.ui.widget.HudButton;
import org.mamoru.omnichat.client.ui.widget.HudSlider;
import org.mamoru.omnichat.client.ui.widget.StatusLine;
import org.mamoru.omnichat.client.ui.widget.VoiceTile;
import org.mamoru.omnichat.network.VoiceSelectionC2SPayload;

import java.util.List;
import java.util.Locale;

public class VoiceTab implements HudTab {
    private static String selected;
    private static int scrollRow;

    private OmnichatScreen screen;
    private List<VoiceCatalog.Entry> entries = List.of();
    private int ticks;

    @Override
    public void init(OmnichatScreen screen, HudLayout l) {
        this.screen = screen;
        OmnichatConfig config = OmnichatClient.getConfig();
        entries = VoiceCatalog.current();
        selected = VoiceCatalog.selectOrFallback(entries, selected, config.getModelPath());
        if (entries.isEmpty()) return;

        var g = l.grid();
        int rowsVisible = Math.max(1, (g.h() + HudLayout.TILE_GAP) / (HudLayout.TILE + HudLayout.TILE_GAP));
        int totalRows = (entries.size() + l.columns() - 1) / l.columns();
        scrollRow = Math.clamp(scrollRow, 0, Math.max(0, totalRows - rowsVisible));
        for (int i = 0; i < entries.size(); i++) {
            int row = i / l.columns() - scrollRow, col = i % l.columns();
            if (row < 0 || row >= rowsVisible) continue;
            VoiceCatalog.Entry e = entries.get(i);
            int x = g.x() + col * (HudLayout.TILE + HudLayout.TILE_GAP);
            int y = g.y() + row * (HudLayout.TILE + HudLayout.TILE_GAP);
            boolean active = e.meta().model().equals(config.getModelPath());
            screen.add(new VoiceTile(x, y, e, e.meta().model().equals(selected), active, this::select, this::preview));
        }

        VoiceCatalog.Entry sel = selectedEntry();
        var d = l.detail();
        int bottom = d.bottom() - StatusLine.HEIGHT - 2;
        if (sel == null) return;
        switch (sel.state()) {
            case REMOTE, FAILED -> screen.add(new HudButton(d.x(), bottom - 18, d.w(), 16,
                    sel.state() == VoiceCatalog.State.FAILED
                            ? Text.translatable("omnichat.ui.voice.retry")
                            : Text.translatable("omnichat.ui.voice.download", formatSize(sel.meta().sizeBytes())),
                    () -> {
                        ModelDownloadManager.getInstance().requestDownload(sel.meta().model());
                        screen.rebuild();
                    }));
            case INSTALLED -> {
                int speakers = SpeakerCounts.get(sel.meta().model(), () -> MinecraftClient.getInstance().execute(screen::rebuild));
                if (speakers > 1 && sel.meta().model().equals(config.getModelPath())) {
                    screen.add(new HudSlider(d.x(), bottom - 16, d.w(), Text.translatable("omnichat.ui.voice.speaker"),
                            0, speakers - 1, config.getSpeakerId(), 1, v -> Text.literal(String.valueOf((int) v)), v -> {
                                config.setSpeakerId((int) v);
                                sendSelection(config);
                            }));
                }
            }
            default -> {
            }
        }
    }

    private VoiceCatalog.Entry selectedEntry() {
        for (VoiceCatalog.Entry e : entries) {
            if (e.meta().model().equals(selected)) return e;
        }
        return null;
    }

    private void select(String model) {
        VoicePreview.stop();
        selected = model;
        VoiceCatalog.Entry e = selectedEntry();
        OmnichatConfig config = OmnichatClient.getConfig();
        if (e != null && e.state() == VoiceCatalog.State.INSTALLED && !model.equals(config.getModelPath())) {
            config.setModelPath(model);
            config.setSpeakerId(0);
            config.save();
            OmnichatClient.getTts().applySettings();
            sendSelection(config);
        }
        screen.rebuild();
    }

    private static void sendSelection(OmnichatConfig config) {
        if (VoiceCache.getInstance().getServerModels().contains(config.getModelPath())
                && ClientNetworkHandler.canSend(VoiceSelectionC2SPayload.ID)) {
            ClientPlayNetworking.send(new VoiceSelectionC2SPayload(config.getModelPath(), config.getSpeakerId()));
        }
    }

    private void preview(String model) {
        selected = model;
        VoiceCatalog.Entry e = selectedEntry();
        if (e != null && e.state() == VoiceCatalog.State.INSTALLED) {
            String sample = e.meta().sample().isBlank()
                    ? Text.translatable("omnichat.ui.voice.default_sample").getString() : e.meta().sample();
            VoicePreview.play(model, sample);
        }
        screen.rebuild();
    }

    @Override
    public void tick() {
        // Downloads progress, reloads and finished installs show up without reopening
        if (++ticks % 10 == 0) {
            List<VoiceCatalog.Entry> now = VoiceCatalog.current();
            if (!VoiceCatalog.signature(now).equals(VoiceCatalog.signature(entries))) screen.rebuild();
        }
    }

    @Override
    public boolean mouseScrolled(double mouseX, double mouseY, double vertical) {
        scrollRow = Math.max(0, scrollRow - (int) Math.signum(vertical));
        screen.rebuild();
        return true;
    }

    @Override
    public void render(DrawContext ctx, int mouseX, int mouseY, float delta, HudLayout l) {
        var tr = MinecraftClient.getInstance().textRenderer;
        var d = l.detail();
        ctx.fill(d.x() - 4, d.y(), d.x() - 3, d.bottom(), HudTheme.ACCENT_DIM);
        if (entries.isEmpty()) {
            int y = l.body().y() + 4;
            for (String line : HudText.wrap(Text.translatable("omnichat.ui.voices.empty").getString(), l.body().w(), 4, tr::getWidth)) {
                ctx.drawText(tr, line, l.body().x(), y, HudTheme.MUTED, false);
                y += 10;
            }
            return;
        }
        VoiceCatalog.Entry e = selectedEntry();
        if (e == null) return;

        int big = 40;
        Identifier portrait = PortraitTextures.get(e.meta());
        int size = PortraitTextures.sizeOf(portrait);
        ctx.fill(d.x(), d.y(), d.x() + big, d.y() + big, HudTheme.TILE_BG);
        ctx.drawTexture(RenderPipelines.GUI_TEXTURED, portrait, d.x() + 4, d.y() + 4, 0, 0, big - 8, big - 8, size, size, size, size);
        HudTheme.frame(ctx, d.x(), d.y(), big, big, HudTheme.ACCENT);

        int tx = d.x() + big + 6, tw = d.right() - tx;
        ctx.drawText(tr, HudText.ellipsize(e.meta().name().toUpperCase(Locale.ROOT), tw, tr::getWidth), tx, d.y(), HudTheme.ACCENT, false);
        String meta = String.join(" · ", List.of(e.meta().language(), formatSize(e.meta().sizeBytes())).stream()
                .filter(s -> !s.isBlank()).toList());
        ctx.drawText(tr, HudText.ellipsize(meta, tw, tr::getWidth), tx, d.y() + 10, HudTheme.MUTED, false);

        // Oscilloscope: live while previewing this voice, flat otherwise
        float[] bars = e.meta().model().equals(VoicePreview.playingModel()) ? VoicePreview.bars(12) : new float[12];
        for (int i = 0; i < bars.length; i++) {
            int bh = Math.max(1, (int) (bars[i] * 16));
            int bx = tx + i * 4;
            ctx.fill(bx, d.y() + 30 - bh / 2, bx + 2, d.y() + 30 + (bh + 1) / 2, HudTheme.ACCENT);
        }

        int y = d.y() + big + 6;
        for (String line : HudText.wrap(e.meta().description(), d.w(), 4, tr::getWidth)) {
            ctx.drawText(tr, line, d.x(), y, HudTheme.TEXT, false);
            y += 10;
        }
        Text hint = e.state() == VoiceCatalog.State.INSTALLED
                ? Text.translatable("omnichat.ui.voice.preview_hint")
                : Text.translatable("omnichat.ui.voice.preview_remote");
        ctx.drawText(tr, hint, d.x(), y + 2, HudTheme.MUTED, false);

        OmnichatConfig config = OmnichatClient.getConfig();
        Text left, right;
        int color;
        switch (e.state()) {
            case DOWNLOADING -> {
                left = e.progress() < 0 ? Text.translatable("omnichat.ui.voice.queued")
                        : Text.translatable("omnichat.ui.voice.downloading", Math.round(e.progress() * 100));
                right = Text.literal(formatSize((long) (Math.max(0, e.progress()) * e.meta().sizeBytes())) + " / " + formatSize(e.meta().sizeBytes()));
                color = HudTheme.WARN;
            }
            case REMOTE -> {
                left = Text.translatable("omnichat.ui.voice.remote");
                right = Text.literal(formatSize(e.meta().sizeBytes()));
                color = HudTheme.WARN;
            }
            case FAILED -> {
                left = Text.translatable("omnichat.ui.voice.failed", e.failure());
                right = Text.literal("!");
                color = HudTheme.ERROR;
            }
            default -> {
                left = e.onServer() ? Text.translatable("omnichat.ui.voice.installed") : Text.translatable("omnichat.ui.voice.local_only");
                boolean active = e.meta().model().equals(config.getModelPath());
                right = active ? Text.translatable("omnichat.ui.voice.active") : Text.empty();
                color = HudTheme.OK;
            }
        }
        StatusLine.draw(ctx, tr, d.x(), d.bottom() - StatusLine.HEIGHT, d.w(), left, right, color);
    }

    @Override
    public Text hints() {
        return Text.translatable("omnichat.ui.hints.voice");
    }

    static String formatSize(long bytes) {
        if (bytes <= 0) return "";
        double mb = bytes / (1024.0 * 1024.0);
        return mb >= 10 ? Math.round(mb) + " MB" : String.format(Locale.ROOT, "%.1f MB", mb);
    }
}
```

When the server is incompatible (`ClientNetworkHandler.canSend(VoiceSelectionC2SPayload.ID)` is false while `MinecraftClient.getInstance().getNetworkHandler() != null`), also draw `Text.translatable("omnichat.ui.voice.incompatible")` in `HudTheme.WARN` above the status line — add this at the end of `render` before `StatusLine.draw` only when `ClientNetworkHandler.isIncompatible()` returns true. Add to `ClientNetworkHandler`:

```java
    /** True when connected to a server whose OmniChat protocol doesn't match ours. */
    public static boolean isIncompatible() {
        return serverProtocol == ServerProtocol.INCOMPATIBLE;
    }
```

- [ ] **Step 6: Keybind + delete old screen**

`OmnichatKeybinds.java`: replace `client.setScreen(new OmnichatSettingsScreen(null));` with `client.setScreen(new OmnichatScreen(null));` and fix the import (`org.mamoru.omnichat.client.ui.screen.OmnichatScreen`). Delete `src/client/java/org/mamoru/omnichat/client/screen/OmnichatSettingsScreen.java`. Run `grep -rn OmnichatSettingsScreen src` → no results.

- [ ] **Step 7: Build and look at it**

Run: `./gradlew build` → `BUILD SUCCESSFUL`, all tests pass.
Run the game: `scripts/smoke.sh -k`, then (only the Listener needs to stay) close the Speaker: `powershell -NoProfile -File scripts/mcproc.ps1 kill "dli.env=client.*username Speaker"`. Focus the Listener (`um win drive --proc java focus "key 0x4F"`), screenshot (`um win shot build/smoke/ui-voice.png --exe java.exe`), press `2` and `3` (`um win drive --proc java "key 0x32"` / `"key 0x33"`) and screenshot each tab. Read the screenshots. Expected: teal HUD panel fully on screen at 854×480, tiles with generated portraits, card on the right, footer hints, Audio/Bubbles rows readable. Right-click a tile (`um win drive --proc java "click X Y right"`) → hear the sample, waveform moves. Stop everything: `powershell -NoProfile -File scripts/mcproc.ps1 kill "dli.env=(client|server)"`.

- [ ] **Step 8: Commit**

```bash
git add -A src/client src/main/resources
git commit -m "feat(ui): replace the settings screen with the pixel hud

Closes #47"
```

---

### Task 10: HUD toasts and the download HUD

**Files:**
- Create: `src/client/java/org/mamoru/omnichat/client/ui/HudToast.java`
- Modify: `src/client/java/org/mamoru/omnichat/client/screen/DownloadProgressHud.java`
- Modify: `src/client/java/org/mamoru/omnichat/client/tts/TtsService.java` (`notifyUser`)
- Modify: `src/client/java/org/mamoru/omnichat/client/network/ClientNetworkHandler.java` (`markIncompatible`)
- Modify: `src/client/java/org/mamoru/omnichat/client/network/ModelDownloadManager.java` (failure chat message → toast; success toast)
- Modify: lang files

**Interfaces:**
- Consumes: `HudTheme`, `HudText`.
- Produces: `HudToast.show(Text title, Text description, int color)` — thread-safe (hops to the render thread).

- [ ] **Step 1: Lang keys**

`en_us.json`:

```json
  "omnichat.toast.downloaded": "Voice downloaded",
  "omnichat.toast.download_failed": "Download failed",
  "omnichat.toast.tts_disabled": "TTS disabled",
  "omnichat.toast.tts_fallback": "TTS fallback",
  "omnichat.toast.incompatible": "Different OmniChat version",
  "omnichat.toast.incompatible.desc": "Voice sync and downloads are off on this server",
  "omnichat.hud.queued": "queued"
```

`ru_ru.json`:

```json
  "omnichat.toast.downloaded": "Голос скачан",
  "omnichat.toast.download_failed": "Загрузка не удалась",
  "omnichat.toast.tts_disabled": "Озвучка отключена",
  "omnichat.toast.tts_fallback": "Запасной голос",
  "omnichat.toast.incompatible": "Другая версия OmniChat",
  "omnichat.toast.incompatible.desc": "Синхронизация голосов и загрузки на этом сервере отключены",
  "omnichat.hud.queued": "в очереди"
```

- [ ] **Step 2: `HudToast`**

```java
package org.mamoru.omnichat.client.ui;

import net.minecraft.client.MinecraftClient;
import net.minecraft.client.font.TextRenderer;
import net.minecraft.client.gui.DrawContext;
import net.minecraft.client.toast.Toast;
import net.minecraft.client.toast.ToastManager;
import net.minecraft.text.Text;

import java.util.List;

/** HUD-style toast: dark panel, colored left bar, title + up to two wrapped lines. ~5 s. */
public class HudToast implements Toast {
    private static final long DURATION_MS = 5000;
    private static final int WIDTH = 180;

    private final Text title;
    private final List<String> lines;
    private final int color;
    private Visibility visibility = Visibility.SHOW;

    private HudToast(Text title, Text description, int color) {
        this.title = title;
        TextRenderer tr = MinecraftClient.getInstance().textRenderer;
        this.lines = description == null ? List.of() : HudText.wrap(description.getString(), WIDTH - 14, 2, tr::getWidth);
        this.color = color;
    }

    public static void show(Text title, Text description, int color) {
        MinecraftClient client = MinecraftClient.getInstance();
        client.execute(() -> client.getToastManager().add(new HudToast(title, description, color)));
    }

    @Override
    public Visibility getVisibility() {
        return visibility;
    }

    @Override
    public void update(ToastManager manager, long time) {
        visibility = time >= DURATION_MS * manager.getNotificationDisplayTimeMultiplier() ? Visibility.HIDE : Visibility.SHOW;
    }

    @Override
    public int getWidth() {
        return WIDTH;
    }

    @Override
    public int getHeight() {
        return 14 + lines.size() * 10;
    }

    @Override
    public void draw(DrawContext ctx, TextRenderer tr, long startTime) {
        int h = getHeight();
        ctx.fill(0, 0, WIDTH, h, HudTheme.BG);
        HudTheme.frame(ctx, 0, 0, WIDTH, h, HudTheme.ACCENT_DIM);
        ctx.fill(0, 0, 2, h, color);
        ctx.drawText(tr, title, 7, 3, color, false);
        int y = 13;
        for (String line : lines) {
            ctx.drawText(tr, line, 7, y, HudTheme.TEXT, false);
            y += 10;
        }
    }
}
```

Check with javap that `ToastManager#getNotificationDisplayTimeMultiplier()` exists in 1.21.11; if not, use `time >= DURATION_MS`.

- [ ] **Step 3: Replace notification sites**

`TtsService.notifyUser(String title, String description)` → change signature to `notifyUser(Text title, Text description)` and body to `HudToast.show(title, description, HudTheme.WARN);`. Update its callers: the "TTS disabled" caller passes `Text.translatable("omnichat.toast.tts_disabled")`, the fallback caller `Text.translatable("omnichat.toast.tts_fallback")`; keep their existing description strings wrapped in `Text.literal(...)` (they contain model names). Remove the `SystemToast` import.

`ClientNetworkHandler.markIncompatible`: replace the `client.player.sendMessage(...)` block with `HudToast.show(Text.translatable("omnichat.toast.incompatible"), Text.translatable("omnichat.toast.incompatible.desc"), HudTheme.WARN);` (keep the warn log).

`ModelDownloadManager`: replace the red chat message after `"Download of model '{}' failed: {}"` with `HudToast.show(Text.translatable("omnichat.toast.download_failed"), Text.literal(d.modelName + ": " + reason), HudTheme.ERROR);`. After the log line `"Model '{}' installed ({} files, {} bytes)"` add `VoiceCatalog.invalidateLocal(d.modelName);` and `HudToast.show(Text.translatable("omnichat.toast.downloaded"), Text.literal(d.modelName), HudTheme.OK);`.

- [ ] **Step 4: Restyle `DownloadProgressHud`**

Replace `onHudRender` body:

```java
    @Override
    public void onHudRender(DrawContext context, RenderTickCounter tickCounter) {
        Map<String, Float> downloads = ModelDownloadManager.getInstance().getActiveDownloads();
        if (downloads.isEmpty()) return;
        MinecraftClient client = MinecraftClient.getInstance();
        TextRenderer tr = client.textRenderer;
        int w = 150, rowH = 18;
        int x = context.getScaledWindowWidth() - w - 6, y = 6;
        int h = downloads.size() * rowH + 4;
        context.fill(x, y, x + w, y + h, HudTheme.BG);
        HudTheme.frame(context, x, y, w, h, HudTheme.ACCENT_DIM);
        int ry = y + 3;
        for (Map.Entry<String, Float> e : downloads.entrySet()) {
            float p = e.getValue();
            String name = HudText.ellipsize(e.getKey(), 90, tr::getWidth);
            String pct = p < 0 ? Text.translatable("omnichat.hud.queued").getString() : Math.round(p * 100) + "%";
            context.drawText(tr, name, x + 5, ry, HudTheme.TEXT, false);
            context.drawText(tr, pct, x + w - 5 - tr.getWidth(pct), ry, p < 0 ? HudTheme.MUTED : HudTheme.WARN, false);
            context.fill(x + 5, ry + 11, x + w - 5, ry + 13, 0xFF2A2430);
            if (p > 0) context.fill(x + 5, ry + 11, x + 5 + (int) ((w - 10) * p), ry + 13, HudTheme.ACCENT);
            ry += rowH;
        }
    }
```

Remove the now-unused color constants of the class (including the old `TEXT_COLOR`), add imports for `HudTheme`, `HudText`, `Text`, `TextRenderer`, `Map`.

- [ ] **Step 5: Build + check**

Run: `./gradlew build` → OK. `grep -rn "sendMessage(Text.literal(\"\[OmniChat\]" src/client` → no results.
In-game: start `scripts/smoke.sh -k`, in the Listener open the HUD, select a voice the Listener doesn't have (set up as in the download test: replace `run/smoke/listener/config/omnichat/models` junction with per-model junctions minus one model, using `cmd /c rmdir` on junctions only), press its Download button, screenshot during download (top-right HUD shows name, %, bar) and after (toast "Voice downloaded"). Restore the junction afterwards exactly as in the previous download test.

- [ ] **Step 6: Commit**

```bash
git add -A src/client src/main/resources
git commit -m "feat(ui): hud-style toasts and download progress"
```

---

### Task 11: Smoke-test screenshots and README

**Files:**
- Modify: `scripts/smoke.sh`
- Modify: `README.md`

**Interfaces:**
- Consumes: `OmnichatScreen` opened with O (Task 9).
- Produces: `build/smoke/ui-voice_small.png`, `ui-audio_small.png`, `ui-bubbles_small.png` on every smoke run.

- [ ] **Step 1: Add the UI step to `scripts/smoke.sh`**

After the existing `# --- 5. screenshot …` block and before `# --- 6. log check`, insert:

```bash
# --- 5b. HUD screens from Listener's window (O opens, 2/3 switch tabs, Esc closes)
listener_pid_ui=$(mcproc pid "dli\.env=client.*username Listener")
[ "$(mcproc focus "$listener_pid_ui")" = "True" ] && {
  drive "key 0x4F" >/dev/null; sleep 1
  um win shot "$OUT/ui-voice.png" --hwnd "$listener_hwnd" --scale 0.5 >/dev/null
  drive "key 0x32" >/dev/null; sleep 0.5
  um win shot "$OUT/ui-audio.png" --hwnd "$listener_hwnd" --scale 0.5 >/dev/null
  drive "key 0x33" >/dev/null; sleep 0.5
  um win shot "$OUT/ui-bubbles.png" --hwnd "$listener_hwnd" --scale 0.5 >/dev/null
  drive "key 0x1B" >/dev/null
}
```

And at the end, next to the existing screenshot echo, add `echo "--- ui: $OUT/ui-voice_small.png ui-audio_small.png ui-bubbles_small.png"`.

- [ ] **Step 2: Run** — `scripts/smoke.sh` → exit 0; read the three `ui-*_small.png` files: panel fully visible at 854×480, correct tab highlighted in each.

- [ ] **Step 3: README section**

In `README.md`, after the "Установка на сервер" subsection, add:

```markdown
### Оформление голосов

В папку модели можно положить два необязательных файла: тогда в меню OmniChat у голоса будут имя, описание и портрет.

`voice.json`:

```json
{ "name": "Денис", "description": "Спокойный мужской голос", "language": "ru",
  "gender": "male", "sample": "Привет, я Денис." }
```

| Поле | Лимит | Назначение |
|---|---|---|
| `name` | 32 символа | Имя в меню |
| `description` | 200 | Описание в карточке |
| `language` | 8 | Код языка, показывается рядом с размером |
| `gender` | 16 | Свободное поле |
| `sample` | 120 | Фраза для прослушивания (ПКМ по голосу) |

`portrait.png` — PNG 16×16 или 32×32, не больше 8 КБ. Если портрета нет, мод нарисует его сам по имени модели.

Сервер раздаёт эти данные всем игрокам вместе со списком голосов, поэтому оформление видно даже у ещё не скачанных моделей. После изменения файлов выполни `/omnichat reload`.
```

Also add a screenshot line under the features list: `![Меню OmniChat](docs/media/omnichat-hud.png)` and copy `build/smoke/ui-voice.png` (full-size) to `docs/media/omnichat-hud.png`.

- [ ] **Step 4: Commit**

```bash
git add scripts/smoke.sh README.md docs/media/omnichat-hud.png
git commit -m "docs: document voice metadata and capture hud screenshots in smoke test"
```

---

## Self-review notes

- Spec coverage: style tokens → Task 6; widgets → Task 7; screen/tabs/layout/#47 → Tasks 6, 9; metadata + protocol v2 → Tasks 2, 3; catalog states → Task 5; generated portraits → Tasks 4, 7; preview + waveform → Task 8; instant apply, keyboard, animations, sounds → Tasks 7, 9; toasts + download HUD → Task 10; localization → Tasks 9, 10; tests → Tasks 1–8; smoke step + README → Task 11; migration (delete old screen, remove `ModelListS2CPayload`) → Tasks 3, 9.
- Out of scope (unchanged): world bubbles/typing indicator, themes, search/filters, in-game metadata editor.
