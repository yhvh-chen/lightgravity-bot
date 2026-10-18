import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import type {
  ConnectionView,
  EmbeddingDraftTestInput,
  EmbeddingDraftTestResult,
  EmbeddingSettingsView,
  EmbeddingUpdateInput,
  EmbeddingUpdateResult,
  GlobalSettingsView,
  SettingsApi,
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
      default_roles: [],
      agent_refs: [],
    },
    ...overrides,
  }
}

function makeEmbedding(
  overrides: Partial<EmbeddingSettingsView> = {},
): EmbeddingSettingsView {
  return {
    enabled: false,
    base_url: 'http://127.0.0.1:9000/v1',
    model: 'embeddinggemma-2-Q8_0',
    timeout_seconds: 60,
    cold_timeout_seconds: 150,
    source: 'settings',
    credential: {
      ref: 'embedding-api',
      configured: true,
      source: 'secret_store',
      version: 'cred_embed_1',
    },
    cache: {
      compatible: false,
      reason: 'model_mismatch_rebuild_required',
      vector_model: 'old-embedding-model',
    },
    ...overrides,
  }
}

function makeSettings(embedding = makeEmbedding()): GlobalSettingsView {
  return {
    revision: 7,
    exists: true,
    content_hash: 'settings-hash-7',
    default_coordinator_connection_ref: null,
    default_worker_connection_ref: null,
    default_reviewer_connection_ref: null,
    defaults: { coordinator: null, worker: null, reviewer: null },
    embedding,
  }
}

function makeDraftResult(
  overrides: Partial<EmbeddingDraftTestResult> = {},
): EmbeddingDraftTestResult {
  return {
    draft: true,
    overall: 'verified',
    requested_model: 'embeddinggemma-2-Q8_0',
    reported_model: 'embeddinggemma-2-Q8_0',
    dim: 768,
    latency_seconds: 0.42,
    finished_at: '2026-10-18T01:00:00Z',
    credential_source: 'secret_store',
    checks: [
      { name: 'config_parse', status: 'passed', detail: 'ok' },
      { name: 'runtime_network', status: 'passed', detail: 'dim=768' },
    ],
    error: null,
    cache_impact: 'none',
    ...overrides,
  }
}

interface FakeState {
  settings: GlobalSettingsView
  updateCalls: EmbeddingUpdateInput[]
  testCalls: EmbeddingDraftTestInput[]
  testResult: EmbeddingDraftTestResult
  testGate: Promise<EmbeddingDraftTestResult> | null
}

