/**
 * LG-161 English transcription Settings tests.
 *
 * Component-level only, with injected clients. These verify the configuration
 * seam frozen in docs/08 §21:
 *  * a missing `settings.english_asr` view hides the form and never probes/writes;
 *  * the view is configuration, so it stays configurable while processing is
 *    unavailable/disabled (health `english_asr` is not a config gate);
 *  * PUT uses the nested `english_asr.revision`, blank write-only paths are
 *    omitted (retain), and saved paths are never rendered;
 *  * pending/errors/revision conflicts stay visible, saving is not success;
 *  * team members never fetch admin settings or see the form.
 *
 * No model, TTS, Reader, browser or backend call is made.
 */

import { act, cleanup, render, screen, waitFor } from '@testing-library/react'
import { fireEvent } from '@testing-library/dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '../src/api/client'
import type {
  EnglishAsrApi,
  EnglishAsrSettingsView,
  EnglishAsrUpdateInput,
  EnglishAsrUpdateResult,
} from '../src/api/englishAsr'
import type { GlobalSettingsView, SettingsApi } from '../src/api/settings'
import type { AuthMeResponse } from '../src/api/teamAuth'
import { AuthProvider, useAuth } from '../src/app/AuthProvider'
import { SettingsView } from '../src/views/settings/SettingsView'
import { HEALTH_FIXTURE, backendFetch } from './setup'

const TEAM_MEMBER = async (): Promise<AuthMeResponse> => ({
  mode: 'team',
  authenticated: true,
  username: 'alice',
  role: 'member',
})

function makeEnglishAsr(
  overrides: Partial<EnglishAsrSettingsView> = {},
): EnglishAsrSettingsView {
  return {
    revision: 3,
    content_hash: 'asr-hash-3',
    enabled: false,
    runtime: 'inprocess',
    configured: false,
    available: false,
    reason: 'disabled',
    language: 'en',
    timestamps_supported: false,
    models: {
      encoder: {
        id: 'google/embeddinggemma-2',
        revision: '914f7f89142e33e77833254d9c9b90c3cef7303b',
        sha256: '197a32965d4b1105faf060417baa899e193fb73cd401f42ec9295234d5553d79',
        license: 'apache-2.0',
      },
      reader: {
        id: 'mlboydaisuke/EmbeddingGemma-2-Transcribe-Reader',
        revision: 'de224fd8fa4ed4519fdddd9aa4154432d46a1bd3',
        sha256: 'd605f6fba8687497be6b5fd717ea6c51beaee5d5f69c30a64225da96ebe0d8c2',
        license: 'apache-2.0',
      },
    },
    limits: {
      max_audio_seconds: 30,
      max_audio_bytes: 10_000_000,
      timeout_seconds: 180,
      max_concurrency: 1,
    },
    ...overrides,
  }
}

