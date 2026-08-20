package com.aishop.worker.notifications

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class NotificationEventMapperTest {
    @Test
    fun mapsAllowlistedPackagesToStableEvents() {
        val first = NotificationEventMapper.map(
            "com.tencent.wework",
            "notification-1",
            "account-1",
            "测试群",
            "检查超时订单",
            1_774_000_000_000,
        )
        val second = NotificationEventMapper.map(
            "com.tencent.wework",
            "notification-1",
            "account-1",
            "测试群",
            "检查超时订单",
            1_774_000_000_000,
        )
        assertEquals("we-com", first?.source)
        assertEquals(first?.eventId, second?.eventId)
        assertEquals("测试群", first?.conversationId)
    }

    @Test
    fun rejectsUnknownPackagesAndEmptyNotifications() {
        assertNull(NotificationEventMapper.map("bad.package", "1", "a", "t", "x", 1))
        assertNull(NotificationEventMapper.map("com.tencent.mm", "1", "a", "", "", 1))
    }
}
