import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type {
  ConnectionCreateInput,
  ConnectionTestInput,
  ConnectionTestResult,
  ConnectionUpdateInput,
  ConnectionView,
  GlobalSettingsView,
  SettingsApi,
} from '../src/api/settings'
import type { AuthMeResponse } from '../src/api/teamAuth'
import { AuthProvider, useAuth } from '../src/app/AuthProvider'
import { SettingsView } from '../src/views/settings/SettingsView'
import {
  connectionCapabilities,
  inferPresetId,
  presetForConnection,
} from '../src/views/settings/backends'

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

function makeSettings(_connections: ConnectionView[]): GlobalSettingsView {
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

function makeTestResult(overrides: Partial<ConnectionTestResult> = {}): ConnectionTestResult {
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
      { name: 'runtime_network', status: 'skipped', detail: 'budget policy pending', duration_ms: null },
    ],
    overall: 'partial',
    note: 'layers are separate',
    ...overrides,
  }
}

interface FakeState {
  connections: ConnectionView[]
  createCalls: ConnectionCreateInput[]
  updateCalls: Array<{ id: string; input: ConnectionUpdateInput }>
  testCalls: Array<{ id: string; input: ConnectionTestInput }>
  removeCredentialCalls: string[]
  testResult: ConnectionTestResult
}

