package com.aishop.worker.accessibility

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class SemanticSelectorTest {
    @Test
    fun `finds deterministic first enabled clickable text match`() {
        val first = SemanticNode(text = "发送", clickable = true)
        val root = SemanticNode(children = listOf(first, SemanticNode(text = "发送", clickable = true)))
        val selector = SemanticSelector(textAny = setOf("发送"), requireClickable = true)
        assertEquals(first, selector.firstMatch(root))
    }

    @Test
    fun `does not match disabled or wrong semantic family`() {
        val root = SemanticNode(text = "发送", contentDescription = "send", enabled = false)
        assertNull(SemanticSelector(textAny = setOf("发送")).firstMatch(root))
        assertNull(SemanticSelector(descriptionAny = setOf("other")).firstMatch(root.copy(enabled = true)))
    }

    @Test(expected = IllegalArgumentException::class)
    fun `rejects multiple selector families`() {
        SemanticSelector(textAny = setOf("发送"), viewIdAny = setOf("send"))
    }
}