function makeSettings(englishAsr?: EnglishAsrSettingsView | null): GlobalSettingsView {
  return {
    revision: 7,
    exists: true,
    content_hash: 'settings-hash-7',
    default_coordinator_connection_ref: null,
    default_worker_connection_ref: null,
    default_reviewer_connection_ref: null,
    defaults: { coordinator: null, worker: null, reviewer: null },
    ...(englishAsr === undefined ? {} : { english_asr: englishAsr }),
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

function resultFor(_input: EnglishAsrUpdateInput, view: EnglishAsrSettingsView): EnglishAsrUpdateResult {
  return {
    revision: view.revision,
    content_hash: view.content_hash,
    english_asr: view,
  }
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

describe('LG-161 English transcription Settings', () => {
  it('hides the form and performs no write when an old backend omits the view', async () => {
    const state = { current: makeSettings(undefined) }
    const english = makeEnglishApi(async () => {
      throw new Error('must not be called')
    })
    render(<SettingsView api={makeSettingsApi(state)} englishAsrApi={english.api} />)

    expect(
      await screen.findByText(/does not expose English transcription settings/),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: 'Configure English transcription' }),
    ).toBeNull()
    expect(screen.queryByRole('dialog', { name: 'English transcription' })).toBeNull()
    expect(english.calls).toHaveLength(0)
  })

  it('shows real view fields and remains configurable while processing is unavailable', async () => {
    const state = { current: makeSettings(makeEnglishAsr()) }
    const english = makeEnglishApi(async (input) =>
      resultFor(input, makeEnglishAsr({ revision: 4, configured: true })),
    )
    render(<SettingsView api={makeSettingsApi(state)} englishAsrApi={english.api} />)

    expect(await screen.findByText('English transcription')).toBeInTheDocument()
    expect(screen.getByText('disabled')).toBeInTheDocument()
    expect(screen.getByText('not configured')).toBeInTheDocument()
    expect(screen.getByText('unavailable')).toBeInTheDocument()
    expect(screen.getByText(/Disabled by configuration/)).toBeInTheDocument()
    expect(
      screen.getAllByText('google/embeddinggemma-2 @ 914f7f89142e33e77833254d9c9b90c3cef7303b').length,
    ).toBeGreaterThan(0)
    expect(screen.getByText(/audio ≤ 30 s/)).toBeInTheDocument()
    expect(screen.getByText(/timeout 180 s/)).toBeInTheDocument()

    await openEditor()
    expect(screen.getByText(/Revision 3 · runtime inprocess/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /test/i })).toBeNull()
    expect(screen.queryByRole('button', { name: /download/i })).toBeNull()
    expect(screen.queryByRole('button', { name: /install/i })).toBeNull()
    expect(screen.queryByRole('button', { name: /train/i })).toBeNull()
    expect(screen.queryByRole('button', { name: /upload/i })).toBeNull()
    expect(screen.queryByRole('button', { name: /transcribe/i })).toBeNull()
  })

  it('saves initial configuration with the nested revision and never renders write-only paths', async () => {
    const state = { current: makeSettings(makeEnglishAsr()) }
    const english = makeEnglishApi(async (input) => {
      const next = makeEnglishAsr({
        revision: 4,
        content_hash: 'asr-hash-4',
        enabled: input.enabled,
        configured: true,
        available: false,
        reason: 'model_missing',
      })
      state.current = makeSettings(next)
      return resultFor(input, next)
    })
    render(<SettingsView api={makeSettingsApi(state)} englishAsrApi={english.api} />)
    await openEditor()

    fireEvent.change(screen.getByLabelText('Model assets directory (write-only)'), {
      target: { value: '/srv/models/embeddinggemma-2' },
    })
    fireEvent.change(screen.getByLabelText('Reader assets directory (write-only)'), {
      target: { value: '/srv/models/eg2-reader-v2' },
    })
    fireEvent.click(screen.getByLabelText('Enable English transcription'))
    fireEvent.click(screen.getByRole('button', { name: 'Save English transcription settings' }))

    await waitFor(() => expect(english.calls).toHaveLength(1))
    expect(english.calls[0]).toMatchObject({
      expected_revision: 3,
      enabled: true,
      runtime: 'inprocess',
      device: 'cpu',
      model_dir: '/srv/models/embeddinggemma-2',
      reader_dir: '/srv/models/eg2-reader-v2',
      timeout_seconds: 180,
      max_audio_seconds: 30,
      max_audio_bytes: 10_000_000,
    })
    expect(english.calls[0]).not.toHaveProperty('threads')
    expect(JSON.stringify(english.calls[0])).not.toContain('credential')

    expect(
      (await screen.findAllByText(/saved at revision 4.*does not run transcription/)).length,
    ).toBeGreaterThan(0)
    expect(screen.getAllByText('configured').length).toBeGreaterThan(0)
    expect(
      screen.getAllByText(/Model files missing at the configured asset directories/).length,
    ).toBeGreaterThan(0)
    expect(screen.getByLabelText('Model assets directory (write-only)')).toHaveValue('')
    expect(screen.getByLabelText('Reader assets directory (write-only)')).toHaveValue('')
    expect(screen.queryByDisplayValue('/srv/models/embeddinggemma-2')).toBeNull()
    expect(screen.queryByText('/srv/models/embeddinggemma-2')).toBeNull()
    expect(screen.queryByText('/srv/models/eg2-reader-v2')).toBeNull()
    // The global document revision is not the nested capability revision.
    expect(state.current.revision).toBe(7)

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(screen.queryByText('/srv/models/embeddinggemma-2')).toBeNull()
    expect(screen.getByText('configured')).toBeInTheDocument()
  })

  it('omits blank paths (retain) and sends only a supplied partial path', async () => {
    const state = { current: makeSettings(makeEnglishAsr({ configured: true, enabled: true, available: true, reason: null })) }
    const english = makeEnglishApi(async (input) => {
      const next = makeEnglishAsr({
        revision: input.expected_revision + 1,
        content_hash: `asr-hash-${input.expected_revision + 1}`,
        configured: true,
        enabled: input.enabled,
        available: true,
        reason: null,
      })
      state.current = makeSettings(next)
      return resultFor(input, next)
    })
    render(<SettingsView api={makeSettingsApi(state)} englishAsrApi={english.api} />)
    await openEditor()

    fireEvent.click(screen.getByRole('button', { name: 'Save English transcription settings' }))
    await waitFor(() => expect(english.calls).toHaveLength(1))
    expect(english.calls[0]).not.toHaveProperty('model_dir')
    expect(english.calls[0]).not.toHaveProperty('reader_dir')
    expect(english.calls[0].expected_revision).toBe(3)

    fireEvent.change(screen.getByLabelText('Reader assets directory (write-only)'), {
      target: { value: '/srv/models/new-reader' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save English transcription settings' }))
    await waitFor(() => expect(english.calls).toHaveLength(2))
    expect(english.calls[1]).not.toHaveProperty('model_dir')
    expect(english.calls[1].reader_dir).toBe('/srv/models/new-reader')
    expect(english.calls[1].expected_revision).toBe(4)
  })

  it('blocks initial enable without both directories before any PUT', async () => {
    const state = { current: makeSettings(makeEnglishAsr()) }
    const english = makeEnglishApi(async (input) =>
      resultFor(input, makeEnglishAsr({ revision: 4, configured: true })),
    )
    render(<SettingsView api={makeSettingsApi(state)} englishAsrApi={english.api} />)
    await openEditor()

    fireEvent.click(screen.getByLabelText('Enable English transcription'))
    fireEvent.change(screen.getByLabelText('Model assets directory (write-only)'), {
      target: { value: '/srv/models/embeddinggemma-2' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save English transcription settings' }))

    expect(
      await screen.findByText(/first enable requires both absolute local asset directories/i),
    ).toBeInTheDocument()
    expect(english.calls).toHaveLength(0)
  })

  it('keeps a pending save visible, then preserves a revision conflict and reloads latest settings', async () => {
    const state = { current: makeSettings(makeEnglishAsr({ configured: true, enabled: true, available: true, reason: null })) }
    let rejectSave: ((cause: unknown) => void) | null = null
    const gate = new Promise<EnglishAsrUpdateResult>((_resolve, reject) => {
      rejectSave = reject
    })
    const conflict = new ApiError({
      message: 'English ASR settings changed elsewhere',
      code: 'revision_conflict',
      httpStatus: 409,
      retryable: false,
    })
    const latest = makeEnglishAsr({
      revision: 5,
      content_hash: 'asr-hash-5',
      configured: true,
      enabled: true,
      available: true,
      reason: null,
    })
    const update = vi
      .fn()
      .mockImplementationOnce(async () => gate)
      .mockImplementationOnce(async (input: EnglishAsrUpdateInput) => resultFor(input, latest))
    const api: EnglishAsrApi = { update }
    render(<SettingsView api={makeSettingsApi(state)} englishAsrApi={api} />)
    await openEditor()

    fireEvent.click(screen.getByRole('button', { name: 'Save English transcription settings' }))
    expect(await screen.findByRole('button', { name: 'Saving…' })).toBeDisabled()

    await act(async () => {
      rejectSave?.(conflict)
      await gate.catch(() => undefined)
    })
    expect(await screen.findByText(/English ASR settings changed elsewhere/)).toBeInTheDocument()
    expect(screen.getByText(/Another write changed the canonical settings/)).toBeInTheDocument()
    expect(screen.queryByText(/settings saved at revision/)).toBeNull()
    expect(update).toHaveBeenCalledTimes(1)

    state.current = makeSettings(latest)
    fireEvent.click(screen.getByRole('button', { name: 'Reload latest settings' }))
    expect(await screen.findByText(/Loaded the current English transcription revision 5/)).toBeInTheDocument()
    expect(update).toHaveBeenCalledTimes(1)

    fireEvent.click(screen.getByRole('button', { name: 'Save English transcription settings' }))
    await waitFor(() => expect(update).toHaveBeenCalledTimes(2))
    expect(update.mock.calls[1][0].expected_revision).toBe(5)
    expect((await screen.findAllByText(/saved at revision 5/)).length).toBeGreaterThan(0)
  })

  it('does not fetch admin settings or show the form for a team member', async () => {
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
            contract_version: '1.20.0',
            capabilities: { ...HEALTH_FIXTURE.capabilities, accounts: false },
          }),
        } as unknown as Response
      }
      return backendFetch(input)
    }) as typeof fetch)

    const state = { current: makeSettings(makeEnglishAsr()) }
    const settingsApi = makeSettingsApi(state)
    const english = makeEnglishApi(async (input) => resultFor(input, makeEnglishAsr()))
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
    expect(settingsApi.listConnections).not.toHaveBeenCalled()
    expect(
      screen.queryByRole('button', { name: 'Configure English transcription' }),
    ).toBeNull()
    expect(english.calls).toHaveLength(0)
  })
})
