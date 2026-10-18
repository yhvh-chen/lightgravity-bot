/**
 * LG-237 Google native ASR UI tests.
 *
 * Injected clients only: no Google, product, ASR, TTS or embedding call is
 * made. These cover the provider-aware Settings form, write-only credential
 * lifecycle, permissions and late-response isolation, plus provider-aware
 * receipt/Files wording from recorded-shape fixtures.
 */

import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'

import type {
  EnglishAsrApi,
  EnglishAsrSettingsView,
  EnglishAsrUpdateInput,
  EnglishAsrUpdateResult,
} from '../src/api/englishAsr'
import {
  GOOGLE_ASR_DEFAULT_BASE_URL,
  GOOGLE_ASR_DEFAULT_MODEL,
} from '../src/api/googleAsr'
import type { GlobalSettingsView, SettingsApi } from '../src/api/settings'
import type {
  SourceReceiptV2,
  SourceTextBranch,
  SourceView,
  SourcesApi,
} from '../src/api/sources'
import type { AuthMeResponse } from '../src/api/teamAuth'
import { AuthProvider, useAuth } from '../src/app/AuthProvider'
import { describeBranch } from '../src/views/chat/ChatMaterialIntake'
import { FilesMaterialsPanel } from '../src/views/files/FilesMaterialsPanel'
import { SettingsView } from '../src/views/settings/SettingsView'
import { HEALTH_FIXTURE, backendFetch } from './setup'

const GOOGLE_SECRET = 'lg237-not-a-real-secret'

const createObjectURL = vi.fn(() => 'blob:google-audio')
const revokeObjectURL = vi.fn()

beforeAll(() => {
  Object.defineProperty(URL, 'createObjectURL', { writable: true, value: createObjectURL })
  Object.defineProperty(URL, 'revokeObjectURL', { writable: true, value: revokeObjectURL })
})

const TEAM_MEMBER = async (): Promise<AuthMeResponse> => ({
  mode: 'team',
  authenticated: true,
  username: 'alice',
  role: 'member',
})

function googleView(
  overrides: Partial<EnglishAsrSettingsView> = {},
): EnglishAsrSettingsView {
  return {
    revision: 5,
    content_hash: 'google-asr-hash-5',
    provider: 'google-native',
    runtime: 'google-native',
    enabled: false,
    configured: false,
    available: false,
    reason: 'disabled',
    language: 'en',
    timestamps_supported: false,
    model: GOOGLE_ASR_DEFAULT_MODEL,
    base_url: GOOGLE_ASR_DEFAULT_BASE_URL,
    credential_configured: false,
    models: {},
    limits: {
      max_audio_seconds: null,
      max_audio_bytes: 10_000_000,
      max_request_bytes: 20_000_000,
      timeout_seconds: 180,
      max_concurrency: 1,
    },
    ...overrides,
  }
}

function makeSettings(view?: EnglishAsrSettingsView | null): GlobalSettingsView {
  return {
    revision: 7,
    exists: true,
    content_hash: 'settings-hash-7',
    default_coordinator_connection_ref: null,
    default_worker_connection_ref: null,
    default_reviewer_connection_ref: null,
    defaults: { coordinator: null, worker: null, reviewer: null },
    ...(view === undefined ? {} : { english_asr: view }),
  }
}

function makeSettingsApi(state: { current: GlobalSettingsView }): SettingsApi {
  return {
    listConnections: vi.fn(async () => []),
    getConnection: vi.fn(),
    getSettings: vi.fn(async () => state.current),
    createConnection: vi.fn(),
    updateConnection: vi.fn(),
    updateSettings: vi.fn(),
    setCredential: vi.fn(),
    keepCredential: vi.fn(),
    removeCredential: vi.fn(),
    testConnection: vi.fn(),
    testDraftConnection: vi.fn(),
    updateEmbedding: vi.fn(),
    testDraftEmbedding: vi.fn(),
    deleteConnection: vi.fn(),
  } as unknown as SettingsApi
}

function resultFor(
  _input: EnglishAsrUpdateInput,
  view: EnglishAsrSettingsView,
): EnglishAsrUpdateResult {
  return { revision: view.revision, content_hash: view.content_hash, english_asr: view }
}

