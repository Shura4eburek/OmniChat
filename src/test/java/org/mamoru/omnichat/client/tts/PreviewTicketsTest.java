package org.mamoru.omnichat.client.tts;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class PreviewTicketsTest {
    @Test
    void staleTicketIsRejected() {
        PreviewTickets t = new PreviewTickets();
        int a = t.next();
        int b = t.next();
        assertFalse(t.isCurrent(a));
        assertTrue(t.isCurrent(b));
    }
}
