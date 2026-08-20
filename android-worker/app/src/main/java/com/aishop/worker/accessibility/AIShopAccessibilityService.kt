package com.aishop.worker.accessibility

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.AccessibilityService.ScreenshotResult
import android.accessibilityservice.AccessibilityService.TakeScreenshotCallback
import android.graphics.Bitmap
import android.os.Build
import android.os.Bundle
import android.view.Display
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import com.aishop.worker.execution.ActionExecutor
import com.aishop.worker.execution.ActionOutcome
import com.aishop.worker.execution.CapturedEvidence
import com.aishop.worker.protocol.ActionType
import com.aishop.worker.protocol.ExecutionStep
import com.aishop.worker.protocol.StepStatus
import java.io.ByteArrayOutputStream
import kotlinx.coroutines.delay
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlin.coroutines.resume

class AIShopAccessibilityService : AccessibilityService() {
    override fun onServiceConnected() {
        instance = this
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) = Unit

    override fun onInterrupt() = Unit

    override fun onDestroy() {
        if (instance === this) instance = null
        super.onDestroy()
    }

    suspend fun execute(step: ExecutionStep): ActionOutcome {
        if (step.arguments.keys.any { it in FORBIDDEN_KEYS }) {
            return takeover("UNSAFE_ARGUMENT", "检测到未授权的坐标或脚本参数")
        }
        if (step.action == ActionType.LAUNCH_APP) return launch(step)
        if (step.action == ActionType.BACK) {
            return if (performGlobalAction(GLOBAL_ACTION_BACK)) success() else retry("BACK_FAILED")
        }
        if (step.action == ActionType.CAPTURE_SCREEN) return capture(step)
        val dangerousPage = detectDangerousPage()
        if (dangerousPage != null) return takeover(dangerousPage, "页面需要人工处理")
        return when (step.action) {
            ActionType.TAP_NODE -> withNode(step) { node ->
                if (click(node)) success(mapOf("matched" to describe(node))) else retry("NODE_NOT_CLICKABLE")
            }
            ActionType.SET_TEXT -> withNode(step) { node ->
                val text = step.arguments["text"]?.jsonPrimitive?.contentOrNull.orEmpty()
                val args = Bundle().apply {
                    putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, text)
                }
                if (node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args)) {
                    success(mapOf("matched" to describe(node), "text_length" to text.length.toString()))
                } else {
                    retry("SET_TEXT_FAILED")
                }
            }
            ActionType.SCROLL -> withNode(step) { node ->
                val direction = step.arguments["direction"]?.jsonPrimitive?.contentOrNull
                val action = if (direction == "BACKWARD") {
                    AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD
                } else {
                    AccessibilityNodeInfo.ACTION_SCROLL_FORWARD
                }
                if (node.performAction(action)) success() else retry("SCROLL_FAILED")
            }
            ActionType.WAIT_FOR, ActionType.VERIFY_NODE -> waitForNode(step)
            else -> takeover("UNSUPPORTED_ACTION", "动作未在白名单中")
        }
    }

    private fun launch(step: ExecutionStep): ActionOutcome {
        val packageName = step.arguments["package_name"]?.jsonPrimitive?.contentOrNull
            ?: return takeover("PACKAGE_MISSING", "缺少 App 包名")
        val intent = packageManager.getLaunchIntentForPackage(packageName)
            ?: return takeover("APP_NOT_INSTALLED", "目标 App 未安装")
        intent.addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK)
        startActivity(intent)
        return success(mapOf("package_name" to packageName))
    }

    private suspend fun waitForNode(step: ExecutionStep): ActionOutcome {
        repeat(step.timeoutSeconds * 4) {
            val root = rootInActiveWindow
            val node = root?.let { find(it, selector(step.arguments)) }
            if (node != null) return success(mapOf("matched" to describe(node)))
            delay(250)
        }
        return retry("NODE_TIMEOUT")
    }

    private fun withNode(
        step: ExecutionStep,
        action: (AccessibilityNodeInfo) -> ActionOutcome,
    ): ActionOutcome {
        val root = rootInActiveWindow ?: return takeover("UNKNOWN_PAGE", "无法读取当前页面")
        val node = find(root, selector(step.arguments)) ?: return takeover("UNKNOWN_PAGE", "语义节点不存在")
        return action(node)
    }

    private fun selector(arguments: Map<String, JsonElement>): SemanticSelector {
        fun values(key: String) = arguments[key]?.jsonArray?.map { it.jsonPrimitive.content }?.toSet().orEmpty()
        return SemanticSelector(
            textAny = values("text_any"),
            descriptionAny = values("description_any"),
            viewIdAny = values("view_id_any"),
            requireEnabled = arguments["require_enabled"]?.jsonPrimitive?.booleanOrNull ?: true,
            requireClickable = arguments["require_clickable"]?.jsonPrimitive?.booleanOrNull ?: false,
        )
    }

    private fun find(node: AccessibilityNodeInfo, selector: SemanticSelector): AccessibilityNodeInfo? {
        if (selector.matches(node.toSemanticNode())) return node
        for (index in 0 until node.childCount) {
            val match = node.getChild(index)?.let { find(it, selector) }
            if (match != null) return match
        }
        return null
    }

    private fun click(node: AccessibilityNodeInfo): Boolean {
        var target: AccessibilityNodeInfo? = node
        while (target != null) {
            if (target.isClickable && target.performAction(AccessibilityNodeInfo.ACTION_CLICK)) return true
            target = target.parent
        }
        return false
    }

    private fun detectDangerousPage(): String? {
        val root = rootInActiveWindow ?: return "UNKNOWN_PAGE"
        val visible = buildString { collectText(root, this) }
        return when {
            CAPTCHA_MARKERS.any(visible::contains) -> "CAPTCHA"
            LOGIN_MARKERS.any(visible::contains) -> "LOGIN_REQUIRED"
            else -> null
        }
    }

    private fun collectText(node: AccessibilityNodeInfo, output: StringBuilder) {
        node.text?.let { output.append(it).append('\n') }
        node.contentDescription?.let { output.append(it).append('\n') }
        for (index in 0 until node.childCount) node.getChild(index)?.let { collectText(it, output) }
    }

    private suspend fun capture(step: ExecutionStep): ActionOutcome {
        if (Build.VERSION.SDK_INT < 30) return takeover("SCREENSHOT_UNSUPPORTED", "Android 11 以下需人工接管")
        val bytes = suspendCancellableCoroutine<ByteArray?> { continuation ->
            takeScreenshot(
                Display.DEFAULT_DISPLAY,
                mainExecutor,
                object : TakeScreenshotCallback {
                    override fun onSuccess(result: ScreenshotResult) {
                        val hardware = Bitmap.wrapHardwareBuffer(result.hardwareBuffer, result.colorSpace)
                        val bitmap = hardware?.copy(Bitmap.Config.ARGB_8888, false)
                        result.hardwareBuffer.close()
                        val scaled = bitmap?.let { source ->
                            val scale = (720f / source.width).coerceAtMost(1f)
                            Bitmap.createScaledBitmap(
                                source,
                                (source.width * scale).toInt().coerceAtLeast(1),
                                (source.height * scale).toInt().coerceAtLeast(1),
                                true,
                            )
                        }
                        val output = ByteArrayOutputStream()
                        scaled?.compress(Bitmap.CompressFormat.JPEG, 68, output)
                        if (scaled !== bitmap) scaled?.recycle()
                        bitmap?.recycle()
                        continuation.resume(output.toByteArray().takeIf { it.isNotEmpty() })
                    }

                    override fun onFailure(errorCode: Int) = continuation.resume(null)
                },
            )
        } ?: return retry("SCREENSHOT_FAILED")
        val label = step.arguments["label"]?.jsonPrimitive?.contentOrNull ?: "Android screen"
        return ActionOutcome(
            StepStatus.SUCCEEDED,
            "OK",
            evidence = CapturedEvidence("image/jpeg", bytes, label),
        )
    }

    private fun AccessibilityNodeInfo.toSemanticNode() = SemanticNode(
        text = text?.toString(),
        contentDescription = contentDescription?.toString(),
        viewId = viewIdResourceName,
        enabled = isEnabled,
        clickable = isClickable,
    )

    private fun describe(node: AccessibilityNodeInfo): String =
        node.viewIdResourceName ?: node.text?.toString() ?: node.contentDescription?.toString().orEmpty()

    private fun success(observed: Map<String, String> = emptyMap()) =
        ActionOutcome(StepStatus.SUCCEEDED, "OK", observed = observed)

    private fun retry(code: String) = ActionOutcome(StepStatus.RETRYABLE, code)

    private fun takeover(code: String, message: String) =
        ActionOutcome(StepStatus.HUMAN_TAKEOVER, code, message)

    companion object {
        @Volatile
        var instance: AIShopAccessibilityService? = null
            private set
        private val FORBIDDEN_KEYS = setOf("x", "y", "coordinates", "shell", "script")
        private val CAPTCHA_MARKERS = setOf("验证码", "安全验证", "滑块验证", "请完成验证")
        private val LOGIN_MARKERS = setOf("重新登录", "登录已失效", "账号登录")

        val executor = ActionExecutor { step ->
            instance?.execute(step)
                ?: ActionOutcome(StepStatus.HUMAN_TAKEOVER, "ACCESSIBILITY_DISABLED", "请启用无障碍服务")
        }
    }
}
