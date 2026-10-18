import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { AvailableAgent, TeamApi } from '../src/api/team'
import type { ViewId } from '../src/app/navigation'
import { ShellProvider } from '../src/app/ShellProvider'
import { TeamView } from '../src/views/team/TeamView'

const PIN = '652b2692f8d8ec2b1f1a38e559073e287dfdc469'

function makeAgent(overrides: Partial<AvailableAgent> = {}): AvailableAgent {
  return {
    id: 'engineering-frontend-developer',
    kind: 'agent',
    title: 'Frontend Developer',
    enabled: true,
    revision: 0,
    template_version: '1',
    connection_ref: null,
    conversation_ref: null,
    skill_refs: [],
    skills_source: 'inline',
    tool_refs: ['view-file', 'create-file', 'edit-file'],
    hook_refs: [],
    mcp_refs: [],
    trigger_refs: [],
    availability: {
      state: 'missing_dependency',
      reasons: ['no explicit connection_ref and no default worker connection configured'],
    },
    executable: false,
    body: 'Imported role guidance.',
    role_category: 'engineering',
    capabilities: ['implementation'],
    agency_source: {
      repository: 'https://github.com/msitarzewski/agency-agents',
      commit: PIN,
      path: 'engineering/engineering-frontend-developer.md',
      blob_sha: '68cf7fe861d8af600b619d62c9cde1625e6e4578',
      sha256: '35961da50f408e00eb6189c87825ac5e62e6b1bf9de3dee198a95536c6d2619e',
      license: 'MIT',
      copyright: 'Copyright (c) 2025 AgentLand Contributors',
    },
    seed: { version: 1, update_available: false },
    summary: 'Expert frontend developer specializing in modern web technologies.',
    unsupported_reasons: [],
    capability_notes: [],
    recruitable: true,
    ...overrides,
  }
}

function makeApi(agents: AvailableAgent[]): TeamApi {
  return {
    async listAvailable() {
      return agents
    },
    async listMembers() {
      return []
    },
  }
}

function renderTeam(agents: AvailableAgent[]) {
  const navigate = vi.fn<(view: ViewId) => void>()
  render(
    <ShellProvider>
      <TeamView
        api={makeApi(agents)}
        taskRef="task_01TASK"
        runRef={null}
        selectedItemRef="team:available"
        teamGroupsCapability={false}
        selectItem={vi.fn()}
        navigate={navigate}
        openChatDraft={vi.fn()}
      />
    </ShellProvider>,
  )
  return { navigate }
}

beforeEach(() => {
  window.sessionStorage.clear()
  window.history.replaceState(null, '', '/')
})

afterEach(() => {
  cleanup()
})

describe('LG-120 complete Available role library', () => {
  it('paginates the complete catalog instead of truncating it', async () => {
    const agents = Array.from({ length: 60 }, (_, index) => {
      const number = String(index).padStart(2, '0')
      return makeAgent({
        id: `role-${number}`,
        title: `Role ${number}`,
        role_category: index % 2 === 0 ? 'engineering' : 'marketing',
        capabilities: index % 2 === 0 ? ['implementation'] : ['writing'],
        summary: `Responsibility for role ${number}.`,
      })
    })
    renderTeam(agents)
    expect(await screen.findByText('60 of 60 role templates')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Role 00/ })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Role 24/ })).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(await screen.findByText('Page 2 of 3')).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: /Role 24/ })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Role 00/ })).toBeNull()
  })

  it('searches and filters by category and capability across the whole catalog', async () => {
    const agents = [
      makeAgent({ id: 'frontend', title: 'Frontend Developer' }),
      makeAgent({
        id: 'content',
        title: 'Content Creator',
        role_category: 'marketing',
        capabilities: ['writing'],
        summary: 'Creates clear campaign copy.',
      }),
      makeAgent({
        id: 'reviewer',
        title: 'Code Reviewer',
        role_category: 'engineering',
        capabilities: ['review'],
        summary: 'Reviews changes for regressions.',
      }),
    ]
    renderTeam(agents)
    await screen.findByText('3 of 3 role templates')

    fireEvent.change(screen.getByLabelText('Search roles'), {
      target: { value: 'campaign' },
    })
    expect(await screen.findByText('1 of 3 role templates')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Content Creator/ })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Frontend Developer/ })).toBeNull()

    fireEvent.change(screen.getByLabelText('Search roles'), { target: { value: '' } })
    fireEvent.change(screen.getByLabelText('Category'), { target: { value: 'engineering' } })
    expect(await screen.findByText('2 of 3 role templates')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Capability'), { target: { value: 'review' } })
    expect(await screen.findByText('1 of 3 role templates')).toBeInTheDocument()
  })

  it('shows source, license and unsupported state without claiming execution', async () => {
    const research = makeAgent({
      id: 'research-synthesist',
      title: 'Research Synthesist',
      role_category: 'research',
      capabilities: ['research'],
      tool_refs: [],
      recruitable: false,
      summary: 'Synthesises source material into evidence.',
      unsupported_reasons: [
        'unsupported: research requires a web tool, which is not available in this version',
      ],
      availability: {
        state: 'unsupported',
        reasons: ['research requires a web tool'],
      },
      agency_source: {
        repository: 'https://github.com/msitarzewski/agency-agents',
        commit: PIN,
        path: 'research/research-synthesist.md',
        blob_sha: 'ff5741421e8cdbc953a930f9b54aff78f3715677',
        sha256: '3618b4a2a73523147731ae38ac4096cea0e83a7de930f55ea9ea6c69e3c77f30',
        license: 'MIT',
        copyright: 'Copyright (c) 2025 AgentLand Contributors',
      },
    })
    renderTeam([research])
    const card = await screen.findByRole('button', { name: /Research Synthesist/ })
    expect(card).toHaveTextContent('unsupported')
    fireEvent.click(card)

    expect((await screen.findAllByText(/requires a web tool/)).length).toBeGreaterThan(0)
    expect(screen.getByText('Source & license')).toBeInTheDocument()
    expect(screen.getByText('research/research-synthesist.md')).toBeInTheDocument()
    expect(screen.getByText(/MIT · Copyright/)).toBeInTheDocument()
    expect(screen.getByText('Capabilities')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Request for current task' })).toBeDisabled()
  })

  it('keeps a disabled template distinct from an unsupported role', async () => {
    renderTeam([
      makeAgent({
        enabled: false,
        recruitable: false,
        availability: { state: 'disabled', reasons: ['declared enabled=false'] },
      }),
    ])
    const card = await screen.findByRole('button', { name: /Frontend Developer/ })
    expect(card).toHaveTextContent('disabled')
    expect(card).not.toHaveTextContent('unsupported')
    fireEvent.click(card)
    expect(screen.getByRole('button', { name: 'Request for current task' })).toBeDisabled()
  })

  it('distinguishes a recruitable role that still needs a connection from unsupported', async () => {
    renderTeam([makeAgent()])
    const card = await screen.findByRole('button', { name: /Frontend Developer/ })
    expect(card).toHaveTextContent('needs setup')
    fireEvent.click(card)
    expect(screen.queryByText('executable')).toBeNull()
    expect(screen.getByRole('button', { name: 'Request for current task' })).toBeEnabled()
    expect(screen.getByText(/Imported guidance only/)).toBeInTheDocument()
  })
})
