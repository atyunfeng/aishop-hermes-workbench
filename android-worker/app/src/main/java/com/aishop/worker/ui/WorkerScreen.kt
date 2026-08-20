package com.aishop.worker.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.ui.unit.dp
import com.aishop.worker.R

private const val SOURCE_URL = "https://github.com/atyunfeng/aishop-hermes-workbench"

@Composable
fun WorkerScreen(
    state: WorkerUiState,
    onPair: (gatewayUrl: String, pairingCode: String, displayName: String) -> Unit,
    onStart: () -> Unit,
    onPause: () -> Unit,
    onResume: () -> Unit,
    onTakeover: () -> Unit,
    onStop: () -> Unit,
    onClearPairing: () -> Unit,
    onEnableAccessibility: () -> Unit,
    onEnableNotifications: () -> Unit,
    onOpenBatterySettings: () -> Unit,
    onAutoStartChange: (Boolean) -> Unit,
    onEnableScreenCapture: () -> Unit,
) {
    val uriHandler = LocalUriHandler.current
    MaterialTheme {
        Surface(modifier = Modifier.fillMaxSize()) {
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .verticalScroll(rememberScrollState())
                    .padding(20.dp),
                verticalArrangement = Arrangement.spacedBy(16.dp),
            ) {
                Text("AIShop 手机员工", style = MaterialTheme.typography.headlineSmall)
                Text("设备：${state.deviceId}", style = MaterialTheme.typography.bodySmall)
                if (state.paired) {
                    PairedWorker(
                        state,
                        onStart,
                        onPause,
                        onResume,
                        onTakeover,
                        onStop,
                        onClearPairing,
                        onEnableAccessibility,
                        onEnableNotifications,
                        onOpenBatterySettings,
                        onAutoStartChange,
                        onEnableScreenCapture,
                    )
                } else {
                    PairingForm(state, onPair)
                }
                Text(
                    stringResource(R.string.open_source_notice),
                    style = MaterialTheme.typography.bodySmall,
                )
                TextButton(onClick = { uriHandler.openUri(SOURCE_URL) }) {
                    Text(stringResource(R.string.open_source_link))
                }
            }
        }
    }
}

@Composable
private fun PairingForm(
    state: WorkerUiState,
    onPair: (String, String, String) -> Unit,
) {
    var gatewayUrl by remember { mutableStateOf("http://192.168.1.20:8000/api/plugins/aishop") }
    var pairingCode by remember { mutableStateOf("") }
    var displayName by remember { mutableStateOf("9号 AI 手机员工") }
    Text("连接本地 Hermes 工作台")
    OutlinedTextField(
        value = gatewayUrl,
        onValueChange = { gatewayUrl = it },
        label = { Text("插件 API 地址") },
        modifier = Modifier.fillMaxWidth(),
        singleLine = true,
    )
    OutlinedTextField(
        value = pairingCode,
        onValueChange = { pairingCode = it.filter(Char::isDigit).take(6) },
        label = { Text("6 位配对码") },
        modifier = Modifier.fillMaxWidth(),
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
        singleLine = true,
    )
    OutlinedTextField(
        value = displayName,
        onValueChange = { displayName = it },
        label = { Text("手机员工名称") },
        modifier = Modifier.fillMaxWidth(),
        singleLine = true,
    )
    if (state.pairingInProgress) LinearProgressIndicator(modifier = Modifier.fillMaxWidth())
    state.errorMessage?.let { Text(it, color = MaterialTheme.colorScheme.error) }
    Button(
        onClick = { onPair(gatewayUrl, pairingCode, displayName) },
        enabled = !state.pairingInProgress && pairingCode.length == 6 && displayName.isNotBlank(),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Text("配对")
    }
    Text(
        "仅连接可信局域网。配对后需手动授权无障碍和画面预览；可随时暂停或接管。",
        style = MaterialTheme.typography.bodySmall,
    )
}

@Composable
private fun PairedWorker(
    state: WorkerUiState,
    onStart: () -> Unit,
    onPause: () -> Unit,
    onResume: () -> Unit,
    onTakeover: () -> Unit,
    onStop: () -> Unit,
    onClearPairing: () -> Unit,
    onEnableAccessibility: () -> Unit,
    onEnableNotifications: () -> Unit,
    onOpenBatterySettings: () -> Unit,
    onAutoStartChange: (Boolean) -> Unit,
    onEnableScreenCapture: () -> Unit,
) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text(state.displayName, style = MaterialTheme.typography.titleMedium)
            Text("状态：${state.workerState}")
            Text("工作台：${state.baseUrl}")
            Text("最近心跳：${state.lastHeartbeatAt ?: "尚未上报"}")
            Text("电量：${state.batteryPercent?.let { "$it%" } ?: "未知"}")
        }
    }
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            Text("权限与能力", style = MaterialTheme.typography.titleMedium)
            Readiness("通知权限", state.notificationsReady)
            Readiness("Accessibility 准备", state.accessibilityReady)
            Readiness("画面采集准备", state.screenCaptureReady)
            Text(
                "只执行版本化 App Skill 的语义动作；验证码、登录失效和未知页面会转人工。",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.error,
            )
        }
    }
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        OutlinedButton(onClick = onEnableAccessibility) { Text("启用无障碍") }
        OutlinedButton(onClick = onEnableNotifications) { Text("启用消息监听") }
        OutlinedButton(onClick = onEnableScreenCapture) { Text("授权画面") }
    }
    Row(
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Text("开机后恢复手机员工", modifier = Modifier.weight(1f))
        Switch(checked = state.autoStartEnabled, onCheckedChange = onAutoStartChange)
    }
    OutlinedButton(onClick = onOpenBatterySettings, modifier = Modifier.fillMaxWidth()) {
        Text("打开电池优化设置")
    }
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Button(onClick = onStart) { Text("启动") }
        OutlinedButton(onClick = onPause) { Text("暂停") }
        OutlinedButton(onClick = onResume) { Text("继续") }
    }
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        OutlinedButton(onClick = onTakeover) { Text("人工接管") }
        OutlinedButton(onClick = onStop) { Text("停止") }
    }
    OutlinedButton(onClick = onClearPairing, modifier = Modifier.fillMaxWidth()) {
        Text("清除配对")
    }
}

@Composable
private fun Readiness(label: String, ready: Boolean) {
    Text("$label：${if (ready) "已就绪" else "未就绪"}")
}
