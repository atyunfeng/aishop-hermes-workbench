package com.aishop.worker.service

import com.aishop.worker.protocol.DeviceCommandType
import com.aishop.worker.protocol.HeartbeatResponse
import com.aishop.worker.protocol.WorkerState

data class CoordinatorState(
    val workerState: WorkerState = WorkerState.IDLE,
    val lastAppliedCommandId: String? = null,
    val pendingAcknowledgementId: String? = null,
)

enum class CoordinatorEffect {
    NONE,
    STOP_SERVICE,
}

data class CoordinatorOutcome(
    val state: CoordinatorState,
    val effect: CoordinatorEffect,
)

class HeartbeatCoordinator {
    fun reduce(state: CoordinatorState, response: HeartbeatResponse): CoordinatorOutcome {
        val command = response.command ?: return CoordinatorOutcome(
            state = state.copy(pendingAcknowledgementId = null),
            effect = CoordinatorEffect.NONE,
        )
        if (command.commandId == state.lastAppliedCommandId) {
            return CoordinatorOutcome(
                state = state.copy(pendingAcknowledgementId = command.commandId),
                effect = CoordinatorEffect.NONE,
            )
        }
        val workerState = when (command.type) {
            DeviceCommandType.PAUSE -> WorkerState.PAUSED
            DeviceCommandType.RESUME -> WorkerState.IDLE
            DeviceCommandType.TAKEOVER -> WorkerState.TAKEOVER
            DeviceCommandType.STOP -> WorkerState.OFFLINE
        }
        return CoordinatorOutcome(
            state = CoordinatorState(
                workerState = workerState,
                lastAppliedCommandId = command.commandId,
                pendingAcknowledgementId = command.commandId,
            ),
            effect = if (command.type == DeviceCommandType.STOP) {
                CoordinatorEffect.STOP_SERVICE
            } else {
                CoordinatorEffect.NONE
            },
        )
    }
}
