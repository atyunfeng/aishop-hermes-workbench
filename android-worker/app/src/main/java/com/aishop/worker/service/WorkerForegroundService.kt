package com.aishop.worker.service

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.os.IBinder
import android.util.Log
import android.util.Base64
import androidx.core.content.ContextCompat
import androidx.core.content.IntentCompat
import androidx.lifecycle.LifecycleService
import com.aishop.worker.WorkerApplication
import com.aishop.worker.accessibility.AIShopAccessibilityService
import com.aishop.worker.data.PairingCredentials
import com.aishop.worker.data.WorkerStatusSnapshot
import com.aishop.worker.execution.JobRunner
import com.aishop.worker.execution.JobRunnerState
import com.aishop.worker.protocol.DeviceHeartbeat
import com.aishop.worker.protocol.EvidenceUpload
import com.aishop.worker.protocol.WorkerState
import com.aishop.worker.system.DeviceHealth
import com.aishop.worker.system.DeviceHealthReader
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

class WorkerForegroundService : LifecycleService() {
    private val serviceScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val coordinator = HeartbeatCoordinator()
    private lateinit var applicationState: WorkerApplication
    private lateinit var healthReader: DeviceHealthReader
    private var heartbeatJob: Job? = null
    private var coordinatorState = CoordinatorState()
    private val jobRunner = JobRunner()
    private var jobRunnerState = JobRunnerState()

    override fun onCreate() {
        super.onCreate()
        applicationState = application as WorkerApplication
        healthReader = DeviceHealthReader(this)
        coordinatorState = applicationState.preferences.coordinatorState()
        jobRunnerState = applicationState.preferences.jobRunnerState()
        createNotificationChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        super.onStartCommand(intent, flags, startId)
        when (intent?.action ?: ACTION_START) {
            ACTION_START -> startHeartbeat()
            ACTION_PAUSE -> updateLocalState(WorkerState.PAUSED)
            ACTION_RESUME -> updateLocalState(WorkerState.IDLE)
            ACTION_TAKEOVER -> updateLocalState(WorkerState.TAKEOVER)
            ACTION_SCREEN_CAPTURE -> {
                startHeartbeat()
                val resultData = intent?.let {
                    IntentCompat.getParcelableExtra(it, EXTRA_PROJECTION_DATA, Intent::class.java)
                }
                if (resultData != null) {
                    applicationState.screenCapture.start(
                        intent?.getIntExtra(EXTRA_PROJECTION_RESULT_CODE, 0) ?: 0,
                        resultData,
                    )
                }
            }
            ACTION_STOP -> stopWorker()
        }
        return START_STICKY
    }

    override fun onBind(intent: Intent): IBinder? = super.onBind(intent)

    override fun onDestroy() {
        heartbeatJob?.cancel()
        serviceScope.cancel()
        super.onDestroy()
    }

    private fun startHeartbeat() {
        startForeground(NOTIFICATION_ID, notification())
        if (heartbeatJob?.isActive == true) return
        heartbeatJob = serviceScope.launch {
            var retryIndex = 0
            while (isActive) {
                val credentials = applicationState.preferences.credentials()
                if (credentials == null) {
                    stopSelf()
                    break
                }
                val health = healthReader.read()
                try {
                    val response = sendHeartbeat(credentials, health)
                    applicationState.preferences.pendingInboundEvents().firstOrNull()?.let { event ->
                        applicationState.workerApi.uploadEvent(
                            credentials.baseUrl,
                            credentials.deviceId,
                            credentials.token,
                            event,
                        )
                        applicationState.preferences.acknowledgeInboundEvent(event.eventId)
                    }
                    applicationState.preferences.saveHeartbeatStatus(
                        WorkerStatusSnapshot(
                            serverTime = response.serverTime,
                            batteryPercent = health.batteryPercent,
                            notificationsReady = health.permissions.notifications,
                            accessibilityReady = health.permissions.accessibility,
                            screenCaptureReady = health.permissions.screenCapture,
                        ),
                    )
                    val outcome = coordinator.reduce(coordinatorState, response)
                    coordinatorState = outcome.state
                    jobRunnerState = jobRunner.acknowledge(
                        jobRunnerState,
                        response.acknowledgedStepId,
                    )
                    if (response.job != null && coordinatorState.workerState !in setOf(
                            WorkerState.PAUSED,
                            WorkerState.TAKEOVER,
                            WorkerState.OFFLINE,
                            WorkerState.ERROR,
                        )
                    ) {
                        coordinatorState = coordinatorState.copy(workerState = WorkerState.BUSY)
                        val jobOutcome = jobRunner.runNext(
                            response.job,
                            jobRunnerState,
                            AIShopAccessibilityService.executor,
                        )
                        jobRunnerState = jobOutcome.state
                        val evidence = jobOutcome.evidence
                        val result = jobRunnerState.pendingResult
                        if (evidence != null && result != null) {
                            val uploaded = applicationState.workerApi.uploadEvidence(
                                credentials.baseUrl,
                                credentials.deviceId,
                                credentials.token,
                                EvidenceUpload(
                                    taskId = response.job.taskId,
                                    jobId = response.job.jobId,
                                    stepId = result.stepId,
                                    mediaType = evidence.mediaType,
                                    contentBase64 = Base64.encodeToString(
                                        evidence.content,
                                        Base64.NO_WRAP,
                                    ),
                                    label = evidence.label,
                                ),
                            )
                            jobRunnerState = jobRunner.attachEvidence(
                                jobRunnerState,
                                uploaded.evidenceId,
                            )
                        }
                    } else if (response.job == null && jobRunnerState.pendingResult == null &&
                        coordinatorState.workerState == WorkerState.BUSY
                    ) {
                        coordinatorState = coordinatorState.copy(workerState = WorkerState.IDLE)
                        jobRunnerState = JobRunnerState()
                    }
                    applicationState.preferences.saveCoordinatorState(coordinatorState)
                    applicationState.preferences.saveJobRunnerState(jobRunnerState)
                    updateNotification()
                    retryIndex = 0
                    if (outcome.effect == CoordinatorEffect.STOP_SERVICE) {
                        acknowledgeStop(credentials, health)
                        stopSelf()
                        break
                    }
                    delay(response.nextHeartbeatSeconds.coerceAtLeast(1) * 1_000L)
                } catch (error: Exception) {
                    Log.w(TAG, "Heartbeat failed: ${error.javaClass.simpleName}")
                    val retrySeconds = RETRY_SECONDS[retryIndex.coerceAtMost(RETRY_SECONDS.lastIndex)]
                    retryIndex = (retryIndex + 1).coerceAtMost(RETRY_SECONDS.lastIndex)
                    delay(retrySeconds * 1_000L)
                }
            }
        }
    }

