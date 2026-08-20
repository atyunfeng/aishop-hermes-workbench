export type TaskState =
  | 'RECEIVED'
  | 'PLANNING'
  | 'WAITING_APPROVAL'
  | 'QUEUED'
  | 'ASSIGNED'
  | 'EXECUTING'
  | 'VERIFYING'
  | 'SUCCEEDED'
  | 'RETRY_WAIT'
  | 'HUMAN_TAKEOVER'
  | 'FAILED'
  | 'CANCELLED'

export interface TaskEnvelope {
  task_id: string
  idempotency_key: string
  source: string
  title: string
  state: TaskState
  version: number
  created_at: string
  updated_at: string
}

export type WorkerState = 'OFFLINE' | 'IDLE' | 'BUSY' | 'PAUSED' | 'TAKEOVER' | 'ERROR'
export type DeviceCommandType = 'PAUSE' | 'RESUME' | 'TAKEOVER' | 'STOP'

export interface DevicePermissions {
  notifications: boolean
  accessibility: boolean
  screen_capture: boolean
}

export interface InstalledApp {
  package_name: string
  version_name: string
}

export interface DeviceCommand {
  command_id: string
  type: DeviceCommandType
  reason: string
  created_at: string
}

export interface DeviceEnvelope {
  device_id: string
  display_name: string
  online: boolean
  worker_state: WorkerState
  app_version: string
  capabilities: string[]
  battery_percent: number | null
  permissions: DevicePermissions
  installed_apps: InstalledApp[]
  last_heartbeat_at: string | null
  pending_command: DeviceCommand | null
}

export interface PairingSession {
  pairing_code: string
  expires_at: string
}

export interface WorkbenchSummary {
  generated_at: string
  task_counts: Record<string, number>
  devices: DeviceEnvelope[]
  approvals: ApprovalEnvelope[]
  recent_tasks: TaskEnvelope[]
}

export interface DiagnosticsEnvelope {
  database_bytes: number
  evidence_bytes: number
  counts: Record<string, number>
  generated_at: string
}

export interface ApprovalEnvelope {
  approval_id: string
  task_id: string
  action: string
  scope: Record<string, unknown>
  status: string
  expires_at: string
  created_at: string
  decided_at: string | null
  used_at: string | null
}

export type DemoMode = 'SIMULATED' | 'DEVICE'

export interface DemoFlowSummary {
  flow_id: string
  name: string
  source: string
}

export interface ExecutionJobEnvelope {
  job_id: string
  task_id: string
  app_skill_id: string
  skill_version: string
  status: string
  lease_id: string | null
  device_id: string | null
  lease_expires_at: string | null
  mode: DemoMode
}

export interface AuditEvent {
  event_id: string
  task_id: string
  job_id: string | null
  event_type: string
  actor: string
  payload: Record<string, unknown>
  created_at: string
}

export interface TaskEventEnvelope {
  event_id: string
  task_id: string
  from_state: TaskState | null
  to_state: TaskState
  reason: string
  created_at: string
  idempotency_key: string
}

export interface DemoRunResult {
  flow_id: string
  flow_name: string
  mode: DemoMode
  fault: string
  task: TaskEnvelope
  job: ExecutionJobEnvelope
  task_events: TaskEventEnvelope[]
  timeline: AuditEvent[]
  workflow_run?: WorkflowRunEnvelope
}

export interface WorkflowNodeEnvelope {
  node_id: string
  name: string
  target: string
  dependencies: string[]
  status: string
  task_id: string | null
  job_id: string | null
  result: Record<string, unknown> | null
}

export interface WorkflowRunEnvelope {
  run_id: string
  parent_task_id: string
  status: string
  nodes: WorkflowNodeEnvelope[]
}
