package com.aishop.worker.notifications

import android.app.Notification
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import com.aishop.worker.WorkerApplication

class CommerceNotificationListener : NotificationListenerService() {
    override fun onNotificationPosted(notification: StatusBarNotification?) {
        val item = notification ?: return
        val extras = item.notification.extras
        val title = extras.getCharSequence(Notification.EXTRA_TITLE)?.toString().orEmpty()
        val text = extras.getCharSequence(Notification.EXTRA_TEXT)?.toString().orEmpty()
        val event = NotificationEventMapper.map(
            item.packageName,
            item.key,
            item.user.toString(),
            title,
            text,
            item.postTime,
        ) ?: return
        (application as WorkerApplication).preferences.enqueueInboundEvent(event)
    }
}