    private fun sendHeartbeat(credentials: PairingCredentials, health: DeviceHealth) =
        applicationState.workerApi.heartbeat(
            credentials.baseUrl,
            credentials.deviceId,
            credentials.token,
            heartbeatPayload(health),
        )

    private fun heartbeatPayload(health: DeviceHealth) = DeviceHeartbeat(
        sequence = applicationState.preferences.nextSequence(),
        workerState = coordinatorState.workerState,
        currentTaskId = jobRunnerState.jobId,
        batteryPercent = health.batteryPercent,
        permissions = health.permissions,
        installedApps = health.installedApps,
        acknowledgedCommandId = coordinatorState.pendingAcknowledgementId,
        completedStep = jobRunnerState.pendingResult,
    )

    private fun acknowledgeStop(credentials: PairingCredentials, health: DeviceHealth) {
        runCatching { sendHeartbeat(credentials, health) }
    }

    private fun updateLocalState(workerState: WorkerState) {
        coordinatorState = coordinatorState.copy(workerState = workerState)
        applicationState.preferences.saveCoordinatorState(coordinatorState)
        applicationState.screenCapture.stop()
        if (workerState == WorkerState.IDLE && heartbeatJob?.isActive != true) {
            startHeartbeat()
        } else {
            updateNotification()
        }
    }

    private fun stopWorker() {
        coordinatorState = coordinatorState.copy(workerState = WorkerState.OFFLINE)
        applicationState.preferences.saveCoordinatorState(coordinatorState)
        stopSelf()
    }

    private fun createNotificationChannel() {
        getSystemService(NotificationManager::class.java).createNotificationChannel(
            NotificationChannel(
                NOTIFICATION_CHANNEL,
                "AIShop Worker status",
                NotificationManager.IMPORTANCE_LOW,
            ),
        )
    }

    private fun updateNotification() {
        getSystemService(NotificationManager::class.java).notify(NOTIFICATION_ID, notification())
    }

    private fun notification(): Notification {
        val toggleAction = if (coordinatorState.workerState == WorkerState.PAUSED) {
            Notification.Action.Builder(
                null,
                "继续",
                servicePendingIntent(ACTION_RESUME, 2),
            ).build()
        } else {
            Notification.Action.Builder(
                null,
                "暂停",
                servicePendingIntent(ACTION_PAUSE, 1),
            ).build()
        }
        return Notification.Builder(this, NOTIFICATION_CHANNEL)
            .setSmallIcon(android.R.drawable.stat_notify_sync)
            .setContentTitle("AIShop 手机员工")
            .setContentText("状态：${coordinatorState.workerState.name}")
            .setOngoing(true)
            .addAction(toggleAction)
            .addAction(
                Notification.Action.Builder(
                    null,
                    "停止",
                    servicePendingIntent(ACTION_STOP, 3),
                ).build(),
            )
            .build()
    }

    private fun servicePendingIntent(action: String, requestCode: Int): PendingIntent =
        PendingIntent.getService(
            this,
            requestCode,
            Intent(action).setComponent(ComponentName(this, WorkerForegroundService::class.java)),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )

    companion object {
        const val ACTION_START = "com.aishop.worker.action.START"
        const val ACTION_PAUSE = "com.aishop.worker.action.PAUSE"
        const val ACTION_RESUME = "com.aishop.worker.action.RESUME"
        const val ACTION_TAKEOVER = "com.aishop.worker.action.TAKEOVER"
        const val ACTION_SCREEN_CAPTURE = "com.aishop.worker.action.SCREEN_CAPTURE"
        const val ACTION_STOP = "com.aishop.worker.action.STOP"
        private const val EXTRA_PROJECTION_RESULT_CODE = "projection_result_code"
        private const val EXTRA_PROJECTION_DATA = "projection_data"
        private const val NOTIFICATION_CHANNEL = "aishop_worker_status"
        private const val NOTIFICATION_ID = 901
        private const val TAG = "AIShopWorker"
        private val RETRY_SECONDS = intArrayOf(5, 10, 20, 30)

        fun sendAction(context: Context, action: String) {
            ContextCompat.startForegroundService(
                context,
                Intent(context, WorkerForegroundService::class.java).setAction(action),
            )
        }

        fun startProjection(context: Context, resultCode: Int, data: Intent) {
            ContextCompat.startForegroundService(
                context,
                Intent(context, WorkerForegroundService::class.java)
                    .setAction(ACTION_SCREEN_CAPTURE)
                    .putExtra(EXTRA_PROJECTION_RESULT_CODE, resultCode)
                    .putExtra(EXTRA_PROJECTION_DATA, data),
            )
        }
    }
}
