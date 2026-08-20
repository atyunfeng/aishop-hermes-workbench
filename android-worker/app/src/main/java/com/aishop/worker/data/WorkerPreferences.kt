package com.aishop.worker.data

import android.content.Context
import com.aishop.worker.execution.JobRunnerState
import com.aishop.worker.protocol.WorkerState
import com.aishop.worker.service.CoordinatorState
import java.util.UUID
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json

data class PairingCredentials(
    val baseUrl: String,
    val deviceId: String,
    val displayName: String,
    val token: String,
)

data class WorkerStatusSnapshot(
    val serverTime: String,
    val batteryPercent: Int,
    val notificationsReady: Boolean,
    val accessibilityReady: Boolean,
    val screenCaptureReady: Boolean,
)

class WorkerPreferences(context: Context) {
    private val preferences = context.getSharedPreferences(PREFERENCES_NAME, Context.MODE_PRIVATE)
    private val credentialStore = SecureCredentialStore(context)

    val deviceId: String
        get() = synchronized(this) {
            preferences.getString(KEY_DEVICE_ID, null) ?: "android-${UUID.randomUUID()}".also {
                check(preferences.edit().putString(KEY_DEVICE_ID, it).commit())
            }
        }

    fun credentials(): PairingCredentials? {
        val baseUrl = preferences.getString(KEY_BASE_URL, null) ?: return null
        val displayName = preferences.getString(KEY_DISPLAY_NAME, null) ?: return null
        val token = credentialStore.readToken() ?: preferences.getString(KEY_TOKEN, null)?.also {
            credentialStore.writeToken(it)
            preferences.edit().remove(KEY_TOKEN).apply()
        } ?: return null
        return PairingCredentials(baseUrl, deviceId, displayName, token)
    }

    fun savePairing(baseUrl: String, displayName: String, token: String) {
        credentialStore.writeToken(token)
        check(
            preferences.edit()
                .putString(KEY_BASE_URL, baseUrl)
                .putString(KEY_DISPLAY_NAME, displayName)
                .commit(),
        )
    }

    @Synchronized
    fun nextSequence(): Long {
        val next = preferences.getLong(KEY_SEQUENCE, 0L) + 1L
        check(preferences.edit().putLong(KEY_SEQUENCE, next).commit())
        return next
    }

    fun clearPairing() {
        credentialStore.clear()
        check(
            preferences.edit()
                .remove(KEY_BASE_URL)
                .remove(KEY_DISPLAY_NAME)
                .remove(KEY_TOKEN)
                .remove(KEY_WORKER_STATE)
                .remove(KEY_LAST_COMMAND_ID)
                .remove(KEY_PENDING_ACKNOWLEDGEMENT_ID)
                .remove(KEY_LAST_HEARTBEAT_AT)
                .remove(KEY_BATTERY_PERCENT)
                .remove(KEY_NOTIFICATIONS_READY)
                .remove(KEY_ACCESSIBILITY_READY)
                .remove(KEY_SCREEN_CAPTURE_READY)
                .remove(KEY_JOB_RUNNER_STATE)
                .commit(),
        )
    }

    fun autoStartEnabled(): Boolean = preferences.getBoolean(KEY_AUTO_START, false)

    fun setAutoStartEnabled(enabled: Boolean) {
        check(preferences.edit().putBoolean(KEY_AUTO_START, enabled).commit())
    }

    fun enqueueInboundEvent(event: com.aishop.worker.protocol.InboundEventPayload) {
        val events = pendingInboundEvents().toMutableList()
        if (events.none { it.eventId == event.eventId && it.source == event.source }) {
            events += event
        }
        val bounded = events.takeLast(100)
        check(preferences.edit().putString(KEY_INBOUND_EVENTS, json.encodeToString(bounded)).commit())
    }

    fun pendingInboundEvents(): List<com.aishop.worker.protocol.InboundEventPayload> =
        preferences.getString(KEY_INBOUND_EVENTS, null)
            ?.let {
                runCatching {
                    json.decodeFromString<List<com.aishop.worker.protocol.InboundEventPayload>>(it)
                }.getOrNull()
            }
            ?: emptyList()