function makeEnglishApi(
  handler: (input: EnglishAsrUpdateInput) => Promise<EnglishAsrUpdateResult>,
): { api: EnglishAsrApi; calls: EnglishAsrUpdateInput[] } {
  const calls: EnglishAsrUpdateInput[] = []
  return {
    api: {
      update: vi.fn(async (input: EnglishAsrUpdateInput) => {
        calls.push(input)
        return handler(input)
      }),
    },
    calls,
  }
}

async function openEditor(): Promise<void> {
  fireEvent.click(await screen.findByRole('button', { name: 'Configure English transcription' }))
  await screen.findByRole('dialog', { name: 'English transcription' })
}

beforeEach(() => {
  window.sessionStorage.clear()
  window.localStorage.clear()
  vi.mocked(globalThis.fetch).mockImplementation(backendFetch as typeof fetch)
})

afterEach(() => {
  cleanup()
  vi.mocked(globalThis.fetch).mockReset()
  vi.mocked(globalThis.fetch).mockImplementation(backendFetch as typeof fetch)
})

describe('LG-237 Google native Settings', () => {
  it('shows a compact Google form without Reader/model-directory or short-audio requirements', async () => {
    const state = { current: makeSettings(googleView()) }
    const english = makeEnglishApi(async (input) =>
      resultFor(input, googleView({ revision: 6 })),
    )
    render(<SettingsView api={makeSettingsApi(state)} englishAsrApi={english.api} />)

    expect((await screen.findAllByText('Google native')).length).toBeGreaterThan(0)
    expect(screen.getByText(/API key not stored/)).toBeInTheDocument()
    expect(screen.getByText(/request ≤/)).toBeInTheDocument()
    expect(screen.queryByText(/audio ≤ 30 s/)).toBeNull()

    await openEditor()
    expect(screen.getByLabelText('Model')).toHaveValue(GOOGLE_ASR_DEFAULT_MODEL)
    expect(screen.getByLabelText('Base URL')).toHaveValue(GOOGLE_ASR_DEFAULT_BASE_URL)
    expect(screen.getByLabelText('Google API key (write-only)')).toHaveValue('')
    expect(screen.queryByLabelText('Model assets directory (write-only)')).toBeNull()
    expect(screen.queryByLabelText('Reader assets directory (write-only)')).toBeNull()
    expect(screen.queryByText(/Maximum audio seconds/)).toBeNull()
    expect(screen.queryByText(/Reader 30-second/)).toBeNull()
    expect(screen.queryByRole('button', { name: /test/i })).toBeNull()
    expect(screen.queryByRole('button', { name: /transcribe/i })).toBeNull()
  })

  it('saves Google fields with the nested revision, omits legacy fields and clears the key', async () => {
    const state = { current: makeSettings(googleView()) }
    const english = makeEnglishApi(async (input) => {
      const next = googleView({
        revision: 6,
        content_hash: 'google-asr-hash-6',
        enabled: input.enabled,
        configured: true,
        available: true,
        reason: null,
        credential_configured: true,
      })
      state.current = makeSettings(next)
      return resultFor(input, next)
    })
    render(<SettingsView api={makeSettingsApi(state)} englishAsrApi={english.api} />)
    await openEditor()

    fireEvent.change(screen.getByLabelText('Model'), {
      target: { value: 'gemini-3.8-flash' },
    })
    fireEvent.change(screen.getByLabelText('Google API key (write-only)'), {
      target: { value: GOOGLE_SECRET },
    })
    fireEvent.click(screen.getByLabelText('Enable English transcription'))
    fireEvent.click(screen.getByRole('button', { name: 'Save English transcription settings' }))

    await waitFor(() => expect(english.calls).toHaveLength(1))
    expect(english.calls[0]).toMatchObject({
      expected_revision: 5,
      enabled: true,
      provider: 'google-native',
      runtime: 'google-native',
      model: GOOGLE_ASR_DEFAULT_MODEL,
      base_url: GOOGLE_ASR_DEFAULT_BASE_URL,
      credential_value: GOOGLE_SECRET,
      timeout_seconds: 180,
      max_audio_bytes: 10_000_000,
    })
    expect(english.calls[0]).not.toHaveProperty('model_dir')
    expect(english.calls[0]).not.toHaveProperty('reader_dir')
    expect(english.calls[0]).not.toHaveProperty('device')
    expect(english.calls[0]).not.toHaveProperty('threads')
    expect(english.calls[0]).not.toHaveProperty('max_audio_seconds')
    expect(english.calls[0]).not.toHaveProperty('credential_ref')

    expect((await screen.findAllByText(/API key configured/)).length).toBeGreaterThan(0)
    expect(screen.getByLabelText('Google API key (write-only)')).toHaveValue('')
    expect(screen.queryByDisplayValue(GOOGLE_SECRET)).toBeNull()
    expect(window.sessionStorage.length).toBe(0)
    expect(window.localStorage.length).toBe(0)
    expect(JSON.stringify(window.sessionStorage)).not.toContain(GOOGLE_SECRET)
    expect(JSON.stringify(window.localStorage)).not.toContain(GOOGLE_SECRET)
    expect(window.location.href).not.toContain(GOOGLE_SECRET)

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(screen.queryByText(GOOGLE_SECRET)).toBeNull()
  })

  it('retains the stored Google key when the write-only field is blank', async () => {
    const state = {
      current: makeSettings(
        googleView({
          enabled: true,
          configured: true,
          available: true,
          reason: null,
          credential_configured: true,
        }),
      ),
    }
    const english = makeEnglishApi(async (input) =>
      resultFor(input, googleView({ revision: 6, configured: true, credential_configured: true })),
    )
    render(<SettingsView api={makeSettingsApi(state)} englishAsrApi={english.api} />)
    await openEditor()

    expect(
      screen.getByPlaceholderText('Leave blank to keep the configured API key'),
    ).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Save English transcription settings' }))

    await waitFor(() => expect(english.calls).toHaveLength(1))
    expect(english.calls[0]).not.toHaveProperty('credential_value')
    expect(english.calls[0]).not.toHaveProperty('credential_ref')
    expect(english.calls[0].expected_revision).toBe(5)
  })

  it('blocks first Google enable without a key before any PUT', async () => {
    const state = { current: makeSettings(googleView()) }
    const english = makeEnglishApi(async (input) =>
      resultFor(input, googleView({ revision: 6 })),
    )
    render(<SettingsView api={makeSettingsApi(state)} englishAsrApi={english.api} />)
    await openEditor()

    fireEvent.click(screen.getByLabelText('Enable English transcription'))
    fireEvent.click(screen.getByRole('button', { name: 'Save English transcription settings' }))

    expect(
      await screen.findByText(/Enter a Google API key before enabling/),
    ).toBeInTheDocument()
    expect(english.calls).toHaveLength(0)

    fireEvent.change(screen.getByLabelText('Google API key (write-only)'), {
      target: { value: GOOGLE_SECRET },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save English transcription settings' }))
    await waitFor(() => expect(english.calls).toHaveLength(1))
    expect(english.calls[0].credential_value).toBe(GOOGLE_SECRET)
  })

  it('ignores a late save response after switching away from the Google draft', async () => {
    const state = { current: makeSettings(googleView()) }
    let resolveSave: ((result: EnglishAsrUpdateResult) => void) | null = null
    const gate = new Promise<EnglishAsrUpdateResult>((resolve) => {
      resolveSave = resolve
    })
    const api: EnglishAsrApi = { update: vi.fn(async () => gate) }
    render(<SettingsView api={makeSettingsApi(state)} englishAsrApi={api} />)
    await openEditor()

    fireEvent.change(screen.getByLabelText('Model'), {
      target: { value: 'draft-model' },
    })
    fireEvent.change(screen.getByLabelText('Google API key (write-only)'), {
      target: { value: GOOGLE_SECRET },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save English transcription settings' }))
    expect(await screen.findByRole('button', { name: 'Saving…' })).toBeDisabled()

    fireEvent.change(screen.getByLabelText('Provider'), {
      target: { value: 'eg2-reader' },
    })
    expect(screen.queryByLabelText('Google API key (write-only)')).toBeNull()

    await act(async () => {
      resolveSave?.(
        resultFor(
          {
            expected_revision: 5,
            enabled: false,
            provider: 'google-native',
            runtime: 'google-native',
            timeout_seconds: 180,
            max_audio_bytes: 10_000_000,
          },
          googleView({
            revision: 9,
            model: 'response-model',
            credential_configured: true,
            configured: true,
          }),
        ),
      )
      await gate
    })

    expect(
      await screen.findByText(/late settings response was ignored because the form changed/),
    ).toBeInTheDocument()
    expect(screen.queryByText('response-model')).toBeNull()

    fireEvent.change(screen.getByLabelText('Provider'), {
      target: { value: 'google-native' },
    })
    expect(screen.getByLabelText('Model')).toHaveValue('draft-model')
    expect(screen.getByLabelText('Google API key (write-only)')).toHaveValue('')
    expect(screen.getByText(/Revision 5/)).toBeInTheDocument()
  })

  it('does not fetch admin settings or expose the Google form to a team member', async () => {
    vi.mocked(globalThis.fetch).mockImplementation((async (input: RequestInfo | URL) => {
      if (String(input).endsWith('/api/v1/health')) {
        return {
          ok: true,
          status: 200,
          headers: {
            get: (name: string) =>
              name.toLowerCase() === 'content-type' ? 'application/json' : null,
          },
          json: async () => ({
            ...HEALTH_FIXTURE,
            contract_version: '1.22.0',
            capabilities: { ...HEALTH_FIXTURE.capabilities, accounts: false },
          }),
        } as unknown as Response
      }
      return backendFetch(input)
    }) as typeof fetch)

    const state = { current: makeSettings(googleView()) }
    const settingsApi = makeSettingsApi(state)
    const english = makeEnglishApi(async (input) =>
      resultFor(input, googleView({ revision: 6 })),
    )
    function ReadySettings() {
      const { status } = useAuth()
      if (status !== 'ready') return <p>auth checking</p>
      return <SettingsView api={settingsApi} englishAsrApi={english.api} />
    }
    render(
      <AuthProvider probe={TEAM_MEMBER}>
        <ReadySettings />
      </AuthProvider>,
    )

    expect(
      await screen.findByText(/Account management is not available on this backend version/),
    ).toBeInTheDocument()
    expect(settingsApi.getSettings).not.toHaveBeenCalled()
    expect(
      screen.queryByRole('button', { name: 'Configure English transcription' }),
    ).toBeNull()
    expect(english.calls).toHaveLength(0)
  })
})

describe('LG-237 provider-aware receipt and Files display', () => {
  it('labels Google receipt provenance and keeps stopped/auth failures honest', () => {
    const branch: SourceTextBranch = {
      status: 'ready',
      reason: null,
      error_code: null,
      language: 'en',
      machine: {
        engine: 'google-native',
        provider: 'google',
        model: GOOGLE_ASR_DEFAULT_MODEL,
        runtime: 'google-native',
        model_version: `google-native:${GOOGLE_ASR_DEFAULT_MODEL}`,
        content_variant: 'machine',
      },
      timestamps: null,
    }
    const ready = describeBranch('text', 'ready', null, null, branch)
    expect(ready.label).toBe('English transcript ready')
    expect(ready.tone).toBe('success')
    expect(ready.detail).toContain('machine Google transcript')
    expect(ready.detail).toContain('Google native')
    expect(ready.detail).toContain('google-native')
    expect(ready.detail).not.toContain('in-process')
    expect(ready.detail).not.toContain('Reader')

    const stopped = describeBranch(
      'text',
      'extracting',
      'asr_stop_unconfirmed',
      null,
      { status: 'extracting', reason: 'asr_stop_unconfirmed', error_code: null },
    )
    expect(stopped.label).toBe('Transcription stop unconfirmed')
    expect(stopped.detail).toContain('provider may still be running')
    expect(stopped.detail).not.toContain('in-process')

    const auth = describeBranch(
      'text',
      'unavailable',
      'asr_auth_failed',
      null,
      { status: 'unavailable', reason: 'asr_auth_failed', error_code: null },
    )
    expect(auth.label).toBe('Transcription authentication failed')
    expect(auth.tone).toBe('warning')
    expect(auth.detail).toContain('rejected the configured credentials')
  })

  it('renders Google machine transcript provenance without legacy Reader pins', async () => {
    const item: SourceView = {
      id: 'source_google_audio',
      source_id: 'source_google_audio',
      title: 'google-audio.mp3',
      title_origin: 'user',
      status: 'indexed',
      intake_mode: 'deferred',
      revision: 4,
      etag: 'rev-4',
      scope: { task_ref: null, project_ref: null, inbox_ref: null },
      origin: { kind: 'upload', external_ref: null, fetched: false },
      content_hash: 'source-hash-google',
      stat_revision: null,
      source_version: 1,
      language: 'en',
      text_status: 'ready',
      original: { path: 'original/google-audio.mp3', media_type: 'audio/mpeg', bytes: 8 },
      derivatives: [
        {
          kind: 'transcript',
          path: 'derivative/machine.v1.md',
          source_version: 1,
          content_hash: 'google-transcript-hash',
          model_version: `google-native:${GOOGLE_ASR_DEFAULT_MODEL}`,
        },
      ],
      formal: { path: 'documents/formal.md', revision: 1, edited_by: 'user' },
      index: { lexical: 'indexed', vector: 'indexed' },
      receipt_ref: 'receipt.jsonl',
      created_at: null,
      updated_at: null,
      path: 'sources/source_google_audio/SOURCE.md',
    }
    const text: SourceTextBranch = {
      status: 'ready',
      reason: null,
      error_code: null,
      language: 'en',
      machine: {
        engine: 'google-native',
        provider: 'google',
        model: GOOGLE_ASR_DEFAULT_MODEL,
        runtime: 'google-native',
        endpoint_host: 'generativelanguage.googleapis.com',
        endpoint_path: '/v1beta/interactions',
        prompt_version: 'google-native-transcribe-v1',
        model_version: `google-native:${GOOGLE_ASR_DEFAULT_MODEL}`,
        content_variant: 'machine',
        generated_at: '2026-10-18T00:00:00Z',
        latency_ms: 6078,
      },
      timestamps: null,
    }
    const receipt: SourceReceiptV2 = {
      source_id: item.source_id,
      revision: 3,
      status: 'indexed',
      source_version: 1,
      receipt_version: 2,
      partial: false,
      items: [
        {
          source_id: item.source_id,
          filename: 'google-audio.mp3',
          status: 'indexed',
          stage: 'done',
          text,
          keyword: { status: 'searchable', reason: null, error_code: null },
          semantic: {
            status: 'searchable',
            reason: null,
            error_code: null,
            model: 'fixture-embed',
            kinds: ['audio'],
            failed_kinds: [],
          },
        },
      ],
      latest: null,
    }
    const api = {
      createSource: vi.fn(),
      listSources: vi.fn(async () => ({ items: [item], next_cursor: null })),
      getSource: vi.fn(async () => item),
      getReceipt: vi.fn(async () => receipt),
      getIntakeJob: vi.fn(async () => null),
      intakeJobAction: vi.fn(),
      getContent: vi.fn(async (_sourceId: string, requested: string) => ({
        source_id: item.source_id,
        kind: requested === 'machine' ? 'machine' : 'formal',
        path:
          requested === 'machine'
            ? 'derivative/machine.v1.md'
            : 'documents/formal.md',
        media_type: 'text/markdown; charset=utf-8',
        content:
          requested === 'machine'
            ? 'Google machine transcript body'
            : 'human corrected formal body',
        formal_present: requested !== 'machine',
      })),
      downloadSource: vi.fn(async () => ({
        blob: new Blob(['audio']),
        filename: 'google-audio.mp3',
        mediaType: 'audio/mpeg',
        statRevision: null,
        kind: 'original',
        contentHash: null,
      })),
      editFormal: vi.fn(),
      sourceAction: vi.fn(),
      appendInboxMessage: vi.fn(),
      search: vi.fn(),
    } as unknown as SourcesApi

    render(<FilesMaterialsPanel api={api} taskRef={null} materialIntakeV2 mediaDirectEmbedding />)
    fireEvent.click(await screen.findByText('google-audio.mp3'))

    expect((await screen.findAllByText(/Machine Google transcript/)).length).toBeGreaterThan(0)
    expect(screen.getAllByText('Google native').length).toBeGreaterThan(0)
    expect(screen.getByText(GOOGLE_ASR_DEFAULT_MODEL)).toBeInTheDocument()
    expect(
      screen.getByText('generativelanguage.googleapis.com/v1beta/interactions'),
    ).toBeInTheDocument()
    expect(screen.getByText('google-native-transcribe-v1')).toBeInTheDocument()
    expect(screen.queryByText('Reader')).toBeNull()
    expect(screen.queryByText('Encoder')).toBeNull()
    expect(screen.queryByText(/Pinned models/)).toBeNull()
    expect(screen.queryByRole('slider')).toBeNull()
  })
})

