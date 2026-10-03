package org.mamoru.omnichat;

import org.junit.jupiter.api.Test;
import org.mamoru.omnichat.client.HearingRange;

import static org.junit.jupiter.api.Assertions.assertEquals;

class SanityTest {
    @Test
    void seesClientClasses() {
        assertEquals(40.0, HearingRange.BLOCKS);
    }
}
