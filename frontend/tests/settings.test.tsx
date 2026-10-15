import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { ApiError } from '../src/api/client'
import type {
  ConnectionCreateInput,
  ConnectionTestInput,
  ConnectionTestResult,
  ConnectionUpdateInput,
  ConnectionView,
  GlobalSettingsView,
  SettingsApi,
  SettingsUpdateInput,
} from '../src/api/settings'
import { SettingsView } from '../src/views/settings/SettingsView'

function makeConnection(overrides: Partial<ConnectionView> = {}): ConnectionView {
  return {
    id: 'deepseek-primary',
    title: 'DeepSeek (primary)',
    enabled: true,
    revision: 3,
    content_hash: 'hash-3',
    backend: 'openai-compat',
    model: 'deepseek-v4-flash',
    base_url: 'https://api.deepseek.com/v1',
    credential_ref: 'deepseek-key',
    credential: {
      ref: 'deepseek-key',
      configured: true,
      source: 'secret_store',
      version: 'cred_1',
    },
    references: {
      connection_id: 'deepseek-primary',
      default_roles: ['coordinator', 'worker'],
      agent_refs: [],
    },
    ...overrides,
  }
}

function makeSettings(overrides: Partial<GlobalSettingsView> = {}): GlobalSettingsView {
  return {
    revision: 2,
    exists: true,
    content_hash: 'settings-hash-2',
    default_coordinator_connection_ref: 'deepseek-primary',
    default_worker_connection_ref: 'deepseek-primary',
    default_reviewer_connection_ref: 'deepseek-primary',
    defaults: {
      coordinator: { ...makeConnection(), resolved: true },
      worker: { ...makeConnection(), resolved: true },
      reviewer: { ...makeConnection(), resolved: true },
    },
    ...overrides,
  }
}

function makeTestResult(overrides: Partial<ConnectionTestResult> = {}): ConnectionTestResult {
  return {
    test_id: 'ctest_1',
    connection_id: 'deepseek-primary',
    connection_revision: 3,
    credential_ref: 'deepseek-key',
    credential_version: 'cred_1',
    backend: 'openai-compat',
    model: 'deepseek-v4-flash',
    base_url_host: 'api.deepseek.com',
    started_at: '2026-10-15T00:00:00Z',
    finished_at: '2026-10-15T00:00:01Z',
    layers: [
      { name: 'config_parse', status: 'passed', detail: 'backend=openai-compat', duration_ms: null },
      { name: 'credential', status: 'passed', detail: 'source=secret_store', duration_ms: null },
      { name: 'capability', status: 'declared', detail: 'sdk=0.1.22', duration_ms: null },
      { name: 'runtime_network', status: 'passed', detail: 'model=deepseek-v4-flash', duration_ms: 120 },
      { name: 'tool_probe', status: 'skipped', detail: 'not requested', duration_ms: null },
      { name: 'structured_output', status: 'skipped', detail: 'not requested', duration_ms: null },
    ],
    overall: 'verified',
    note: 'layers are separate',
    ...overrides,
  }
}

interface FakeState {
  connections: ConnectionView[]
  settings: GlobalSettingsView
  updateConnectionCalls: Array<{ id: string; input: ConnectionUpdateInput }>
  updateSettingsCalls: SettingsUpdateInput[]
  createConnectionCalls: ConnectionCreateInput[]
  removeCredentialCalls: string[]
  testConnectionCalls: Array<{ id: string; input: ConnectionTestInput }>
  nextUpdateError: ApiError | null
  testResult: ConnectionTestResult
}

