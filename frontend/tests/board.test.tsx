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
    acceptance: {
      status: 'awaiting', candidate_ref: 'run_01X', candidate_plan_hash: 'plan-current',
      requirements_revision: 2, deliverable_revision: 3,
    },
    candidate: {
      task_id: 'task_01A', run_id: 'run_01X', candidate_ref: 'run_01X',
      run_state: 'awaiting_acceptance', plan_hash: 'plan-current',
      requirements_revision: 2, deliverable_revision: 3,
    },
    checks: { satisfied: true, results: [], authorized: [], registered: [] },
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

function readyApi(overrides: Partial<TaskApi> = {}) {
  return makeTaskApi({
    getTask: vi.fn(async () => makeDetail({
      phase: 'awaiting_acceptance', revision: 9,
      run: { id: 'run_01X', state: 'awaiting_acceptance' },
    })),
    ...overrides,
  })
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
    const api = readyApi({
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
    expect(call.target_run_id).toBe('run_01X')
    expect(call.expected_requirements_revision).toBe(2)
    expect(call.expected_deliverable_revision).toBe(3)
  })

  it('surfaces an acceptance_stale decision without pretending success', async () => {
    const api = readyApi({
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

  it('opens real artifacts in the safe Tasks preview with exact Task/Run binding', async () => {
    renderBoard(makeTaskApi())
    fireEvent.click(await screen.findByText('Add login'))

    expect(await screen.findByText('diff.patch')).toBeInTheDocument()
    const link = screen.getByRole('link', { name: 'Preview' })
    const target = new URL(link.getAttribute('href')!, location.origin)
    expect(target.searchParams.get('view')).toBe('tasks')
    expect(target.searchParams.get('item')).toBe('evidence:run_01X/diff@sha256:abc')
    fireEvent.click(link)
    await waitFor(() => expect(new URLSearchParams(location.search).get('view')).toBe('tasks'))
    expect(new URLSearchParams(location.search).get('task')).toBe('task_01A')
    expect(new URLSearchParams(location.search).get('run')).toBe('run_01X')
    expect(new URLSearchParams(location.search).get('item')).toBe('evidence:run_01X/diff@sha256:abc')
  })

  it('offers a canonical evidence Download link without absolute refs', async () => {
    renderBoard(makeTaskApi())
    fireEvent.click(await screen.findByText('Add login'))

    const download = await screen.findByRole('link', { name: 'Download' })
    expect(download).toHaveAttribute(
      'href',
      '/api/v1/tasks/task_01A/artifacts/download?evidence_ref=evidence%3Arun_01X%2Fdiff%40sha256%3Aabc',
    )
    // The Task-scoped endpoint re-authorizes the canonical evidence ref; the UI
    // never emits an absolute path, a protocol URL or a cross-Task escape.
    const href = download.getAttribute('href') ?? ''
    const params = new URLSearchParams(href.split('?')[1])
    expect(params.get('evidence_ref')).toBe('evidence:run_01X/diff@sha256:abc')
    expect(href).not.toContain('://')
    expect(href).not.toContain('../')
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


describe('LG-082 current candidate decisions', () => {
  it('keeps failed pending delivery without an active Run or candidate unavailable', async () => {
    const api = makeTaskApi({
      getTask: vi.fn(async () => makeDetail({ phase: 'failed', run: null })),
      getAcceptance: vi.fn(async () => makeAcceptance({
        phase: 'failed', deliverable_revision: 0,
        acceptance: { status: 'pending' }, candidate: null, checks: null,
      })),
    })
    renderBoard(api)
    fireEvent.click(await screen.findByText('Add login'))
    expect(await screen.findByText(/no active Run/)).toBeInTheDocument()
    for (const name of ['Accept', 'Reject']) {
      const button = screen.getByRole('button', { name })
      expect(button).toBeDisabled()
      fireEvent.click(button)
    }
    expect(api.act).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Retry' })).toBeDisabled()
  })

  it.each([
    ['pending acceptance', { acceptance: { ...makeAcceptance().acceptance, status: 'pending' } }],
    ['candidate absent', { candidate: null }],
    ['verification/stop handoff absent', { phase: 'verifying' }],
    ['snapshot from another Task', { task_id: 'task_other' }],
    ['snapshot from another revision', { revision: 10 }],
    ['requirements changed', { requirements_revision: 3 }],
    ['deliverable changed', { deliverable_revision: 4 }],
    ['candidate from another Run', { candidate: { ...makeAcceptance().candidate, run_id: 'run_other' } }],
    ['candidate from another Task', { candidate: { ...makeAcceptance().candidate, task_id: 'task_other' } }],
    ['candidate still executing', { candidate: { ...makeAcceptance().candidate, run_state: 'executing' } }],
    ['candidate requirements changed', { candidate: { ...makeAcceptance().candidate, requirements_revision: 3 } }],
    ['candidate deliverable changed', { candidate: { ...makeAcceptance().candidate, deliverable_revision: 4 } }],
    ['candidate plan changed', { candidate: { ...makeAcceptance().candidate, plan_hash: 'new-plan' } }],
    ['decision bound to another Run', { acceptance: { ...makeAcceptance().acceptance, candidate_ref: 'run_other' } }],
    ['machine checks failed', { checks: { satisfied: false } }],
    ['machine checks unavailable', { checks: null }],
  ] satisfies Array<[string, Partial<AcceptanceSnapshot>]>)('disables decisions when %s', async (_reason, snapshot) => {
    const api = readyApi({ getAcceptance: vi.fn(async () => makeAcceptance(snapshot)) })
    renderBoard(api)
    fireEvent.click(await screen.findByText('Add login'))
    expect(await screen.findByRole('button', { name: 'Accept' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Reject' })).toBeDisabled()
    expect(api.act).not.toHaveBeenCalled()
  })

  it('does not enable stale decisions while a refreshed snapshot is loading', async () => {
    let resolveRefresh!: (value: TaskDetail) => void
    const api = readyApi()
    vi.mocked(api.getTask).mockResolvedValueOnce(makeDetail({
      phase: 'awaiting_acceptance', revision: 9,
      run: { id: 'run_01X', state: 'awaiting_acceptance' },
    })).mockImplementationOnce(() => new Promise((resolve) => { resolveRefresh = resolve }))
    vi.mocked(api.act).mockResolvedValueOnce({ action: 'cancel', state: 'confirmed', confirmed: true, task_id: 'task_01A' })
    renderBoard(api)
    fireEvent.click(await screen.findByText('Add login'))
    expect(await screen.findByRole('button', { name: 'Accept' })).toBeEnabled()
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(await screen.findByText('Loading Task…')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Accept' })).toBeDisabled()
    resolveRefresh(makeDetail({ phase: 'cancelled', revision: 10 }))
    await waitFor(() => expect(screen.queryByText('Loading Task…')).not.toBeInTheDocument())
    expect(screen.getByRole('button', { name: 'Accept' })).toBeDisabled()
  })
})
