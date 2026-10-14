import { useState } from 'react'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '../src/api/client'
import type {
  ResourceChangeResult,
  ResourceDetail,
  ResourceKind,
  ResourceProposalInput,
  ResourceSummary,
  ResourcesApi,
} from '../src/api/resources'
import { ShellProvider } from '../src/app/ShellProvider'
import { ResourcesView } from '../src/views/resources/ResourcesView'

function makeSummary(overrides: Partial<ResourceSummary> & { id: string; kind: ResourceKind }): ResourceSummary {
  return {
    title: overrides.id,
    enabled: true,
    revision: 1,
    etag: '"1"',
    availability: { state: 'unknown', reasons: ['runtime health was not checked'] },
    ...overrides,
  }
}

function makeDetail(overrides: Partial<ResourceDetail> & { id: string; kind: ResourceKind }): ResourceDetail {
  return {
    title: overrides.id,
    enabled: true,
    revision: 1,
    etag: '"1"',
    availability: { state: 'unknown', reasons: ['runtime health was not checked'] },
    entity: {},
    body: '',
    declared: { enabled: true },
    parsed: { valid: true },
    diagnostics: [],
    references: [],
    inbound_refs: [],
    ...overrides,
  }
}

interface FakeState {
  summaries: Partial<Record<ResourceKind, ResourceSummary[]>>
  details: Record<string, ResourceDetail>
  updateError: ApiError | null
  updateCalls: Array<{ kind: ResourceKind; id: string; input: unknown }>
  listCalls: ResourceKind[]
  proposalError: ApiError | null
  proposalCalls: Array<{ taskId: string; proposal: ResourceProposalInput }>
  proposalResult: ResourceChangeResult
}

function makeApi(initial: Partial<FakeState> = {}): { api: ResourcesApi; state: FakeState } {
  const state: FakeState = {
    summaries: {},
    details: {},
    updateError: null,
    updateCalls: [],
    listCalls: [],
    proposalError: null,
    proposalCalls: [],
    proposalResult: {
      kind: 'resource_change',
      reply: '已按程序校验写入',
      task_id: 'task_01TASK',
      data: { status: 'applied', revision: 5, recorded_in_conversation: true },
    },
    ...initial,
  }
  const api: ResourcesApi = {
    async listResources(kind) {
      state.listCalls.push(kind)
      return { items: state.summaries[kind] ?? [], next_cursor: null }
    },
    async getResource(kind, id) {
      const detail = state.details[`${kind}:${id}`]
      if (!detail) {
        throw new ApiError({
          message: 'not found',
          code: 'not_found',
          httpStatus: 404,
          retryable: false,
        })
      }
      return detail
    },
    async updateResource(kind, id, input) {
      state.updateCalls.push({ kind, id, input })
      if (state.updateError) {
        const error = state.updateError
        state.updateError = null
        throw error
      }
      const current = state.details[`${kind}:${id}`]
      const patch = input.patch as Record<string, unknown>
      const updated: ResourceDetail = {
        ...current,
        title: typeof patch.title === 'string' ? patch.title : current.title,
        enabled: typeof patch.enabled === 'boolean' ? patch.enabled : current.enabled,
        body: input.body ?? current.body,
        revision: (current.revision ?? 0) + 1,
      }
      state.details[`${kind}:${id}`] = updated
      return updated
    },
    async proposeResourceChange(taskId, proposal) {
      state.proposalCalls.push({ taskId, proposal })
      if (state.proposalError) {
        const error = state.proposalError
        state.proposalError = null
        throw error
      }
      return state.proposalResult
    },
  }
  return { api, state }
}

/** Mimics the shell: selection changes flow back as the selectedItemRef prop. */
function ViewWithState({
  api,
  initialRef,
  onNavigate,
  onSelectItem,
}: {
  api: ResourcesApi
  initialRef: string | null
  onNavigate: (view: string) => void
  onSelectItem?: (ref: string | null) => void
}) {
  const [ref, setRef] = useState<string | null>(initialRef)
  return (
    <ShellProvider>
      <ResourcesView
        api={api}
        selectedItemRef={ref}
        selectItem={(next) => {
          setRef(next)
          onSelectItem?.(next)
        }}
        navigate={(view) => onNavigate(view)}
      />
    </ShellProvider>
  )
}

