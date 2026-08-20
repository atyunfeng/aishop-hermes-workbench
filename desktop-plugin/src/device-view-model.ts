import type { DeviceCommandType, DeviceEnvelope, WorkerState } from './types'


const STATUS_LABELS: Record<WorkerState, string> = {
  OFFLINE: '离线',
  IDLE: '空闲',
  BUSY: '执行中',
  PAUSED: '已暂停',
  TAKEOVER: '人工接管',
  ERROR: '异常',
}

const ACTIONS: Record<WorkerState, DeviceCommandType[]> = {
  OFFLINE: [],
  IDLE: ['PAUSE', 'TAKEOVER', 'STOP'],
  BUSY: ['PAUSE', 'TAKEOVER', 'STOP'],
  PAUSED: ['RESUME', 'TAKEOVER', 'STOP'],
  TAKEOVER: ['RESUME', 'STOP'],
  ERROR: ['TAKEOVER', 'STOP'],
}

export interface DeviceViewModel {
  device: DeviceEnvelope
  statusLabel: string
  permissionWarnings: string[]
  actions: DeviceCommandType[]
}

export function buildDeviceViewModels(devices: DeviceEnvelope[]): DeviceViewModel[] {
  return [...devices]
    .sort((left, right) => {
      const onlineDifference = Number(right.online) - Number(left.online)
      return onlineDifference || left.display_name.localeCompare(right.display_name, 'zh-CN')
    })
    .map(device => ({
      device,
      statusLabel: STATUS_LABELS[device.worker_state],
      permissionWarnings: [
        !device.permissions.notifications && '通知未就绪',
        !device.permissions.accessibility && 'Accessibility 未就绪',
        !device.permissions.screen_capture && '画面采集未就绪',
      ].filter((warning): warning is string => Boolean(warning)),
      actions: device.online && !device.pending_command ? ACTIONS[device.worker_state] : [],
    }))
}
