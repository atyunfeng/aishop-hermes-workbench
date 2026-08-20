package com.aishop.worker.accessibility

data class SemanticSelector(
    val textAny: Set<String> = emptySet(),
    val descriptionAny: Set<String> = emptySet(),
    val viewIdAny: Set<String> = emptySet(),
    val requireEnabled: Boolean = true,
    val requireClickable: Boolean = false,
) {
    init {
        require(listOf(textAny, descriptionAny, viewIdAny).count { it.isNotEmpty() } == 1) {
            "exactly one semantic selector family is required"
        }
    }

    fun matches(node: SemanticNode): Boolean {
        if (requireEnabled && !node.enabled) return false
        if (requireClickable && !node.clickable) return false
        return when {
            textAny.isNotEmpty() -> node.text in textAny
            descriptionAny.isNotEmpty() -> node.contentDescription in descriptionAny
            else -> node.viewId in viewIdAny
        }
    }

    fun firstMatch(root: SemanticNode): SemanticNode? {
        if (matches(root)) return root
        return root.children.firstNotNullOfOrNull(::firstMatch)
    }
}
