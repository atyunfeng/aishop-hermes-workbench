package com.aishop.worker.system

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class DiagnosticBufferTest {
    @Test
    fun boundsAndRedactsEntries() {
        val buffer = DiagnosticBuffer(2)
        buffer.add("first")
        buffer.add("token=secret")
        buffer.add("message=private")
        val snapshot = buffer.snapshot()
        assertEquals(2, snapshot.size)
        assertTrue(snapshot.all { "[REDACTED]" in it })
        assertFalse(snapshot.any { "secret" in it || "private" in it })
    }

    @Test
    fun bootRequiresPairingAndExplicitOptIn() {
        assertTrue(shouldStartAfterBoot(paired = true, optedIn = true))
        assertFalse(shouldStartAfterBoot(paired = true, optedIn = false))
        assertFalse(shouldStartAfterBoot(paired = false, optedIn = true))
    }
}
