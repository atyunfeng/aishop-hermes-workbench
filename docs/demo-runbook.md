# AIShop Phase 1 演示手册

## 演示前 15 分钟

1. 在 Windows 11 解压 `AIShop-Hermes-Workbench-phase1.zip`，运行 `scripts/preflight.ps1`，处理全部 `required_failures`。
2. 运行 `scripts/install-dev.ps1`，确认 `hermes plugins doctor` 通过，再手动启用 AIShop Python 与 Desktop 插件。
3. 手机与 Windows 处于可信专用局域网；防火墙只放行实际 Hermes 端口，不对公网开放。
4. 设置或读取本地 `operator.token`，在桌面工作台完成操作员认证；安装 `artifacts/aishop-worker-debug.apk`，生成 6 位配对码并完成配对。
5. 手机手动启用“AIShop 手机员工”无障碍服务和“AIShop 消息监听”；需要画面证据时点击“授权画面”并接受 Android 系统 MediaProjection 弹窗。
6. 只登录测试账号并核对白名单联系人：`AIShop 测试客户`、`AIShop 售后测试客户`、`AIShop 微信测试客户`、`AIShop 企业微信测试群`。
7. 在工作台确认通知、Accessibility、画面采集、目标 App 安装状态均就绪。

## 3～5 分钟主演示

### 1. 千牛 24 小时客服接管

选择“真实手机”，运行“千牛 24 小时客服接管”。讲解 Hermes 生成结构化计划、设备获得 30 秒短租约、手机按语义节点打开白名单会话、填写回复、发送、验证回显并采集截图。演示中点击“暂停”，确认 5 秒内停止新动作，再点击“继续”。

### 2. 抖店/飞鸽图片售后

运行“抖店/飞鸽图片售后”。说明系统只发送售后处理说明，不自动执行退款或退货。任何资金动作都会进入审批，当前 App Skill 不暴露绕过入口。

### 3. 微信私域服务

运行“微信客户私域服务”。展示测试订单快照生成个性化回复、截图证据和任务时间线。点击“人工接管”，确认手机停止自动动作且其他设备不受影响。

### 4. 企业微信指挥多手机

运行“企业微信指挥多手机协作”。展示持久化父子工作流中千牛与抖店两个并行节点、企业微信依赖汇总节点，以及最终完成/部分成功/人工接管摘要。第一阶段的演示数据是本地快照，不声称已连接 ERP。

## 确定性演示模式

平台账号、网络或 App 页面临时不可用时切换“确定性模拟”。模拟模式使用真实 App Skill 编译器、任务状态机、租约结果和证据模型，但不操作外部平台；页面会持续显示“确定性模拟”和 `SIMULATED` 证据，演示人员不得口头称为真机成功。

命令行回归：

```powershell
.\.venv\Scripts\python.exe .\scripts\run-demo.py --flow all --mode simulated
```

## 异常演练

- 断网：租约 30 秒后过期，任务进入 `RETRY_WAIT`，兼容设备可从最后成功步骤继续。
- 验证码、登录失效、未知页面：立即进入 `HUMAN_TAKEOVER`，不得盲点或绕过。
- 全局急停：桌面点击“全部停止”并二次确认；所有非终态任务进入 `CANCELLED`。
- 单机接管：设备卡片点击“接管”并二次确认；只影响该手机。

## 收尾与回滚

使用 `scripts/export-local-data.py` 导出脱敏元数据后停止手机服务、停止 MediaProjection、禁用插件。插件数据位于 `$HERMES_HOME\plugins-data\aishop`，回滚插件时不要删除数据目录。运行 `hermes plugins disable aishop`，再将插件安装目录改名保留。
