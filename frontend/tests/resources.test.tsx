import { useState } from 'react'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '../src/api/client'
import type {
  ResourceDetail,
  ResourceKind,
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
}

function makeApi(initial: Partial<FakeState> = {}): { api: ResourcesApi; state: FakeState } {
  const state: FakeState = {
    summaries: {},
    details: {},
    updateError: null,
    updateCalls: [],
    listCalls: [],
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
  }
  return { api, state }
}

/** Mimics the shell: selection changes flow back as the selectedItemRef prop. */
function ViewWithState({
  api,
  initialRef,
  onNavigate,
}: {
  api: ResourcesApi
  initialRef: string | null
  onNavigate: (view: string) => void
}) {
  const [ref, setRef] = useState<string | null>(initialRef)
  return (
    <ShellProvider>
      <ResourcesView
        api={api}
        selectedItemRef={ref}
        selectItem={setRef}
        navigate={(view) => onNavigate(view)}
      />
    </ShellProvider>
  )
}

function renderResources(
  api: ResourcesApi,
  { initialRef = null, onNavigate = vi.fn() }: { initialRef?: string | null; onNavigate?: (view: string) => void } = {},
) {
  render(<ViewWithState api={api} initialRef={initialRef} onNavigate={onNavigate} />)
  return { onNavigate }
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
    const { onNavigate } = renderResources(api)
    fireEvent.click(await screen.findByRole('button', { name: /DeepSeek/ }))
    const edit = await screen.findByRole('button', { name: 'Edit in Settings' })
    fireEvent.click(edit)
    expect(onNavigate).toHaveBeenCalledWith('settings')
    // No controlled-change form and no duplicated model editor is rendered.
    expect(screen.queryByRole('button', { name: 'Save controlled change' })).toBeNull()
    expect(screen.getByText(/same record Settings edits/)).toBeInTheDocument()
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

describe('LG-015 Resources: controlled change', () => {
  it('submits an allow-listed change with the expected revision', async () => {
    const { api, state } = makeApi({
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
    renderResources(api, { initialRef: 'hooks' })
    fireEvent.click(await screen.findByRole('button', { name: /Task policy/ }))

    fireEvent.change(await screen.findByLabelText('Title'), { target: { value: 'Policy v2' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save controlled change' }))

    await waitFor(() => expect(state.updateCalls).toHaveLength(1))
    expect(state.updateCalls[0]).toMatchObject({
      kind: 'hook',
      id: 'task-policy',
      input: { expected_revision: 4, patch: { title: 'Policy v2', enabled: true } },
    })
  })

  it('surfaces a revision conflict as a real error', async () => {
    const { api, state } = makeApi({
      summaries: { hook: [makeSummary({ id: 'task-policy', kind: 'hook', title: 'Task policy' })] },
      details: {
        'hook:task-policy': makeDetail({
          id: 'task-policy',
          kind: 'hook',
          title: 'Task policy',
          revision: 4,
          entity: { handler: 'task-policy' },
        }),
      },
    })
    state.updateError = new ApiError({
      message: 'stale write',
      code: 'revision_conflict',
      httpStatus: 409,
      retryable: false,
    })
    renderResources(api, { initialRef: 'hooks' })
    fireEvent.click(await screen.findByRole('button', { name: /Task policy/ }))
    fireEvent.click(await screen.findByRole('button', { name: 'Save controlled change' }))
    expect(await screen.findByText('Revision conflict')).toBeInTheDocument()
    expect(screen.getByText(/revision_conflict/)).toBeInTheDocument()
  })

  it('surfaces a rejected reference change instead of pretending success', async () => {
    const { api, state } = makeApi({
      summaries: { hook: [makeSummary({ id: 'task-policy', kind: 'hook', title: 'Task policy' })] },
      details: {
        'hook:task-policy': makeDetail({
          id: 'task-policy',
          kind: 'hook',
          title: 'Task policy',
          entity: { handler: 'task-policy' },
        }),
      },
    })
    state.updateError = new ApiError({
      message: 'references resources that do not resolve',
      code: 'reference_invalid',
      httpStatus: 422,
      retryable: false,
    })
    renderResources(api, { initialRef: 'hooks' })
    fireEvent.click(await screen.findByRole('button', { name: /Task policy/ }))
    fireEvent.click(await screen.findByRole('button', { name: 'Save controlled change' }))
    expect(await screen.findByText('Change rejected')).toBeInTheDocument()
    expect(screen.getByText(/reference_invalid/)).toBeInTheDocument()
  })
})
