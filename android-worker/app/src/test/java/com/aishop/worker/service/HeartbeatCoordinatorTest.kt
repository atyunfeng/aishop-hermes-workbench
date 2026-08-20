package com.aishop.worker.service

import com.aishop.worker.protocol.DeviceCommand
import com.aishop.worker.protocol.DeviceCommandType
import com.aishop.worker.protocol.HeartbeatResponse
import com.aishop.worker.protocol.WorkerState
import org.junit.Assert.assertEquals
import org.junit.Test

class HeartbeatCoordinatorTest {
    private val coordinator = HeartbeatCoordinator()

    @Test
    fun `pause resume takeover and stop map to safe local states`() {
        assertEquals(WorkerState.PAUSED, reduce(DeviceCommandType.PAUSE).state.workerState)
        assertEquals(WorkerState.IDLE, reduce(DeviceCommandType.RESUME, WorkerState.PAUSED).state.workerState)
        assertEquals(WorkerState.TAKEOVER, reduce(DeviceCommandType.TAKEOVER).state.workerState)
        val stopped = reduce(DeviceCommandType.STOP)
        assertEquals(WorkerState.OFFLINE, stopped.state.workerState)
        assertEquals(CoordinatorEffect.STOP_SERVICE, stopped.effect)
    }

    @Test
    fun `replayed command is acknowledged without repeating effect`() {
        val first = reduce(DeviceCommandType.STOP)
        val replay = coordinator.reduce(first.state, response(command(DeviceCommandType.STOP)))
        assertEquals("command-1", replay.state.pendingAcknowledgementId)
        assertEquals(CoordinatorEffect.NONE, replay.effect)
    }

    @Test
    fun `empty response confirms acknowledgement`() {
        val first = reduce(DeviceCommandType.PAUSE)
        val confirmed = coordinator.reduce(first.state, response(null))
        assertEquals(null, confirmed.state.pendingAcknowledgementId)
        assertEquals("command-1", confirmed.state.lastAppliedCommandId)
    }

    private fun reduce(
        type: DeviceCommandType,
        initialState: WorkerState = WorkerState.IDLE,
    ): CoordinatorOutcome = coordinator.reduce(
        CoordinatorState(workerState = initialState),
        response(command(type)),
    )

    private fun command(type: DeviceCommandType) = DeviceCommand(
        commandId = "command-1",
        type = type,
        reason = "operator command",
        createdAt = "2026-08-17T12:00:00+00:00",
    )

    private fun response(command: DeviceCommand?) = HeartbeatResponse(
        serverTime = "2026-08-17T12:00:00+00:00",
        nextHeartbeatSeconds = 5,
        command = command,
        job = null,
        acknowledgedStepId = null,
    )
}
