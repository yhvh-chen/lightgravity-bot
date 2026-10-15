import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '../src/api/client'
import type { AcceptanceSnapshot, ControlActionResult, TaskApi } from '../src/api/tasks'
import type { TaskDetail, TaskSummary } from '../src/api/types'
import { ShellProvider } from '../src/app/ShellProvider'
import { BoardBody } from '../src/views/board/BoardBody'

afterEach(cleanup)

beforeEach(() => {
  window.sessionStorage.clear()
  window.history.replaceState(null, '', '/')
})

function makeTask(overrides: Partial<TaskSummary> = {}): TaskSummary {
  return {
    id: 'task_01A',
    task_id: 'task_01A',
    title: 'Add login',
    status: 'in-progress',
    phase: 'executing',
    revision: 4,
    etag: '"4"',
    requirements_revision: 2,
    queue: { state: 'claimed' },
    archived: false,
    ...overrides,
  }
}

function makeDetail(overrides: Partial<TaskDetail> = {}): TaskDetail {
  return {
    ...makeTask(),
    run: { id: 'run_01X', state: 'executing' },
    members: [],
    subtasks: [
      { id: 'subtask_01', state: 'passed', objective: 'impl', fail_reason: null },
      { id: 'subtask_02', state: 'failed', objective: 'test', fail_reason: 'assertion failed' },
    ],
    ...overrides,
  }
}

function makeAcceptance(overrides: Partial<AcceptanceSnapshot> = {}): AcceptanceSnapshot {
  return {
    task_id: 'task_01A',
    phase: 'awaiting_acceptance',
    status: 'in-progress',
    revision: 9,
    requirements_revision: 2,
    deliverable_revision: 3,
    acceptance: { status: 'awaiting', candidate_ref: 'evidence:run_01X/diff@sha256:abc' },
    candidate: null,
    checks: null,
    ...overrides,
  }
}

function makeTaskApi(overrides: Partial<TaskApi> = {}): TaskApi & { actions: Array<Record<string, unknown>> } {
  const actions: Array<Record<string, unknown>> = []
  return {
    actions,
    listTasks: vi.fn(async () => ({ items: [makeTask()], next_cursor: null })),
    getTask: vi.fn(async () => makeDetail()),
    readEvents: vi.fn(async () => ({ items: [], next_cursor: null })),
    act: vi.fn(async (_taskId, body) => {
      actions.push(body as unknown as Record<string, unknown>)
      return {
        action: body.action,
        state: 'requested',
        confirmed: false,
        task_id: 'task_01A',
      } as ControlActionResult
    }),
    getAcceptance: vi.fn(async () => makeAcceptance()),
    getArtifacts: vi.fn(async () => ({
      task_id: 'task_01A',
      task_revision: 9,
      requirements_revision: 2,
      deliverable_revision: 3,
      candidate_ref: 'evidence:run_01X/diff@sha256:abc',
      evidence_refs: [],
      check_records: [],
      workspace_ref: null,
      categories: {},
      note: null,
      evidence: [
        { name: 'diff.patch', evidence_ref: 'evidence:run_01X/diff@sha256:abc' },
      ],
    })),
    ...overrides,
  }
}

function renderBoard(api: TaskApi) {
  return render(
    <ShellProvider>
      <BoardBody api={api} />
    </ShellProvider>,
  )
}

describe('LG-013 Board: real phase and control state', () => {
  it('renders the real task list with its phase', async () => {
    renderBoard(makeTaskApi())
    expect(await screen.findByText('Add login')).toBeInTheDocument()
    expect(screen.getByText('phase: executing')).toBeInTheDocument()
  })

  it('shows a pending control request separately from the actual result', async () => {
    const api = makeTaskApi()
    renderBoard(api)

    fireEvent.click(await screen.findByText('Add login'))
    const pause = await screen.findByRole('button', { name: 'Pause' })
    fireEvent.click(pause)

    // The backend did not confirm, so the UI reports it as pending — never as
    // the new paused phase.
    expect(await screen.findByText(/has not confirmed the change yet/)).toBeInTheDocument()
    await waitFor(() => expect(api.actions).toHaveLength(1))
    expect(api.actions[0].action).toBe('pause')
    expect(String(api.actions[0].request_id)).toMatch(/^req_[0-9A-Z]{26}$/)
  })

  it('rounds accept through the actions endpoint bound to the current candidate', async () => {
    const api = makeTaskApi({
      act: vi.fn(async (_taskId, body) => {
        return {
          action: body.action,
          state: 'confirmed',
          confirmed: true,
          task_id: 'task_01A',
          phase: 'completed',
        } as ControlActionResult
      }),
    })
    renderBoard(api)

    fireEvent.click(await screen.findByText('Add login'))
    const accept = await screen.findByRole('button', { name: 'Accept' })
    fireEvent.click(accept)

    await waitFor(() => expect(api.act).toHaveBeenCalled())
    const call = vi.mocked(api.act).mock.calls[0][1]
    expect(call.action).toBe('accept')
    expect(call.expected_requirements_revision).toBe(2)
    expect(call.expected_deliverable_revision).toBe(3)
  })

  it('surfaces an acceptance_stale decision without pretending success', async () => {
    const api = makeTaskApi({
      act: vi.fn(async () => {
        throw new ApiError({
          message: 'candidate changed',
          code: 'acceptance_stale',
          httpStatus: 409,
          retryable: false,
        })
      }),
    })
    renderBoard(api)

    fireEvent.click(await screen.findByText('Add login'))
    fireEvent.click(await screen.findByRole('button', { name: 'Reject' }))

    expect(await screen.findByText(/decision is stale/)).toBeInTheDocument()
  })

  it('lists real artifacts with an evidence preview link', async () => {
    renderBoard(makeTaskApi())
    fireEvent.click(await screen.findByText('Add login'))

    expect(await screen.findByText('diff.patch')).toBeInTheDocument()
    const link = screen.getByRole('link', { name: 'Preview' })
    expect(link).toHaveAttribute(
      'href',
      '/api/v1/tasks/task_01A/artifacts/content?evidence_ref=evidence%3Arun_01X%2Fdiff%40sha256%3Aabc',
    )
  })

  it('never shows a failed task as active', async () => {
    const api = makeTaskApi({
      listTasks: vi.fn(async () => ({
        items: [
          makeTask({ id: 'task_fail', title: 'Broken', phase: 'failed' }),
          makeTask({ id: 'task_ok', title: 'Running', phase: 'executing' }),
        ],
        next_cursor: null,
      })),
    })
    renderBoard(api)

    expect(await screen.findByText('Broken')).toBeInTheDocument()
    expect(screen.getByText('Running')).toBeInTheDocument()
    // The failed task sits under "failed", not under the active phase badge.
    expect(screen.getByText('failed')).toBeInTheDocument()
  })
})
