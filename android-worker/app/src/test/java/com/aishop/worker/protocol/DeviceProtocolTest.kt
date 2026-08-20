package com.aishop.worker.protocol

import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.junit.Test

class DeviceProtocolTest {
    private val json = Json {
        explicitNulls = true
        ignoreUnknownKeys = false
    }

    @Test
    fun `pair request uses locked snake case fields`() {
        val request = PairDeviceRequest(
            pairingCode = "482731",
            deviceId = "android-1",
            displayName = "9号 AI 手机员工",
            appVersion = "0.1.0",
            capabilities = listOf("heartbeat", "manual_control"),
        )

        val encoded = json.encodeToString(request)

        assertEquals(
            """{"pairing_code":"482731","device_id":"android-1","display_name":"9号 AI 手机员工","app_version":"0.1.0","capabilities":["heartbeat","manual_control"]}""",
            encoded,
        )
    }

    @Test
    fun `heartbeat response decodes nullable command`() {
        val response = json.decodeFromString<HeartbeatResponse>(
            """{"server_time":"2026-08-17T12:00:00+00:00","next_heartbeat_seconds":5,"command":null}""",
        )

        assertEquals(5, response.nextHeartbeatSeconds)
        assertNull(response.command)
    }

    @Test
    fun `gateway url accepts only http and https`() {
        assertEquals("http://192.168.1.20:8000", normalizeGatewayUrl("http://192.168.1.20:8000/"))
        assertThrows(IllegalArgumentException::class.java) {
            normalizeGatewayUrl("ftp://192.168.1.20")
        }
    }
}
