package com.aishop.worker.system

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.os.BatteryManager
import android.os.Build
import android.provider.Settings
import androidx.core.app.NotificationManagerCompat
import com.aishop.worker.protocol.InstalledApp
import com.aishop.worker.protocol.PermissionState
import com.aishop.worker.WorkerApplication

data class DeviceHealth(
    val batteryPercent: Int,
    val permissions: PermissionState,
    val installedApps: List<InstalledApp>,
)

class DeviceHealthReader(private val context: Context) {
    fun read(): DeviceHealth = DeviceHealth(
        batteryPercent = context.getSystemService(BatteryManager::class.java)
            .getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY)
            .coerceIn(0, 100),
        permissions = PermissionState(
            notifications = hasNotificationPermission() && isNotificationListenerEnabled(),
            accessibility = isAIShopAccessibilityEnabled(),
            screenCapture = (context.applicationContext as WorkerApplication).screenCapture.active,
        ),
        installedApps = PACKAGES.mapNotNull(::installedApp),
    )

    private fun isAIShopAccessibilityEnabled(): Boolean {
        val enabled = Settings.Secure.getString(
            context.contentResolver,
            Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES,
        ).orEmpty()
        return enabled.split(':').any { it.startsWith(context.packageName) }
    }

    private fun hasNotificationPermission(): Boolean = Build.VERSION.SDK_INT < 33 ||
        context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) ==
        PackageManager.PERMISSION_GRANTED

    private fun isNotificationListenerEnabled(): Boolean =
        NotificationManagerCompat.getEnabledListenerPackages(context).contains(context.packageName)

    @Suppress("DEPRECATION")
    private fun installedApp(packageName: String): InstalledApp? = runCatching {
        val info = context.packageManager.getPackageInfo(packageName, 0)
        InstalledApp(packageName, info.versionName ?: "unknown")
    }.getOrNull()

    private companion object {
        val PACKAGES = listOf(
            "com.tencent.mm",
            "com.tencent.wework",
            "com.tencent.mobileqq",
            "com.taobao.qianniu",
            "com.ss.android.ugc.aweme",
            "com.bytedance.ep.android",
        )
    }
}
