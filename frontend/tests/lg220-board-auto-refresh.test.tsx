/**
 * LG-220: Board auto-refresh and the explicit Task destination helper.
 *
 * These are executor-local tests for the new capability.  The existing broken
 * TopBar notification click and Chat create_task view switch are intentionally
 * not changed here; the native repair owner consumes `openTaskDestination`.
 */
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { AcceptanceSnapshot, TaskApi } from '../src/api/tasks'
import type { TaskDetail, TaskSummary } from '../src/api/types'
import { ShellProvider } from '../src/app/ShellProvider'
import { openTaskDestination } from '../src/app/taskDestination'
import { createInitialState, shellReducer } from '../src/app/uiState'
import { BoardBody } from '../src/views/board/BoardBody'

afterEach(cleanup)

beforeEach(() => {
  window.sessionStorage.clear()
  window.history.replaceState(null, '', '/')
})

type MutablePhase = 'executing' | 'awaiting_acceptance'

function makeTask(phase: MutablePhase): TaskSummary {
  return {
    id: 'task_01A',
    task_id: 'task_01A',
    title: 'Add login',
    status: 'in-progress',
    phase,
    revision: phase === 'executing' ? 4 : 9,
    etag: phase === 'executing' ? '"4"' : '"9"',
    requirements_revision: 2,
    queue: { state: 'claimed' },
    archived: false,
  }
}

function makeDetail(phase: MutablePhase): TaskDetail {
  return {
    ...makeTask(phase),
    run: { id: 'run_01X', state: phase },
    members: [],
    subtasks: [],
  }
}

function makeApi(phase: () => MutablePhase): TaskApi {
  return {
    listTasks: vi.fn(async () => ({ items: [makeTask(phase())], next_cursor: null })),
    getTask: vi.fn(async () => makeDetail(phase())),
    readEvents: vi.fn(async () => ({ items: [], next_cursor: null })),
    act: vi.fn(),
    getAcceptance: vi.fn(async (): Promise<AcceptanceSnapshot | null> => null),
    getArtifacts: vi.fn(async () => ({
      task_id: 'task_01A',
      task_revision: 4,
      requirements_revision: 2,
      deliverable_revision: null,
      candidate_ref: null,
      evidence_refs: [],
      check_records: [],
      workspace_ref: null,
      categories: {},
      note: null,
      evidence: [],
    })),
  } as unknown as TaskApi
}

function renderBoard(api: TaskApi, autoRefreshMs: number) {
  return render(
    <ShellProvider>
      <BoardBody api={api} autoRefreshMs={autoRefreshMs} />
    </ShellProvider>,
  )
}

describe('LG-220 Board auto-refresh', () => {
  it('updates the real list phase and the selected Task detail without manual Refresh', async () => {
    let phase: MutablePhase = 'executing'
    const api = makeApi(() => phase)
    window.history.replaceState(
      null,
      '',
      '/?view=board&task=task_01A&run=run_01X',
    )
    renderBoard(api, 50)

    const pause = await screen.findByRole('button', { name: 'Pause' })
    expect(await screen.findByText(/Run run_01X \(executing\)/)).toBeInTheDocument()

    // Focus and scope must survive the background reads.
    pause.focus()
    expect(pause).toHaveFocus()
    expect(window.location.search).toContain('run=run_01X')

    phase = 'awaiting_acceptance'
    await waitFor(
      () => expect(screen.getByText(/Run run_01X \(awaiting_acceptance\)/)).toBeInTheDocument(),
      { timeout: 2000 },
    )

    // The selected Task stays open, its native Refresh never ran and the URL
    // scope is unchanged by the auto-refresh.
    expect(screen.getByText(/updated automatically/)).toBeInTheDocument()
    expect(screen.getByLabelText('Task detail')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Pause' })).toHaveFocus()
    expect(screen.getByRole('button', { name: 'Refresh' })).toBeInTheDocument()
    expect(window.location.search).toContain('task=task_01A')
    expect(window.location.search).toContain('run=run_01X')
  })

  it('does not swap the detail for a loading state during a background read', async () => {
    let phase: MutablePhase = 'executing'
    const api = makeApi(() => phase)
    let resolveRefresh!: (detail: TaskDetail) => void
    vi.mocked(api.getTask)
      .mockResolvedValueOnce(makeDetail('executing'))
      .mockImplementationOnce(
        () => new Promise<TaskDetail>((resolve) => {
          resolveRefresh = resolve
        }),
      )
    renderBoard(api, 200)

    fireEvent.click(await screen.findByText('Add login'))
    expect(await screen.findByRole('button', { name: 'Pause' })).toBeInTheDocument()

    await waitFor(() => expect(api.getTask).toHaveBeenCalledTimes(2), { timeout: 1500 })
    expect(screen.queryByText('Loading Task…')).not.toBeInTheDocument()
    expect(screen.getByLabelText('Task detail')).toBeInTheDocument()

    resolveRefresh(makeDetail(phase))
    await waitFor(() => expect(screen.getByText(/Run run_01X \(executing\)/)).toBeInTheDocument())
    expect(screen.queryByText('Loading Task…')).not.toBeInTheDocument()
  })
})

describe('LG-220 openTaskDestination', () => {
  it('applies view/task/run/item together and preserves chat and drafts', () => {
    const initial = {
      ...createInitialState(),
      view: 'board' as const,
      taskRef: 'task_old',
      runRef: 'run_old',
      selectedItemRef: 'item_old',
      drafts: { 'chat:task_old': 'unfinished message' },
      chatOpen: false,
      chatChannel: 'team' as const,
    }

    const next = shellReducer(
      initial,
      openTaskDestination({
        taskRef: 'task_notification',
        runRef: 'run_notification',
        view: 'tasks',
        itemRef: 'source:run_notification',
      }),
    )

    expect(next.view).toBe('tasks')
    expect(next.taskRef).toBe('task_notification')
    expect(next.runRef).toBe('run_notification')
    expect(next.selectedItemRef).toBe('source:run_notification')
    expect(next.chatOpen).toBe(false)
    expect(next.chatChannel).toBe('team')
    expect(next.drafts).toBe(initial.drafts)
  })

  it('defaults to the Tasks workspace and clears the old Run/item when omitted', () => {
    const initial = {
      ...createInitialState(),
      view: 'board' as const,
      taskRef: 'task_old',
      runRef: 'run_old',
      selectedItemRef: 'item_old',
    }

    const next = shellReducer(
      initial,
      openTaskDestination({ taskRef: 'task_new' }),
    )

    expect(next.view).toBe('tasks')
    expect(next.taskRef).toBe('task_new')
    expect(next.runRef).toBeNull()
    expect(next.selectedItemRef).toBeNull()
  })
})
