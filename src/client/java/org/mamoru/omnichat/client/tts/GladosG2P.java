package org.mamoru.omnichat.client.tts;

import com.google.gson.Gson;
import com.google.gson.reflect.TypeToken;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.BufferedReader;
import java.io.IOException;
import java.lang.reflect.Type;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class GladosG2P {
    private static final Logger LOGGER = LoggerFactory.getLogger("OmniChat");
    private static final Pattern PUNCT_PATTERN = Pattern.compile("([!'(),.\\-.:;?])");

    private final Map<String, String> dictionary;
    private final Map<String, List<Integer>> phonemeIdMap;
    private final ModelConfig modelConfig;
    private final AtomicBoolean unsupportedLogged = new AtomicBoolean();

    public GladosG2P(Path modelDir) throws IOException {
        this.dictionary = loadDictionary(modelDir.resolve("dictionary.txt"));
        Map<String, Object> config = loadConfig(modelDir.resolve("config.json"));
        this.phonemeIdMap = parsePhonemeIdMap(config);
        this.modelConfig = ModelConfig.from(config);
        LOGGER.info("GladosG2P loaded: {} dictionary entries, {} phoneme symbols",
                dictionary.size(), phonemeIdMap.size());
    }

    /** Audio and inference settings read from the same {@code config.json}. */
    public ModelConfig modelConfig() {
        return modelConfig;
    }

    /**
     * Converts text to model input ids. Returns an empty array when the text yields no
     * phoneme the model knows (e.g. an unsupported alphabet), so no inference is run on
     * the bare {@code ^ _ $} frame.
     */

    public long[] textToPhonemeIds(String text) {
        // Separate punctuation with spaces (matching Python: re.sub("([!'(),-.:;?])", r' \1 ', text))
        text = PUNCT_PATTERN.matcher(text).replaceAll(" $1 ");

        List<String> phonemes = new ArrayList<>();
        String[] words = text.split("\\s+");

        for (String word : words) {
            if (word.isEmpty()) continue;

            // Punctuation passes through directly
            if (word.length() == 1 && PUNCT_PATTERN.matcher(word).matches()) {
                phonemes.add(word);
                continue;
            }

            String lower = word.toLowerCase(Locale.ROOT);
            if (!phonemes.isEmpty()) {
                phonemes.add(" ");
            }

            if (dictionary.containsKey(lower)) {
                String[] phons = dictionary.get(lower).split("\\s+");
                for (String p : phons) {
                    if (!p.isEmpty()) phonemes.add(p);
                }
            } else {
                // Fallback: pass individual characters as phonemes
                for (char c : lower.toCharArray()) {
                    String cs = String.valueOf(c);
                    if (phonemeIdMap.containsKey(cs)) {
                        phonemes.add(cs);
                    }
                }
            }
        }

        // Build phoneme ID sequence: ^ _ (phoneme _)* $
        List<Integer> ids = new ArrayList<>();
        addIds(ids, "^");
        addIds(ids, "_");
        int realPhonemes = 0;
        for (String p : phonemes) {
            if (phonemeIdMap.containsKey(p)) {
                addIds(ids, p);
                addIds(ids, "_");
                // word separators and punctuation alone are not speech
                if (!p.isBlank() && !PUNCT_PATTERN.matcher(p).matches()) {
                    realPhonemes++;
                }
            }
        }
        addIds(ids, "$");

        if (realPhonemes == 0) {
            if (unsupportedLogged.compareAndSet(false, true)) {
                LOGGER.warn("GLaDOS model produced no phonemes for a message (unsupported alphabet?); "
                        + "such messages are skipped. Logged once per model load.");
            }
            return new long[0];
        }

        // Intersperse with 0 (blank/padding) between every element
        List<Integer> interspersed = new ArrayList<>(ids.size() * 2 + 1);
        for (int i = 0; i < ids.size(); i++) {
            if (i > 0) interspersed.add(0);
            interspersed.add(ids.get(i));
        }

        long[] result = new long[interspersed.size()];
        for (int i = 0; i < interspersed.size(); i++) {
            result[i] = interspersed.get(i);
        }
        return result;
    }

    private void addIds(List<Integer> ids, String phoneme) {
        List<Integer> mapped = phonemeIdMap.get(phoneme);
        if (mapped != null) {
            ids.addAll(mapped);
        }
    }

    private static Map<String, String> loadDictionary(Path path) throws IOException {
        Map<String, String> dict = new HashMap<>();
        try (BufferedReader reader = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
            String line;
            while ((line = reader.readLine()) != null) {
                line = line.trim();
                if (line.isEmpty()) continue;
                int spaceIdx = line.indexOf(' ');
                if (spaceIdx < 0) continue;
                String word = line.substring(0, spaceIdx);
                String phonemes = line.substring(spaceIdx + 1).trim();
                dict.put(word, phonemes);
            }
        }
        return dict;
    }

    private static Map<String, Object> loadConfig(Path configPath) throws IOException {
        String json = Files.readString(configPath, StandardCharsets.UTF_8);
        Type mapType = new TypeToken<Map<String, Object>>() {}.getType();
        Map<String, Object> config = new Gson().fromJson(json, mapType);
        if (config == null) {
            throw new IOException("config.json is empty");
        }
        return config;
    }

    @SuppressWarnings("unchecked")
    private static Map<String, List<Integer>> parsePhonemeIdMap(Map<String, Object> config) throws IOException {
        Object rawMap = config.get("phoneme_id_map");
        if (rawMap == null) {
            throw new IOException("config.json missing 'phoneme_id_map'");
        }

        Map<String, List<Integer>> result = new HashMap<>();
        Map<String, Object> rawPhonemeMap = (Map<String, Object>) rawMap;
        for (Map.Entry<String, Object> entry : rawPhonemeMap.entrySet()) {
            List<?> rawList = (List<?>) entry.getValue();
            List<Integer> idList = new ArrayList<>();
            for (Object val : rawList) {
                idList.add(((Number) val).intValue());
            }
            result.put(entry.getKey(), idList);
        }
        return result;
    }

    /**
     * Sample rate and VITS inference scales from {@code config.json}. Supports the Piper layout
     * ({@code audio.sample_rate}, {@code inference.noise_scale/length_scale/noise_w}) and the
     * TeraTTS layout ({@code model_config.samplerate}); missing values fall back to the
     * defaults the engine always used (22050 Hz, 0.667 / 1.0 / 0.8).
     */
    public record ModelConfig(int sampleRate, float noiseScale, float lengthScale, float noiseW) {
        public static final int DEFAULT_SAMPLE_RATE = 22050;
        public static final float DEFAULT_NOISE_SCALE = 0.667f;
        public static final float DEFAULT_LENGTH_SCALE = 1.0f;
        public static final float DEFAULT_NOISE_W = 0.8f;

        static ModelConfig from(Map<String, Object> config) {
            Number rate = number(config, "audio", "sample_rate");
            if (rate == null) rate = number(config, "model_config", "samplerate");
            Number noise = number(config, "inference", "noise_scale");
            Number length = number(config, "inference", "length_scale");
            Number noiseW = number(config, "inference", "noise_w");

            int sampleRate = rate != null && rate.intValue() > 0 ? rate.intValue() : DEFAULT_SAMPLE_RATE;
            return new ModelConfig(sampleRate,
                    nonNegativeOr(noise, DEFAULT_NOISE_SCALE),
                    length != null && length.floatValue() > 0f ? length.floatValue() : DEFAULT_LENGTH_SCALE,
                    nonNegativeOr(noiseW, DEFAULT_NOISE_W));
        }

        private static float nonNegativeOr(Number value, float fallback) {
            return value != null && value.floatValue() >= 0f ? value.floatValue() : fallback;
        }

        private static Number number(Map<String, Object> config, String section, String key) {
            if (config.get(section) instanceof Map<?, ?> map && map.get(key) instanceof Number n) {
                return n;
            }
            return null;
        }
    }
}
