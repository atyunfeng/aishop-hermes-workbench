package com.aishop.worker.execution

import com.aishop.worker.protocol.ExecutionStep
import com.aishop.worker.protocol.StepStatus

data class CapturedEvidence(
    val mediaType: String,
    val content: ByteArray,
    val label: String,
)

data class ActionOutcome(
    val status: StepStatus,
    val code: String,
    val message: String = "",
    val observed: Map<String, String> = emptyMap(),
    val evidence: CapturedEvidence? = null,
)

fun interface ActionExecutor {
    suspend fun execute(step: ExecutionStep): ActionOutcome
}
