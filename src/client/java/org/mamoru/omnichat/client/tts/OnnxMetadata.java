package org.mamoru.omnichat.client.tts;

import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Reads {@code metadata_props} of an ONNX model by walking the top-level fields of the
 * protobuf ModelProto (field 14 = StringStringEntryProto {key = 1, value = 2}); other
 * fields, including the large graph, are skipped by length.
 */
public final class OnnxMetadata {
    private static final int METADATA_PROPS = 14;

    private OnnxMetadata() {
    }

    /** Best effort: returns whatever entries were read before the data ended or became invalid. */
    public static Map<String, String> parse(byte[] model) {
        Map<String, String> out = new LinkedHashMap<>();
        Reader r = new Reader(model, 0, model.length);
        while (r.hasMore()) {
            long tag = r.varint();
            if (tag < 0) break;
            int number = (int) (tag >>> 3), wire = (int) (tag & 7);
            if (wire == 2) {
                long len = r.varint();
                if (len < 0 || len > r.remaining()) break;
                if (number == METADATA_PROPS) readEntry(model, r.pos, (int) len, out);
                r.pos += (int) len;
            } else if (!r.skip(wire)) {
                break;
            }
        }
        return out;
    }

    private static void readEntry(byte[] data, int start, int len, Map<String, String> out) {
        Reader r = new Reader(data, start, start + len);
        String key = null, value = "";
        while (r.hasMore()) {
            long tag = r.varint();
            if (tag < 0 || (tag & 7) != 2) return;
            long l = r.varint();
            if (l < 0 || l > r.remaining()) return;
            String s = new String(data, r.pos, (int) l, StandardCharsets.UTF_8);
            if ((tag >>> 3) == 1) key = s;
            else if ((tag >>> 3) == 2) value = s;
            r.pos += (int) l;
        }
        if (key != null) out.put(key, value);
    }

    /**
     * Why sherpa-onnx can't safely run this VITS model, or null if it can. A piper export without the
     * espeak {@code voice} entry makes sherpa-onnx throw a native exception on the first sentence,
     * which kills the JVM, so it must be refused before loading.
     */
    public static String vitsProblem(Map<String, String> meta) {
        if (!meta.containsKey("n_speakers")) return "missing 'n_speakers' metadata";
        if ("piper".equalsIgnoreCase(meta.getOrDefault("comment", "")) && meta.getOrDefault("voice", "").isBlank()) {
            return "missing 'voice' metadata (espeak voice)";
        }
        return null;
    }

    private static final class Reader {
        final byte[] data;
        final int end;
        int pos;

        Reader(byte[] data, int start, int end) {
            this.data = data;
            this.pos = start;
            this.end = end;
        }

        boolean hasMore() {
            return pos < end;
        }

        long remaining() {
            return end - pos;
        }

        /** -1 if the varint is truncated or longer than 10 bytes. */
        long varint() {
            long v = 0;
            for (int shift = 0; shift < 70; shift += 7) {
                if (pos >= end) return -1;
                int b = data[pos++] & 0xFF;
                v |= (long) (b & 0x7F) << shift;
                if ((b & 0x80) == 0) return v;
            }
            return -1;
        }

        boolean skip(int wire) {
            switch (wire) {
                case 0 -> { return varint() >= 0; }
                case 1 -> pos += 8;
                case 5 -> pos += 4;
                default -> { return false; }
            }
            return pos <= end;
        }
    }
}