function makeFakeApi(initial?: Partial<FakeState>): { api: SettingsApi; state: FakeState } {
  const state: FakeState = {
    connections: [makeConnection()],
    settings: makeSettings(),
    updateConnectionCalls: [],
    updateSettingsCalls: [],
    createConnectionCalls: [],
    removeCredentialCalls: [],
    testConnectionCalls: [],
    nextUpdateError: null,
    testResult: makeTestResult(),
    ...initial,
  }

  const api: SettingsApi = {
    async listConnections() {
      return state.connections.map((connection) => ({ ...connection }))
    },
    async getConnection(id) {
      const found = state.connections.find((connection) => connection.id === id)
      if (!found) throw new Error('not found')
      return { ...found }
    },
    async getSettings() {
      return state.settings
    },
    async createConnection(input) {
      state.createConnectionCalls.push(input)
      const created = makeConnection({
        id: input.id,
        title: input.title ?? input.id,
        revision: 1,
        enabled: input.enabled ?? true,
        model: input.model ?? null,
        base_url: input.base_url ?? null,
        credential_ref: input.credential_ref ?? null,
        credential: {
          ref: input.credential_ref ?? '',
          configured: Boolean(input.credential_value),
          source: input.credential_value ? 'secret_store' : null,
          version: input.credential_value ? 'cred_new' : null,
        },
        references: { connection_id: input.id, default_roles: [], agent_refs: [] },
      })
      state.connections = [...state.connections, created]
      return created
    },
    async updateConnection(id, input) {
      state.updateConnectionCalls.push({ id, input })
      if (state.nextUpdateError) {
        const error = state.nextUpdateError
        state.nextUpdateError = null
        throw error
      }
      const index = state.connections.findIndex((connection) => connection.id === id)
      const current = state.connections[index]
      const removing = input.credential_action === 'remove'
      const updated: ConnectionView = {
        ...current,
        revision: current.revision + 1,
        title: input.title ?? current.title,
        enabled: input.enabled ?? current.enabled,
        model: input.model !== undefined ? input.model : current.model,
        base_url: input.base_url !== undefined ? input.base_url : current.base_url,
        credential_ref: removing
          ? null
          : (input.credential_ref !== undefined
              ? input.credential_ref
              : current.credential_ref),
        credential: removing
          ? { ref: '', configured: false, source: null, version: null }
          : current.credential,
      }
      if (input.credential_action === 'set' && input.credential_value) {
        updated.credential = {
          ref: updated.credential_ref ?? '',
          configured: true,
          source: 'secret_store',
          version: 'cred_2',
        }
      }
      state.connections[index] = updated
      return updated
    },
    async updateSettings(input) {
      state.updateSettingsCalls.push(input)
      const updated: GlobalSettingsView = {
        ...state.settings,
        revision: state.settings.revision + 1,
        default_coordinator_connection_ref:
          input.default_coordinator_connection_ref !== undefined
            ? input.default_coordinator_connection_ref
            : state.settings.default_coordinator_connection_ref,
        default_worker_connection_ref:
          input.default_worker_connection_ref !== undefined
            ? input.default_worker_connection_ref
            : state.settings.default_worker_connection_ref,
        default_reviewer_connection_ref:
          input.default_reviewer_connection_ref !== undefined
            ? input.default_reviewer_connection_ref
            : state.settings.default_reviewer_connection_ref,
      }
      state.settings = updated
      return updated
    },
    async setCredential(ref, _value) {
      return { ref, configured: true, source: 'secret_store', version: 'cred_2' }
    },
    async keepCredential(ref) {
      return { ref, configured: true, source: 'secret_store', version: 'cred_1' }
    },
    async removeCredential(ref) {
      state.removeCredentialCalls.push(ref)
      return { ref, configured: false, source: null, version: null }
    },
    async testConnection(id, input) {
      state.testConnectionCalls.push({ id, input })
      return state.testResult
    },
  }

  return { api, state }
}

beforeEach(() => {
  window.sessionStorage.clear()
  window.localStorage.clear()
})

afterEach(() => {
  cleanup()
})

describe('LG-026 Settings: load and list', () => {
  it('loads one Connection authority from the settings endpoints', async () => {
    const { api, state } = makeFakeApi()
    render(<SettingsView api={api} />)
    expect(await screen.findByRole('button', { name: /DeepSeek \(primary\)/ })).toBeInTheDocument()
    expect(state.connections).toHaveLength(1)
    // Same list drives the defaults selector (no second provider list).
    expect(screen.getByLabelText('Default coordinator connection')).toBeInTheDocument()
  })

  it('selects the Connection record located by id from Resources', async () => {
    const { api } = makeFakeApi({
      connections: [
        makeConnection({ id: 'deepseek-primary', title: 'DeepSeek (primary)' }),
        makeConnection({ id: 'deepseek-backup', title: 'DeepSeek (backup)' }),
      ],
    })
    render(<SettingsView api={api} connectionId="deepseek-backup" taskRef="task_01TASK" />)
    const selected = await screen.findByRole('button', { name: /DeepSeek \(backup\)/ })
    expect(selected).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: /DeepSeek \(primary\)/ })).toHaveAttribute(
      'aria-pressed',
      'false',
    )
    // The Task scope is preserved while Settings is open.
    expect(screen.getByText('task_01TASK')).toBeInTheDocument()
  })

  it('marks a planned backend as unavailable and disables executable actions', async () => {
    const { api } = makeFakeApi({
      connections: [
        makeConnection({
          id: 'gemini-one',
          title: 'Gemini (planned)',
          backend: 'gemini',
          credential_ref: null,
          credential: { ref: '', configured: false, source: null, version: null },
          references: { connection_id: 'gemini-one', default_roles: [], agent_refs: [] },
        }),
      ],
      settings: makeSettings({ default_coordinator_connection_ref: null, default_worker_connection_ref: null }),
    })
    render(<SettingsView api={api} />)
    expect(await screen.findByText(/gemini · planned/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save changes' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Test connection' })).toBeDisabled()
    expect(screen.getByText(/not a verified executable backend/)).toBeInTheDocument()
  })
})

