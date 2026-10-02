package org.mamoru.omnichat.client.chat;

import org.mamoru.omnichat.client.OmnichatClient;

import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.function.Function;

public class ChatBubbleManager {
    private static final ChatBubbleManager INSTANCE = new ChatBubbleManager();
    private static final long DISPLAY_AFTER_COMPLETE_MS = 3000;

    private final Map<UUID, ChatBubble> activeBubbles = new ConcurrentHashMap<>();
    private final Set<UUID> typingPlayers = ConcurrentHashMap.newKeySet();

    public static ChatBubbleManager getInstance() {
        return INSTANCE;
    }

    public void addBubble(UUID playerUuid, String text) {
        typingPlayers.remove(playerUuid);
        activeBubbles.put(playerUuid, new ChatBubble(text, System.currentTimeMillis()));
    }

    public void setTyping(UUID playerUuid, boolean typing) {
        if (typing) {
            typingPlayers.add(playerUuid);
        } else {
            typingPlayers.remove(playerUuid);
        }
    }

    /** Keeps running while bubbles are hidden, so a bubble never outlives its time once re-enabled. */
    public void tick() {
        long now = System.currentTimeMillis();
        float charsPerSec = OmnichatClient.getConfig().getBubbleTextSpeed();

        activeBubbles.entrySet().removeIf(entry -> {
            ChatBubble bubble = entry.getValue();
            long elapsed = now - bubble.startTimeMs;

            if (charsPerSec <= 0) {
                bubble.visibleChars = bubble.codePointCount;
            } else {
                bubble.visibleChars = Math.min(bubble.codePointCount,
                        (int) (elapsed * charsPerSec / 1000.0f));
            }

            if (bubble.visibleChars >= bubble.codePointCount) {
                if (bubble.completeTimeMs == 0) {
                    bubble.completeTimeMs = now;
                }
                return now - bubble.completeTimeMs > DISPLAY_AFTER_COMPLETE_MS;
            }
            return false;
        });
    }

    public Map<UUID, ChatBubble> getActiveBubbles() {
        return activeBubbles;
    }

    public Set<UUID> getTypingPlayers() {
        return typingPlayers;
    }

    public void clear() {
        activeBubbles.clear();
        typingPlayers.clear();
    }

    public static class ChatBubble {
        public final String fullText;
        public final long startTimeMs;
        /** Length of {@link #fullText} in code points, so surrogate pairs (emoji) are never split. */
        public final int codePointCount;
        /** Number of visible code points. */
        public volatile int visibleChars;
        public long completeTimeMs;

        // Render-thread cache of the wrapped visible text, rebuilt only when it grows
        private int wrappedChars = -1;
        private List<String> wrappedLines = List.of();

        public ChatBubble(String fullText, long startTimeMs) {
            this.fullText = fullText;
            this.startTimeMs = startTimeMs;
            this.codePointCount = fullText.codePointCount(0, fullText.length());
            this.visibleChars = 0;
            this.completeTimeMs = 0;
        }

        public String getVisibleText() {
            int chars = Math.min(visibleChars, codePointCount);
            return fullText.substring(0, fullText.offsetByCodePoints(0, chars));
        }

        /** The visible text split into lines by {@code wrapper}, recomputed only when it changes. */
        public List<String> getWrappedLines(Function<String, List<String>> wrapper) {
            int chars = Math.min(visibleChars, codePointCount);
            if (chars != wrappedChars) {
                wrappedLines = wrapper.apply(getVisibleText());
                wrappedChars = chars;
            }
            return wrappedLines;
        }
    }
}
