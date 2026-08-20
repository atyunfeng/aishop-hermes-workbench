import {
  Badge,
  Button,
  ConfirmDialog,
  EmptyState,
  ROUTES_AREA,
  SIDEBAR_NAV_AREA,
  STATUSBAR_AREAS,
  useQuery,
  useQueryClient,
  type HermesPlugin,
  type PluginContext,
} from '@hermes/plugin-sdk'
import { useState } from 'react'

import { createApi } from './api'
import { buildDeviceViewModels } from './device-view-model'
import { buildExecutionViewModel } from './execution-view-model'
import type {
  DemoFlowSummary,
  DemoMode,
  DemoRunResult,
  DeviceCommandType,
  DeviceEnvelope,
  TaskEnvelope,
} from './types'
import {
  approvalConfirmation,
  buildWorkbenchViewModel,
  filterTasks,
  resolveActiveRun,
} from './view-model'


type Api = ReturnType<typeof createApi>

const WORKBENCH_QUERY_KEY = ['aishop', 'workbench'] as const
const SOURCE_URL = 'https://github.com/atyunfeng/aishop-hermes-workbench'

function StateBadge({ task }: { task: TaskEnvelope }) {
  const variant = task.state === 'FAILED'
    ? 'destructive'
    : task.state === 'SUCCEEDED'
      ? 'muted'
      : task.state === 'WAITING_APPROVAL'
        ? 'warn'
        : 'default'
  return <Badge variant={variant}>{task.state}</Badge>
}

