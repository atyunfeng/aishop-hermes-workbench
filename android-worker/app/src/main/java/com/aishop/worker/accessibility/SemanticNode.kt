package com.aishop.worker.accessibility

data class SemanticNode(
    val text: String? = null,
    val contentDescription: String? = null,
    val viewId: String? = null,
    val enabled: Boolean = true,
    val clickable: Boolean = false,
    val children: List<SemanticNode> = emptyList(),
)