function renderResources(
  api: ResourcesApi,
  {
    initialRef = null,
    onNavigate = vi.fn(),
    onSelectItem = vi.fn(),
  }: {
    initialRef?: string | null
    onNavigate?: (view: string) => void
    onSelectItem?: (ref: string | null) => void
  } = {},
) {
  render(
    <ViewWithState
      api={api}
      initialRef={initialRef}
      onNavigate={onNavigate}
      onSelectItem={onSelectItem}
    />,
  )
  return { onNavigate, onSelectItem }
}

beforeEach(() => {
  window.sessionStorage.clear()
  window.history.replaceState(null, '', '/')
})

afterEach(() => {
  cleanup()
})

describe('LG-015 Resources: catalogue and detail', () => {
  it('lists the selected category and shows availability without faking health', async () => {
    const { api, state } = makeApi({
      summaries: { connection: [makeSummary({ id: 'deepseek', kind: 'connection', title: 'DeepSeek' })] },
      details: {
        'connection:deepseek': makeDetail({
          id: 'deepseek',
          kind: 'connection',
          title: 'DeepSeek',
          entity: { backend: 'openai-compat', model: 'deepseek-v4-flash' },
          references: [
            { field: 'credential_ref', kind: 'credential', ref: 'deepseek-key', state: 'resolved', configured: true },
          ],
        }),
      },
    })
    renderResources(api)
    expect(await screen.findByText('1 Connections')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /DeepSeek/ }))
    expect(await screen.findByText('health unknown')).toBeInTheDocument()
    expect(screen.getByText('openai-compat')).toBeInTheDocument()
    expect(state.listCalls).toContain('connection')
  })

  it('switches category through the internal navigation', async () => {
    const { api, state } = makeApi({
      summaries: {
        connection: [makeSummary({ id: 'deepseek', kind: 'connection', title: 'DeepSeek' })],
        skill: [makeSummary({ id: 'implementation', kind: 'skill' })],
      },
    })
    renderResources(api)
    await screen.findByText('1 Connections')
    fireEvent.click(screen.getByRole('button', { name: 'Skills' }))
    await waitFor(() => expect(state.listCalls).toContain('skill'))
  })
})

describe('LG-015 Resources: connection ownership', () => {
  it('sends Connection edits to Settings instead of building a second model list', async () => {
    const { api } = makeApi({
      summaries: { connection: [makeSummary({ id: 'deepseek', kind: 'connection', title: 'DeepSeek' })] },
      details: {
        'connection:deepseek': makeDetail({
          id: 'deepseek',
          kind: 'connection',
          title: 'DeepSeek',
          entity: { backend: 'openai-compat', model: 'deepseek-v4-flash', base_url: 'https://api.deepseek.com/v1' },
        }),
      },
    })
    const { onNavigate, onSelectItem } = renderResources(api)
    fireEvent.click(await screen.findByRole('button', { name: /DeepSeek/ }))
    // The connection-only detail explains Settings owns the same record.
    expect(await screen.findByText(/same record Settings edits/)).toBeInTheDocument()
    const edit = await screen.findByRole('button', { name: 'Edit in Settings' })
    fireEvent.click(edit)
    expect(onNavigate).toHaveBeenCalledWith('settings')
    // The concrete Connection id travels with the navigation so Settings can
    // select the same record (no second model list).
    expect(onSelectItem).toHaveBeenCalledWith('settings:connection:deepseek')
    // No controlled-change form and no duplicated model editor is rendered.
    expect(screen.queryByRole('button', { name: 'Save controlled change' })).toBeNull()
  })
})

describe('LG-015 Resources: session profiles are templates', () => {
  it('states that a Session Profile is not a live conversation', async () => {
    const { api } = makeApi({
      summaries: { conversation: [makeSummary({ id: 'task-worker', kind: 'conversation', title: 'Task worker' })] },
      details: {
        'conversation:task-worker': makeDetail({
          id: 'task-worker',
          kind: 'conversation',
          title: 'Task worker',
          entity: { session_continuation_mode: 'resume' },
        }),
      },
    })
    renderResources(api, { initialRef: 'session-profiles' })
    fireEvent.click(await screen.findByRole('button', { name: /Task worker/ }))
    expect(await screen.findAllByText(/configuration templates/)).not.toHaveLength(0)
    expect(screen.getByRole('button', { name: 'Open Chat' })).toBeInTheDocument()
  })
})

