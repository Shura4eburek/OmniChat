package org.mamoru.omnichat.client.tts;

import java.util.concurrent.atomic.AtomicInteger;

/** "Latest request wins": a preview finishing after a newer one was requested is dropped. */
public final class PreviewTickets {
    private final AtomicInteger current = new AtomicInteger();

    public int next() {
        return current.incrementAndGet();
    }

    public boolean isCurrent(int ticket) {
        return current.get() == ticket;
    }
}
