import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { ApiError } from '../src/api/client'
import type {
  ConnectionCreateInput,
  ConnectionTestResult,
  ConnectionUpdateInput,
  ConnectionView,
  DraftConnectionTestInput,
  DraftConnectionTestResult,
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
      { name: 'config_parse', status: 'passed', detail: 'ok', duration_ms: null },
      { name: 'credential', status: 'passed', detail: 'configured', duration_ms: null },
    ],
    overall: 'verified',
    note: 'layers are separate',
    ...overrides,
  }
}

function makeDraftResult(): DraftConnectionTestResult {
  return { ...makeTestResult(), draft: true, connection_ref: null, revision: null }
}

interface FakeState {
  connections: ConnectionView[]
  settings: GlobalSettingsView
  updateConnectionCalls: Array<{ id: string; input: ConnectionUpdateInput }>
  updateSettingsCalls: SettingsUpdateInput[]
  createConnectionCalls: ConnectionCreateInput[]
  removeCredentialCalls: string[]
  draftTestCalls: DraftConnectionTestInput[]
  deleteCalls: string[]
  nextUpdateError: ApiError | null
}

function makeFakeApi(initial?: Partial<FakeState>): { api: SettingsApi; state: FakeState } {
  const state: FakeState = {
    connections: [makeConnection()],
    settings: makeSettings(),
    updateConnectionCalls: [],
    updateSettingsCalls: [],
    createConnectionCalls: [],
    removeCredentialCalls: [],
    draftTestCalls: [],
    deleteCalls: [],
    nextUpdateError: null,
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
          : input.credential_ref !== undefined
            ? input.credential_ref
            : current.credential_ref,
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
    async setCredential(ref) {
      return { ref, configured: true, source: 'secret_store', version: 'cred_2' }
    },
    async keepCredential(ref) {
      return { ref, configured: true, source: 'secret_store', version: 'cred_1' }
    },
    async removeCredential(ref) {
      state.removeCredentialCalls.push(ref)
      return { ref, configured: false, source: null, version: null }
    },
    async testConnection() {
      return makeTestResult()
    },
    async testDraftConnection(input) {
      state.draftTestCalls.push(input)
      return makeDraftResult()
    },
    async updateEmbedding() {
      throw new Error('embedding API is not used in this test')
    },
    async testDraftEmbedding() {
      throw new Error('embedding API is not used in this test')
    },
    async deleteConnection(id) {
      state.deleteCalls.push(id)
      state.connections = state.connections.filter(
        (connection) => connection.id !== id,
      )
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

function openDetails(summaryText: string): void {
  const summary = screen.getByText(summaryText, { selector: 'summary' })
  const details = summary.closest('details')
  if (details) details.setAttribute('open', '')
}

describe('LG-026 Settings: list and defaults', () => {
  it('loads one Connection authority as a list with defaults in a separate section', async () => {
    const { api, state } = makeFakeApi()
    render(<SettingsView api={api} />)
    expect(await screen.findByText('DeepSeek (primary)')).toBeInTheDocument()
    expect(state.connections).toHaveLength(1)
    expect(screen.getByRole('button', { name: 'New connection' })).toBeInTheDocument()
    expect(
      screen.getByText('Default models', { selector: 'summary' }),
    ).toBeInTheDocument()
    // No always-open long editor.
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(screen.queryByRole('combobox', { name: 'Provider' })).toBeNull()
  })

  it('saves coordinator/worker defaults with the settings revision', async () => {
    const { api, state } = makeFakeApi()
    render(<SettingsView api={api} />)
    await screen.findByText('Default models', { selector: 'summary' })
    openDetails('Default models')
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
    await screen.findByText('Default models', { selector: 'summary' })
    openDetails('Default models')
    fireEvent.change(screen.getByLabelText('Default reviewer connection'), {
      target: { value: 'deepseek-reviewer' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save defaults' }))

    await waitFor(() => expect(state.updateSettingsCalls).toHaveLength(1))
    expect(state.updateSettingsCalls[0].default_reviewer_connection_ref).toBe(
      'deepseek-reviewer',
    )
  })
})

describe('LG-026 Settings: save, conflict and credentials', () => {
  it('saves with expected_revision, sends a write-only key, clears it and closes', async () => {
    const { api, state } = makeFakeApi()
    render(<SettingsView api={api} />)
    fireEvent.click(
      await screen.findByRole('button', { name: 'Edit DeepSeek (primary)' }),
    )
    await screen.findByRole('dialog')

    fireEvent.change(screen.getByLabelText(/^Name/), {
      target: { value: 'DeepSeek edited' },
    })
    const secret = screen.getByLabelText(/API key/)
    fireEvent.change(secret, { target: { value: 'sk-test-secret-value' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))

    await waitFor(() => expect(state.updateConnectionCalls).toHaveLength(1))
    const call = state.updateConnectionCalls[0]
    expect(call.id).toBe('deepseek-primary')
    expect(call.input.expected_revision).toBe(3)
    expect(call.input.title).toBe('DeepSeek edited')
    expect(call.input.credential_action).toBe('set')
    expect(call.input.credential_value).toBe('sk-test-secret-value')

    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(await screen.findByText('DeepSeek edited')).toBeInTheDocument()
    expect(JSON.stringify(window.sessionStorage)).not.toContain('sk-test-secret-value')
    expect(JSON.stringify(window.localStorage)).not.toContain('sk-test-secret-value')
  })

  it('surfaces a real revision conflict, reloads the latest revision and retries safely', async () => {
    const { api, state } = makeFakeApi()
    state.nextUpdateError = new ApiError({
      message: 'stale write',
      code: 'revision_conflict',
      httpStatus: 409,
      retryable: false,
      details: { expected_revision: 3, actual_revision: 4 },
    })
    state.connections[0] = { ...state.connections[0], revision: 4 }

    render(<SettingsView api={api} />)
    fireEvent.click(
      await screen.findByRole('button', { name: 'Edit DeepSeek (primary)' }),
    )
    await screen.findByRole('dialog')
    fireEvent.change(screen.getByLabelText(/^Name/), {
      target: { value: 'Edited during conflict' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))

    expect(await screen.findByText('Revision conflict')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    await waitFor(() => expect(state.updateConnectionCalls).toHaveLength(2))
    expect(state.updateConnectionCalls[1].input.expected_revision).toBe(4)
  })

  it('shows the real unauthorized error inline and preserves the draft/key', async () => {
    const { api, state } = makeFakeApi()
    state.nextUpdateError = new ApiError({
      message: 'sensitive endpoint requires an injected authorization mechanism',
      code: 'unauthorized',
      httpStatus: 401,
      retryable: false,
    })
    render(<SettingsView api={api} />)
    fireEvent.click(
      await screen.findByRole('button', { name: 'Edit DeepSeek (primary)' }),
    )
    await screen.findByRole('dialog')
    fireEvent.change(screen.getByLabelText(/API key/), {
      target: { value: 'sk-keep-after-error' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))

    expect(await screen.findByText('Request failed')).toBeInTheDocument()
    expect(screen.getByText(/unauthorized/)).toBeInTheDocument()
    expect(screen.getByLabelText(/API key/)).toHaveValue('sk-keep-after-error')
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('removes a credential only through the explicit Advanced action', async () => {
    const { api, state } = makeFakeApi()
    render(<SettingsView api={api} />)
    fireEvent.click(
      await screen.findByRole('button', { name: 'Edit DeepSeek (primary)' }),
    )
    await screen.findByRole('dialog')
    openDetails('Advanced')
    fireEvent.click(
      screen.getByRole('button', { name: 'Remove saved credential…' }),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Remove credential' }))

    await waitFor(() => expect(state.removeCredentialCalls).toEqual(['deepseek-key']))
    expect(state.updateConnectionCalls[0].input.credential_action).toBe('remove')
    expect(await screen.findByText(/removed from the local secret store/)).toBeInTheDocument()
  })

  it('preserves an old custom OpenAI-compatible record without injecting optional fields', async () => {
    const { api, state } = makeFakeApi({
      connections: [
        makeConnection({
          id: 'local-ollama',
          title: 'Local Ollama',
          model: 'llama3',
          base_url: 'http://127.0.0.1:11434/v1',
          credential_ref: 'ollama-key',
          auth_mode: null,
        }),
      ],
    })
    render(<SettingsView api={api} />)
    fireEvent.click(
      await screen.findByRole('button', { name: 'Edit Local Ollama' }),
    )
    await screen.findByRole('dialog')
    expect(screen.getByRole('combobox', { name: 'Provider' })).toHaveValue(
      'legacy-openai',
    )
    fireEvent.change(screen.getByLabelText(/^Name/), {
      target: { value: 'Local Ollama preserved' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))

    await waitFor(() => expect(state.updateConnectionCalls).toHaveLength(1))
    const payload = state.updateConnectionCalls[0].input
    expect(payload.backend).toBeUndefined()
    expect(payload.auth_mode).toBeUndefined()
    expect(payload.base_url).toBe('http://127.0.0.1:11434/v1')
    expect(payload.credential_action).toBe('keep')
    expect(payload.credential_value).toBeUndefined()
  })
})