describe('LG-015 Resources: diagnostics', () => {
  it('renders parsed diagnostics for an invalid resource', async () => {
    const { api } = makeApi({
      summaries: { tool: [makeSummary({ id: 'broken', kind: 'tool', title: 'Broken' })] },
      details: {
        'tool:broken': makeDetail({
          id: 'broken',
          kind: 'tool',
          title: 'Broken',
          parsed: { valid: false },
          diagnostics: [
            { code: 'implementation_missing', message: 'tool.implementation is required', level: 'error', location: 'tool.implementation' },
          ],
          availability: { state: 'invalid', reasons: ['tool frontmatter failed validation'] },
        }),
      },
    })
    renderResources(api, { initialRef: 'tools' })
    fireEvent.click(await screen.findByRole('button', { name: /Broken/ }))
    expect(await screen.findByText('implementation_missing')).toBeInTheDocument()
    expect(screen.getByText('invalid')).toBeInTheDocument()
  })
})

describe('LG-015 Resources: controlled change via Task conversation', () => {
  function hookResource() {
    return makeApi({
      summaries: { hook: [makeSummary({ id: 'task-policy', kind: 'hook', title: 'Task policy' })] },
      details: {
        'hook:task-policy': makeDetail({
          id: 'task-policy',
          kind: 'hook',
          title: 'Task policy',
          revision: 4,
          entity: { handler: 'task-policy' },
          body: '# Policy',
        }),
      },
    })
  }

  it('sends a structured proposal in the current Task conversation', async () => {
    window.history.replaceState(null, '', '/?task=task_01TASK')
    const { api, state } = hookResource()
    renderResources(api, { initialRef: 'hooks' })
    fireEvent.click(await screen.findByRole('button', { name: /Task policy/ }))

    fireEvent.change(await screen.findByLabelText('Title'), { target: { value: 'Policy v2' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save controlled change' }))

    await waitFor(() => expect(state.proposalCalls).toHaveLength(1))
    expect(state.proposalCalls[0]).toMatchObject({
      taskId: 'task_01TASK',
      proposal: {
        kind: 'hook',
        id: 'task-policy',
        expected_revision: 4,
        patch: { title: 'Policy v2', enabled: true },
      },
    })
    expect(await screen.findByText(/Applied through Task chat at revision 5/)).toBeInTheDocument()
  })

  it('guides instead of faking a shared-template edit without a Task scope', async () => {
    const { api, state } = hookResource()
    renderResources(api, { initialRef: 'hooks' })
    fireEvent.click(await screen.findByRole('button', { name: /Task policy/ }))
    fireEvent.click(await screen.findByRole('button', { name: 'Save controlled change' }))

    expect(state.proposalCalls).toHaveLength(0)
    expect(
      await screen.findByText(/Select a Task before changing a shared resource/),
    ).toBeInTheDocument()
  })

  it('surfaces the coordinator-recorded revision conflict', async () => {
    window.history.replaceState(null, '', '/?task=task_01TASK')
    const { api, state } = hookResource()
    state.proposalResult = {
      kind: 'resource_change',
      reply: 'task-policy 修改冲突：期望 revision 4，实际 6。未写入；请重读后再提交。',
      task_id: 'task_01TASK',
      data: { status: 'conflict', error_code: 'revision_conflict', actual_revision: 6 },
    }
    renderResources(api, { initialRef: 'hooks' })
    fireEvent.click(await screen.findByRole('button', { name: /Task policy/ }))
    fireEvent.click(await screen.findByRole('button', { name: 'Save controlled change' }))
    expect(await screen.findByText('Revision conflict')).toBeInTheDocument()
    expect(screen.getByText(/revision_conflict/)).toBeInTheDocument()
  })

  it('surfaces a rejected reference change instead of pretending success', async () => {
    window.history.replaceState(null, '', '/?task=task_01TASK')
    const { api, state } = hookResource()
    state.proposalResult = {
      kind: 'resource_change',
      reply: 'hook:task-policy 修改被拒绝（reference_invalid）：references do not resolve',
      task_id: 'task_01TASK',
      data: { status: 'rejected', error_code: 'reference_invalid' },
    }
    renderResources(api, { initialRef: 'hooks' })
    fireEvent.click(await screen.findByRole('button', { name: /Task policy/ }))
    fireEvent.click(await screen.findByRole('button', { name: 'Save controlled change' }))
    expect(await screen.findByText('Change rejected')).toBeInTheDocument()
    expect(screen.getAllByText(/reference_invalid/).length).toBeGreaterThan(0)
  })
})
