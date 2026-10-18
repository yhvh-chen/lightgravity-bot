import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { AvailableAgent, TeamApi, TeamMember } from '../src/api/team'
import type {
  TeamGroup,
  TeamGroupsApi,
  TeamGroupsQuery,
} from '../src/api/teamGroups'
import type { QueueState, RunState, SubtaskState, TaskPhase } from '../src/api/types'
import type { ViewId } from '../src/app/navigation'
import { ShellProvider } from '../src/app/ShellProvider'
import { TeamContextRail } from '../src/views/team/contextRail'
import { TeamView } from '../src/views/team/TeamView'

function makeAgent(overrides: Partial<AvailableAgent> = {}): AvailableAgent {
  return {
    id: 'developer',
    kind: 'agent',
    title: 'Developer',
    enabled: true,
    revision: 2,
    template_version: '1',
    connection_ref: 'deepseek',
    conversation_ref: 'task-worker',
    skill_refs: ['implementation'],
    skills_source: 'paths',
    tool_refs: ['view-file'],
    hook_refs: [],
    mcp_refs: [],
    trigger_refs: [],
    availability: {
      state: 'unknown',
      reasons: ['configuration is declared and parsed; runtime health was not checked'],
    },
    executable: true,
    body: 'Implement the change.',
    ...overrides,
  }
}

function makeMember(overrides: Partial<TeamMember> = {}): TeamMember {
  return {
    id: 'member_01ABC',
    kind: 'member',
    title: 'developer',
    state: 'running',
    released: false,
    revision: 3,
    run_ref: 'run_01XYZ',
    role_ref: 'developer',
    template_version: '1',
    connection_ref: 'deepseek',
    skill_refs: ['implementation'],
    tool_policy: { allowed_tools: ['view-file'] },
    assigned_subtask_refs: ['subtask_01A'],
    session_ref: 'sdk-session-1',
    config_hash: 'hash-abc',
    budget: {},
    fail_reason: null,
    availability: { state: 'unknown', reasons: ['no live session check performed'] },
    body: '',
    ...overrides,
  }
}

interface GroupOptions {
  id?: string
  title?: string
  phase?: TaskPhase
  activeRun?: string | null
  lastRun?: string | null
  runState?: RunState
  attempt?: number
  cleanupStatus?: string
  reviewerConfirmed?: boolean | null
  sessionRefs?: string[] | null
  queueState?: QueueState
  memberState?: string | null
  memberRole?: string
  subtaskState?: SubtaskState
  waitingReason?: string | null
  dependsOn?: string[]
  blockedBy?: string[]
  oldMember?: boolean
}

function makeGroup(options: GroupOptions = {}): TeamGroup {
  const taskId = options.id ?? 'task_01TASK'
  const title = options.title ?? 'Build launch page'
  const phase = options.phase ?? 'executing'
  const activeRunId = options.activeRun === undefined ? 'run_01RUN' : options.activeRun
  const lastRunId = options.lastRun === undefined ? activeRunId : options.lastRun
  const runId = activeRunId ?? lastRunId ?? 'run_01RUN'
  const attempt = options.attempt ?? 1
  const runState = options.runState ?? (activeRunId ? 'executing' : 'failed')
  const memberId = 'member_01DEV'
  const subtaskState = options.subtaskState ?? 'running'
  const subtask = {
    id: 'subtask_01PAGE',
    key: 'page',
    capability: 'implementation',
    state: subtaskState,
    depends_on: options.dependsOn ?? [],
    blocked_by: options.blockedBy ?? [],
    assignee_member_ref: memberId,
    waiting_reason: options.waitingReason ?? null,
    acceptance: { status: subtaskState === 'passed' ? 'passed' : 'pending' },
    fail_reason: subtaskState === 'failed' ? 'test failed' : null,
  }
  const member = {
    id: memberId,
    run_ref: runId,
    role_ref: options.memberRole ?? 'engineering-frontend-developer',
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
    state: runState,
    attempt,
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
    fail_reason: runState === 'failed' ? 'worker failed' : null,
    waiting_reason: null,
  }
  const members = [member]
  const runs = [run]
  if (options.oldMember) {
    members.push({
      id: 'member_01OLD',
      run_ref: 'run_01OLD',
      role_ref: 'old-role',
      state: 'released',
      template_version: '1',
      connection_ref: null,
      skill_refs: [],
      capabilities: [],
      assigned_subtask_refs: [],
      assigned_subtasks: [],
      config_hash: 'old-cfg',
      fail_reason: null,
    })
    runs.unshift({
      id: 'run_01OLD',
      state: 'failed',
      attempt: 0,
      plan_source: 'rules',
      plan_hash: 'old-plan',
      team_refs: ['member_01OLD'],
      cleanup: { status: 'done' },
      reviewer_cleanup: null,
      session_refs: [],
      ended_at: '2026-10-17T23:00:00Z',
      fail_reason: 'old attempt failed',
      waiting_reason: null,
    })
  }
  return {
    task: {
      id: taskId,
      title,
      status: phase === 'completed' ? 'done' : 'in-progress',
      phase,
      revision: 1,
      requirements_revision: 1,
      deliverable_revision: 0,
      archived: false,
      active_run: activeRunId,
      last_run: lastRunId,
      queue: {
        state: options.queueState ?? (activeRunId ? 'claimed' : 'not_queued'),
        order: 1,
        queued_at: null,
        owner: null,
        waiting_reason: null,
      },
    },
    active_run: activeRunId ? run : null,
    runs,
    members,
    subtasks: [subtask],
  }
}

