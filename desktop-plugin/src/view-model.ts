import type {
  ApprovalEnvelope,
  DemoRunResult,
  TaskEnvelope,
  TaskState,
  WorkbenchSummary,
} from './types'


const TERMINAL_STATES = new Set<TaskState>(['SUCCEEDED', 'FAILED', 'CANCELLED'])

export interface WorkbenchViewModel {
  activeCount: number
  tasks: TaskEnvelope[]
}

export function buildWorkbenchViewModel(summary: WorkbenchSummary): WorkbenchViewModel {
  const tasks = [...summary.recent_tasks].sort((left, right) => {
    const activeDifference = Number(TERMINAL_STATES.has(left.state))
      - Number(TERMINAL_STATES.has(right.state))
    if (activeDifference !== 0) {
      return activeDifference
    }
    return right.created_at.localeCompare(left.created_at)
  })
  return {
    activeCount: tasks.filter(task => !TERMINAL_STATES.has(task.state)).length,
    tasks,
  }
}

export function filterTasks(
  tasks: TaskEnvelope[],
  search: string,
  filter: string,
): TaskEnvelope[] {
  const needle = search.toLowerCase()
  return tasks.filter(task => {
    const matchesSearch = `${task.title} ${task.source}`.toLowerCase().includes(needle)
    const matchesFilter = filter === 'ALL'
      || (filter === 'ACTIVE' && !TERMINAL_STATES.has(task.state))
      || (filter === 'FAILED' && ['FAILED', 'RETRY_WAIT', 'HUMAN_TAKEOVER'].includes(task.state))
      || (filter === 'SUCCEEDED' && task.state === 'SUCCEEDED')
    return matchesSearch && matchesFilter
  })
}

export function resolveActiveRun(
  run: DemoRunResult,
  task: TaskEnvelope | null | undefined,
  job: DemoRunResult['job'] | null | undefined,
): DemoRunResult {
  return { ...run, task: task ?? run.task, job: job ?? run.job }
}

export function approvalConfirmation(approval: ApprovalEnvelope): string {
  return [
    `动作：${approval.action}`,
    `目标：${String(approval.scope.target ?? '未指定')}`,
    `流程：${String(approval.scope.workflow_id ?? '未指定')}`,
    `有效期：${new Date(approval.expires_at).toLocaleString()}`,
    `绑定摘要：${String(approval.scope.binding ?? '').slice(0, 16)}`,
  ].join(' · ')
}
