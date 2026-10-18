import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '../src/api/client'
import type { TeamApi } from '../src/api/team'
import type {
  TeamGroup,
  TeamGroupsApi,
  TeamGroupsQuery,
} from '../src/api/teamGroups'
import type { QueueState, RunState, SubtaskState, TaskPhase } from '../src/api/types'
import { ShellProvider } from '../src/app/ShellProvider'
import { RecruitedPanel } from '../src/views/team/RecruitedPanel'
import { TeamView } from '../src/views/team/TeamView'

interface GroupOptions {
  id?: string
  title?: string
  phase?: TaskPhase
  activeRun?: string | null
  runState?: RunState
  attempt?: number
  cleanupStatus?: string
  reviewerConfirmed?: boolean | null
  sessionRefs?: string[] | null
  queueState?: QueueState
  memberState?: string | null
  subtaskState?: SubtaskState
  waitingReason?: string | null
  dependsOn?: string[]
}

function makeGroup(options: GroupOptions = {}): TeamGroup {
  const taskId = options.id ?? 'task_01TASK'
  const activeRunId = options.activeRun === undefined ? 'run_01RUN' : options.activeRun
  const runId = activeRunId ?? 'run_01RUN'
  const memberId = `member_${taskId}`
  const subtaskState = options.subtaskState ?? 'running'
  const subtask = {
    id: `subtask_${taskId}`,
    key: 'page',
    capability: 'implementation',
    state: subtaskState,
    depends_on: options.dependsOn ?? [],
    blocked_by: [],
    assignee_member_ref: memberId,
    waiting_reason: options.waitingReason ?? null,
    acceptance: { status: subtaskState === 'passed' ? 'passed' : 'pending' },
    fail_reason: null,
  }
  const member = {
    id: memberId,
    run_ref: runId,
    role_ref: 'engineering-frontend-developer',
    state: options.memberState ?? 'ready',
    template_version: '1',
    connection_ref: null,
    skill_refs: ['implementation'],
    capabilities: ['implementation'],
    assigned_subtask_refs: [subtask.id],
    assigned_subtasks: [subtask],
    config_hash: 'cfg-123',
    fail_reason: null,
  }
  const run = {
    id: runId,
    state: options.runState ?? (activeRunId ? 'executing' : 'failed'),
    attempt: options.attempt ?? 1,
    plan_source: 'rules',
    plan_hash: 'plan-hash',
    team_refs: [memberId],
    cleanup: { status: options.cleanupStatus ?? 'pending' },
    reviewer_cleanup:
      options.reviewerConfirmed === undefined
        ? null
        : { confirmed: options.reviewerConfirmed },
    session_refs:
      options.sessionRefs === null
        ? undefined
        : options.sessionRefs ?? ['sdk-session-1'],
    ended_at: activeRunId ? null : '2026-10-18T01:00:00Z',
    fail_reason: options.runState === 'failed' ? 'worker failed' : null,
    waiting_reason: null,
  }
  return {
    task: {
      id: taskId,
      title: options.title ?? 'Build launch page',
      status: options.phase === 'completed' ? 'done' : 'in-progress',
      phase: options.phase ?? 'executing',
      revision: 1,
      requirements_revision: 1,
      deliverable_revision: 0,
      archived: false,
      active_run: activeRunId,
      last_run: runId,
      queue: {
        state: options.queueState ?? (activeRunId ? 'claimed' : 'not_queued'),
        order: 1,
        queued_at: null,
        owner: null,
        waiting_reason: null,
      },
    },
    active_run: activeRunId ? run : null,
    runs: [run],
    members: [member],
    subtasks: [subtask],
  }
}

function availableApi(): TeamApi {
  return {
    async listAvailable() {
      return []
    },
    async listMembers() {
      return []
    },
  }
}

