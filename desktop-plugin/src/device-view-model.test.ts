import { describe, expect, it } from 'vitest'

import { buildDeviceViewModels } from './device-view-model'
import type { DeviceEnvelope } from './types'


function device(overrides: Partial<DeviceEnvelope>): DeviceEnvelope {
  return {
    device_id: 'android-1',
    display_name: '9号 AI 手机员工',
    online: true,
    worker_state: 'IDLE',
    app_version: '0.1.0',
    capabilities: ['heartbeat', 'manual_control'],
    battery_percent: 86,
    permissions: { notifications: true, accessibility: false, screen_capture: false },
    installed_apps: [],
    last_heartbeat_at: '2026-08-17T12:00:00+00:00',
    pending_command: null,
    ...overrides,
  }
}

describe('buildDeviceViewModels', () => {
  it('sorts online workers before offline workers', () => {
    const result = buildDeviceViewModels([
      device({ device_id: 'offline', display_name: '离线设备', online: false }),
      device({ device_id: 'online', display_name: '在线设备', online: true }),
    ])
    expect(result.map(item => item.device.device_id)).toEqual(['online', 'offline'])
  })

  it('summarizes permission warnings and state-specific actions', () => {
    const [paused] = buildDeviceViewModels([
      device({ worker_state: 'PAUSED', permissions: {
        notifications: false,
        accessibility: false,
        screen_capture: false,
      } }),
    ])
    expect(paused.permissionWarnings).toEqual(['通知未就绪', 'Accessibility 未就绪', '画面采集未就绪'])
    expect(paused.actions).toEqual(['RESUME', 'TAKEOVER', 'STOP'])
    expect(paused.statusLabel).toBe('已暂停')
  })

  it('distinguishes takeover and hides controls for offline workers', () => {
    const [worker] = buildDeviceViewModels([
      device({ online: false, worker_state: 'TAKEOVER' }),
    ])
    expect(worker.statusLabel).toBe('人工接管')
    expect(worker.actions).toEqual([])
  })
})