function makeApi(agents: AvailableAgent[], members: TeamMember[] = []) {
  const calls: { available: number; members: Array<Record<string, unknown>> } = {
    available: 0,
    members: [],
  }
  const api: TeamApi = {
    async listAvailable() {
      calls.available += 1
      return agents
    },
    async listMembers(query) {
      calls.members.push({ ...query })
      return members
    },
  }
  return { api, calls }
}

function makeGroupsApi(groups: TeamGroup[]) {
  const calls: TeamGroupsQuery[] = []
  const api: TeamGroupsApi = {
    async listGroups(query = {}) {
      calls.push({ ...query })
      return { items: groups, next_cursor: null }
    },
  }
  return { api, calls }
}

function renderTeam(
  api: TeamApi,
  options: {
    groups?: TeamGroup[]
    groupsApi?: TeamGroupsApi
    teamGroupsCapability?: boolean
    taskRef?: string | null
    runRef?: string | null
    selectedItemRef?: string | null
  } = {},
) {
  const groupsFixture = makeGroupsApi(options.groups ?? [])
  const groupsApi = options.groupsApi ?? groupsFixture.api
  const selectItem = vi.fn<(ref: string | null) => void>()
  const navigate = vi.fn<(view: ViewId) => void>()
  const openChatDraft = vi.fn<(message: string) => void>()
  const onOpenTaskChat = vi.fn<(taskRef: string) => void>()
  const onViewTask = vi.fn<(taskRef: string) => void>()
  render(
    <ShellProvider>
      <TeamView
        api={api}
        groupsApi={groupsApi}
        teamGroupsCapability={options.teamGroupsCapability ?? true}
        pollIntervalMs={0}
        taskRef={options.taskRef === undefined ? 'task_01TASK' : options.taskRef}
        runRef={options.runRef ?? null}
        selectedItemRef={
          options.selectedItemRef === undefined ? 'team:available' : options.selectedItemRef
        }
        selectItem={selectItem}
        navigate={navigate}
        openChatDraft={openChatDraft}
        onOpenTaskChat={onOpenTaskChat}
        onViewTask={onViewTask}
      />
    </ShellProvider>,
  )
  return { selectItem, navigate, openChatDraft, onOpenTaskChat, onViewTask, groupsCalls: groupsFixture.calls }
}

beforeEach(() => {
  window.sessionStorage.clear()
  window.history.replaceState(null, '', '/')
})

afterEach(() => {
  cleanup()
})

