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
