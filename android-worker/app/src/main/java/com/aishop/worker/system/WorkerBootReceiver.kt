package com.aishop.worker.system

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import com.aishop.worker.WorkerApplication
import com.aishop.worker.service.WorkerForegroundService

fun shouldStartAfterBoot(paired: Boolean, optedIn: Boolean): Boolean = paired && optedIn

class WorkerBootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent?) {
        if (intent?.action != Intent.ACTION_BOOT_COMPLETED) return
        val preferences = (context.applicationContext as WorkerApplication).preferences
        if (shouldStartAfterBoot(preferences.credentials() != null, preferences.autoStartEnabled())) {
            WorkerForegroundService.sendAction(context, WorkerForegroundService.ACTION_START)
        }
    }
}