describe('LG-026 Settings: save and credentials', () => {
  it('saves with expected_revision, sends a write-only key and clears it', async () => {
    const { api, state } = makeFakeApi()
    render(<SettingsView api={api} />)
    await screen.findByRole('button', { name: /DeepSeek \(primary\)/ })

    fireEvent.change(screen.getByLabelText('Title'), {
      target: { value: 'DeepSeek edited' },
    })
    const secret = screen.getByLabelText(/New API key/)
    fireEvent.change(secret, { target: { value: 'sk-test-secret-value' } })
    expect(secret).toHaveValue('sk-test-secret-value')

    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))

    await waitFor(() => expect(state.updateConnectionCalls).toHaveLength(1))
    const call = state.updateConnectionCalls[0]
    expect(call.id).toBe('deepseek-primary')
    expect(call.input.expected_revision).toBe(3)
    expect(call.input.title).toBe('DeepSeek edited')
    expect(call.input.credential_action).toBe('set')
    expect(call.input.credential_value).toBe('sk-test-secret-value')

    // The value is cleared from the form after submit and never persisted.
    await waitFor(() => expect(secret).toHaveValue(''))
    expect(JSON.stringify(window.sessionStorage)).not.toContain('sk-test-secret-value')
    expect(JSON.stringify(window.localStorage)).not.toContain('sk-test-secret-value')
    expect(await screen.findByText(/Saved revision 4/)).toBeInTheDocument()
  })

  it('removes a credential reference and deletes the stored secret', async () => {
    const { api, state } = makeFakeApi()
    render(<SettingsView api={api} />)
    await screen.findByRole('button', { name: /DeepSeek \(primary\)/ })

    fireEvent.click(screen.getByRole('button', { name: 'Remove credential' }))
    await waitFor(() => expect(state.removeCredentialCalls).toEqual(['deepseek-key']))
    expect(state.updateConnectionCalls[0].input.credential_action).toBe('remove')
    expect(await screen.findByText(/removed from the local secret store/)).toBeInTheDocument()
  })

  it('surfaces a real revision conflict and reloads the latest revision', async () => {
    const { api, state } = makeFakeApi()
    state.nextUpdateError = new ApiError({
      message: 'stale write',
      code: 'revision_conflict',
      httpStatus: 409,
      retryable: false,
      details: { expected_revision: 3, actual_revision: 4 },
    })
    // The connection moved on elsewhere: reload must observe revision 4.
    state.connections[0] = { ...state.connections[0], revision: 4 }

    render(<SettingsView api={api} />)
    await screen.findByRole('button', { name: /DeepSeek \(primary\)/ })
    fireEvent.change(screen.getByLabelText('Title'), {
      target: { value: 'Edited during conflict' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))

    expect(await screen.findByText('Revision conflict')).toBeInTheDocument()

    // A second save uses the reloaded revision, not the stale one.
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    await waitFor(() => expect(state.updateConnectionCalls).toHaveLength(2))
    expect(state.updateConnectionCalls[1].input.expected_revision).toBe(4)
  })

  it('shows the real unauthorized error when no runtime token is available', async () => {
    const { api, state } = makeFakeApi()
    state.nextUpdateError = new ApiError({
      message: 'sensitive endpoint requires an injected authorization mechanism',
      code: 'unauthorized',
      httpStatus: 401,
      retryable: false,
    })
    render(<SettingsView api={api} />)
    await screen.findByRole('button', { name: /DeepSeek \(primary\)/ })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))

    expect(await screen.findByText('Request failed')).toBeInTheDocument()
    expect(screen.getByText(/unauthorized/)).toBeInTheDocument()
    expect(screen.queryByText(/^Saved revision/)).toBeNull()
  })
})

