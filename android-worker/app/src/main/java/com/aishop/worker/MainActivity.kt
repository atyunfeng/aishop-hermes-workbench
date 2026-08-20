package com.aishop.worker

import android.Manifest
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.lifecycleScope
import com.aishop.worker.protocol.PairDeviceRequest
import com.aishop.worker.protocol.normalizeGatewayUrl
import com.aishop.worker.service.WorkerForegroundService
import com.aishop.worker.ui.WorkerScreen
import com.aishop.worker.ui.WorkerUiState
import com.aishop.worker.ui.buildWorkerUiState
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class MainActivity : ComponentActivity() {
    private val applicationState by lazy { application as WorkerApplication }
    private val refreshHandler = Handler(Looper.getMainLooper())
    private var pairingInProgress = false
    private var errorMessage: String? = null
    private var uiState by mutableStateOf(emptyUiState())
    private val notificationPermission = registerForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { startWorker() }
    private val screenCapturePermission = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult(),
    ) { result ->
        val data = result.data
        if (result.resultCode == RESULT_OK && data != null) {
            WorkerForegroundService.startProjection(this, result.resultCode, data)
            errorMessage = null
        } else {
            errorMessage = "画面预览未授权；Accessibility 截图证据仍可使用"
        }
        refreshUi()
    }
    private val refresh = object : Runnable {
        override fun run() {
            refreshUi()
            refreshHandler.postDelayed(this, 1_000)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        refreshUi()
        setContent {
            WorkerScreen(
                state = uiState,
                onPair = ::pair,
                onStart = ::requestNotificationAndStart,
                onPause = { sendAction(WorkerForegroundService.ACTION_PAUSE) },
                onResume = { sendAction(WorkerForegroundService.ACTION_RESUME) },
                onTakeover = { sendAction(WorkerForegroundService.ACTION_TAKEOVER) },
                onStop = { sendAction(WorkerForegroundService.ACTION_STOP) },
                onClearPairing = ::clearPairing,
                onEnableAccessibility = {
                    startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
                },
                onEnableNotifications = {
                    startActivity(Intent("android.settings.ACTION_NOTIFICATION_LISTENER_SETTINGS"))
                },
                onOpenBatterySettings = {
                    startActivity(Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS))
                },
                onAutoStartChange = {
                    applicationState.preferences.setAutoStartEnabled(it)
                    refreshUi()
                },
                onEnableScreenCapture = {
                    screenCapturePermission.launch(applicationState.screenCapture.consentIntent())
                },
            )
        }
    }

    override fun onResume() {
        super.onResume()
        refreshHandler.post(refresh)
    }

    override fun onPause() {
        refreshHandler.removeCallbacks(refresh)
        super.onPause()
    }

    private fun pair(gatewayUrl: String, pairingCode: String, displayName: String) {
        if (pairingInProgress) return
        pairingInProgress = true
        errorMessage = null
        refreshUi()
        lifecycleScope.launch {
            runCatching {
                withContext(Dispatchers.IO) {
                    val normalizedUrl = normalizeGatewayUrl(gatewayUrl)
                    val response = applicationState.workerApi.pair(
                        normalizedUrl,
                        PairDeviceRequest(
                            pairingCode = pairingCode,
                            deviceId = applicationState.preferences.deviceId,
                            displayName = displayName.trim(),
                            appVersion = BuildConfig.VERSION_NAME,
                            capabilities = listOf(
                                "heartbeat",
                                "manual_control",
                                "accessibility",
                                "screen_capture",
                            ),
                        ),
                    )
                    applicationState.preferences.savePairing(
                        normalizedUrl,
                        displayName.trim(),
                        response.deviceToken,
                    )
                }
            }.onFailure {
                errorMessage = "配对失败：${it.message ?: it.javaClass.simpleName}"
            }
            pairingInProgress = false
            refreshUi()
        }
    }

    private fun requestNotificationAndStart() {
        if (Build.VERSION.SDK_INT >= 33 &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) !=
            android.content.pm.PackageManager.PERMISSION_GRANTED
        ) {
            notificationPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
        } else {
            startWorker()
        }
    }

    private fun startWorker() = sendAction(WorkerForegroundService.ACTION_START)

    private fun sendAction(action: String) {
        WorkerForegroundService.sendAction(this, action)
        refreshHandler.postDelayed(::refreshUi, 250)
    }

    private fun clearPairing() {
        sendAction(WorkerForegroundService.ACTION_STOP)
        applicationState.screenCapture.stop()
        applicationState.preferences.clearPairing()
        errorMessage = null
        refreshUi()
    }

    private fun refreshUi() {
        val preferences = applicationState.preferences
        uiState = buildWorkerUiState(
            deviceId = preferences.deviceId,
            credentials = preferences.credentials(),
            coordinator = preferences.coordinatorState(),
            status = preferences.statusSnapshot(),
            pairingInProgress = pairingInProgress,
            errorMessage = errorMessage,
            autoStartEnabled = preferences.autoStartEnabled(),
        )
    }

    private fun emptyUiState() = WorkerUiState(
        paired = false,
        pairingInProgress = false,
        deviceId = "",
        displayName = "",
        baseUrl = "",
        workerState = "IDLE",
        lastHeartbeatAt = null,
        batteryPercent = null,
        notificationsReady = false,
        accessibilityReady = false,
        screenCaptureReady = false,
        autoStartEnabled = false,
        errorMessage = null,
    )
}