function groupsApiFor(groups: TeamGroup[]) {
  const calls: TeamGroupsQuery[] = []
  const api: TeamGroupsApi = {
    async listGroups(query = {}) {
      calls.push({ ...query })
      return { items: groups, next_cursor: null }
    },
  }
  return { api, calls }
}

function renderView(
  groupsApi: TeamGroupsApi,
  options: {
    groups?: TeamGroup[]
    capability?: boolean
    taskRef?: string | null
    selectedItemRef?: string | null
    pollIntervalMs?: number
  } = {},
) {
  const selectItem = vi.fn<(ref: string | null) => void>()
  const onOpenTaskChat = vi.fn<(taskRef: string) => void>()
  const onViewTask = vi.fn<(taskRef: string) => void>()
  const view = render(
    <ShellProvider>
      <TeamView
        api={availableApi()}
        groupsApi={groupsApi}
        teamGroupsCapability={options.capability ?? true}
        pollIntervalMs={options.pollIntervalMs ?? 0}
        taskRef={options.taskRef === undefined ? 'task_01TASK' : options.taskRef}
        runRef={null}
        selectedItemRef={options.selectedItemRef ?? null}
        selectItem={selectItem}
        navigate={vi.fn()}
        openChatDraft={vi.fn()}
        onOpenTaskChat={onOpenTaskChat}
        onViewTask={onViewTask}
      />
      {options.groups ? <output data-testid="fixture-groups">{options.groups.length}</output> : null}
    </ShellProvider>,
  )
  return { view, selectItem, onOpenTaskChat, onViewTask }
}

function panel(groups: TeamGroup[], extra: Partial<Parameters<typeof RecruitedPanel>[0]> = {}) {
  return render(
    <RecruitedPanel
      groups={groups}
      nextCursor={null}
      loading={false}
      loadingMore={false}
      error={null}
      stale={false}
      lastUpdatedAt={null}
      currentTaskRef="task_01TASK"
      onRetry={vi.fn()}
      onLoadMore={vi.fn()}
      onSelectGroup={vi.fn()}
      onOpenChat={vi.fn()}
      onViewTask={vi.fn()}
      recentReleaseMs={5000}
      {...extra}
    />,
  )
}

beforeEach(() => {
  window.sessionStorage.clear()
  window.history.replaceState(null, '', '/')
})

afterEach(() => {
  cleanup()
})

