/**
 * LG-161 English ASR receipt / Files / search tests.
 *
 * Injected clients only: no real model, TTS, Reader, browser or backend call.
 * They verify the additive 1.20 receipt fields, machine content read path,
 * legacy OCR compatibility, failure isolation/timestamps and independent search
 * branches.
 */

import { cleanup, configure, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'

import { ApiError } from '../src/api/client'
import type { SearchApi } from '../src/api/search'
import type {
  SourceContentView,
  SourceReceiptV2,
  SourceTextBranch,
  SourceView,
  SourcesApi,
} from '../src/api/sources'
import { HEALTH_FIXTURE } from './setup'
import { ShellProvider } from '../src/app/ShellProvider'
import { MaterialSearch } from '../src/components/MaterialSearch'
import {
  ChatMaterialReceipts,
} from '../src/views/chat/ChatMaterialIntake'
import { FilesMaterialsPanel } from '../src/views/files/FilesMaterialsPanel'

configure({ asyncUtilTimeout: 3000 })

const createObjectURL = vi.fn(() => 'blob:original-audio')
const revokeObjectURL = vi.fn()

beforeAll(() => {
  Object.defineProperty(URL, 'createObjectURL', { writable: true, value: createObjectURL })
  Object.defineProperty(URL, 'revokeObjectURL', { writable: true, value: revokeObjectURL })
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  createObjectURL.mockClear()
  revokeObjectURL.mockClear()
})

function machineProvenance(overrides: Record<string, unknown> = {}) {
  return {
    engine: 'eg2-reader-v2',
    encoder: {
      id: 'google/embeddinggemma-2',
      revision: '914f7f89142e33e77833254d9c9b90c3edf7303b',
      sha256: '197a32965d4b1105faf060417baa899e193fb73cd401f42ec9295234d5553d79',
      license: 'apache-2.0',
    },
    reader: {
      id: 'mlboydaisuke/EmbeddingGemma-2-Transcribe-Reader',
      revision: 'de224fd8fa4ed4519fdddd9aa4154432d46a1bd3',
      sha256: 'd605f6fba8687497be6b5fd717ea6c51beaee5d5f69c30a64225da96ebe0d8c2',
      license: 'apache-2.0',
    },
    runtime: 'inprocess',
    model_version: 'eg2-reader-v2+embeddinggemma-2@914f7f89',
    content_variant: 'machine',
    generated_at: '2026-10-18T00:00:00Z',
    ...overrides,
  }
}

function source(overrides: Partial<SourceView> = {}): SourceView {
  return {
    id: 'source_audio',
    source_id: 'source_audio',
    title: 'meeting.mp3',
    title_origin: 'user',
    status: 'indexed',
    intake_mode: 'deferred',
    revision: 4,
    etag: 'rev-4',
    scope: { task_ref: null, project_ref: null, inbox_ref: null },
    origin: { kind: 'upload', external_ref: null, fetched: false },
    content_hash: 'source-hash-1',
    stat_revision: null,
    source_version: 1,
    language: 'en',
    text_status: 'ready',
    original: { path: 'original/meeting.mp3', media_type: 'audio/mpeg', bytes: 8 },
    derivatives: [
      {
        kind: 'transcript',
        path: 'derivative/machine.v1.md',
        source_version: 1,
        content_hash: 'transcript-hash-1',
        model_version: 'eg2-reader-v2+embeddinggemma-2@914f7f89',
      },
    ],
    formal: { path: null, revision: null, edited_by: null },
    index: { lexical: 'indexed', vector: 'indexed' },
    receipt_ref: 'receipt.jsonl',
    created_at: null,
    updated_at: null,
    path: 'sources/source_audio/SOURCE.md',
    ...overrides,
  }
}

function textBranch(overrides: Partial<SourceTextBranch> = {}): SourceTextBranch {
  return {
    status: 'ready',
    reason: null,
    error_code: null,
    language: 'en',
    machine: machineProvenance(),
    timestamps: null,
    ...overrides,
  }
}

function receipt(
  text: SourceTextBranch,
  overrides: Partial<SourceReceiptV2> = {},
): SourceReceiptV2 {
  return {
    source_id: 'source_audio',
    revision: 3,
    status: 'indexed',
    source_version: 1,
    receipt_version: 2,
    partial: text.status !== 'ready',
    items: [
      {
        source_id: 'source_audio',
        filename: 'meeting.mp3',
        status: 'indexed',
        stage: 'done',
        text,
        keyword: {
          status: text.status === 'ready' ? 'searchable' : 'no_text',
          reason: text.status === 'ready' ? null : 'no_trusted_body',
          error_code: null,
        },
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
    ...overrides,
  }
}

function makeApi(options: {
  receipts?: SourceReceiptV2
  source?: SourceView
  getContent?: ReturnType<typeof vi.fn>
  search?: ReturnType<typeof vi.fn>
} = {}): SourcesApi {
  const item = options.source ?? source()
  return {
    createSource: vi.fn(),
    listSources: vi.fn(async () => ({ items: [item], next_cursor: null })),
    getSource: vi.fn(async () => item),
    getReceipt: vi.fn(async () => options.receipts ?? receipt(textBranch())),
    getIntakeJob: vi.fn(async () => null),
    intakeJobAction: vi.fn(),
    getContent:
      options.getContent ??
      vi.fn(async (_sourceId: string, kind: string): Promise<SourceContentView> => ({
        source_id: item.source_id,
        kind,
        path: kind === 'machine' ? 'derivative/machine.v1.md' : 'original/meeting.mp3',
        media_type: 'text/markdown; charset=utf-8',
        content: kind === 'machine' ? 'the small green truck crossed the bridge' : 'formal body',
        formal_present: false,
      })),
    downloadSource: vi.fn(async () => ({
      blob: new Blob(['audio']),
      filename: 'meeting.mp3',
      mediaType: 'audio/mpeg',
      statRevision: null,
      kind: 'original',
      contentHash: null,
    })),
    editFormal: vi.fn(),
    sourceAction: vi.fn(),
    appendInboxMessage: vi.fn(),
    search:
      options.search ??
      vi.fn(async () => ({
        query: 'truck',
        kind: [],
        hits: [],
        stale: [],
        skipped: [],
        index_status: 'ok',
        authorized_scope: {
          task_ref: null,
          project_ref: null,
          inbox_ref: null,
          include_global: true,
        },
      })),
  } as unknown as SourcesApi
}

function renderReceipt(api: SourcesApi) {
  return render(
    <ChatMaterialReceipts
      refs={[{ source_id: 'source_audio', source_version: 1, content_hash: 'source-hash-1', scope: { task_ref: null, project_ref: null, inbox_ref: null } }]}
      api={api}
      onOpen={() => {}}
      materialIntakeV2
      maxAttempts={1}
    />,
  )
}

describe('LG-161 Chat English receipt', () => {
  it('shows ready English machine provenance, null timestamps and receipt-only context note', async () => {
    renderReceipt(makeApi())

    expect(await screen.findByText('English transcript ready')).toBeInTheDocument()
    expect(screen.getByText(/machine English transcript/)).toBeInTheDocument()
    expect(screen.getByText(/eg2-reader-v2/)).toBeInTheDocument()
    expect(
      screen.getAllByText(/eg2-reader-v2\+embeddinggemma-2@914f7f89/).length,
    ).toBeGreaterThan(0)
    expect(screen.getAllByText(/word timestamps not available/).length).toBeGreaterThan(0)
    expect(
      screen.getByText(/Receipts only — not model context. Select materials explicitly to include context./),
    ).toBeInTheDocument()
    expect(screen.queryByRole('slider')).toBeNull()
    expect(screen.queryByRole('button', { name: /seek/i })).toBeNull()
  })

  it('keeps failed and non-terminal ASR states honest (no success inference)', async () => {
    const api = makeApi({ receipts: receipt(textBranch({ status: 'failed', reason: 'asr_timeout', machine: null, language: null })) })
    renderReceipt(api)
    expect(await screen.findByText('English transcription timed out')).toBeInTheDocument()
    expect(screen.queryByText('English transcript ready')).toBeNull()
    expect(screen.queryByText('Text ready')).toBeNull()

    cleanup()
    const pendingApi = makeApi({
      receipts: receipt(
        textBranch({
          status: 'extracting',
          reason: 'asr_stop_unconfirmed',
          machine: null,
          language: null,
        }),
      ),
    })
    renderReceipt(pendingApi)
    expect(await screen.findByText('Transcription stop unconfirmed')).toBeInTheDocument()
    expect(screen.getByText(/may still be running/)).toBeInTheDocument()
    expect(screen.queryByText('English transcript ready')).toBeNull()
  })
})

describe('LG-161 Files machine English transcript', () => {
  it('reads the machine content JSON endpoint while keeping formal-first text and original audio', async () => {
    const getContent = vi.fn(async (_sourceId: string, kind: string): Promise<SourceContentView> => {
      if (kind === 'machine') {
        return {
          source_id: 'source_audio',
          kind: 'machine',
          path: 'derivative/machine.v1.md',
          media_type: 'text/markdown; charset=utf-8',
          content: 'the small green truck crossed the bridge',
          formal_present: true,
        }
      }
      return {
        source_id: 'source_audio',
        kind: 'formal',
        path: 'documents/formal.md',
        media_type: 'text/markdown; charset=utf-8',
        content: 'human corrected formal body',
        formal_present: true,
      }
    })
    const api = makeApi({
      source: source({ formal: { path: 'documents/formal.md', revision: 2, edited_by: 'user' } }),
      getContent,
    })
    render(<FilesMaterialsPanel api={api} taskRef={null} materialIntakeV2 mediaDirectEmbedding />)
    fireEvent.click(await screen.findByText('meeting.mp3'))

    expect(await screen.findByText('Machine English transcript')).toBeInTheDocument()
    expect(getContent).toHaveBeenCalledWith('source_audio', 'machine', expect.anything())
    expect(
      (await screen.findAllByText('the small green truck crossed the bridge')).length,
    ).toBeGreaterThan(0)
    expect(screen.getAllByText('human corrected formal body').length).toBeGreaterThan(0)
    expect(screen.getByText(/v1 · #source-hash-1/)).toBeInTheDocument()
    expect(screen.getAllByText(/word timestamps not available/).length).toBeGreaterThan(0)
    expect(
      screen.getAllByText(/eg2-reader-v2\+embeddinggemma-2@914f7f89/).length,
    ).toBeGreaterThan(0)
    expect(document.querySelector('audio')).not.toBeNull()
    expect(screen.getByRole('button', { name: 'Download original' })).toBeInTheDocument()
    expect(screen.queryByRole('slider')).toBeNull()
  })

  it('keeps legacy OCR machine text without claiming an English transcript if provenance is absent', async () => {
    const getContent = vi.fn(async (_sourceId: string, _kind: string): Promise<SourceContentView> => ({
      source_id: 'source_audio',
      kind: 'machine',
      path: 'derivative/machine.v1.md',
      media_type: 'text/markdown; charset=utf-8',
      content: 'legacy OCR machine text',
      formal_present: false,
    }))
    const api = makeApi({
      source: source({ language: null, text_status: undefined, derivatives: [] }),
      receipts: receipt({ status: 'ready', reason: null, error_code: null, language: null, machine: null, timestamps: null }),
      getContent,
    })
    render(<FilesMaterialsPanel api={api} taskRef={null} materialIntakeV2 />)
    fireEvent.click(await screen.findByText('meeting.mp3'))

    expect((await screen.findAllByText('legacy OCR machine text')).length).toBeGreaterThan(0)
    expect(screen.getByText('machine', { selector: 'strong' })).toBeInTheDocument()
    expect(screen.queryByText('Machine English transcript')).toBeNull()
    expect(getContent).toHaveBeenCalledWith('source_audio', 'auto')
    expect(getContent).not.toHaveBeenCalledWith('source_audio', 'machine', expect.anything())
  })

  it('does not hide the original audio or media semantic branch when ASR failed', async () => {
    const api = makeApi({
      source: source({
        language: null,
        text_status: 'failed',
        derivatives: [],
        formal: { path: null, revision: null, edited_by: null },
      }),
      receipts: receipt(
        textBranch({ status: 'failed', reason: 'asr_timeout', language: null, machine: null }),
      ),
      getContent: vi.fn(async () => {
        throw new ApiError({
          message: 'no trusted body',
          code: 'not_found',
          httpStatus: 404,
          retryable: false,
        })
      }),
    })
    render(<FilesMaterialsPanel api={api} taskRef={null} materialIntakeV2 mediaDirectEmbedding />)
    fireEvent.click(await screen.findByText('meeting.mp3'))

    expect(await screen.findByText('English transcription timed out')).toBeInTheDocument()
    expect(screen.getByText('Searchable')).toBeInTheDocument()
    expect(screen.getByText(/media vector: audio/)).toBeInTheDocument()
    expect(document.querySelector('audio')).not.toBeNull()
    expect(screen.queryByText('Machine English transcript')).toBeNull()
  })
})

describe('LG-161 search independence', () => {
  it('finds a machine transcript through keyword search and keeps semantic audio separate', async () => {
    const keywordHit = {
      source_id: 'source_audio',
      source_version: 1,
      content_hash: 'source-hash-1',
      basis: 'transcript',
      scope: { task_ref: null, project_ref: null, inbox_ref: null },
      title: 'meeting.mp3',
      locators: [],
      snippet: 'small green truck transcript snippet',
      verified: true,
      stale: false,
      reason: null,
    }
    const semanticHit = {
      ...keywordHit,
      kind: 'audio',
      basis: 'original',
      snippet: '',
    }
    const sourcesApi = makeApi({
      search: vi.fn(async () => ({
        query: 'truck',
        kind: [],
        hits: [keywordHit],
        stale: [],
        skipped: [],
        index_status: 'ok',
        authorized_scope: {
          task_ref: null,
          project_ref: null,
          inbox_ref: null,
          include_global: true,
        },
      })),
    })
    const searchApi = {
      getVectorStatus: vi.fn(async () => ({
        enabled: true,
        backend: { configured: true, model: 'fixture-embed' },
        cache: { exists: true, readable: true, documents: 1, compatible: true, reason: null },
        model_mismatch_rebuild_required: false,
        reason: null,
      })),
      searchSemantic: vi.fn(async () => ({
        query: 'truck',
        kind: [],
        hits: [semanticHit],
        stale: [],
        skipped: [],
        index_status: 'ok',
        authorized_scope: {
          task_ref: null,
          project_ref: null,
          inbox_ref: null,
          include_global: true,
        },
      })),
      searchKeyword: vi.fn(),
      rebuildVector: vi.fn(),
    } as unknown as SearchApi

    render(
      <ShellProvider>
        <MaterialSearch
          health={{
            ...HEALTH_FIXTURE,
            contract_version: '1.20.0',
            capabilities: {
              ...HEALTH_FIXTURE.capabilities,
              semantic_search: true,
              media_direct_embedding: true,
            },
          }}
          sourcesApi={sourcesApi}
          searchApi={searchApi}
        />
      </ShellProvider>,
    )

    const input = screen.getByRole('searchbox', { name: 'Search' })
    fireEvent.change(input, { target: { value: 'truck' } })
    fireEvent.keyDown(input, { key: 'Enter' })

    expect(await screen.findByText('small green truck transcript snippet')).toBeInTheDocument()
    expect(screen.getByText(/basis: transcript/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('tab', { name: 'Semantic' }))
    fireEvent.keyDown(input, { key: 'Enter' })
    await waitFor(() => expect(searchApi.searchSemantic).toHaveBeenCalledTimes(1))
    expect(
      await screen.findByText(/Keyword search may find the machine English transcript when one is ready/),
    ).toBeInTheDocument()
    expect(screen.getByText('Audio')).toBeInTheDocument()
    expect(screen.getByText(/basis: original · audio/)).toBeInTheDocument()
  })
})