describe('LG-026 Settings: layered test connection', () => {
  it('renders separate layers and marks a stale result', async () => {
    const { api, state } = makeFakeApi({
      testResult: makeTestResult({ connection_revision: 2 }),
    })
    render(<SettingsView api={api} />)
    await screen.findByRole('button', { name: /DeepSeek \(primary\)/ })

    fireEvent.click(screen.getByRole('button', { name: 'Test connection' }))
    await waitFor(() => expect(state.testConnectionCalls).toHaveLength(1))
    expect(state.testConnectionCalls[0].input.expected_revision).toBe(3)
    expect(state.testConnectionCalls[0].input.allow_network).toBe(true)

    expect(await screen.findByText('runtime_network')).toBeInTheDocument()
    expect(screen.getByText('tool_probe')).toBeInTheDocument()
    expect(screen.getByText('stale')).toBeInTheDocument()
    // Network success is not presented as full SDK verification.
    expect(screen.getByText('declared')).toBeInTheDocument()
  })
})

describe('LG-026 Settings: defaults', () => {
  it('saves coordinator/worker defaults with the settings revision', async () => {
    const { api, state } = makeFakeApi()
    render(<SettingsView api={api} />)
    await screen.findByText('Default models')

    fireEvent.change(screen.getByLabelText('Default worker connection'), {
      target: { value: '' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save defaults' }))

    await waitFor(() => expect(state.updateSettingsCalls).toHaveLength(1))
    expect(state.updateSettingsCalls[0].expected_revision).toBe(2)
    expect(state.updateSettingsCalls[0].default_worker_connection_ref).toBeNull()
    expect(await screen.findByText(/Defaults saved at revision 3/)).toBeInTheDocument()
  })

  it('saves the independent reviewer default explicitly (LG-017)', async () => {
    const { api, state } = makeFakeApi({
      connections: [
        makeConnection({ id: 'deepseek-primary', title: 'DeepSeek (primary)' }),
        makeConnection({ id: 'deepseek-reviewer', title: 'DeepSeek (reviewer)' }),
      ],
    })
    render(<SettingsView api={api} />)
    await screen.findByText('Default models')

    fireEvent.change(screen.getByLabelText('Default reviewer connection'), {
      target: { value: 'deepseek-reviewer' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save defaults' }))

    await waitFor(() => expect(state.updateSettingsCalls).toHaveLength(1))
    expect(state.updateSettingsCalls[0].default_reviewer_connection_ref).toBe(
      'deepseek-reviewer',
    )
  })

  it('clears the reviewer default to an honest no-reviewer state', async () => {
    const { api, state } = makeFakeApi({
      settings: makeSettings({ default_reviewer_connection_ref: 'deepseek-primary' }),
    })
    render(<SettingsView api={api} />)
    await screen.findByText('Default models')

    fireEvent.change(screen.getByLabelText('Default reviewer connection'), {
      target: { value: '' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save defaults' }))

    await waitFor(() => expect(state.updateSettingsCalls).toHaveLength(1))
    expect(state.updateSettingsCalls[0].default_reviewer_connection_ref).toBeNull()
    expect(
      screen.getByText(/worker connection is never silently/),
    ).toBeInTheDocument()
  })
})

describe('LG-026 Settings: create', () => {
  it('creates a connection from the typed form when the list is empty', async () => {
    const { api, state } = makeFakeApi({ connections: [] })
    render(<SettingsView api={api} />)

    fireEvent.click(await screen.findByRole('button', { name: 'New connection' }))
    fireEvent.change(screen.getByLabelText(/Connection id/), {
      target: { value: 'deepseek-secondary' },
    })
    fireEvent.change(screen.getByLabelText('Title'), {
      target: { value: 'DeepSeek secondary' },
    })
    fireEvent.change(screen.getByLabelText(/Credential reference/), {
      target: { value: 'deepseek-secondary-key' },
    })
    fireEvent.change(screen.getByLabelText(/New API key/), {
      target: { value: 'sk-new-key' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Create connection' }))

    await waitFor(() => expect(state.createConnectionCalls).toHaveLength(1))
    expect(state.createConnectionCalls[0]).toMatchObject({
      id: 'deepseek-secondary',
      backend: 'openai-compat',
      credential_ref: 'deepseek-secondary-key',
      credential_value: 'sk-new-key',
    })
  })
})