describe('LG-015/LG-125 Team: available templates', () => {
  it('renders templates with a compiled availability badge (unknown is not success)', async () => {
    const { api } = makeApi([makeAgent()])
    renderTeam(api)
    expect(await screen.findByText('Developer')).toBeInTheDocument()
    expect(screen.getByText('health unknown')).toBeInTheDocument()
    expect(screen.queryByText('available')).toBeNull()
  })

  it('shows an explicit empty state when there are no templates', async () => {
    const { api } = makeApi([])
    renderTeam(api)
    expect(await screen.findByText('No role templates')).toBeInTheDocument()
  })

  it('opens role detail and navigates skill references to Resources with a return position', async () => {
    const { api } = makeApi([makeAgent()])
    const { selectItem, navigate } = renderTeam(api)
    const card = await screen.findByRole('button', { name: /Developer/ })
    fireEvent.click(card)

    expect(await screen.findByText('Declared references')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /skill:implementation/ }))
    expect(selectItem).toHaveBeenCalledWith('resources:skill:implementation')
    expect(navigate).toHaveBeenCalledWith('resources')
    expect(window.sessionStorage.getItem('lg015.team-return')).toContain('team:agent:developer')
  })

  it('opens a Connection reference in Settings at the stable id', async () => {
    const { api } = makeApi([makeAgent()])
    const { selectItem, navigate } = renderTeam(api)
    fireEvent.click(await screen.findByRole('button', { name: /Developer/ }))
    fireEvent.click(await screen.findByRole('button', { name: /connection:deepseek/ }))
    expect(selectItem).toHaveBeenCalledWith('settings:connection:deepseek')
    expect(navigate).toHaveBeenCalledWith('settings')
    expect(navigate).not.toHaveBeenCalledWith('resources')
  })

  it('requests a role through Task Chat instead of starting a worker', async () => {
    const { api } = makeApi([makeAgent()])
    const { navigate, openChatDraft } = renderTeam(api)
    fireEvent.click(await screen.findByRole('button', { name: /Developer/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Request for current task' }))
    expect(openChatDraft).toHaveBeenCalledTimes(1)
    expect(String(openChatDraft.mock.calls[0][0])).toContain('consider recruiting role')
    expect(navigate).toHaveBeenCalledWith('tasks')
  })

  it('blocks a role request without a Task scope', async () => {
    const { api } = makeApi([makeAgent()])
    const { navigate, openChatDraft } = renderTeam(api, { taskRef: null })
    fireEvent.click(await screen.findByRole('button', { name: /Developer/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Request for current task' }))
    expect(openChatDraft).not.toHaveBeenCalled()
    expect(navigate).not.toHaveBeenCalled()
    expect(screen.getByText(/Select a Task before requesting a role/)).toBeInTheDocument()
  })
})

describe('LG-125 Team: grouped Recruited', () => {
  it('defaults to Recruited and shows real Task/Run/member/Subtask facts', async () => {
    const { api } = makeApi([])
    renderTeam(api, {
      groups: [makeGroup()],
      selectedItemRef: null,
    })
    expect(await screen.findByText('Build launch page')).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /Recruited/ })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByText('Running')).toBeInTheDocument()
    expect(screen.getByText('engineering-frontend-developer')).toBeInTheDocument()
    // member.state=ready, but the assigned Subtask is running: display Working.
    expect(screen.getByText('Working')).toBeInTheDocument()
    expect(screen.getByText(/page — Working/)).toBeInTheDocument()
  })

  it('does not mix old Run members into the current team', async () => {
    const { api } = makeApi([])
    renderTeam(api, {
      groups: [makeGroup({ oldMember: true })],
      taskRef: 'task_01TASK',
      selectedItemRef: null,
    })
    expect(await screen.findByText('engineering-frontend-developer')).toBeInTheDocument()
    expect(screen.queryByText('old-role')).toBeNull()
  })

  it('opens an explicit Task chat and Board task with the group Task id', async () => {
    const { api } = makeApi([])
    const { onOpenTaskChat, onViewTask } = renderTeam(api, {
      groups: [makeGroup()],
      selectedItemRef: null,
    })
    await screen.findByText('Build launch page')
    fireEvent.click(screen.getByRole('button', { name: 'Open chat for Build launch page' }))
    fireEvent.click(screen.getByRole('button', { name: 'View task Build launch page' }))
    expect(onOpenTaskChat).toHaveBeenCalledWith('task_01TASK')
    expect(onViewTask).toHaveBeenCalledWith('task_01TASK')
  })
})

describe('LG-015 Team: data-driven secondary rail', () => {
  it('shows real Available templates and Recruited history with no mock data', async () => {
    window.history.replaceState(null, '', '/?task=task_01TASK')
    const { api, calls } = makeApi(
      [makeAgent()],
      [
        makeMember(),
        makeMember({ id: 'member_02REL', role_ref: 'reviewer', state: 'released', released: true }),
      ],
    )
    const onSelect = vi.fn()
    render(
      <ShellProvider>
        <TeamContextRail api={api} selectedId="team:agent:developer" onSelect={onSelect} />
      </ShellProvider>,
    )
    const available = await screen.findByRole('button', { name: /Developer/ })
    expect(available).toHaveAttribute('aria-pressed', 'true')
    expect(await screen.findByRole('button', { name: /reviewer · member_02REL/ })).toBeInTheDocument()
    expect(screen.queryByText('MOCK LAYOUT DATA — not from backend')).toBeNull()
    expect(calls.members[0]).toMatchObject({ taskRef: 'task_01TASK' })
  })
})
