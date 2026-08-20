import type {
  DeviceCommand,
  DeviceCommandType,
  PairingSession,
  TaskEnvelope,
  WorkbenchSummary,
  AuditEvent,
  ApprovalEnvelope,
  DemoFlowSummary,
  DemoMode,
  DemoRunResult,
  DiagnosticsEnvelope,
  WorkflowRunEnvelope,
} from './types'


export interface PluginRestOptions {
  method?: string
  body?: unknown
  headers?: Record<string, string>
}

export type PluginRest = <T>(path: string, options?: PluginRestOptions) => Promise<T>

export function createApi(rest: PluginRest, operatorToken: () => string = () => '') {
  const authorized: PluginRest = (path, options = {}) => rest(path, {
    ...options,
    headers: {
      ...options.headers,
      'X-AIShop-Operator-Token': operatorToken(),
    },
  })
  return {
    getWorkbench: () => authorized<WorkbenchSummary>('/workbench'),
    getDiagnostics: () => authorized<DiagnosticsEnvelope>('/diagnostics'),
    createPairingSession: () => authorized<PairingSession>('/devices/pairing-sessions', {
      method: 'POST',
    }),
    sendDeviceCommand: (deviceId: string, type: DeviceCommandType, reason: string) =>
      authorized<DeviceCommand>(`/devices/${encodeURIComponent(deviceId)}/commands`, {
        method: 'POST',
        body: { type, reason },
      }),
    stopAll: (reason: string) =>
      authorized<TaskEnvelope[]>('/stop-all', {
        method: 'POST',
        body: { reason },
      }),
    listDemoFlows: () => authorized<DemoFlowSummary[]>('/demo/flows'),
    runDemoFlow: (flowId: string, mode: DemoMode, fault = 'none') =>
      authorized<DemoRunResult>(`/demo/flows/${encodeURIComponent(flowId)}/run`, {
        method: 'POST',
        body: { mode, fault },
      }),
    getTimeline: (taskId: string) =>
      authorized<AuditEvent[]>(`/tasks/${encodeURIComponent(taskId)}/timeline`),
    getTask: (taskId: string) =>
      authorized<TaskEnvelope>(`/tasks/${encodeURIComponent(taskId)}`),
    getExecutionJob: (jobId: string) =>
      authorized<DemoRunResult['job']>(`/execution/jobs/${encodeURIComponent(jobId)}`),
    getEvidenceData: (evidenceId: string) => authorized<{
      evidence_id: string
      media_type: string
      sha256: string
      content_base64: string
    }>(`/evidence/${encodeURIComponent(evidenceId)}/data`),
    retryTask: (taskId: string) =>
      authorized<TaskEnvelope>(`/tasks/${encodeURIComponent(taskId)}/retry`, { method: 'POST' }),
    reconcileWorkflow: (runId: string) =>
      authorized<WorkflowRunEnvelope>(`/workflow-runs/${encodeURIComponent(runId)}/reconcile`, {
        method: 'POST',
      }),
    decideApproval: (approvalId: string, approved: boolean) =>
      authorized<ApprovalEnvelope & { task?: TaskEnvelope; job?: DemoRunResult['job'] }>(
        `/approvals/${encodeURIComponent(approvalId)}/decision`,
        { method: 'POST', body: { approved } },
      ),
  }
}
