package org.mamoru.omnichat.client.tts;

import ai.onnxruntime.*;
import org.mamoru.omnichat.client.config.OmnichatConfig;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.nio.FloatBuffer;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

public class GladosTtsEngine implements ITtsEngine {
    private static final Logger LOGGER = LoggerFactory.getLogger("OmniChat");
    private static final int SAMPLE_RATE = 22050;

    private final OrtEnvironment env;
    private final OrtSession session;
    private final GladosG2P g2p;

    private GladosTtsEngine(OrtEnvironment env, OrtSession session, GladosG2P g2p) {
        this.env = env;
        this.session = session;
        this.g2p = g2p;
    }

    public static GladosTtsEngine create(OmnichatConfig config) {
        return create(config.getResolvedModelDir());
    }

    public static GladosTtsEngine create(Path modelDir) {
        Path modelFile = findOnnxModel(modelDir);

        try {
            GladosG2P g2p = new GladosG2P(modelDir);

            OrtEnvironment env = OrtEnvironment.getEnvironment();
            OrtSession.SessionOptions opts = new OrtSession.SessionOptions();
            opts.setIntraOpNumThreads(2);
            OrtSession session = env.createSession(modelFile.toString(), opts);

            LOGGER.info("GLaDOS TTS engine initialized (model={}, sampleRate={})",
                    modelFile.getFileName(), SAMPLE_RATE);
            return new GladosTtsEngine(env, session, g2p);
        } catch (OrtException | IOException e) {
            throw new RuntimeException("Failed to initialize GLaDOS TTS engine", e);
        }
    }

    @Override
    public float[] generate(String text, int speakerId, float speed) {
        if (text == null || text.isBlank()) {
            return new float[0];
        }

        try {
            long[] phonemeIds = g2p.textToPhonemeIds(text);
            if (phonemeIds.length == 0) {
                return new float[0];
            }

            long[][] inputData = new long[][] { phonemeIds };
            long[] inputLengths = new long[] { phonemeIds.length };
            float[] scales = new float[] { 0.667f, 1.0f / speed, 0.8f };

            try (OnnxTensor inputTensor = OnnxTensor.createTensor(env, inputData);
                 OnnxTensor lengthsTensor = OnnxTensor.createTensor(env, inputLengths);
                 OnnxTensor scalesTensor = OnnxTensor.createTensor(env, scales)) {

                Map<String, OnnxTensor> inputs = Map.of(
                        "input", inputTensor,
                        "input_lengths", lengthsTensor,
                        "scales", scalesTensor
                );

                try (OrtSession.Result result = session.run(inputs)) {
                    // Output shape: [1, 1, 1, samples] — extract the 1D audio array
                    float[][][][] output = (float[][][][]) result.get(0).getValue();
                    return output[0][0][0];
                }
            }
        } catch (OrtException e) {
            LOGGER.error("GLaDOS TTS inference failed", e);
            return new float[0];
        }
    }

    @Override
    public int getSampleRate() {
        return SAMPLE_RATE;
    }

    @Override
    public void release() {
        try {
            session.close();
        } catch (OrtException e) {
            LOGGER.error("Failed to close ONNX session", e);
        }
    }

    private static Path findOnnxModel(Path modelDir) {
        try (var stream = Files.list(modelDir)) {
            return stream
                    .filter(p -> p.getFileName().toString().endsWith(".onnx"))
                    .findFirst()
                    .orElseThrow(() -> new RuntimeException("No .onnx model file found in " + modelDir));
        } catch (IOException e) {
            throw new RuntimeException("Failed to scan model directory: " + modelDir, e);
        }
    }
}
