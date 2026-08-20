package com.aishop.worker

import android.app.Application
import com.aishop.worker.data.WorkerPreferences
import com.aishop.worker.capture.ScreenCaptureController
import com.aishop.worker.protocol.WorkerApi

class WorkerApplication : Application() {
    lateinit var preferences: WorkerPreferences
        private set
    lateinit var workerApi: WorkerApi
        private set
    lateinit var screenCapture: ScreenCaptureController
        private set

    override fun onCreate() {
        super.onCreate()
        preferences = WorkerPreferences(this)
        workerApi = WorkerApi()
        screenCapture = ScreenCaptureController(this)
    }
}