function makeFakeApi(initial?: Partial<FakeState>): {
  api: SettingsApi
  state: FakeState
} {
  const state: FakeState = {
    settings: makeSettings(),
    updateCalls: [],
    testCalls: [],
    testResult: makeDraftResult(),
    testGate: null,
    ...initial,
  }
  const api: SettingsApi = {
    async listConnections() {
      return [makeConnection()]
    },
    async getConnection() {
      return makeConnection()
    },
    async getSettings() {
      return state.settings
    },
    async createConnection() {
      throw new Error('not used')
    },
    async updateConnection() {
      throw new Error('not used')
    },
    async updateSettings() {
      return state.settings
    },
    async setCredential(ref) {
      return { ref, configured: true, source: 'secret_store', version: 'v' }
    },
    async keepCredential(ref) {
      return { ref, configured: true, source: 'secret_store', version: 'v' }
    },
    async removeCredential(ref) {
      return { ref, configured: false, source: null, version: null }
    },
    async testConnection() {
      throw new Error('not used')
    },
    async testDraftConnection() {
      throw new Error('not used')
    },
    async updateEmbedding(input) {
      state.updateCalls.push(input)
      const embedding: EmbeddingSettingsView = {
        ...state.settings.embedding!,
        enabled: input.enabled,
        base_url: input.base_url,
        model: input.model,
        timeout_seconds: input.timeout_seconds ?? 60,
        cold_timeout_seconds: input.cold_timeout_seconds ?? 150,
        source: 'settings',
        credential:
          input.credential_action === 'remove'
            ? { ref: null, configured: false, source: null, version: null }
            : input.credential_action === 'set'
              ? {
                  ref: 'embedding-api',
                  configured: true,
                  source: 'secret_store',
                  version: 'cred_embed_2',
                }
              : state.settings.embedding!.credential,
        cache: { compatible: null, reason: 'cache_missing', vector_model: null },
      }
      const result: EmbeddingUpdateResult = {
        ...embedding,
        revision: input.expected_revision + 1,
        content_hash: 'settings-hash-8',
      }
      state.settings = {
        ...state.settings,
        revision: result.revision,
        content_hash: result.content_hash,
        embedding: embedding,
      }
      return result
    },
    async testDraftEmbedding(input) {
      state.testCalls.push(input)
      if (state.testGate) return state.testGate
      return state.testResult
    },
    async deleteConnection() {
      throw new Error('not used')
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

async function openEmbedding(): Promise<void> {
  fireEvent.click(await screen.findByRole('button', { name: 'Configure Embedding' }))
  await screen.findByRole('dialog', { name: 'Embedding' })
}

describe('LG-117 Embedding settings', () => {
  it('renders the independent Embedding area without making any test or save call', async () => {
    const { api, state } = makeFakeApi()
    render(<SettingsView api={api} />)

    expect(await screen.findByText('Embedding')).toBeInTheDocument()
    expect(screen.getByText('source: settings')).toBeInTheDocument()
    expect(screen.getByText('vector rebuild required')).toBeInTheDocument()
    expect(screen.getByText('old-embedding-model')).toBeInTheDocument()
    expect(state.testCalls).toHaveLength(0)
    expect(state.updateCalls).toHaveLength(0)
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('runs Test only on click with explicit network allow and shows actual model/dim/latency', async () => {
    const { api, state } = makeFakeApi()
    render(<SettingsView api={api} />)
    await openEmbedding()

    expect(state.testCalls).toHaveLength(0)
    fireEvent.click(screen.getByRole('button', { name: 'Test' }))

    await waitFor(() => expect(state.testCalls).toHaveLength(1))
    expect(state.testCalls[0]).toMatchObject({
      base_url: 'http://127.0.0.1:9000/v1',
      model: 'embeddinggemma-2-Q8_0',
      use_existing_credential: true,
      allow_network: true,
    })
    expect(await screen.findByText('reported model')).toBeInTheDocument()
    expect(screen.getByText('768')).toBeInTheDocument()
    expect(screen.getByText('420 ms')).toBeInTheDocument()
    expect(screen.getByText('draft · not saved')).toBeInTheDocument()
    expect(state.updateCalls).toHaveLength(0)
  })

  it('invalidates the shown result when a field changes and discards a late result', async () => {
    let resolveTest: ((result: EmbeddingDraftTestResult) => void) | null = null
    const gate = new Promise<EmbeddingDraftTestResult>((resolve) => {
      resolveTest = resolve
    })
    const { api, state } = makeFakeApi({ testGate: gate })
    render(<SettingsView api={api} />)
    await openEmbedding()

    fireEvent.click(screen.getByRole('button', { name: 'Test' }))
    await waitFor(() => expect(state.testCalls).toHaveLength(1))
    fireEvent.change(screen.getByLabelText('Actual model ID'), {
      target: { value: 'changed-model' },
    })
    await act(async () => {
      resolveTest?.(makeDraftResult({ requested_model: 'late-old-model' }))
      await gate
    })
    expect(
      await screen.findByText(/late result was discarded/),
    ).toBeInTheDocument()
    expect(screen.queryByText('reported model')).toBeNull()
  })

  it('saves credential_action=set with the settings revision and clears the typed secret', async () => {
    const { api, state } = makeFakeApi()
    render(<SettingsView api={api} />)
    await openEmbedding()

    fireEvent.change(screen.getByLabelText('API base URL'), {
      target: { value: 'https://embed.example/v1' },
    })
    fireEvent.change(screen.getByLabelText('Actual model ID'), {
      target: { value: 'new-embed-model' },
    })
    fireEvent.change(screen.getByLabelText('Replace API key'), {
      target: { value: 'embed-secret-write-only' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save embedding settings' }))

    await waitFor(() => expect(state.updateCalls).toHaveLength(1))
    expect(state.updateCalls[0]).toMatchObject({
      expected_revision: 7,
      enabled: false,
      base_url: 'https://embed.example/v1',
      model: 'new-embed-model',
      credential_action: 'set',
      credential_value: 'embed-secret-write-only',
    })
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(await screen.findByText(/Embedding settings saved at settings revision 8/)).toBeInTheDocument()
    expect(screen.queryByText('embed-secret-write-only')).toBeNull()
    expect(JSON.stringify(window.sessionStorage)).not.toContain('embed-secret-write-only')
    expect(JSON.stringify(window.localStorage)).not.toContain('embed-secret-write-only')
  })

  it('clears the transient secret when closing with unsaved edits', async () => {
    const { api, state } = makeFakeApi()
    render(<SettingsView api={api} />)
    await openEmbedding()

    fireEvent.change(screen.getByLabelText('Replace API key'), {
      target: { value: 'close-should-clear-this' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(await screen.findByText(/Discard the unsaved Embedding changes/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Discard changes' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())

    await openEmbedding()
    expect(screen.getByLabelText('Replace API key')).toHaveValue('')
    expect(state.updateCalls).toHaveLength(0)
    expect(state.testCalls).toHaveLength(0)
  })

  it('offers removal without sending a credential value', async () => {
    const { api, state } = makeFakeApi()
    render(<SettingsView api={api} />)
    await openEmbedding()

    fireEvent.click(screen.getByRole('button', { name: 'Remove saved key' }))
    fireEvent.click(screen.getByRole('button', { name: 'Save embedding settings' }))
    await waitFor(() => expect(state.updateCalls).toHaveLength(1))
    expect(state.updateCalls[0].credential_action).toBe('remove')
    expect(state.updateCalls[0].credential_value).toBeUndefined()
  })

  it('shows an honest unavailable state when the backend omits embedding settings', async () => {
    const { api, state } = makeFakeApi()
    state.settings = { ...makeSettings(), embedding: undefined }
    render(<SettingsView api={api} />)
    expect(
      await screen.findByText(/does not expose independent Embedding settings/),
    ).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Configure Embedding' })).toBeNull()
  })
})