function makeFakeApi(initial?: Partial<FakeState>): {
  api: SettingsApi
  state: FakeState
} {
  const state: FakeState = {
    connections: [makeConnection()],
    createCalls: [],
    updateCalls: [],
    testCalls: [],
    removeCredentialCalls: [],
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
      return makeSettings(state.connections)
    },
    async createConnection(input) {
      state.createCalls.push(input)
      const id = input.id
      const created = makeConnection({
        id,
        title: input.title ?? id,
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
        references: { connection_id: id, default_roles: [], agent_refs: [] },
      })
      state.connections = [...state.connections, created]
      return created
    },
    async updateConnection(id, input) {
      state.updateCalls.push({ id, input })
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
      return makeSettings(state.connections)
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
    async testConnection(id, input) {
      state.testCalls.push({ id, input })
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

describe('LG-106 provider preset mapping', () => {
  interface MatrixCase {
    name: string
    preset: string
    idPattern: RegExp
    fill?: () => void
    expected: Partial<ConnectionCreateInput>
    noApiKey?: boolean
    noModel?: boolean
  }

  const cases: MatrixCase[] = [
    {
      name: 'Gemini API',
      preset: 'gemini-api',
      idPattern: /^gemini-api-[a-z0-9]+$/,
      fill: () => {
        fireEvent.change(screen.getByLabelText(/API key/), {
          target: { value: 'sk-gemini-test' },
        })
      },
      expected: {
        backend: 'gemini',
        auth_mode: 'api_key',
        model: 'gemini-3.8-flash',
        project: null,
        location: null,
        model_path: null,
        litert_backend: null,
      },
    },
    {
      name: 'Vertex Express',
      preset: 'vertex-express',
      idPattern: /^vertex-express-[a-z0-9]+$/,
      fill: () => {
        fireEvent.change(screen.getByLabelText(/API key/), {
          target: { value: 'sk-vertex-test' },
        })
      },
      expected: {
        backend: 'vertex',
        auth_mode: 'api_key',
        model: 'gemini-3.8-flash',
        project: null,
        location: null,
      },
    },
    {
      name: 'Vertex ADC',
      preset: 'vertex-adc',
      idPattern: /^vertex-adc-[a-z0-9]+$/,
      fill: () => {
        fireEvent.change(screen.getByLabelText(/Project ID/), {
          target: { value: 'project-1' },
        })
        fireEvent.change(screen.getByLabelText(/Location/), {
          target: { value: 'us-central1' },
        })
      },
      expected: {
        backend: 'vertex',
        auth_mode: 'adc',
        model: 'gemini-3.8-flash',
        project: 'project-1',
        location: 'us-central1',
      },
      noApiKey: true,
    },
    {
      name: 'DeepSeek OpenAI-compatible',
      preset: 'deepseek',
      idPattern: /^deepseek-[a-z0-9]+$/,
      fill: () => {
        fireEvent.change(screen.getByLabelText(/API key/), {
          target: { value: 'sk-deepseek-test' },
        })
      },
      expected: {
        backend: 'openai-compat',
        model: 'deepseek-v4-flash',
        base_url: DEEPSEEK_BASE_URL,
      },
    },
    {
      name: 'LiteRT local model',
      preset: 'litert',
      idPattern: /^litert-[a-z0-9]+$/,
      fill: () => {
        fireEvent.change(screen.getByLabelText(/Model file path/), {
          target: { value: '/models/gemma.litertlm' },
        })
        fireEvent.change(screen.getByLabelText(/LiteRT backend/), {
          target: { value: 'CPU' },
        })
      },
      expected: {
        backend: 'litert',
        auth_mode: 'none',
        model: null,
        model_path: '/models/gemma.litertlm',
        litert_backend: 'CPU',
        credential_ref: null,
      },
      noApiKey: true,
      noModel: true,
    },
  ]

  it.each(cases)('maps the $name preset to the real backend fields', async (testCase) => {
    const { api, state } = makeFakeApi({ connections: [] })
    render(<SettingsView api={api} />)

    fireEvent.click(await screen.findByRole('button', { name: 'New connection' }))
    fireEvent.change(screen.getByRole('combobox', { name: 'Provider' }), {
      target: { value: testCase.preset },
    })
    if (testCase.noApiKey) {
      expect(screen.queryByLabelText(/API key/)).toBeNull()
    } else {
      expect(screen.getByLabelText(/API key/)).toBeInTheDocument()
    }
    if (testCase.noModel) {
      expect(screen.queryByPlaceholderText('gemini-3.8-flash')).toBeNull()
      expect(screen.queryByPlaceholderText('deepseek-v4-flash')).toBeNull()
    } else {
      const model = testCase.preset === 'deepseek' ? 'deepseek-v4-flash' : 'gemini-3.8-flash'
      expect(screen.getByPlaceholderText(model)).toHaveValue(model)
    }
    testCase.fill?.()
    fireEvent.click(screen.getByRole('button', { name: 'Save connection' }))

    await waitFor(() => expect(state.createCalls).toHaveLength(1))
    const call = state.createCalls[0]
    expect(call.id).toMatch(testCase.idPattern)
    expect(call).toMatchObject(testCase.expected)
    if (testCase.preset === 'deepseek') {
      // Legacy-compatible omission: auth_mode defaults to the proxy path.
      expect(call.auth_mode).toBeUndefined()
      expect(call.credential_ref).toBe(`${call.id}-key`)
    }
  })

  it('keeps an existing custom OpenAI-compatible endpoint as a legacy preset', async () => {
    const { api, state } = makeFakeApi({
      connections: [
        makeConnection({
          id: 'local-ollama',
          title: 'Local Ollama',
          model: 'llama3',
          base_url: 'http://127.0.0.1:11434/v1',
          credential_ref: 'ollama-key',
          credential: {
            ref: 'ollama-key',
            configured: true,
            source: 'secret_store',
            version: 'cred_1',
          },
        }),
      ],
    })
    render(<SettingsView api={api} />)

    await screen.findByRole('heading', { name: 'Local Ollama' })
    expect(screen.getByRole('combobox', { name: 'Provider' })).toHaveValue(
      'legacy-openai',
    )

    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    await waitFor(() => expect(state.updateCalls).toHaveLength(1))
    const payload = state.updateCalls[0].input
    // No migration and no optional fields injected into an old record.
    expect(payload.backend).toBeUndefined()
    expect(payload.auth_mode).toBeUndefined()
    expect(payload.base_url).toBe('http://127.0.0.1:11434/v1')
    expect(payload.credential_action).toBe('keep')
    expect(payload.credential_value).toBeUndefined()
  })

  it('infers presets from auth_mode/project fields without mutating old records', () => {
    expect(inferPresetId(makeConnection({ backend: 'gemini' }))).toBe('gemini-api')
    expect(
      inferPresetId(makeConnection({ backend: 'vertex', auth_mode: 'api_key' })),
    ).toBe('vertex-express')
    expect(
      inferPresetId(
        makeConnection({
          backend: 'vertex',
          auth_mode: 'adc',
          project: 'p',
          location: 'us-central1',
        }),
      ),
    ).toBe('vertex-adc')
    expect(inferPresetId(makeConnection({ backend: 'litert', auth_mode: 'none' }))).toBe(
      'litert',
    )
    expect(
      presetForConnection(makeConnection({ base_url: 'https://example.test/v1' })).id,
    ).toBe('legacy-openai')
    expect(presetForConnection(makeConnection()).id).toBe('deepseek')
  })

  it('keeps capability facts separate and only defaults executable connections', () => {
    const gemini = makeConnection({
      backend: 'gemini',
      capabilities: { configurable: true, testable: true, executable: false },
    })
    expect(connectionCapabilities(gemini)).toMatchObject({
      configurable: true,
      testable: true,
      executable: false,
      vendor_verified: false,
    })
    const deepseek = makeConnection()
    expect(connectionCapabilities(deepseek)).toMatchObject({
      executable: true,
      vendor_verified: true,
    })
  })
})

describe('LG-106 secret preservation and dirty test rules', () => {
  it('sends no key and no removal when the write-only field is empty', async () => {
    const { api, state } = makeFakeApi()
    render(<SettingsView api={api} />)
    await screen.findByRole('heading', { name: 'DeepSeek (primary)' })

    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))

    await waitFor(() => expect(state.updateCalls).toHaveLength(1))
    const payload = state.updateCalls[0].input
    expect(payload.credential_action).toBe('keep')
    expect(payload.credential_value).toBeUndefined()
    expect(payload.credential_ref).toBeUndefined()
    expect(state.removeCredentialCalls).toHaveLength(0)
    expect(JSON.stringify(window.localStorage)).not.toContain('sk-')
    expect(JSON.stringify(window.sessionStorage)).not.toContain('sk-')
  })

  it('switching provider keeps the stored key and never deletes it', async () => {
    const { api, state } = makeFakeApi()
    render(<SettingsView api={api} />)
    await screen.findByRole('heading', { name: 'DeepSeek (primary)' })

    fireEvent.change(screen.getByRole('combobox', { name: 'Provider' }), {
      target: { value: 'gemini-api' },
    })
    expect(screen.getByLabelText(/API key/)).toHaveValue('')
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))

    await waitFor(() => expect(state.updateCalls).toHaveLength(1))
    const payload = state.updateCalls[0].input
    expect(payload.backend).toBe('gemini')
    expect(payload.auth_mode).toBe('api_key')
    expect(payload.credential_action).toBe('keep')
    expect(payload.credential_value).toBeUndefined()
    expect(payload.credential_ref).toBeUndefined()
    expect(state.removeCredentialCalls).toHaveLength(0)
    // The old reference is still present on the resulting record.
    expect(state.connections[0].credential_ref).toBe('deepseek-primary-key')
  })

  it('requires Save before Test and never tests automatically', async () => {
    const { api, state } = makeFakeApi()
    render(<SettingsView api={api} />)
    await screen.findByRole('heading', { name: 'DeepSeek (primary)' })

    // No request on load or selection.
    expect(state.testCalls).toHaveLength(0)
    const testButton = screen.getByRole('button', { name: 'Test connection' })
    expect(testButton).toBeEnabled()

    fireEvent.click(testButton)
    await waitFor(() => expect(state.testCalls).toHaveLength(1))
    expect(state.testCalls[0].input).toMatchObject({
      expected_revision: 3,
      allow_network: true,
    })
    expect(await screen.findByText('runtime_network')).toBeInTheDocument()

    // A dirty edit disables Test until the revision is saved.
    fireEvent.change(screen.getByLabelText(/^Model/), {
      target: { value: 'deepseek-v4-flash-next' },
    })
    expect(screen.getByRole('button', { name: 'Test connection' })).toBeDisabled()
    expect(screen.getByText(/Save your changes first/)).toBeInTheDocument()
    expect(state.testCalls).toHaveLength(1)

    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    await waitFor(() => expect(state.updateCalls).toHaveLength(1))
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Test connection' })).toBeEnabled(),
    )
    // Saving itself never triggers a test.
    expect(state.testCalls).toHaveLength(1)
  })

  it('honours a backend-declared testable=false without pretending', async () => {
    const { api, state } = makeFakeApi({
      connections: [
        makeConnection({
          backend: 'gemini',
          model: 'gemini-3.8-flash',
          base_url: null,
          capabilities: {
            configurable: true,
            testable: false,
            executable: false,
            vendor_verified: false,
          },
        }),
      ],
    })
    render(<SettingsView api={api} />)
    await screen.findByRole('heading', { name: 'DeepSeek (primary)' })
    const testButton = screen.getByRole('button', { name: 'Test connection' })
    expect(testButton).toBeDisabled()
    expect(
      screen.getByText(/has not enabled Test for this provider/),
    ).toBeInTheDocument()
    expect(state.testCalls).toHaveLength(0)
  })

  it('surfaces a real save validation error instead of a fake success', async () => {
    const { api, state } = makeFakeApi({ connections: [] })
    render(<SettingsView api={api} />)
    fireEvent.click(await screen.findByRole('button', { name: 'New connection' }))
    fireEvent.change(screen.getByRole('combobox', { name: 'Provider' }), {
      target: { value: 'vertex-adc' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save connection' }))

    expect(await screen.findByText(/Google Cloud project ID/)).toBeInTheDocument()
    expect(state.createCalls).toHaveLength(0)
  })
})

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

describe('LG-106 member boundary', () => {
  it('never fetches Models/Connections for a team member', async () => {
    const listConnections = vi.fn(async () => [makeConnection()])
    const getSettings = vi.fn(async () => makeSettings([makeConnection()]))
    const api = {
      ...makeFakeApi().api,
      listConnections,
      getSettings,
    } as SettingsApi

    render(
      <AuthProvider probe={MEMBER_PROBE}>
        <MemberBoundaryHarness api={api} />
      </AuthProvider>,
    )

    expect(await screen.findByText('role:member')).toBeInTheDocument()
    expect(listConnections).not.toHaveBeenCalled()
    expect(getSettings).not.toHaveBeenCalled()
    expect(screen.queryByText('Models & Providers')).toBeNull()
    expect(
      screen.getByText(/configuration is managed by administrators/),
    ).toBeInTheDocument()
  })
})

describe('LG-106 late response guard', () => {
  it('does not let a late save change the selected connection', async () => {
    const { api, state } = makeFakeApi({
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

    render(<SettingsView api={api} connectionId="deepseek-primary" />)
    await screen.findByRole('heading', { name: 'DeepSeek (primary)' })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    await waitFor(() => expect(release).not.toBeNull())

    fireEvent.click(screen.getByRole('button', { name: /DeepSeek \(backup\)/ }))
    expect(screen.getByRole('heading', { name: 'DeepSeek (backup)' })).toBeInTheDocument()

    ;(release as unknown as () => void)()
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /DeepSeek \(backup\)/ })).toHaveAttribute(
        'aria-pressed',
        'true',
      ),
    )
    expect(screen.getByRole('heading', { name: 'DeepSeek (backup)' })).toBeInTheDocument()
    expect(screen.queryByText('primary saved later')).toBeNull()
    expect(state.updateCalls).toHaveLength(0)
  })
})

describe('LG-106 unknown target', () => {
  it('shows a miss without selecting another connection', async () => {
    const { api } = makeFakeApi({
      connections: [
        makeConnection({ id: 'deepseek-primary', title: 'DeepSeek (primary)' }),
        makeConnection({ id: 'deepseek-backup', title: 'DeepSeek (backup)' }),
      ],
    })
    render(<SettingsView api={api} connectionId="missing-connection" />)
    expect(await screen.findByText('Connection not found')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Save changes' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Test connection' })).toBeNull()
  })
})