function WorkbenchPage({ api, onClearToken }: { api: Api; onClearToken?: () => void }) {
  const [stopDialogOpen, setStopDialogOpen] = useState(false)
  const [demoMode, setDemoMode] = useState<DemoMode>('SIMULATED')
  const [activeRun, setActiveRun] = useState<DemoRunResult | null>(null)
  const [runningFlowId, setRunningFlowId] = useState<string | null>(null)
  const [taskSearch, setTaskSearch] = useState('')
  const [taskFilter, setTaskFilter] = useState('ALL')
  const [approvalDecision, setApprovalDecision] = useState<null | {
    approval: import('./types').ApprovalEnvelope
    approved: boolean
  }>(null)
  const queryClient = useQueryClient()
  const query = useQuery({
    queryKey: WORKBENCH_QUERY_KEY,
    queryFn: api.getWorkbench,
    refetchInterval: 3000,
  })
  const demoFlows = useQuery({
    queryKey: ['aishop', 'demo-flows'],
    queryFn: api.listDemoFlows,
  })
  const diagnostics = useQuery({
    queryKey: ['aishop', 'diagnostics'],
    queryFn: api.getDiagnostics,
    refetchInterval: 10000,
  })
  const liveTimeline = useQuery({
    queryKey: ['aishop', 'timeline', activeRun?.task.task_id ?? 'none'],
    queryFn: () => activeRun ? api.getTimeline(activeRun.task.task_id) : Promise.resolve([]),
    refetchInterval: activeRun ? 2000 : undefined,
  })
  const liveTask = useQuery({
    queryKey: ['aishop', 'task', activeRun?.task.task_id ?? 'none'],
    queryFn: () => activeRun ? api.getTask(activeRun.task.task_id) : Promise.resolve(null),
    refetchInterval: activeRun ? 2000 : undefined,
  })
  const liveJob = useQuery({
    queryKey: ['aishop', 'job', activeRun?.job.job_id ?? 'none'],
    queryFn: () => activeRun ? api.getExecutionJob(activeRun.job.job_id) : Promise.resolve(null),
    refetchInterval: activeRun ? 2000 : undefined,
  })
  const liveWorkflow = useQuery({
    queryKey: ['aishop', 'workflow-run', activeRun?.workflow_run?.run_id ?? 'none'],
    queryFn: () => activeRun?.workflow_run && activeRun.mode === 'DEVICE'
      ? api.reconcileWorkflow(activeRun.workflow_run.run_id)
      : Promise.resolve(activeRun?.workflow_run),
    refetchInterval: activeRun?.workflow_run && activeRun.mode === 'DEVICE' ? 2000 : undefined,
  })

  if (query.isLoading) {
    return <EmptyState title="正在连接 AI 员工作台" description="读取本地任务状态…" />
  }
  if (!query.data || query.error) {
    return <EmptyState title="工作台暂不可用" description="请检查 AIShop 插件后端。" />
  }

  const viewModel = buildWorkbenchViewModel(query.data)
  return (
    <main className="flex h-full flex-col gap-4 overflow-auto p-5 text-sm">
      <header className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-lg font-semibold">AI 员工作台</h1>
          <p className="mt-1 text-xs text-(--ui-text-tertiary)">
            Hermes 本地任务指挥舱 · 3 秒自动刷新
          </p>
        </div>
        <div className="flex gap-2">
          {onClearToken ? (
            <Button variant="outline" onClick={onClearToken}>重新认证</Button>
          ) : null}
          <Button variant="destructive" onClick={() => setStopDialogOpen(true)}>
            全部停止
          </Button>
        </div>
      </header>

      <section className="grid grid-cols-4 gap-3">
        <Metric label="活跃任务" value={viewModel.activeCount} />
        <Metric label="等待审批" value={query.data.approvals.length} />
        <Metric label="在线手机员工" value={query.data.devices.filter(device => device.online).length} />
        <Metric
          label="证据占用 MiB"
          value={Math.round((diagnostics.data?.evidence_bytes ?? 0) / 1024 / 1024)}
        />
      </section>

      <DemoLauncher
        flows={demoFlows.data ?? []}
        mode={demoMode}
        runningFlowId={runningFlowId}
        onModeChange={setDemoMode}
        onRun={async flowId => {
          setRunningFlowId(flowId)
          try {
            const result = await api.runDemoFlow(flowId, demoMode)
            setActiveRun(result)
            await queryClient.invalidateQueries({ queryKey: WORKBENCH_QUERY_KEY })
          } finally {
            setRunningFlowId(null)
          }
        }}
      />

      {activeRun ? (
        <ExecutionPanel
          api={api}
          run={resolveActiveRun(
            {
              ...activeRun,
              workflow_run: liveWorkflow.data ?? activeRun.workflow_run,
            },
            liveTask.data,
            liveJob.data,
          )}
          liveTimeline={liveTimeline.data}
        />
      ) : null}

      {query.data.approvals.length > 0 ? (
        <section className="rounded-md border border-(--ui-warning) p-4">
          <h2 className="mb-3 font-medium">等待人工审批</h2>
          <div className="flex flex-col gap-2">
            {query.data.approvals.map(approval => (
              <article
                key={approval.approval_id}
                className="flex items-center justify-between gap-3 rounded border border-(--ui-stroke-secondary) p-3"
              >
                <div>
                  <div className="font-medium">高风险动作：{approval.action}</div>
                  <div className="mt-1 text-xs text-(--ui-text-tertiary)">
                    任务 {approval.task_id} · 目标 {String(approval.scope.target ?? '未指定')}
                    {' · '}流程 {String(approval.scope.workflow_id ?? '未指定')}
                    {' · '}截止 {new Date(approval.expires_at).toLocaleTimeString()}
                  </div>
                </div>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    onClick={() => setApprovalDecision({ approval, approved: false })}
                  >
                    拒绝
                  </Button>
                  <Button
                    variant="destructive"
                    onClick={() => setApprovalDecision({ approval, approved: true })}
                  >
                    限定批准一次
                  </Button>
                </div>
              </article>
            ))}
          </div>
        </section>
      ) : null}

      <section className="grid min-h-0 flex-1 grid-cols-[minmax(0,2fr)_minmax(16rem,1fr)] gap-4">
        <div className="rounded-md border border-(--ui-stroke-secondary) p-4">
          <div className="mb-3 flex items-center justify-between gap-2">
            <h2 className="font-medium">最近任务</h2>
            <div className="flex gap-2">
              <input
                aria-label="搜索任务"
                className="rounded border border-(--ui-stroke-secondary) bg-transparent px-2 py-1 text-xs"
                placeholder="标题或来源"
                value={taskSearch}
                onChange={event => setTaskSearch(event.target.value)}
              />
              <select
                aria-label="筛选任务状态"
                className="rounded border border-(--ui-stroke-secondary) bg-transparent px-2 py-1 text-xs"
                value={taskFilter}
                onChange={event => setTaskFilter(event.target.value)}
              >
                <option value="ALL">全部</option>
                <option value="ACTIVE">进行中</option>
                <option value="FAILED">失败/接管</option>
                <option value="SUCCEEDED">已完成</option>
              </select>
            </div>
          </div>
          {viewModel.tasks.length === 0 ? (
            <EmptyState title="暂无任务" description="通过 Hermes 指令创建第一个任务。" />
          ) : (
            <div className="flex flex-col gap-2">
              {filterTasks(viewModel.tasks, taskSearch, taskFilter).map(task => (
                <article
                  key={task.task_id}
                  className="flex items-center justify-between gap-3 rounded border border-(--ui-stroke-secondary) px-3 py-2"
                >
                  <div className="min-w-0">
                    <div className="truncate font-medium">{task.title}</div>
                    <div className="mt-1 text-xs text-(--ui-text-tertiary)">
                      {task.source} · v{task.version}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {(task.state === 'RETRY_WAIT' || task.state === 'HUMAN_TAKEOVER') ? (
                      <Button
                        variant="outline"
                        onClick={async () => {
                          await api.retryTask(task.task_id)
                          await queryClient.invalidateQueries({ queryKey: WORKBENCH_QUERY_KEY })
                        }}
                      >
                        安全重试
                      </Button>
                    ) : null}
                    <StateBadge task={task} />
                  </div>
                </article>
              ))}
            </div>
          )}
        </div>

        <div className="rounded-md border border-(--ui-stroke-secondary) p-4">
          <DeviceWall api={api} devices={query.data.devices} />
        </div>
      </section>

      <footer className="flex flex-wrap items-center justify-between gap-2 border-t border-(--ui-stroke-secondary) pt-3 text-xs text-(--ui-text-tertiary)">
        <span>AIShop v0.1.0-alpha · AGPLv3 · 按原样提供，不附带担保</span>
        <a
          className="font-medium text-(--ui-text-primary) underline underline-offset-4 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
          href={SOURCE_URL}
          rel="noreferrer"
          target="_blank"
        >
          查看完整源码
        </a>
      </footer>

      <ConfirmDialog
        open={stopDialogOpen}
        onClose={() => setStopDialogOpen(false)}
        onConfirm={async () => {
          await api.stopAll('operator emergency stop')
          await queryClient.invalidateQueries({ queryKey: WORKBENCH_QUERY_KEY })
        }}
        title="停止全部 AIShop 任务？"
        description="所有未完成任务都会进入 CANCELLED；已经完成的任务不会改变。"
        confirmLabel="确认全部停止"
        destructive
      />
      <ConfirmDialog
        open={approvalDecision !== null}
        onClose={() => setApprovalDecision(null)}
        onConfirm={async () => {
          if (!approvalDecision) return
          await api.decideApproval(
            approvalDecision.approval.approval_id,
            approvalDecision.approved,
          )
          setApprovalDecision(null)
          await queryClient.invalidateQueries({ queryKey: WORKBENCH_QUERY_KEY })
        }}
        title={approvalDecision?.approved ? '批准这个精确范围的动作？' : '拒绝这个动作？'}
        description={approvalDecision
          ? approvalConfirmation(approvalDecision.approval)
          : undefined}
        confirmLabel={approvalDecision?.approved ? '限定批准并恢复作业' : '确认拒绝'}
        destructive={approvalDecision?.approved === true}
      />
    </main>
  )
}

