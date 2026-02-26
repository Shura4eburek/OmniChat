package org.mamoru.omnichat.client.chat;

import org.mamoru.omnichat.client.OmnichatClient;

import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

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

    public void tick() {
        if (!OmnichatClient.getConfig().isShowChatBubbles()) {
            return;
        }

        long now = System.currentTimeMillis();
        float charsPerSec = OmnichatClient.getConfig().getBubbleTextSpeed();

        activeBubbles.entrySet().removeIf(entry -> {
            ChatBubble bubble = entry.getValue();
            long elapsed = now - bubble.startTimeMs;

            if (charsPerSec <= 0) {
                bubble.visibleChars = bubble.fullText.length();
            } else {
                bubble.visibleChars = Math.min(bubble.fullText.length(),
                        (int) (elapsed * charsPerSec / 1000.0f));
            }

            if (bubble.visibleChars >= bubble.fullText.length()) {
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
        public int visibleChars;
        public long completeTimeMs;

        public ChatBubble(String fullText, long startTimeMs) {
            this.fullText = fullText;
            this.startTimeMs = startTimeMs;
            this.visibleChars = 0;
            this.completeTimeMs = 0;
        }

        public String getVisibleText() {
            return fullText.substring(0, Math.min(visibleChars, fullText.length()));
        }
    }
}
