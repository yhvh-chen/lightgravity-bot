import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type { TaskApi } from '../src/api/tasks'
import type { TaskDetail } from '../src/api/types'
import { ShellProvider } from '../src/app/ShellProvider'
import { ExecutionAvailability } from '../src/components/ExecutionAvailability'
import { NotificationList } from '../src/components/NotificationList'
import { TaskRunFailure } from '../src/components/TaskRunFailure'
import { BoardBody } from '../src/views/board/BoardBody'

const availability = vi.hoisted(() => ({ value: true as boolean | null }))
vi.mock('../src/api/useBackendStatus', () => ({ useBackendStatus: () => ({ state: 'connected',
  health: { capabilities: { sdk_adapter: availability.value } },
}) }))
function detail(phase: TaskDetail['phase'] = 'failed'): TaskDetail {
  return { id: 'task_1', task_id: 'task_1', title: 'Delivery', status: 'in-progress', phase,
    revision: 1, etag: '1', requirements_revision: 1, queue: { state: 'not_queued' }, archived: false,
    run: { id: 'run_1', state: phase, fail_reason: phase === 'failed' ? 'Executor is disabled.' : null },
    subtasks: [], members: [],
  }
}
function apiFor(task: TaskDetail): TaskApi {
  return { listTasks: vi.fn(async () => ({ items: [task], next_cursor: null })),
    getTask: vi.fn(async () => task), getAcceptance: vi.fn(async () => null),
    getArtifacts: vi.fn(async () => ({ evidence: [] })), act: vi.fn(),
  } as unknown as TaskApi
}
beforeEach(() => { availability.value = true; localStorage.clear(); history.replaceState(null, '', '?view=board&task=task_1') })
afterEach(cleanup)
it('shows actual Run failure and prevents another retry when execution is disabled', async () => {
  availability.value = false
  render(<ShellProvider><BoardBody api={apiFor(detail())} /></ShellProvider>)
  expect(await screen.findByText('Failure reason: Executor is disabled.')).toBeInTheDocument()
  expect(screen.getByText(/Execution unavailable/)).toBeInTheDocument()
  for (const name of ['Pause', 'Cancel', 'Retry']) expect(screen.getByRole('button', { name })).toBeDisabled()
  expect(screen.getByText(/Retry unavailable: Task execution is disabled/)).toBeInTheDocument()
})
it.each(['executing', 'completed', 'failed'] as const)('gates controls for %s using existing server phases', async (phase) => {
  render(<ShellProvider><BoardBody api={apiFor(detail(phase))} /></ShellProvider>)
  await screen.findByText(/Task task_1 · revision/)
  const pause = screen.getByRole('button', { name: 'Pause' })
  const cancel = screen.getByRole('button', { name: 'Cancel' })
  const retry = screen.getByRole('button', { name: 'Retry' })
  if (phase === 'executing') { expect(pause).toBeEnabled(); expect(cancel).toBeEnabled(); expect(retry).toBeDisabled() }
  if (phase === 'completed') { expect(pause).toBeDisabled(); expect(cancel).toBeDisabled(); expect(retry).toBeDisabled() }
  if (phase === 'failed') { expect(pause).toBeDisabled(); expect(cancel).toBeDisabled(); expect(retry).toBeEnabled() }
})
it('keeps unknown availability distinct from disabled execution', () => {
  render(<ExecutionAvailability available={null} />)
  expect(screen.getByText(/Execution status unknown/)).toBeInTheDocument()
  expect(screen.queryByText(/Execution unavailable/)).not.toBeInTheDocument()
})
it('shows current failure facts in Task chat without a fabricated assistant message or cross-Task leak', async () => {
  const api = apiFor(detail())
  const view = render(<TaskRunFailure taskRef="task_1" api={api} />)
  expect(await screen.findByText('Run run_1 failed: Executor is disabled.')).toBeInTheDocument()
  view.rerender(<TaskRunFailure taskRef="task_2" api={api} />)
  expect(screen.queryByText(/Executor is disabled/)).not.toBeInTheDocument()
})
it('renders the persisted notification reason alongside its title', () => {
  const onSelect = vi.fn()
  render(<NotificationList items={[{ id: 'n1', title: 'Task failed', at: 'now', body: 'Executor is disabled.' }]} onSelect={onSelect} />)
  expect(screen.getByText('Executor is disabled.')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button'))
  expect(onSelect).toHaveBeenCalled()
})