    fun acknowledgeInboundEvent(eventId: String) {
        val remaining = pendingInboundEvents().filterNot { it.eventId == eventId }
        check(preferences.edit().putString(KEY_INBOUND_EVENTS, json.encodeToString(remaining)).commit())
    }

    fun coordinatorState(): CoordinatorState = CoordinatorState(
        workerState = runCatching {
            WorkerState.valueOf(
                preferences.getString(KEY_WORKER_STATE, WorkerState.IDLE.name)
                    ?: WorkerState.IDLE.name,
            )
        }.getOrDefault(WorkerState.IDLE),
        lastAppliedCommandId = preferences.getString(KEY_LAST_COMMAND_ID, null),
        pendingAcknowledgementId = preferences.getString(KEY_PENDING_ACKNOWLEDGEMENT_ID, null),
    )

    fun saveCoordinatorState(state: CoordinatorState) {
        check(
            preferences.edit()
                .putString(KEY_WORKER_STATE, state.workerState.name)
                .putString(KEY_LAST_COMMAND_ID, state.lastAppliedCommandId)
                .putString(KEY_PENDING_ACKNOWLEDGEMENT_ID, state.pendingAcknowledgementId)
                .commit(),
        )
    }

    fun saveHeartbeatStatus(status: WorkerStatusSnapshot) {
        check(
            preferences.edit()
                .putString(KEY_LAST_HEARTBEAT_AT, status.serverTime)
                .putInt(KEY_BATTERY_PERCENT, status.batteryPercent)
                .putBoolean(KEY_NOTIFICATIONS_READY, status.notificationsReady)
                .putBoolean(KEY_ACCESSIBILITY_READY, status.accessibilityReady)
                .putBoolean(KEY_SCREEN_CAPTURE_READY, status.screenCaptureReady)
                .commit(),
        )
    }

    fun statusSnapshot(): WorkerStatusSnapshot? {
        val serverTime = preferences.getString(KEY_LAST_HEARTBEAT_AT, null) ?: return null
        return WorkerStatusSnapshot(
            serverTime = serverTime,
            batteryPercent = preferences.getInt(KEY_BATTERY_PERCENT, 0),
            notificationsReady = preferences.getBoolean(KEY_NOTIFICATIONS_READY, false),
            accessibilityReady = preferences.getBoolean(KEY_ACCESSIBILITY_READY, false),
            screenCaptureReady = preferences.getBoolean(KEY_SCREEN_CAPTURE_READY, false),
        )
    }

    fun jobRunnerState(): JobRunnerState = preferences.getString(KEY_JOB_RUNNER_STATE, null)
        ?.let { runCatching { json.decodeFromString<JobRunnerState>(it) }.getOrNull() }
        ?: JobRunnerState()

    fun saveJobRunnerState(state: JobRunnerState) {
        check(preferences.edit().putString(KEY_JOB_RUNNER_STATE, json.encodeToString(state)).commit())
    }

    private companion object {
        const val PREFERENCES_NAME = "aishop_worker"
        const val KEY_DEVICE_ID = "device_id"
        const val KEY_BASE_URL = "base_url"
        const val KEY_DISPLAY_NAME = "display_name"
        const val KEY_TOKEN = "device_token"
        const val KEY_SEQUENCE = "heartbeat_sequence"
        const val KEY_WORKER_STATE = "worker_state"
        const val KEY_LAST_COMMAND_ID = "last_command_id"
        const val KEY_PENDING_ACKNOWLEDGEMENT_ID = "pending_acknowledgement_id"
        const val KEY_LAST_HEARTBEAT_AT = "last_heartbeat_at"
        const val KEY_BATTERY_PERCENT = "battery_percent"
        const val KEY_NOTIFICATIONS_READY = "notifications_ready"
        const val KEY_ACCESSIBILITY_READY = "accessibility_ready"
        const val KEY_SCREEN_CAPTURE_READY = "screen_capture_ready"
        const val KEY_JOB_RUNNER_STATE = "job_runner_state"
        const val KEY_AUTO_START = "auto_start_enabled"
        const val KEY_INBOUND_EVENTS = "pending_inbound_events"
        val json = Json { ignoreUnknownKeys = false }
    }
}
