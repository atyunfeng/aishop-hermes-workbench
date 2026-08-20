package com.aishop.worker.execution

import com.aishop.worker.protocol.DeviceJob
import com.aishop.worker.protocol.StepResult
import com.aishop.worker.protocol.StepStatus
import java.time.Instant
import kotlinx.serialization.Serializable

@Serializable
data class JobRunnerState(
    val jobId: String? = null,
    val leaseId: String? = null,
    val completedStepIds: Set<String> = emptySet(),
    val pendingResult: StepResult? = null,
)

data class JobRunnerOutcome(
    val state: JobRunnerState,
    val evidence: CapturedEvidence? = null,
)

class JobRunner(
    private val now: () -> String = { Instant.now().toString() },
) {
    suspend fun runNext(
        job: DeviceJob,
        state: JobRunnerState,
        executor: ActionExecutor,
    ): JobRunnerOutcome {
        if (state.pendingResult != null) return JobRunnerOutcome(state)
        val current = if (state.jobId == job.jobId) {
            state.copy(leaseId = job.leaseId)
        } else {
            JobRunnerState(jobId = job.jobId, leaseId = job.leaseId)
        }
        val step = job.steps.sortedBy { it.ordinal }
            .firstOrNull { it.stepId !in current.completedStepIds }
            ?: return JobRunnerOutcome(current)
        val outcome = executor.execute(step)
        val result = StepResult(
            jobId = job.jobId,
            leaseId = job.leaseId,
            stepId = step.stepId,
            status = outcome.status,
            code = outcome.code,
            message = outcome.message.take(500),
            observed = outcome.observed,
            evidenceIds = emptyList(),
            completedAt = now(),
        )
        return JobRunnerOutcome(current.copy(pendingResult = result), outcome.evidence)
    }

    fun attachEvidence(state: JobRunnerState, evidenceId: String): JobRunnerState {
        val pending = state.pendingResult ?: return state
        return state.copy(pendingResult = pending.copy(evidenceIds = listOf(evidenceId)))
    }

    fun acknowledge(state: JobRunnerState, stepId: String?): JobRunnerState {
        val pending = state.pendingResult ?: return state
        if (pending.stepId != stepId) return state
        val completed = if (pending.status == StepStatus.SUCCEEDED) {
            state.completedStepIds + pending.stepId
        } else {
            state.completedStepIds
        }
        return state.copy(completedStepIds = completed, pendingResult = null)
    }
}
