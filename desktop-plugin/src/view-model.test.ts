import { describe, expect, it } from 'vitest'

import {
  approvalConfirmation,
  buildWorkbenchViewModel,
  filterTasks,
  resolveActiveRun,
} from './view-model'


describe('buildWorkbenchViewModel', () => {
  it('orders active tasks before terminal tasks', () => {
    const vm = buildWorkbenchViewModel({
      generated_at: '2026-08-17T00:00:00Z',
      task_counts: { SUCCEEDED: 1, EXECUTING: 1 },
      devices: [],
      approvals: [],
      recent_tasks: [
        {
          task_id: 'done',
          idempotency_key: 'done:1',
          source: 'demo',
          state: 'SUCCEEDED',
          version: 3,
          title: 'done',
          created_at: '2026-08-17T00:00:00Z',
          updated_at: '2026-08-17T00:02:00Z',
        },
        {
          task_id: 'run',
          idempotency_key: 'run:1',
          source: 'demo',
          state: 'EXECUTING',
          version: 2,
          title: 'run',
          created_at: '2026-08-17T00:01:00Z',
          updated_at: '2026-08-17T00:01:30Z',
        },
      ],
    })
    expect(vm.tasks.map(task => task.task_id)).toEqual(['run', 'done'])
    expect(vm.activeCount).toBe(1)
  })

  it('filters tasks and replaces stale active-run state', () => {
    const tasks = [
      {
        task_id: 'run', idempotency_key: 'run:1', source: '微信', state: 'EXECUTING' as const,
        version: 2, title: '回复客户', created_at: '2026-08-17T00:01:00Z',
        updated_at: '2026-08-17T00:01:30Z',
      },
      {
        task_id: 'done', idempotency_key: 'done:1', source: '抖店', state: 'SUCCEEDED' as const,
        version: 3, title: '完成', created_at: '2026-08-17T00:00:00Z',
        updated_at: '2026-08-17T00:02:00Z',
      },
    ]
    expect(filterTasks(tasks, '微信', 'ACTIVE')).toHaveLength(1)
    expect(filterTasks(tasks, '', 'SUCCEEDED')).toHaveLength(1)
    const run = {
      flow_id: 'f', flow_name: 'flow', mode: 'DEVICE' as const, fault: 'none',
      task: tasks[0],
      job: {
        job_id: 'j', task_id: 'run', app_skill_id: 'x', skill_version: '1',
        status: 'QUEUED', lease_id: null, device_id: null, lease_expires_at: null,
        mode: 'DEVICE' as const,
      },
      task_events: [], timeline: [],
    }
    const authoritative = { ...tasks[0], state: 'SUCCEEDED' as const, version: 9 }
    expect(resolveActiveRun(run, authoritative, { ...run.job, status: 'SUCCEEDED' }).task.version)
      .toBe(9)
  })

  it('renders exact approval scope and binding in confirmation copy', () => {
    const copy = approvalConfirmation({
      approval_id: 'a', task_id: 't', action: 'return_goods',
      scope: { target: 'ORDER-1', workflow_id: 'return', binding: '1234567890abcdefZZ' },
      status: 'PENDING', expires_at: '2026-08-20T12:10:00Z',
      created_at: '2026-08-20T12:00:00Z', decided_at: null, used_at: null,
    })
    expect(copy).toContain('ORDER-1')
    expect(copy).toContain('return_goods')
    expect(copy).toContain('1234567890abcdef')
  })
})
