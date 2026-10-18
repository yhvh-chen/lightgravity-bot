import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

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
} from '../src/api/settings'
import type { AuthMeResponse } from '../src/api/teamAuth'
import { AuthProvider, useAuth } from '../src/app/AuthProvider'
import { SettingsView } from '../src/views/settings/SettingsView'

const DEEPSEEK_BASE_URL = 'https://api.deepseek.com/v1'

function makeConnection(overrides: Partial<ConnectionView> = {}): ConnectionView {
  return {
    id: 'deepseek-primary',
    title: 'DeepSeek (primary)',
    enabled: true,
    revision: 3,
    content_hash: 'hash-3',
    backend: 'openai-compat',
    model: 'deepseek-v4-flash',
    base_url: DEEPSEEK_BASE_URL,
    credential_ref: 'deepseek-primary-key',
    credential: {
      ref: 'deepseek-primary-key',
      configured: true,
      source: 'secret_store',
      version: 'cred_1',
    },
    references: {
      connection_id: 'deepseek-primary',
      default_roles: [],
      agent_refs: [],
    },
    ...overrides,
  }
}

function makeSettings(): GlobalSettingsView {
  return {
    revision: 2,
    exists: true,
    content_hash: 'settings-hash-2',
    default_coordinator_connection_ref: null,
    default_worker_connection_ref: null,
    default_reviewer_connection_ref: null,
    defaults: { coordinator: null, worker: null, reviewer: null },
  }
}

function makeTestResult(
  overrides: Partial<ConnectionTestResult> = {},
): ConnectionTestResult {
  return {
    test_id: 'ctest_1',
    connection_id: 'deepseek-primary',
    connection_revision: 3,
    credential_ref: 'deepseek-primary-key',
    credential_version: 'cred_1',
    backend: 'openai-compat',
    model: 'deepseek-v4-flash',
    base_url_host: 'api.deepseek.com',
    started_at: '2026-10-17T00:00:00Z',
    finished_at: '2026-10-17T00:00:01Z',
    layers: [
      { name: 'config_parse', status: 'passed', detail: 'ok', duration_ms: null },
      { name: 'credential', status: 'passed', detail: 'configured', duration_ms: null },
      {
        name: 'runtime_network',
        status: 'passed',
        detail: 'model=deepseek-v4-flash',
        duration_ms: 120,
      },
    ],
    overall: 'verified',
    note: 'layers are separate',
    ...overrides,
  }
}

function makeDraftResult(
  overrides: Partial<DraftConnectionTestResult> = {},
): DraftConnectionTestResult {
  return {
    ...makeTestResult(),
    draft: true,
    connection_ref: null,
    revision: null,
    ...overrides,
  }
}

interface FakeState {
  connections: ConnectionView[]
  createCalls: ConnectionCreateInput[]
  updateCalls: Array<{ id: string; input: ConnectionUpdateInput }>
  draftTestCalls: DraftConnectionTestInput[]
  deleteCalls: Array<{ id: string; revision?: number }>
  removeCredentialCalls: string[]
  nextUpdateError: ApiError | null
  nextDeleteError: ApiError | null
  nextDraftError: ApiError | null
  draftResult: DraftConnectionTestResult
}

