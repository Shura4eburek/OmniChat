package org.mamoru.omnichat.client.tts;

import com.k2fsa.sherpa.onnx.*;
import org.mamoru.omnichat.util.ModelScanner;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class TtsEngine implements ITtsEngine {
    private static final Logger LOGGER = LoggerFactory.getLogger("OmniChat");

    private final OfflineTts tts;
    private final int sampleRate;

    private TtsEngine(OfflineTts tts) {
        this.tts = tts;
        this.sampleRate = tts.getSampleRate();
    }

    public static TtsEngine create(Path modelDir) {
        if (!Files.isDirectory(modelDir)) {
            throw new RuntimeException("Model directory not found: " + modelDir);
        }

        String modelFile = ModelScanner.resolveOnnxModel(modelDir).toString();
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

        // Natives only after the model passed the pure-Java checks; loaded once per JVM.
        SherpaNatives.ensureLoaded();

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
        GeneratedAudio audio = tts.generate(text, speakerId, speed);
        return audio.getSamples();
    }

    @Override
    public int getSampleRate() {
        return sampleRate;
    }

    private boolean closed;

    @Override
    public synchronized void release() {
        if (closed) return;
        closed = true;
        try {
            tts.release();
        } catch (RuntimeException e) {
            LOGGER.error("Failed to release sherpa TTS engine", e);
        }
    }

    /**
     * Refuses models sherpa-onnx would crash on natively (not catchable by try/catch):
     * no 'n_speakers' metadata, or a piper export without the espeak 'voice' entry.
     */
    private static void validateVitsModel(Path modelPath) {
        byte[] data;
        try {
            data = Files.readAllBytes(modelPath);
        } catch (IOException e) {
            throw new RuntimeException("Failed to read model file: " + modelPath, e);
        }
        String problem = OnnxMetadata.vitsProblem(OnnxMetadata.parse(data));
        if (problem != null) {
            throw new RuntimeException("Model " + modelPath.getFileName() + " is not a compatible VITS model (" + problem + ")");
        }
    }
}
