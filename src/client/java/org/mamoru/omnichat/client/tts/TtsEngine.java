package org.mamoru.omnichat.client.tts;

import com.k2fsa.sherpa.onnx.*;
import org.mamoru.omnichat.client.config.OmnichatConfig;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import com.sun.jna.Library;
import com.sun.jna.Native;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

public class TtsEngine implements ITtsEngine {
    private static final Logger LOGGER = LoggerFactory.getLogger("OmniChat");
    private static final String[] NATIVE_LIBS = {
            "onnxruntime.dll",
            "onnxruntime_providers_shared.dll",
            "cargs.dll",
            "sherpa-onnx-c-api.dll",
            "sherpa-onnx-cxx-api.dll",
            "sherpa-onnx-jni.dll"
    };

    private final OfflineTts tts;
    private final int sampleRate;

    private TtsEngine(OfflineTts tts) {
        this.tts = tts;
        this.sampleRate = tts.getSampleRate();
    }

    public static TtsEngine create(OmnichatConfig config) {
        return create(config.getResolvedModelDir());
    }

    public static TtsEngine create(Path modelDir) {
        loadNativeLibraries();

        if (!Files.isDirectory(modelDir)) {
            throw new RuntimeException("Model directory not found: " + modelDir);
        }

        String modelFile = findOnnxModel(modelDir);
        validateVitsModel(Path.of(modelFile));

        Path tokensFile = modelDir.resolve("tokens.txt");
        if (!Files.exists(tokensFile)) {
            throw new RuntimeException("tokens.txt not found in " + modelDir);
        }

        String dataDir = "";
        Path espeakDir = modelDir.resolve("espeak-ng-data");
        if (Files.isDirectory(espeakDir)) {
            Path phontab = espeakDir.resolve("phontab");
            if (!Files.exists(phontab)) {
                throw new RuntimeException("espeak-ng-data is incomplete (missing phontab) in " + modelDir
                        + ". Remove the espeak-ng-data directory if this model doesn't need it.");
            }
            dataDir = espeakDir.toString();
        }

        OfflineTtsVitsModelConfig vitsConfig = OfflineTtsVitsModelConfig.builder()
                .setModel(modelFile)
                .setTokens(tokensFile.toString())
                .setDataDir(dataDir)
                .setLengthScale(1.0f)
                .build();

        OfflineTtsModelConfig modelConfig = OfflineTtsModelConfig.builder()
                .setVits(vitsConfig)
                .setNumThreads(2)
                .setDebug(false)
                .build();

        OfflineTtsConfig ttsConfig = OfflineTtsConfig.builder()
                .setModel(modelConfig)
                .build();

        OfflineTts offlineTts = new OfflineTts(ttsConfig);
        LOGGER.info("TTS engine initialized (sampleRate={})", offlineTts.getSampleRate());
        return new TtsEngine(offlineTts);
    }

    @Override
    public float[] generate(String text, int speakerId, float speed) {
        GeneratedAudio audio = tts.generate(text, speakerId, 1.0f / speed);
        return audio.getSamples();
    }

    @Override
    public int getSampleRate() {
        return sampleRate;
    }

    @Override
    public void release() {
        tts.release();
    }

    private static void loadNativeLibraries() {
        // Disable sherpa-onnx's own auto-loading; we handle it ourselves
        LibraryLoader.setAutoLoadEnabled(false);

        Path tempDir;
        try {
            tempDir = Files.createTempDirectory("omnichat-natives");
            tempDir.toFile().deleteOnExit();
        } catch (IOException e) {
            throw new RuntimeException("Failed to create temp dir for native libs", e);
        }

        // First, extract all DLLs to temp directory
        for (String libName : NATIVE_LIBS) {
            String resourcePath = "/natives/win-x64/" + libName;
            try (InputStream is = TtsEngine.class.getResourceAsStream(resourcePath)) {
                if (is == null) {
                    throw new RuntimeException("Native library not found in resources: " + resourcePath);
                }
                Path target = tempDir.resolve(libName);
                Files.copy(is, target, StandardCopyOption.REPLACE_EXISTING);
                target.toFile().deleteOnExit();
            } catch (IOException e) {
                throw new RuntimeException("Failed to extract native library: " + libName, e);
            }
        }

        // Set DLL search directory so Windows can resolve dependent DLLs
        NativeKernel32.INSTANCE.SetDllDirectoryA(tempDir.toAbsolutePath().toString());

        // Now load all DLLs in dependency order
        for (String libName : NATIVE_LIBS) {
            Path target = tempDir.resolve(libName);
            System.load(target.toAbsolutePath().toString());
            LOGGER.debug("Loaded native library: {}", libName);
        }
    }

    private interface NativeKernel32 extends Library {
        NativeKernel32 INSTANCE = Native.load("kernel32", NativeKernel32.class);
        boolean SetDllDirectoryA(String lpPathName);
    }

    /**
     * Validates that the ONNX model is a VITS TTS model by checking for
     * 'n_speakers' in the binary metadata. Models without this field crash
     * the JVM at the native level (not catchable by try/catch).
     */
    private static void validateVitsModel(Path modelPath) {
        try {
            byte[] data = Files.readAllBytes(modelPath);
            String marker = "n_speakers";
            byte[] markerBytes = marker.getBytes(java.nio.charset.StandardCharsets.US_ASCII);
            boolean found = false;
            for (int i = 0; i <= data.length - markerBytes.length; i++) {
                boolean match = true;
                for (int j = 0; j < markerBytes.length; j++) {
                    if (data[i + j] != markerBytes[j]) {
                        match = false;
                        break;
                    }
                }
                if (match) {
                    found = true;
                    break;
                }
            }
            if (!found) {
                throw new RuntimeException("Model " + modelPath.getFileName()
                        + " is not a compatible VITS model (missing 'n_speakers' metadata)");
            }
        } catch (IOException e) {
            throw new RuntimeException("Failed to read model file: " + modelPath, e);
        }
    }

    private static String findOnnxModel(Path modelDir) {
        try (var stream = Files.list(modelDir)) {
            return stream
                    .filter(p -> p.getFileName().toString().endsWith(".onnx"))
                    .findFirst()
                    .orElseThrow(() -> new RuntimeException("No .onnx model file found in " + modelDir))
                    .toString();
        } catch (IOException e) {
            throw new RuntimeException("Failed to scan model directory: " + modelDir, e);
        }
    }
}