describe('LG-125 grouped team release semantics', () => {
  it('keeps failed cleanup-unconfirmed in Active and only moves confirmed release to History', async () => {
    const failed = makeGroup({
      id: 'task_01FAIL',
      title: 'Failed cleanup task',
      phase: 'failed',
      activeRun: null,
      runState: 'failed',
      cleanupStatus: 'pending',
      sessionRefs: ['sdk-still-live'],
      memberState: 'ready',
    })
    const released = makeGroup({
      id: 'task_02DONE',
      title: 'Completed release task',
      phase: 'completed',
      activeRun: null,
      runState: 'completed',
      cleanupStatus: 'done',
      reviewerConfirmed: true,
      sessionRefs: [],
      memberState: 'released',
      queueState: 'not_queued',
      subtaskState: 'passed',
    })
    const fixture = groupsApiFor([failed, released])
    renderView(fixture.api, { taskRef: 'task_01FAIL' })

    expect(await screen.findByText('Failed cleanup task')).toBeInTheDocument()
    expect(screen.getByText('Failed · Cleanup unconfirmed')).toBeInTheDocument()
    expect(screen.getByText('Worker stop is not confirmed')).toBeInTheDocument()
    expect(screen.queryByText('Completed release task')).toBeNull()

    fireEvent.click(screen.getByRole('tab', { name: /History/ }))
    expect(await screen.findByText('Completed release task')).toBeInTheDocument()
    expect(screen.getByText('Completed · Released')).toBeInTheDocument()
    expect(screen.queryByText('Failed cleanup task')).toBeNull()
  })

  it('never releases recovery_required or an unconfirmed reviewer cleanup', async () => {
    const recovery = makeGroup({
      id: 'task_01REC',
      title: 'Recovery path task',
      phase: 'recovery_required',
      activeRun: null,
      runState: 'recovery_required',
      cleanupStatus: 'done',
      reviewerConfirmed: true,
      sessionRefs: [],
      memberState: 'released',
      queueState: 'not_queued',
      subtaskState: 'passed',
    })
    const reviewerPending = makeGroup({
      id: 'task_02REV',
      title: 'Reviewer cleanup task',
      phase: 'failed',
      activeRun: null,
      runState: 'failed',
      cleanupStatus: 'done',
      reviewerConfirmed: false,
      sessionRefs: [],
      memberState: 'released',
      queueState: 'not_queued',
    })
    const fixture = groupsApiFor([recovery, reviewerPending])
    renderView(fixture.api, { taskRef: 'task_01REC' })

    expect(await screen.findByText('Recovery required')).toBeInTheDocument()
    expect(screen.getByText('Failed · Cleanup unconfirmed')).toBeInTheDocument()
    expect(screen.getByText('Reviewer stop is not confirmed')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: /History/ }))
    expect(await screen.findByText('No released teams yet')).toBeInTheDocument()
  })

  it('shows dependency and capacity waits instead of treating member ready as idle', async () => {
    const dependency = makeGroup({
      id: 'task_01DEP',
      title: 'Dependency task',
      memberState: 'ready',
      subtaskState: 'pending',
      dependsOn: ['subtask_missing_upstream'],
    })
    const capacity = makeGroup({
      id: 'task_02CAP',
      title: 'Capacity task',
      memberState: 'ready',
      subtaskState: 'pending',
      waitingReason: 'global_session_limit',
    })
    const fixture = groupsApiFor([dependency, capacity])
    renderView(fixture.api, { taskRef: 'task_01DEP' })

    expect(await screen.findByText('Dependency task')).toBeInTheDocument()
    expect(screen.getByText('Waiting · dependency')).toBeInTheDocument()
    expect(screen.queryByText('Waiting · ready')).toBeNull()
    expect(screen.getByText(/page — Waiting · dependency/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Show details for engineering-frontend-developer/ }))
    expect(await screen.findByText(/depends on: subtask_missing_upstream/)).toBeInTheDocument()
    expect(screen.getByText(/acceptance: pending/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Hide details for engineering-frontend-developer/ }))

    fireEvent.click(screen.getByRole('button', { name: /^Capacity task/ }))
    expect(await screen.findByText('Waiting · Waiting for session capacity')).toBeInTheDocument()
  })

  it('keeps Task filter/search local and explicit actions carry the correct Task id', async () => {
    const alpha = makeGroup({ id: 'task_01ALPHA', title: 'Alpha task' })
    const beta = makeGroup({ id: 'task_02BETA', title: 'Beta task' })
    const fixture = groupsApiFor([alpha, beta])
    const { selectItem, onOpenTaskChat, onViewTask } = renderView(fixture.api, {
      taskRef: 'task_01ALPHA',
    })

    expect(await screen.findByRole('button', { name: /^Alpha task/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^Beta task/ })).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Task filter'), { target: { value: 'task_02BETA' } })
    expect(screen.queryByRole('button', { name: /^Alpha task/ })).toBeNull()
    expect(screen.getByRole('button', { name: /^Beta task/ })).toBeInTheDocument()
    expect(onOpenTaskChat).not.toHaveBeenCalled()
    expect(selectItem).not.toHaveBeenCalled()

    fireEvent.change(screen.getByLabelText('Task filter'), { target: { value: 'all' } })
    fireEvent.change(screen.getByLabelText('Search tasks'), { target: { value: 'alpha' } })
    expect(screen.getByRole('button', { name: /^Alpha task/ })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Beta task/ })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Clear filters' }))

    fireEvent.click(screen.getByRole('button', { name: 'Open chat for Alpha task' }))
    fireEvent.click(screen.getByRole('button', { name: 'View task Alpha task' }))
    expect(onOpenTaskChat).toHaveBeenCalledWith('task_01ALPHA')
    expect(onViewTask).toHaveBeenCalledWith('task_01ALPHA')
    expect(window.sessionStorage.getItem('lg125.team-groups-ui')).toContain('task_01ALPHA')
  })

  it('turns an Active -> History transition into an explicit View history action', async () => {
    const active = makeGroup({ id: 'task_01REL', title: 'Release soon' })
    const view = panel([active], { currentTaskRef: 'task_01REL' })
    expect(await screen.findByText('Release soon')).toBeInTheDocument()
    expect(screen.getByText('Members')).toBeInTheDocument()

    const history = makeGroup({
      id: 'task_01REL',
      title: 'Release soon',
      phase: 'completed',
      activeRun: null,
      runState: 'completed',
      cleanupStatus: 'done',
      reviewerConfirmed: true,
      sessionRefs: [],
      memberState: 'released',
      queueState: 'not_queued',
      subtaskState: 'passed',
    })
    view.rerender(
      <RecruitedPanel
        groups={[history]}
        nextCursor={null}
        loading={false}
        loadingMore={false}
        error={null}
        stale={false}
        lastUpdatedAt={null}
        currentTaskRef="task_01REL"
        onRetry={vi.fn()}
        onLoadMore={vi.fn()}
        onSelectGroup={vi.fn()}
        onOpenChat={vi.fn()}
        onViewTask={vi.fn()}
        recentReleaseMs={5000}
      />,
    )

    expect(await screen.findByRole('button', { name: 'View history' })).toBeInTheDocument()
    expect(screen.getByText('Completed · Released')).toBeInTheDocument()
    // The expanded group survives the poll/rerender.
    expect(screen.getByText('Members')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'View history' }))
    expect(screen.getByRole('tab', { name: /History/ })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByText('Release soon')).toBeInTheDocument()
  })

  it('keeps the last successful polling snapshot and marks it disconnected', async () => {
    let calls = 0
    const api: TeamGroupsApi = {
      async listGroups() {
        calls += 1
        if (calls === 1) {
          return { items: [makeGroup({ id: 'task_01POLL', title: 'Polled snapshot' })], next_cursor: null }
        }
        throw new ApiError({
          message: 'socket closed',
          code: 'network_error',
          httpStatus: null,
          retryable: true,
        })
      },
    }
    renderView(api, { taskRef: 'task_01POLL', pollIntervalMs: 25 })
    expect(await screen.findByText('Polled snapshot')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('Disconnected')).toBeInTheDocument())
    expect(screen.getByText('Polled snapshot')).toBeInTheDocument()
    expect(screen.queryByText('Completed · Released')).toBeNull()
  })

  it('keeps the last snapshot visibly stale when disconnected', async () => {
    panel([makeGroup({ id: 'task_01STALE', title: 'Stale snapshot task' })], {
      stale: true,
      lastUpdatedAt: new Date('2026-10-18T02:00:00Z'),
    })
    expect(await screen.findByText('Disconnected')).toBeInTheDocument()
    expect(screen.getByText(/Showing the last snapshot/)).toBeInTheDocument()
    expect(screen.getByText('Stale snapshot task')).toBeInTheDocument()
    expect(screen.queryByText('Completed · Released')).toBeNull()
  })
})

describe('LG-125 grouped team capability gate', () => {
  it('does not call /team/groups when the backend lacks the capability', async () => {
    const fixture = groupsApiFor([makeGroup()])
    renderView(fixture.api, { capability: false })
    expect(await screen.findByText('Grouped teams unavailable')).toBeInTheDocument()
    expect(screen.getByText(/No team-groups request was sent/)).toBeInTheDocument()
    expect(fixture.calls).toHaveLength(0)
  })
})
