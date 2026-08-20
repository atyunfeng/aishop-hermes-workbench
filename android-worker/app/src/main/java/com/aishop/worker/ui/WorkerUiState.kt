package com.aishop.worker.ui

import com.aishop.worker.data.PairingCredentials
import com.aishop.worker.data.WorkerStatusSnapshot
import com.aishop.worker.service.CoordinatorState

data class WorkerUiState(
    val paired: Boolean,
    val pairingInProgress: Boolean,
    val deviceId: String,
    val displayName: String,
    val baseUrl: String,
    val workerState: String,
    val lastHeartbeatAt: String?,
    val batteryPercent: Int?,
    val notificationsReady: Boolean,
    val accessibilityReady: Boolean,
    val screenCaptureReady: Boolean,
    val autoStartEnabled: Boolean,
    val errorMessage: String?,
) {
    fun visibleText(): String = listOfNotNull(
        deviceId,
        displayName,
        baseUrl,
        workerState,
        lastHeartbeatAt,
        batteryPercent?.toString(),
        errorMessage,
    ).joinToString(" ")
}

fun buildWorkerUiState(
    deviceId: String,
    credentials: PairingCredentials?,
    coordinator: CoordinatorState,
    status: WorkerStatusSnapshot?,
    pairingInProgress: Boolean = false,
    errorMessage: String? = null,
    autoStartEnabled: Boolean = false,
): WorkerUiState = WorkerUiState(
    paired = credentials != null,
    pairingInProgress = pairingInProgress,
    deviceId = deviceId,
    displayName = credentials?.displayName.orEmpty(),
    baseUrl = credentials?.baseUrl.orEmpty(),
    workerState = coordinator.workerState.name,
    lastHeartbeatAt = status?.serverTime,
    batteryPercent = status?.batteryPercent,
    notificationsReady = status?.notificationsReady ?: false,
    accessibilityReady = status?.accessibilityReady ?: false,
    screenCaptureReady = status?.screenCaptureReady ?: false,
    autoStartEnabled = autoStartEnabled,
    errorMessage = errorMessage,
)
