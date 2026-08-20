import { describe, expect, it } from 'vitest'

import { buildExecutionViewModel } from './execution-view-model'
import type { DemoRunResult } from './types'

const run: DemoRunResult = {
  flow_id: 'we_chat_private_service',
  flow_name: '微信客户私域服务',
  mode: 'SIMULATED',
  fault: 'none',
  task: {
    task_id: 'task-1',
    idempotency_key: 'key',
    source: 'we-chat',
    title: 'reply',
    state: 'SUCCEEDED',
    version: 7,
    created_at: '2026-08-17T12:00:00Z',
    updated_at: '2026-08-17T12:00:04Z',
  },
  job: {
    job_id: 'job-1',
    task_id: 'task-1',
    app_skill_id: 'we-chat',
    skill_version: '1.0.0',
    status: 'SUCCEEDED',
    lease_id: null,
    device_id: null,
    lease_expires_at: null,
    mode: 'SIMULATED',
  },
  task_events: [{
    event_id: 'task-event',
    task_id: 'task-1',
    from_state: 'VERIFYING',
    to_state: 'SUCCEEDED',
    reason: 'verified',
    created_at: '2026-08-17T12:00:04Z',
    idempotency_key: 'succeeded',
  }],
  timeline: [{
    event_id: 'evidence-event',
    task_id: 'task-1',
    job_id: 'job-1',
    event_type: 'EVIDENCE_STORED',
    actor: 'SIMULATED',
    payload: {
      evidence_id: 'evidence 1',
      source: 'SIMULATED',
      media_type: 'text/plain',
      label: 'SIMULATED receipt',
      sha256: 'abc',
    },
    created_at: '2026-08-17T12:00:03Z',
  }],
}

describe('buildExecutionViewModel', () => {
  it('preserves simulated labelling and builds encoded evidence links', () => {
    const result = buildExecutionViewModel(run)
    expect(result.modeLabel).toBe('确定性模拟')
    expect(result.isSimulated).toBe(true)
    expect(result.evidence[0]).toMatchObject({
      source: 'SIMULATED',
      url: '/api/plugins/aishop/evidence/evidence%201',
    })
    expect(result.timeline.map(item => item.id)).toEqual(['evidence-event', 'task-event'])
  })
})
