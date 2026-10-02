package org.mamoru.omnichat.client.tts;

import ai.onnxruntime.*;
import org.mamoru.omnichat.util.ModelScanner;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.nio.FloatBuffer;
import java.nio.file.Path;
import java.util.Map;

public class GladosTtsEngine implements ITtsEngine {
    private static final Logger LOGGER = LoggerFactory.getLogger("OmniChat");
    private final OrtEnvironment env;
    private final OrtSession session;
    private final GladosG2P g2p;
    private final GladosG2P.ModelConfig modelConfig;
    private boolean closed;

    private GladosTtsEngine(OrtEnvironment env, OrtSession session, GladosG2P g2p) {
        this.env = env;
        this.session = session;
        this.g2p = g2p;
        this.modelConfig = g2p.modelConfig();
    }

    public static GladosTtsEngine create(Path modelDir) {
        Path modelFile = ModelScanner.resolveOnnxModel(modelDir);

        try {
            GladosG2P g2p = new GladosG2P(modelDir);

            OrtEnvironment env = OrtEnvironment.getEnvironment();
            OrtSession.SessionOptions opts = new OrtSession.SessionOptions();
            opts.setIntraOpNumThreads(2);
            OrtSession session = env.createSession(modelFile.toString(), opts);

            GladosG2P.ModelConfig mc = g2p.modelConfig();
            LOGGER.info("GLaDOS TTS engine initialized (model={}, sampleRate={})",
                    modelFile.getFileName(), mc.sampleRate());
            LOGGER.debug("GLaDOS inference scales: noise={}, length={}, noiseW={}",
                    mc.noiseScale(), mc.lengthScale(), mc.noiseW());
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
            float[] scales = new float[] {
                    modelConfig.noiseScale(), modelConfig.lengthScale() / speed, modelConfig.noiseW() };

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
        return modelConfig.sampleRate();
    }

    @Override
    public synchronized void release() {
        // OrtSession.close() throws IllegalStateException when called twice
        if (closed) return;
        closed = true;
        try {
            session.close();
        } catch (OrtException | RuntimeException e) {
            LOGGER.error("Failed to close ONNX session", e);
        }
    }
}
