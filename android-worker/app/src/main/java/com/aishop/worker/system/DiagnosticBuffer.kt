package com.aishop.worker.system

class DiagnosticBuffer(private val capacity: Int = 100) {
    private val entries = ArrayDeque<String>()

    @Synchronized
    fun add(message: String) {
        val redacted = message
            .replace(Regex("(?i)(token|authorization|message|text)=\\S+"), "$1=[REDACTED]")
            .take(500)
        entries.addLast(redacted)
        while (entries.size > capacity.coerceAtLeast(1)) entries.removeFirst()
    }

    @Synchronized
    fun snapshot(): List<String> = entries.toList()
}
