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
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class GladosG2P {
    private static final Logger LOGGER = LoggerFactory.getLogger("OmniChat");
    private static final Pattern PUNCT_PATTERN = Pattern.compile("([!'(),.\\-.:;?])");

    private final Map<String, String> dictionary;
    private final Map<String, List<Integer>> phonemeIdMap;

    public GladosG2P(Path modelDir) throws IOException {
        this.dictionary = loadDictionary(modelDir.resolve("dictionary.txt"));
        this.phonemeIdMap = loadPhonemeIdMap(modelDir.resolve("config.json"));
        LOGGER.info("GladosG2P loaded: {} dictionary entries, {} phoneme symbols",
                dictionary.size(), phonemeIdMap.size());
    }

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

            String lower = word.toLowerCase();
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
        for (String p : phonemes) {
            if (phonemeIdMap.containsKey(p)) {
                addIds(ids, p);
                addIds(ids, "_");
            }
        }
        addIds(ids, "$");

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

    @SuppressWarnings("unchecked")
    private static Map<String, List<Integer>> loadPhonemeIdMap(Path configPath) throws IOException {
        String json = Files.readString(configPath, StandardCharsets.UTF_8);
        Gson gson = new Gson();
        Type mapType = new TypeToken<Map<String, Object>>() {}.getType();
        Map<String, Object> config = gson.fromJson(json, mapType);

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
}