function DemoLauncher({
  flows,
  mode,
  runningFlowId,
  onModeChange,
  onRun,
}: {
  flows: DemoFlowSummary[]
  mode: DemoMode
  runningFlowId: string | null
  onModeChange: (mode: DemoMode) => void
  onRun: (flowId: string) => Promise<void>
}) {
  return (
    <section className="rounded-md border border-(--ui-stroke-secondary) p-4">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <h2 className="font-medium">主演示流程</h2>
          <p className="mt-1 text-xs text-(--ui-text-tertiary)">
            模拟与真机使用同一 App Skill 和证据协议；模拟结果始终明确标注。
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant={mode === 'SIMULATED' ? 'default' : 'outline'}
            onClick={() => onModeChange('SIMULATED')}
          >
            确定性模拟
          </Button>
          <Button
            variant={mode === 'DEVICE' ? 'default' : 'outline'}
            onClick={() => onModeChange('DEVICE')}
          >
            真实手机
          </Button>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2">
        {flows.map(flow => (
          <article
            key={flow.flow_id}
            className="flex items-center justify-between gap-3 rounded border border-(--ui-stroke-secondary) p-3"
          >
            <div>
              <div className="font-medium">{flow.name}</div>
              <div className="mt-1 text-xs text-(--ui-text-tertiary)">{flow.source}</div>
            </div>
            <Button
              variant="outline"
              disabled={runningFlowId !== null}
              onClick={() => void onRun(flow.flow_id)}
            >
              {runningFlowId === flow.flow_id ? '运行中…' : '运行'}
            </Button>
          </article>
        ))}
      </div>
    </section>
  )
}

