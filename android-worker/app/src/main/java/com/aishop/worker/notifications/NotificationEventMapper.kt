package com.aishop.worker.notifications

import com.aishop.worker.protocol.InboundEventPayload
import java.security.MessageDigest
import java.time.Instant

object NotificationEventMapper {
    val supportedPackages = mapOf(
        "com.taobao.qianniu" to "qian-niu",
        "com.bytedance.ep.android" to "dou-dian",
        "com.ss.android.ugc.aweme" to "dou-dian",
        "com.tencent.mm" to "we-chat",
        "com.tencent.wework" to "we-com",
        "com.tencent.mobileqq" to "qq",
    )

    fun map(
        packageName: String,
        notificationKey: String,
        accountId: String,
        title: String,
        text: String,
        postedAtMillis: Long,
    ): InboundEventPayload? {
        val source = supportedPackages[packageName] ?: return null
        if (title.isBlank() && text.isBlank()) return null
        val digest = MessageDigest.getInstance("SHA-256")
            .digest("$packageName\n$notificationKey\n$postedAtMillis".toByteArray())
            .joinToString("") { "%02x".format(it) }
        return InboundEventPayload(
            eventId = digest,
            source = source,
            accountId = accountId,
            conversationId = title.ifBlank { notificationKey },
            sender = title.ifBlank { source },
            eventType = "MESSAGE",
            text = text.take(4_000),
            attachments = emptyList(),
            occurredAt = Instant.ofEpochMilli(postedAtMillis).toString(),
        )
    }
}
