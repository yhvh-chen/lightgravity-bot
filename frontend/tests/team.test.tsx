import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { AvailableAgent, TeamApi, TeamMember } from '../src/api/team'
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

function makeApi(agents: AvailableAgent[], members: TeamMember[]) {
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

function renderTeam(
  api: TeamApi,
  options: {
    taskRef?: string | null
    runRef?: string | null
    selectedItemRef?: string | null
  } = {},
) {
  const selectItem = vi.fn<(ref: string | null) => void>()
  const navigate = vi.fn<(view: ViewId) => void>()
  const openChatDraft = vi.fn<(message: string) => void>()
  render(
    <ShellProvider>
      <TeamView
        api={api}
        taskRef={options.taskRef === undefined ? 'task_01TASK' : options.taskRef}
        runRef={options.runRef ?? null}
        selectedItemRef={options.selectedItemRef ?? null}
        selectItem={selectItem}
        navigate={navigate}
        openChatDraft={openChatDraft}
      />
    </ShellProvider>,
  )
  return { selectItem, navigate, openChatDraft }
}

beforeEach(() => {
  window.sessionStorage.clear()
  window.history.replaceState(null, '', '/')
})

afterEach(() => {
  cleanup()
})

describe('LG-015 Team: available templates', () => {
  it('renders templates with a compiled availability badge (unknown is not success)', async () => {
    const { api } = makeApi([makeAgent()], [])
    renderTeam(api)
    expect(await screen.findByText('Developer')).toBeInTheDocument()
    expect(screen.getByText('health unknown')).toBeInTheDocument()
    expect(screen.queryByText('available')).toBeNull()
  })

  it('shows an explicit empty state when there are no templates', async () => {
    const { api } = makeApi([], [])
    renderTeam(api)
    expect(await screen.findByText('No role templates')).toBeInTheDocument()
  })

  it('opens role detail and navigates skill references to Resources with a return position', async () => {
    const { api } = makeApi([makeAgent()], [])
    const { selectItem, navigate } = renderTeam(api)
    const card = await screen.findByRole('button', { name: /Developer/ })
    fireEvent.click(card)

    expect(await screen.findByText('Declared references')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /skill:implementation/ }))
    expect(selectItem).toHaveBeenCalledWith('resources:skill:implementation')
    expect(navigate).toHaveBeenCalledWith('resources')
    expect(window.sessionStorage.getItem('lg015.team-return')).toContain('team:agent:developer')
  })

  it('requests a role through Task Chat instead of starting a worker', async () => {
    const { api } = makeApi([makeAgent()], [])
    const { navigate, openChatDraft } = renderTeam(api)
    fireEvent.click(await screen.findByRole('button', { name: /Developer/ }))
    fireEvent.click(await screen.findByRole('button', { name: 'Request for current task' }))
    expect(openChatDraft).toHaveBeenCalledTimes(1)
    expect(String(openChatDraft.mock.calls[0][0])).toContain('consider recruiting role')
    expect(navigate).toHaveBeenCalledWith('chat')
  })

  it('blocks a role request without a Task scope', async () => {
    const { api } = makeApi([makeAgent()], [])
    const { navigate, openChatDraft } = renderTeam(api, { taskRef: null })
    fireEvent.click(await screen.findByRole('button', { name: /Developer/ }))
    fireEvent.click(await screen.findByRole('button', { name: 'Request for current task' }))
    expect(openChatDraft).not.toHaveBeenCalled()
    expect(navigate).not.toHaveBeenCalled()
    expect(screen.getByText(/Select a Task before requesting a role/)).toBeInTheDocument()
  })
})

describe('LG-015 Team: recruited members', () => {
  it('excludes released members from the current team but keeps them in history', async () => {
    const { api } = makeApi(
      [],
      [
        makeMember(),
        makeMember({
          id: 'member_02REL',
          role_ref: 'reviewer',
          state: 'released',
          released: true,
        }),
      ],
    )
    renderTeam(api)
    const recruitedTab = await screen.findByRole('tab', { name: /Recruited \(1\)/ })
    fireEvent.click(recruitedTab)
    expect(await screen.findByText(/developer · member_01ABC/)).toBeInTheDocument()
    expect(screen.queryByText(/reviewer · member_02REL/)).toBeNull()

    fireEvent.click(screen.getByLabelText(/Show released history/))
    expect(await screen.findByText(/reviewer · member_02REL/)).toBeInTheDocument()
  })

  it('distinguishes a released current team from never recruited', async () => {
    const { api } = makeApi([], [makeMember({ state: 'released', released: true })])
    renderTeam(api)
    fireEvent.click(await screen.findByRole('tab', { name: /Recruited \(0\)/ }))
    expect(await screen.findByText('Current team released')).toBeInTheDocument()

    const other = makeApi([], [])
    cleanup()
    renderTeam(other.api, { taskRef: 'task_other' })
    fireEvent.click(await screen.findByRole('tab', { name: /Recruited \(0\)/ }))
    expect(await screen.findByText('No members recruited yet')).toBeInTheDocument()
  })

  it('shows the pinned configuration version for a member', async () => {
    const { api } = makeApi([], [makeMember()])
    renderTeam(api)
    fireEvent.click(await screen.findByRole('tab', { name: /Recruited \(1\)/ }))
    fireEvent.click(await screen.findByRole('button', { name: /developer · member_01ABC/ }))
    expect(await screen.findByText('Pinned configuration')).toBeInTheDocument()
    expect(screen.getByText('hash-abc')).toBeInTheDocument()
    expect(screen.getByText(/do not hot-swap/)).toBeInTheDocument()
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