function ExecutionPanel({
  api,
  run,
  liveTimeline,
}: {
  api: Api
  run: DemoRunResult
  liveTimeline?: DemoRunResult['timeline']
}) {
  const viewModel = buildExecutionViewModel(run, liveTimeline ?? run.timeline)
  return (
    <section className="grid grid-cols-[minmax(0,3fr)_minmax(14rem,2fr)] gap-4 rounded-md border border-(--ui-stroke-secondary) p-4">
      <div>
        <div className="mb-3 flex items-center gap-2">
          <h2 className="font-medium">{run.flow_name}</h2>
          <Badge variant={viewModel.isSimulated ? 'warn' : 'default'}>{viewModel.modeLabel}</Badge>
          <Badge variant="muted">{run.task.state}</Badge>
        </div>
        {viewModel.isSimulated ? (
          <div className="mb-3 rounded border border-(--ui-warning) p-2 text-xs">
            这是确定性模拟回放，没有声称操作真实平台账号。
          </div>
        ) : null}
        {run.workflow_run ? (
          <div className="mb-3 rounded border border-(--ui-stroke-secondary) p-2 text-xs">
            <div className="font-medium">多手机协作 · {run.workflow_run.status}</div>
            <div className="mt-1 text-(--ui-text-tertiary)">
              {run.workflow_run.nodes.map(node => `${node.name} ${node.status}`).join(' · ')}
            </div>
          </div>
        ) : null}
        <div className="flex max-h-64 flex-col gap-2 overflow-auto">
          {viewModel.timeline.map(item => (
            <article key={item.id} className="rounded border border-(--ui-stroke-secondary) p-2">
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium">{item.label}</span>
                <span className="text-xs text-(--ui-text-tertiary)">
                  {new Date(item.at).toLocaleTimeString()}
                </span>
              </div>
              <div className="mt-1 text-xs text-(--ui-text-tertiary)">{item.detail}</div>
            </article>
          ))}
        </div>
      </div>
      <div>
        <h3 className="mb-3 font-medium">证据与手机画面</h3>
        {viewModel.evidence.length === 0 ? (
          <EmptyState title="等待证据" description="真实手机执行后会在这里显示截图和回执。" />
        ) : (
          <div className="flex max-h-72 flex-col gap-2 overflow-auto">
            {viewModel.evidence.map(item => (
              <article key={item.evidenceId} className="rounded border border-(--ui-stroke-secondary) p-2">
                {item.mediaType.startsWith('image/') ? (
                  <EvidencePreview api={api} evidenceId={item.evidenceId} label={item.label} />
                ) : null}
                <div className="text-xs font-medium">{item.label}</div>
                <div className="mt-1 text-xs text-(--ui-text-tertiary)">
                  {item.source} · {item.sha256.slice(0, 12)}
                </div>
              </article>
            ))}
          </div>
        )}
      </div>
    </section>
  )
}

