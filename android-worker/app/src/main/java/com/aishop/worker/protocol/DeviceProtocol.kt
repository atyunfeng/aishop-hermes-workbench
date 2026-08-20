package com.aishop.worker.protocol

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonElement

@Serializable
enum class WorkerState {
    OFFLINE,
    IDLE,
    BUSY,
    PAUSED,
    TAKEOVER,
    ERROR,
}

@Serializable
enum class DeviceCommandType {
    PAUSE,
    RESUME,
    TAKEOVER,
    STOP,
}

@Serializable
data class PairDeviceRequest(
    @SerialName("pairing_code") val pairingCode: String,
    @SerialName("device_id") val deviceId: String,
    @SerialName("display_name") val displayName: String,
    @SerialName("app_version") val appVersion: String,
    val capabilities: List<String>,
)

@Serializable
data class PairDeviceResponse(
    @SerialName("device_id") val deviceId: String,
    @SerialName("device_token") val deviceToken: String,
    @SerialName("heartbeat_interval_seconds") val heartbeatIntervalSeconds: Int,
)

@Serializable
data class PermissionState(
    val notifications: Boolean,
    val accessibility: Boolean,
    @SerialName("screen_capture") val screenCapture: Boolean,
)

@Serializable
data class InstalledApp(
    @SerialName("package_name") val packageName: String,
    @SerialName("version_name") val versionName: String,
)

@Serializable
data class DeviceHeartbeat(
    val sequence: Long,
    @SerialName("worker_state") val workerState: WorkerState,
    @SerialName("current_task_id") val currentTaskId: String?,
    @SerialName("battery_percent") val batteryPercent: Int,
    val permissions: PermissionState,
    @SerialName("installed_apps") val installedApps: List<InstalledApp>,
    @SerialName("acknowledged_command_id") val acknowledgedCommandId: String?,
    @SerialName("completed_step") val completedStep: StepResult? = null,
)

@Serializable
data class DeviceCommand(
    @SerialName("command_id") val commandId: String,
    val type: DeviceCommandType,
    val reason: String,
    @SerialName("created_at") val createdAt: String,
)

@Serializable
data class HeartbeatResponse(
    @SerialName("server_time") val serverTime: String,
    @SerialName("next_heartbeat_seconds") val nextHeartbeatSeconds: Int,
    val command: DeviceCommand?,
    val job: DeviceJob? = null,
    @SerialName("acknowledged_step_id") val acknowledgedStepId: String? = null,
)

@Serializable
enum class ActionType {
    LAUNCH_APP,
    TAP_NODE,
    SET_TEXT,
    SCROLL,
    BACK,
    WAIT_FOR,
    VERIFY_NODE,
    CAPTURE_SCREEN,
}

@Serializable
enum class StepStatus {
    SUCCEEDED,
    RETRYABLE,
    HUMAN_TAKEOVER,
    FAILED,
}

@Serializable
data class ExecutionStep(
    @SerialName("step_id") val stepId: String,
    val ordinal: Int,
    val action: ActionType,
    val arguments: Map<String, JsonElement>,
    @SerialName("timeout_seconds") val timeoutSeconds: Int,
    @SerialName("evidence_required") val evidenceRequired: Boolean,
)

@Serializable
data class DeviceJob(
    @SerialName("job_id") val jobId: String,
    @SerialName("task_id") val taskId: String,
    @SerialName("app_skill_id") val appSkillId: String,
    @SerialName("skill_version") val skillVersion: String,
    val status: String,
    @SerialName("required_packages") val requiredPackages: List<String>,
    @SerialName("required_capabilities") val requiredCapabilities: List<String>,
    @SerialName("lease_id") val leaseId: String,
    @SerialName("device_id") val deviceId: String?,
    @SerialName("lease_expires_at") val leaseExpiresAt: String,
    val mode: String,
    val steps: List<ExecutionStep>,
    @SerialName("created_at") val createdAt: String,
    @SerialName("updated_at") val updatedAt: String,
)

@Serializable
data class StepResult(
    @SerialName("job_id") val jobId: String,
    @SerialName("lease_id") val leaseId: String,
    @SerialName("step_id") val stepId: String,
    val status: StepStatus,
    val code: String,
    val message: String,
    val observed: Map<String, String>,
    @SerialName("evidence_ids") val evidenceIds: List<String>,
    @SerialName("completed_at") val completedAt: String,
)

@Serializable
data class EvidenceUpload(
    @SerialName("task_id") val taskId: String,
    @SerialName("job_id") val jobId: String,
    @SerialName("step_id") val stepId: String,
    val source: String = "DEVICE",
    @SerialName("media_type") val mediaType: String,
    @SerialName("content_base64") val contentBase64: String,
    val label: String,
)

@Serializable
data class EvidenceResponse(
    @SerialName("evidence_id") val evidenceId: String,
)

@Serializable
data class InboundAttachment(
    val id: String,
    @SerialName("media_type") val mediaType: String,
)

@Serializable
data class InboundEventPayload(
    @SerialName("event_id") val eventId: String,
    val source: String,
    @SerialName("account_id") val accountId: String,
    @SerialName("conversation_id") val conversationId: String,
    val sender: String,
    @SerialName("event_type") val eventType: String,
    val text: String,
    val attachments: List<InboundAttachment>,
    @SerialName("occurred_at") val occurredAt: String,
)