function makeFakeApi(initial?: Partial<FakeState>): {
  api: SettingsApi
  state: FakeState
} {
  const state: FakeState = {
    connections: [makeConnection()],
    createCalls: [],
    updateCalls: [],
    draftTestCalls: [],
    deleteCalls: [],
    removeCredentialCalls: [],
    nextUpdateError: null,
    nextDeleteError: null,
    nextDraftError: null,
    draftResult: makeDraftResult(),
    ...initial,
  }

  const api: SettingsApi = {
    async listConnections() {
      return state.connections.map((connection) => ({
        ...connection,
        credential: { ...connection.credential },
        references: { ...connection.references },
      }))
    },
    async getConnection(id) {
      const found = state.connections.find((connection) => connection.id === id)
      if (!found) throw new Error('not found')
      return { ...found }
    },
    async getSettings() {
      return makeSettings()
    },
    async createConnection(input) {
      state.createCalls.push(input)
      const created = makeConnection({
        id: input.id,
        title: input.title ?? input.id,
        enabled: input.enabled ?? true,
        revision: 1,
        content_hash: 'hash-new',
        backend: input.backend ?? 'openai-compat',
        model: input.model ?? null,
        base_url: input.base_url ?? null,
        credential_ref: input.credential_ref ?? null,
        credential: {
          ref: input.credential_ref ?? '',
          configured: Boolean(input.credential_value),
          source: input.credential_value ? 'secret_store' : null,
          version: input.credential_value ? 'cred_new' : null,
        },
        auth_mode: input.auth_mode ?? null,
        project: input.project ?? null,
        location: input.location ?? null,
        model_path: input.model_path ?? null,
        litert_backend: input.litert_backend ?? null,
        last_test: null,
        references: { connection_id: input.id, default_roles: [], agent_refs: [] },
      })
      state.connections = [...state.connections, created]
      return created
    },
    async updateConnection(id, input) {
      state.updateCalls.push({ id, input })
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
        backend: input.backend ?? current.backend,
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
      if (input.auth_mode !== undefined) updated.auth_mode = input.auth_mode
      if (input.project !== undefined) updated.project = input.project
      if (input.location !== undefined) updated.location = input.location
      if (input.model_path !== undefined) updated.model_path = input.model_path
      if (input.litert_backend !== undefined) {
        updated.litert_backend = input.litert_backend
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
    async updateSettings() {
      return makeSettings()
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
      if (state.nextDraftError) {
        const error = state.nextDraftError
        state.nextDraftError = null
        throw error
      }
      return state.draftResult
    },
    async updateEmbedding() {
      throw new Error('embedding API is not used in this test')
    },
    async testDraftEmbedding() {
      throw new Error('embedding API is not used in this test')
    },
    async deleteConnection(id, expectedRevision) {
      state.deleteCalls.push({ id, revision: expectedRevision })
      if (state.nextDeleteError) {
        const error = state.nextDeleteError
        state.nextDeleteError = null
        throw error
      }
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

async function openNewConnection(): Promise<HTMLElement> {
  fireEvent.click(await screen.findByRole('button', { name: 'New connection' }))
  return screen.findByRole('dialog')
}

async function openEditConnection(title: string): Promise<HTMLElement> {
  fireEvent.click(await screen.findByRole('button', { name: `Edit ${title}` }))
  return screen.findByRole('dialog')
}

describe('LG-110 landing list', () => {
  it('shows Name/Provider/Model and only backend-persisted test status, with no editor mounted', async () => {
    const { api } = makeFakeApi({
      connections: [
        makeConnection({
          id: 'tested',
          title: 'Tested connection',
          last_test: {
            overall: 'verified',
            finished_at: '2026-10-17T10:00:00Z',
            connection_revision: 3,
            credential_version: 'cred_1',
          },
        }),
        makeConnection({
          id: 'untested',
          title: 'Untested connection',
          revision: 5,
          last_test: null,
        }),
      ],
    })
    render(<SettingsView api={api} />)

    expect(await screen.findByText('Tested connection')).toBeInTheDocument()
    expect(screen.getAllByText('DeepSeek (OpenAI-compatible)').length).toBeGreaterThan(0)
    expect(screen.getByText(/verified · 2026-10-17T10:00:00Z/)).toBeInTheDocument()
    expect(screen.getByText('Not tested')).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(screen.queryByRole('combobox', { name: 'Provider' })).toBeNull()
    expect(screen.queryByLabelText(/API key/)).toBeNull()
  })

  it('marks a persisted test stale instead of promoting it to current verification', async () => {
    const { api } = makeFakeApi({
      connections: [
        makeConnection({
          revision: 7,
          last_test: {
            overall: 'verified',
            finished_at: '2026-10-17T10:00:00Z',
            connection_revision: 6,
            credential_version: 'cred_1',
          },
        }),
      ],
    })
    render(<SettingsView api={api} />)
    expect(await screen.findByText(/verified · stale/)).toBeInTheDocument()
  })
})

describe('LG-110 modal lifecycle and accessibility', () => {
  it('opens one accessible modal, traps Tab, makes the background inert and returns focus on close', async () => {
    const { api, state } = makeFakeApi()
    render(<SettingsView api={api} />)
    const trigger = await screen.findByRole('button', {
      name: 'Edit DeepSeek (primary)',
    })
    trigger.focus()
    const dialog = await openEditConnection('DeepSeek (primary)')

    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(dialog).toHaveAccessibleName(/Edit DeepSeek/)
    expect(document.querySelector('[inert]')).not.toBeNull()
    expect(state.draftTestCalls).toHaveLength(0)
    expect(state.updateCalls).toHaveLength(0)

    const save = screen.getByRole('button', { name: 'Save changes' })
    save.focus()
    fireEvent.keyDown(dialog, { key: 'Tab' })
    expect(screen.getByRole('button', { name: 'Close connection dialog' })).toHaveFocus()

    fireEvent.keyDown(dialog, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    await waitFor(() => expect(trigger).toHaveFocus())
  })

  it('keeps the draft when the dirty-close confirmation is cancelled, then discards on request', async () => {
    const { api, state } = makeFakeApi()
    render(<SettingsView api={api} />)
    const trigger = await screen.findByRole('button', {
      name: 'Edit DeepSeek (primary)',
    })
    await openEditConnection('DeepSeek (primary)')

    fireEvent.change(screen.getByLabelText(/^Name/), {
      target: { value: 'Unsaved draft name' },
    })
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' })
    expect(screen.getByText(/Discard this unsaved draft/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Keep editing' }))
    expect(screen.getByLabelText(/^Name/)).toHaveValue('Unsaved draft name')
    expect(state.updateCalls).toHaveLength(0)

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.getByText(/Discard this unsaved draft/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Discard and close' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    await waitFor(() => expect(trigger).toHaveFocus())
    expect(state.updateCalls).toHaveLength(0)
  })

  it('clears typed secrets on provider switch and never writes them to storage or the URL', async () => {
    const { api } = makeFakeApi({ connections: [] })
    render(<SettingsView api={api} />)
    await openNewConnection()
    const key = screen.getByLabelText(/API key/)
    fireEvent.change(key, { target: { value: 'sk-never-persist-me' } })
    expect(key).toHaveValue('sk-never-persist-me')

    fireEvent.change(screen.getByRole('combobox', { name: 'Provider' }), {
      target: { value: 'gemini-api' },
    })
    expect(screen.getByLabelText(/API key/)).toHaveValue('')
    expect(JSON.stringify(window.localStorage)).not.toContain('sk-never-persist-me')
    expect(JSON.stringify(window.sessionStorage)).not.toContain('sk-never-persist-me')
    expect(window.location.href).not.toContain('sk-never-persist-me')
  })
})

describe('LG-110 create/edit and custom endpoint', () => {

  it('keeps the preset endpoint in Advanced and requires a fresh key before testing its edits', async () => {
    const { api, state } = makeFakeApi()
    render(<SettingsView api={api} />)
    const dialog = await openEditConnection('DeepSeek (primary)')
    const fields = dialog.querySelector('[aria-label="Connection fields"]')!
    const advanced = screen.getByLabelText('Advanced connection settings')
    const endpoint = screen.getByLabelText('Base URL')
    expect(advanced).not.toHaveAttribute('open')
    expect(advanced).toContainElement(endpoint)
    expect(fields).not.toContainElement(endpoint)

    fireEvent.click(screen.getByText('Advanced', { selector: 'summary' }))
    fireEvent.change(endpoint, { target: { value: 'https://custom.example/v1' } })
    const testButton = screen.getByRole('button', { name: 'Test connection' })
    expect(testButton).toBeDisabled()
    expect(state.draftTestCalls).toHaveLength(0)

    fireEvent.change(screen.getByLabelText(/^API key/), {
      target: { value: 'dummy-new-endpoint-key' },
    })
    expect(testButton).toBeEnabled()
    fireEvent.click(testButton)
    await waitFor(() => expect(state.draftTestCalls).toHaveLength(1))
    expect(state.draftTestCalls[0]).toMatchObject({
      connection: { base_url: 'https://custom.example/v1' },
      credential_value: 'dummy-new-endpoint-key',
    })
    expect(state.createCalls).toHaveLength(0)
    expect(state.updateCalls).toHaveLength(0)
  })

  it('creates a genuinely selectable custom OpenAI-compatible connection with Base URL required and no Test/Save coupling', async () => {
    const { api, state } = makeFakeApi({ connections: [] })
    render(<SettingsView api={api} />)
    await openNewConnection()

    fireEvent.change(screen.getByRole('combobox', { name: 'Provider' }), {
      target: { value: 'custom-openai' },
    })
    expect(screen.getByLabelText(/Base URL/)).toBeInTheDocument()
    expect(screen.getByText(/may be blocked before any network request/)).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText(/^Name/), {
      target: { value: 'My custom server' },
    })
    fireEvent.change(screen.getByLabelText(/API key/), {
      target: { value: 'sk-custom-secret' },
    })
    fireEvent.change(screen.getByLabelText(/Base URL/), {
      target: { value: 'https://custom.example/v1' },
    })
    fireEvent.change(screen.getByLabelText(/^Model/), {
      target: { value: 'my-model' },
    })

    fireEvent.click(screen.getByRole('button', { name: 'Save connection' }))
    await waitFor(() => expect(state.createCalls).toHaveLength(1))
    expect(state.createCalls[0]).toMatchObject({
      title: 'My custom server',
      backend: 'openai-compat',
      auth_mode: 'proxy_api_key',
      base_url: 'https://custom.example/v1',
      model: 'my-model',
      credential_value: 'sk-custom-secret',
    })
    expect(state.draftTestCalls).toHaveLength(0)
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    const rowHeading = await screen.findByText('My custom server')
    await waitFor(() => expect(rowHeading.closest('li')).toHaveFocus())
    // The fake backend reports no persisted test; saving must not invent one.
    expect(screen.getByText('Not tested')).toBeInTheDocument()
  })

  it('edits with expected_revision and optional provider fields without auto-testing', async () => {
    const { api, state } = makeFakeApi({
      connections: [
        makeConnection({
          id: 'gemini-one',
          title: 'Gemini API',
          backend: 'gemini',
          auth_mode: 'api_key',
          model: 'gemini-3.8-flash',
          base_url: null,
          credential_ref: 'gemini-one-key',
        }),
      ],
    })
    render(<SettingsView api={api} />)
    await openEditConnection('Gemini API')
    fireEvent.change(screen.getByLabelText(/^Model/), {
      target: { value: 'gemini-3.8-pro' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))

    await waitFor(() => expect(state.updateCalls).toHaveLength(1))
    expect(state.updateCalls[0]).toMatchObject({
      id: 'gemini-one',
      input: {
        expected_revision: 3,
        model: 'gemini-3.8-pro',
        auth_mode: 'api_key',
        credential_action: 'keep',
      },
    })
    expect(state.updateCalls[0].input.backend).toBeUndefined()
    expect(state.draftTestCalls).toHaveLength(0)
  })
})

describe('LG-110 draft Test → Save', () => {
  it('tests the unsaved draft envelope without saving, marks edits stale, then saves separately', async () => {
    const { api, state } = makeFakeApi()
    render(<SettingsView api={api} />)
    await openEditConnection('DeepSeek (primary)')

    fireEvent.change(screen.getByLabelText(/^Model/), {
      target: { value: 'deepseek-draft-model' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Test connection' }))

    await waitFor(() => expect(state.draftTestCalls).toHaveLength(1))
    expect(state.draftTestCalls[0]).toMatchObject({
      existing_connection_id: 'deepseek-primary',
      expected_revision: 3,
      allow_network: true,
      connection: {
        backend: 'openai-compat',
        model: 'deepseek-draft-model',
        base_url: DEEPSEEK_BASE_URL,
        auth_mode: 'proxy_api_key',
      },
    })
    expect(state.draftTestCalls[0].credential_value).toBeUndefined()
    expect(state.updateCalls).toHaveLength(0)
    expect(await screen.findByText('draft · not saved')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText(/^Model/), {
      target: { value: 'deepseek-draft-model-2' },
    })
    expect(screen.getByText('stale')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    await waitFor(() => expect(state.updateCalls).toHaveLength(1))
    expect(state.updateCalls[0].input.model).toBe('deepseek-draft-model-2')
    expect(state.draftTestCalls).toHaveLength(1)
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  })

  it('keeps the draft and key after a failed test, and a valid Save still works', async () => {
    const { api, state } = makeFakeApi()
    state.nextDraftError = new ApiError({
      message: 'upstream rejected the draft key',
      code: 'validation_failed',
      httpStatus: 422,
      retryable: false,
    })
    render(<SettingsView api={api} />)
    await openEditConnection('DeepSeek (primary)')

    fireEvent.change(screen.getByLabelText(/API key/), {
      target: { value: 'sk-retry-me' },
    })
    fireEvent.change(screen.getByLabelText(/^Model/), {
      target: { value: 'deepseek-retry-model' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Test connection' }))
    expect(await screen.findByText('Draft test failed')).toBeInTheDocument()
    expect(screen.getByLabelText(/API key/)).toHaveValue('sk-retry-me')
    expect(screen.getByLabelText(/^Model/)).toHaveValue('deepseek-retry-model')
    expect(state.updateCalls).toHaveLength(0)

    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    await waitFor(() => expect(state.updateCalls).toHaveLength(1))
    expect(state.updateCalls[0].input.credential_value).toBe('sk-retry-me')
    expect(state.updateCalls[0].input.model).toBe('deepseek-retry-model')
  })

  it('requires a fresh key when the credential recipient changes and never reuses the old key', async () => {
    const { api, state } = makeFakeApi()
    render(<SettingsView api={api} />)
    await openEditConnection('DeepSeek (primary)')
    fireEvent.change(screen.getByRole('combobox', { name: 'Provider' }), {
      target: { value: 'gemini-api' },
    })

    const testButton = screen.getByRole('button', { name: 'Test connection' })
    expect(testButton).toBeDisabled()
    expect(
      screen.getByText(/saved key is not sent to a different provider or host/),
    ).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText(/API key/), {
      target: { value: 'sk-brand-new-gemini-key' },
    })
    expect(testButton).toBeEnabled()
    fireEvent.click(testButton)
    await waitFor(() => expect(state.draftTestCalls).toHaveLength(1))
    expect(state.draftTestCalls[0]).toMatchObject({
      credential_value: 'sk-brand-new-gemini-key',
      existing_connection_id: 'deepseek-primary',
      connection: { backend: 'gemini', auth_mode: 'api_key' },
    })
    expect(state.draftTestCalls[0].connection.base_url).toBeNull()
  })

  it('discards a late draft result after the same modal draft changes', async () => {
    const { api, state } = makeFakeApi()
    let release: (() => void) | null = null
    api.testDraftConnection = vi.fn(
      (input) =>
        new Promise<DraftConnectionTestResult>((resolve) => {
          state.draftTestCalls.push(input)
          release = () => resolve(makeDraftResult({ model: 'late-old-model' }))
        }),
    )
    render(<SettingsView api={api} />)
    await openEditConnection('DeepSeek (primary)')

    fireEvent.click(screen.getByRole('button', { name: 'Test connection' }))
    await waitFor(() => expect(release).not.toBeNull())
    fireEvent.change(screen.getByLabelText(/^Model/), {
      target: { value: 'new-model-after-test-started' },
    })
    await act(async () => {
      release?.()
    })
    expect(
      await screen.findByText(/late result was discarded/),
    ).toBeInTheDocument()
    expect(screen.queryByText('draft · not saved')).toBeNull()
  })

  it('never applies a late result from a closed modal to a reopened one', async () => {
    const { api, state } = makeFakeApi()
    let release: (() => void) | null = null
    api.testDraftConnection = vi.fn(
      (input) =>
        new Promise<DraftConnectionTestResult>((resolve) => {
          state.draftTestCalls.push(input)
          release = () => resolve(makeDraftResult({ model: 'closed-modal-result' }))
        }),
    )
    render(<SettingsView api={api} />)
    await openEditConnection('DeepSeek (primary)')
    fireEvent.click(screen.getByRole('button', { name: 'Test connection' }))
    await waitFor(() => expect(release).not.toBeNull())
    fireEvent.click(screen.getByRole('button', { name: 'Close connection dialog' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())

    await openEditConnection('DeepSeek (primary)')
    await act(async () => {
      release?.()
    })
    expect(screen.queryByText('draft · not saved')).toBeNull()
    expect(screen.queryByText('closed-modal-result')).toBeNull()
  })
  it('retains the real Vertex Project + ADC fields and tests them as an unsaved draft', async () => {
    const { api, state } = makeFakeApi({ connections: [] })
    render(<SettingsView api={api} />)
    await openNewConnection()
    fireEvent.change(screen.getByRole('combobox', { name: 'Provider' }), {
      target: { value: 'vertex-adc' },
    })
    expect(screen.queryByLabelText(/API key/)).toBeNull()
    expect(screen.getByLabelText(/Project ID/)).toBeInTheDocument()
    expect(screen.getByLabelText(/Location/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Test connection' })).toBeDisabled()
    expect(state.draftTestCalls).toHaveLength(0)

    fireEvent.change(screen.getByLabelText(/Project ID/), {
      target: { value: 'project-1' },
    })
    fireEvent.change(screen.getByLabelText(/Location/), {
      target: { value: 'us-central1' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Test connection' }))
    await waitFor(() => expect(state.draftTestCalls).toHaveLength(1))
    expect(state.draftTestCalls[0]).toMatchObject({
      expected_revision: 0,
      allow_network: true,
      connection: {
        backend: 'vertex',
        auth_mode: 'adc',
        project: 'project-1',
        location: 'us-central1',
      },
    })
    expect(state.draftTestCalls[0].credential_value).toBeUndefined()
  })

  it('retains the real LiteRT model-path/backend fields and never sends a model or key', async () => {
    const { api, state } = makeFakeApi({ connections: [] })
    render(<SettingsView api={api} />)
    await openNewConnection()
    fireEvent.change(screen.getByRole('combobox', { name: 'Provider' }), {
      target: { value: 'litert' },
    })
    expect(screen.queryByLabelText(/API key/)).toBeNull()
    expect(screen.queryByLabelText(/^Model$/)).toBeNull()
    fireEvent.change(screen.getByLabelText(/Model file path/), {
      target: { value: '/models/gemma.litertlm' },
    })
    fireEvent.change(screen.getByLabelText(/LiteRT backend/), {
      target: { value: 'CPU' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Test connection' }))
    await waitFor(() => expect(state.draftTestCalls).toHaveLength(1))
    expect(state.draftTestCalls[0]).toMatchObject({
      connection: {
        backend: 'litert',
        auth_mode: 'none',
        model: null,
        model_path: '/models/gemma.litertlm',
        litert_backend: 'CPU',
      },
    })
    expect(state.draftTestCalls[0].credential_value).toBeUndefined()
  })

  it('does not apply a late Save response after an external target opens another modal', async () => {
    const { api } = makeFakeApi({
      connections: [
        makeConnection({ id: 'deepseek-primary', title: 'DeepSeek (primary)' }),
        makeConnection({ id: 'deepseek-backup', title: 'DeepSeek (backup)' }),
      ],
    })
    let release: (() => void) | null = null
    api.updateConnection = vi.fn(
      () =>
        new Promise<ConnectionView>((resolve) => {
          release = () =>
            resolve(
              makeConnection({
                id: 'deepseek-primary',
                title: 'primary saved later',
                revision: 4,
              }),
            )
        }),
    )
    const view = render(
      <SettingsView api={api} connectionId="deepseek-primary" />,
    )
    await screen.findByRole('heading', { name: 'Edit DeepSeek (primary)' })
    fireEvent.change(screen.getByLabelText(/^Name/), {
      target: { value: 'primary edit' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    await waitFor(() => expect(release).not.toBeNull())

    view.rerender(<SettingsView api={api} connectionId="deepseek-backup" />)
    expect(
      await screen.findByRole('heading', { name: 'Edit DeepSeek (backup)' }),
    ).toBeInTheDocument()
    await act(async () => {
      release?.()
    })
    expect(
      screen.getByRole('heading', { name: 'Edit DeepSeek (backup)' }),
    ).toBeInTheDocument()
    expect(screen.queryByText('primary saved later')).toBeNull()
  })
})

describe('LG-110 deletion and references', () => {
  it('requires inline confirmation and lets the server block deletion honestly', async () => {
    const { api, state } = makeFakeApi({
      connections: [
        makeConnection({
          id: 'referenced',
          title: 'Referenced connection',
          references: {
            connection_id: 'referenced',
            default_roles: ['worker'],
            agent_refs: [],
          },
        }),
      ],
    })
    render(<SettingsView api={api} />)
    fireEvent.click(
      await screen.findByRole('button', { name: 'Delete Referenced connection' }),
    )
    expect(screen.getByText(/Delete "Referenced connection"/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Delete connection' }))
    expect(screen.getByText(/still referenced by default worker/)).toBeInTheDocument()
    expect(state.deleteCalls).toHaveLength(0)
    expect(screen.getByText('Referenced connection')).toBeInTheDocument()
  })

  it('deletes an unreferenced connection only after inline confirmation', async () => {
    const { api, state } = makeFakeApi()
    render(<SettingsView api={api} />)
    fireEvent.click(
      await screen.findByRole('button', { name: 'Delete DeepSeek (primary)' }),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Delete connection' }))
    await waitFor(() => expect(state.deleteCalls).toHaveLength(1))
    expect(await screen.findByText(/Deleted "DeepSeek \(primary\)"/)).toBeInTheDocument()
    expect(screen.queryByText('DeepSeek (primary)')).toBeNull()
  })

  it('surfaces a real server delete rejection without silently removing the row', async () => {
    const { api, state } = makeFakeApi()
    state.nextDeleteError = new ApiError({
      message: 'connection is referenced by a member',
      code: 'referenced',
      httpStatus: 409,
      retryable: false,
    })
    render(<SettingsView api={api} />)
    fireEvent.click(
      await screen.findByRole('button', { name: 'Delete DeepSeek (primary)' }),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Delete connection' }))
    await waitFor(() => expect(state.deleteCalls).toHaveLength(1))
    expect(await screen.findByText(/referenced by a member/)).toBeInTheDocument()
    expect(screen.getByText('DeepSeek (primary)')).toBeInTheDocument()
  })
})

describe('LG-110 preserved boundaries', () => {
  const MEMBER_PROBE = async (): Promise<AuthMeResponse> => ({
    mode: 'team',
    authenticated: true,
    username: 'alice',
    role: 'member',
  })

  function MemberBoundaryHarness({ api }: { api: SettingsApi }) {
    const { status, isAdmin } = useAuth()
    if (status !== 'ready') return <p>checking auth</p>
    return (
      <div>
        <p>{isAdmin ? 'role:admin' : 'role:member'}</p>
        <SettingsView api={api} connectionId="deepseek-primary" />
      </div>
    )
  }

  it('never fetches Models/Connections for a team member', async () => {
    const listConnections = vi.fn(async () => [makeConnection()])
    const getSettings = vi.fn(async () => makeSettings())
    const api = { ...makeFakeApi().api, listConnections, getSettings } as SettingsApi

    render(
      <AuthProvider probe={MEMBER_PROBE}>
        <MemberBoundaryHarness api={api} />
      </AuthProvider>,
    )

    expect(await screen.findByText('role:member')).toBeInTheDocument()
    expect(listConnections).not.toHaveBeenCalled()
    expect(getSettings).not.toHaveBeenCalled()
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(
      screen.getByText(/configuration is managed by administrators/),
    ).toBeInTheDocument()
  })

  it('opens the deeplink target exactly once and shows an unknown target without selecting another', async () => {
    const { api } = makeFakeApi({
      connections: [
        makeConnection({ id: 'deepseek-primary', title: 'DeepSeek (primary)' }),
        makeConnection({ id: 'deepseek-backup', title: 'DeepSeek (backup)' }),
      ],
    })
    const view = render(
      <SettingsView api={api} connectionId="deepseek-backup" />,
    )
    expect(
      await screen.findByRole('heading', { name: 'Edit DeepSeek (backup)' }),
    ).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Close connection dialog' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(screen.queryByRole('heading', { name: 'Edit DeepSeek (backup)' })).toBeNull()

    view.rerender(
      <SettingsView api={api} connectionId="missing-connection" />,
    )
    expect(await screen.findByText('Connection not found')).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(screen.queryByText('DeepSeek (primary)')).toBeInTheDocument()
    expect(screen.queryByText('DeepSeek (backup)')).toBeInTheDocument()
  })
})