function EvidencePreview({ api, evidenceId, label }: {
  api: Api
  evidenceId: string
  label: string
}) {
  const query = useQuery({
    queryKey: ['aishop', 'evidence-data', evidenceId],
    queryFn: () => api.getEvidenceData(evidenceId),
  })
  if (!query.data) return <div className="mb-2 text-xs text-(--ui-text-tertiary)">读取证据…</div>
  return (
    <img
      className="mb-2 max-h-48 w-full rounded object-contain"
      src={`data:${query.data.media_type};base64,${query.data.content_base64}`}
      alt={label}
    />
  )
}

function DeviceWall({ api, devices }: { api: Api; devices: DeviceEnvelope[] }) {
  const queryClient = useQueryClient()
  const [pairingSession, setPairingSession] = useState<null | {
    pairing_code: string
    expires_at: string
  }>(null)
  const [confirmation, setConfirmation] = useState<null | {
    device: DeviceEnvelope
    type: DeviceCommandType
  }>(null)
  const viewModels = buildDeviceViewModels(devices)

  async function sendCommand(device: DeviceEnvelope, type: DeviceCommandType) {
    const reasons: Record<DeviceCommandType, string> = {
      PAUSE: 'operator requested pause',
      RESUME: 'operator released pause or takeover',
      TAKEOVER: 'operator requested manual takeover',
      STOP: 'operator requested device stop',
    }
    await api.sendDeviceCommand(device.device_id, type, reasons[type])
    await queryClient.invalidateQueries({ queryKey: WORKBENCH_QUERY_KEY })
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        <h2 className="font-medium">手机员工</h2>
        <Button
          variant="outline"
          onClick={async () => setPairingSession(await api.createPairingSession())}
        >
          生成配对码
        </Button>
      </div>

      {pairingSession ? (
        <div className="rounded border border-(--ui-accent) p-3 text-center">
          <div className="text-xs text-(--ui-text-tertiary)">5 分钟内在手机输入</div>
          <div className="mt-1 font-mono text-2xl tracking-[0.25em]">{pairingSession.pairing_code}</div>
          <div className="mt-1 text-xs text-(--ui-text-tertiary)">
            过期时间 {new Date(pairingSession.expires_at).toLocaleTimeString()}
          </div>
        </div>
      ) : null}

      {viewModels.length === 0 ? (
        <EmptyState title="尚未连接设备" description="生成配对码后，在 Android Worker 中完成连接。" />
      ) : (
        <div className="flex flex-col gap-2">
          {viewModels.map(({ device, statusLabel, permissionWarnings, actions }) => (
            <article key={device.device_id} className="rounded border border-(--ui-stroke-secondary) p-3">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="truncate font-medium">{device.display_name}</div>
                  <div className="mt-1 text-xs text-(--ui-text-tertiary)">
                    {device.battery_percent === null ? '电量未知' : `电量 ${device.battery_percent}%`}
                    {' · '}v{device.app_version}
                  </div>
                </div>
                <Badge variant={device.online ? 'default' : 'muted'}>
                  {device.online ? statusLabel : '离线'}
                </Badge>
              </div>

              {permissionWarnings.length > 0 ? (
                <div className="mt-2 text-xs text-(--ui-text-tertiary)">
                  {permissionWarnings.join(' · ')}
                </div>
              ) : null}
              {device.pending_command ? (
                <div className="mt-2 text-xs text-(--ui-accent)">
                  等待手机确认：{device.pending_command.type}
                </div>
              ) : null}

              {actions.length > 0 ? (
                <div className="mt-3 flex flex-wrap gap-2">
                  {actions.map(type => (
                    <Button
                      key={type}
                      variant={type === 'STOP' ? 'destructive' : 'outline'}
                      onClick={() => {
                        if (type === 'STOP' || type === 'TAKEOVER') {
                          setConfirmation({ device, type })
                        } else {
                          void sendCommand(device, type)
                        }
                      }}
                    >
                      {deviceActionLabel(type)}
                    </Button>
                  ))}
                </div>
              ) : null}
            </article>
          ))}
        </div>
      )}

      <ConfirmDialog
        open={confirmation !== null}
        onClose={() => setConfirmation(null)}
        onConfirm={async () => {
          if (confirmation) await sendCommand(confirmation.device, confirmation.type)
        }}
        title={confirmation?.type === 'STOP' ? '停止这台手机员工？' : '进入人工接管？'}
        description="命令会持续投递，直到 Android Worker 明确确认。"
        confirmLabel={confirmation?.type === 'STOP' ? '确认停止' : '确认接管'}
        destructive={confirmation?.type === 'STOP'}
      />
    </div>
  )
}

