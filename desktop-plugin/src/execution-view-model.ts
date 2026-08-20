import type { AuditEvent, DemoRunResult, TaskEventEnvelope } from './types'

export interface TimelineItem {
  id: string
  at: string
  label: string
  detail: string
  kind: 'task' | 'execution' | 'warning'
}

export interface EvidenceItem {
  evidenceId: string
  label: string
  source: string
  mediaType: string
  sha256: string
  url: string
}

export function buildExecutionViewModel(
  run: DemoRunResult,
  liveTimeline: AuditEvent[] = run.timeline,
) {
  const taskItems = run.task_events.map(taskEventItem)
  const executionItems = liveTimeline.map(event => ({
    id: event.event_id,
    at: event.created_at,
    label: event.event_type,
    detail: executionDetail(event),
    kind: event.event_type.includes('EXPIRED') ? 'warning' as const : 'execution' as const,
  }))
  const evidence = liveTimeline
    .filter(event => event.event_type === 'EVIDENCE_STORED')
    .map(event => {
      const evidenceId = String(event.payload.evidence_id ?? '')
      return {
        evidenceId,
        label: String(event.payload.label ?? '执行证据'),
        source: String(event.payload.source ?? run.mode),
        mediaType: String(event.payload.media_type ?? ''),
        sha256: String(event.payload.sha256 ?? ''),
        url: `/api/plugins/aishop/evidence/${encodeURIComponent(evidenceId)}`,
      }
    })
  return {
    modeLabel: run.mode === 'SIMULATED' ? '确定性模拟' : '真实设备',
    isSimulated: run.mode === 'SIMULATED',
    timeline: [...taskItems, ...executionItems].sort(
      (left, right) => left.at.localeCompare(right.at) || left.id.localeCompare(right.id),
    ),
    evidence,
  }
}

function taskEventItem(event: TaskEventEnvelope): TimelineItem {
  return {
    id: event.event_id,
    at: event.created_at,
    label: event.to_state,
    detail: event.reason,
    kind: event.to_state === 'HUMAN_TAKEOVER' || event.to_state === 'RETRY_WAIT'
      ? 'warning'
      : 'task',
  }
}

function executionDetail(event: AuditEvent): string {
  if (event.event_type === 'STEP_RESULT') {
    return `${String(event.payload.step_id ?? '')} · ${String(event.payload.status ?? '')}`
  }
  if (event.event_type === 'EVIDENCE_STORED') {
    return `${String(event.payload.source ?? '')} · ${String(event.payload.label ?? '')}`
  }
  return event.actor
}
