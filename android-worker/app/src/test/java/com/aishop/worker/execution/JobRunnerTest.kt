package com.aishop.worker.execution

import com.aishop.worker.protocol.ActionType
import com.aishop.worker.protocol.DeviceJob
import com.aishop.worker.protocol.ExecutionStep
import com.aishop.worker.protocol.StepStatus
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.JsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Test

class JobRunnerTest {
    private val job = DeviceJob(
        jobId = "job-1",
        taskId = "task-1",
        appSkillId = "we-chat",
        skillVersion = "1.0.0",
        status = "LEASED",
        requiredPackages = listOf("com.tencent.mm"),
        requiredCapabilities = listOf("accessibility"),
        leaseId = "lease-1",
        deviceId = "phone-1",
        leaseExpiresAt = "2026-08-17T12:00:30Z",
        mode = "DEVICE",
        steps = listOf(
            ExecutionStep("launch", 0, ActionType.LAUNCH_APP, mapOf("package_name" to JsonPrimitive("com.tencent.mm")), 15, false),
            ExecutionStep("verify", 1, ActionType.VERIFY_NODE, mapOf("text_any" to JsonPrimitive("发送")), 15, false),
        ),
        createdAt = "2026-08-17T12:00:00Z",
        updatedAt = "2026-08-17T12:00:00Z",
    )

    @Test
    fun `does not repeat a step before server acknowledgement`() = runBlocking {
        var calls = 0
        val runner = JobRunner { "2026-08-17T12:00:01Z" }
        val executor = ActionExecutor { calls += 1; ActionOutcome(StepStatus.SUCCEEDED, "OK") }
        val first = runner.runNext(job, JobRunnerState(), executor)
        val replay = runner.runNext(job, first.state, executor)
        assertEquals(1, calls)
        assertEquals("launch", replay.state.pendingResult?.stepId)
    }

    @Test
    fun `acknowledged success advances to next step and preserves checkpoint across lease`() = runBlocking {
        val runner = JobRunner { "2026-08-17T12:00:01Z" }
        val executor = ActionExecutor { ActionOutcome(StepStatus.SUCCEEDED, "OK") }
        val first = runner.runNext(job, JobRunnerState(), executor)
        val acknowledged = runner.acknowledge(first.state, "launch")
        val resumed = runner.runNext(job.copy(leaseId = "lease-2"), acknowledged, executor)
        assertEquals("verify", resumed.state.pendingResult?.stepId)
        assertEquals(setOf("launch"), resumed.state.completedStepIds)
    }
}
