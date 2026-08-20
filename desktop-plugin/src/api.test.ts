import { describe, expect, it, vi } from 'vitest'

import { createApi, type PluginRest } from './api'

describe('createApi', () => {
  it('adds the operator token to every operator request', async () => {
    const restMock = vi.fn(async () => ({
      generated_at: '2026-08-20T00:00:00Z',
      task_counts: {}, devices: [], approvals: [], recent_tasks: [],
    }))
    const rest = restMock as unknown as PluginRest
    const api = createApi(rest, () => 'operator-secret')
    await api.getWorkbench()
    expect(restMock).toHaveBeenCalledWith('/workbench', {
      headers: { 'X-AIShop-Operator-Token': 'operator-secret' },
    })
  })
})