function deviceActionLabel(type: DeviceCommandType): string {
  return { PAUSE: '暂停', RESUME: '继续', TAKEOVER: '接管', STOP: '停止' }[type]
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md border border-(--ui-stroke-secondary) p-3">
      <div className="text-xs text-(--ui-text-tertiary)">{label}</div>
      <div className="mt-1 text-2xl font-semibold">{value}</div>
    </div>
  )
}

function WorkbenchStatus({ api }: { api: Api }) {
  const { data } = useQuery({
    queryKey: WORKBENCH_QUERY_KEY,
    queryFn: api.getWorkbench,
    refetchInterval: 3000,
  })
  const activeCount = data ? buildWorkbenchViewModel(data).activeCount : 0
  return <span className="text-xs">AIShop {activeCount}</span>
}

function WorkbenchRoot({ rest }: { rest: PluginContext['rest'] }) {
  const [token, setToken] = useState(() => localStorage.getItem('aishop.operatorToken') ?? '')
  const [draft, setDraft] = useState(token)
  if (!token) {
    return (
      <main className="flex h-full items-center justify-center p-6">
        <section className="w-full max-w-lg rounded-md border border-(--ui-stroke-secondary) p-5">
          <h1 className="text-lg font-semibold">连接 AIShop 本地操作员</h1>
          <p className="mt-2 text-xs text-(--ui-text-tertiary)">
            输入 AISHOP_OPERATOR_TOKEN，或数据目录 operator.token 文件中的令牌。
          </p>
          <input
            aria-label="操作员令牌"
            className="mt-4 w-full rounded border border-(--ui-stroke-secondary) bg-transparent px-3 py-2"
            type="password"
            value={draft}
            onChange={event => setDraft(event.target.value)}
          />
          <Button
            className="mt-3"
            disabled={!draft.trim()}
            onClick={() => {
              const value = draft.trim()
              localStorage.setItem('aishop.operatorToken', value)
              setToken(value)
            }}
          >
            连接
          </Button>
        </section>
      </main>
    )
  }
  return (
    <WorkbenchPage
      api={createApi(rest, () => token)}
      onClearToken={() => {
        localStorage.removeItem('aishop.operatorToken')
        setToken('')
        setDraft('')
      }}
    />
  )
}

function RegisteredWorkbenchStatus({ rest }: { rest: PluginContext['rest'] }) {
  const token = localStorage.getItem('aishop.operatorToken') ?? ''
  if (!token) return <span className="text-xs">AIShop 未认证</span>
  return <WorkbenchStatus api={createApi(rest, () => token)} />
}

const plugin: HermesPlugin = {
  id: 'aishop',
  name: 'AIShop',
  description: '本地电商 AI 员工任务指挥舱',
  defaultEnabled: false,
  register(ctx: PluginContext) {
    ctx.registerMany([
      {
        id: 'workbench-page',
        area: ROUTES_AREA,
        data: { path: '/aishop' },
        render: () => <WorkbenchRoot rest={ctx.rest} />,
      },
      {
        id: 'workbench-nav',
        area: SIDEBAR_NAV_AREA,
        data: { path: '/aishop', label: 'AI 员工作台', codicon: 'dashboard' },
      },
      {
        id: 'workbench-status',
        area: STATUSBAR_AREAS.right,
        order: 120,
        render: () => <RegisteredWorkbenchStatus rest={ctx.rest} />,
      },
    ])
  },
}

export default plugin
