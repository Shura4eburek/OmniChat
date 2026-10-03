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

    /**
     * Same result as {@link #parse(byte[])} but streams the file: only the few top-level headers and the
     * metadata payloads are read, the graph is skipped by position (models can be ~80 MB).
     */
    public static Map<String, String> parse(java.nio.file.Path file) throws java.io.IOException {
        Map<String, String> out = new LinkedHashMap<>();
        try (java.nio.channels.FileChannel ch = java.nio.channels.FileChannel.open(file, java.nio.file.StandardOpenOption.READ)) {
            long size = ch.size();
            long[] pos = {0};
            while (pos[0] < size) {
                long tag = readVarint(ch, pos, size);
                if (tag < 0) break;
                int number = (int) (tag >>> 3), wire = (int) (tag & 7);
                if (wire == 2) {
                    long len = readVarint(ch, pos, size);
                    if (len < 0 || len > size - pos[0]) break;
                    if (number == METADATA_PROPS) {
                        java.nio.ByteBuffer buf = java.nio.ByteBuffer.allocate((int) len);
                        long at = pos[0];
                        while (buf.hasRemaining()) {
                            int n = ch.read(buf, at + buf.position());
                            if (n < 0) return out;
                        }
                        readEntry(buf.array(), 0, (int) len, out);
                    }
                    pos[0] += len;
                } else if (wire == 0) {
                    if (readVarint(ch, pos, size) < 0) break;
                } else if (wire == 1 || wire == 5) {
                    pos[0] += wire == 1 ? 8 : 4;
                    if (pos[0] > size) break;
                } else {
                    break;
                }
            }
        }
        return out;
    }

    private static long readVarint(java.nio.channels.FileChannel ch, long[] pos, long size) throws java.io.IOException {
        java.nio.ByteBuffer one = java.nio.ByteBuffer.allocate(1);
        long v = 0;
        for (int shift = 0; shift < 70; shift += 7) {
            if (pos[0] >= size) return -1;
            one.clear();
            if (ch.read(one, pos[0]++) < 1) return -1;
            int b = one.get(0) & 0xFF;
            v |= (long) (b & 0x7F) << shift;
            if ((b & 0x80) == 0) return v;
        }
        return -1;
    }

    /** Copy of the model without the metadata_props entries whose key is in {@code keys}. */
    public static byte[] removeEntries(byte[] model, java.util.Set<String> keys) {
        java.io.ByteArrayOutputStream out = new java.io.ByteArrayOutputStream(model.length);
        Reader r = new Reader(model, 0, model.length);
        int copiedTo = 0;
        while (r.hasMore()) {
            int fieldStart = r.pos;
            long tag = r.varint();
            if (tag < 0) break;
            int number = (int) (tag >>> 3), wire = (int) (tag & 7);
            if (wire == 2) {
                long len = r.varint();
                if (len < 0 || len > r.remaining()) break;
                int payload = r.pos;
                r.pos += (int) len;
                if (number == METADATA_PROPS) {
                    Map<String, String> e = new LinkedHashMap<>();
                    readEntry(model, payload, (int) len, e);
                    if (!e.isEmpty() && keys.contains(e.keySet().iterator().next())) {
                        out.write(model, copiedTo, fieldStart - copiedTo);
                        copiedTo = r.pos;
                    }
                }
            } else if (!r.skip(wire)) {
                break;
            }
        }
        out.write(model, copiedTo, model.length - copiedTo);
        return out.toByteArray();
    }

    /** True when the only problem is a missing/blank espeak {@code voice} on a piper model. */
    public static boolean missingVoiceOnly(Map<String, String> meta) {
        return meta.containsKey("n_speakers")
                && "piper".equalsIgnoreCase(meta.getOrDefault("comment", ""))
                && meta.getOrDefault("voice", "").isBlank();
    }

    /**
     * The model bytes followed by one metadata_props entry per map entry. Protobuf allows repeated
     * top-level fields anywhere, so appending is a valid way to add metadata without rewriting the graph.
     */
    public static byte[] appendEntries(byte[] model, Map<String, String> entries) {
        java.io.ByteArrayOutputStream out = new java.io.ByteArrayOutputStream(model.length + 64);
        out.writeBytes(model);
        for (Map.Entry<String, String> e : entries.entrySet()) {
            java.io.ByteArrayOutputStream entry = new java.io.ByteArrayOutputStream();
            writeString(entry, 1, e.getKey());
            writeString(entry, 2, e.getValue());
            writeVarint(out, ((long) METADATA_PROPS << 3) | 2);
            writeVarint(out, entry.size());
            out.writeBytes(entry.toByteArray());
        }
        return out.toByteArray();
    }

    private static void writeString(java.io.ByteArrayOutputStream out, int number, String s) {
        byte[] b = s.getBytes(StandardCharsets.UTF_8);
        writeVarint(out, ((long) number << 3) | 2);
        writeVarint(out, b.length);
        out.writeBytes(b);
    }

    private static void writeVarint(java.io.ByteArrayOutputStream out, long v) {
        while ((v & ~0x7FL) != 0) {
            out.write((int) ((v & 0x7F) | 0x80));
            v >>>= 7;
        }
        out.write((int) v);
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
