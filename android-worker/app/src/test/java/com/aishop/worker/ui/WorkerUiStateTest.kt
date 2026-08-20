package com.aishop.worker.ui

import com.aishop.worker.data.PairingCredentials
import com.aishop.worker.protocol.WorkerState
import com.aishop.worker.service.CoordinatorState
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class WorkerUiStateTest {
    @Test
    fun `unpaired state exposes pairing form and blocks duplicate submission`() {
        val state = buildWorkerUiState(
            deviceId = "android-1",
            credentials = null,
            coordinator = CoordinatorState(),
            status = null,
            pairingInProgress = true,
        )
        assertFalse(state.paired)
        assertTrue(state.pairingInProgress)
    }

    @Test
    fun `paired state exposes status without bearer token`() {
        val credentials = PairingCredentials(
            baseUrl = "http://192.168.1.20:8000/api/plugins/aishop",
            deviceId = "android-1",
            displayName = "9号 AI 手机员工",
            token = "raw-secret-token",
        )
        val state = buildWorkerUiState(
            deviceId = credentials.deviceId,
            credentials = credentials,
            coordinator = CoordinatorState(workerState = WorkerState.PAUSED),
            status = null,
        )
        assertTrue(state.paired)
        assertTrue(state.visibleText().contains("PAUSED"))
        assertFalse(state.visibleText().contains(credentials.token))
    }
}
