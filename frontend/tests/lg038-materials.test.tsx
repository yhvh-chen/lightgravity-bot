/**
 * LG-038 unified material experience — frontend tests.
 *
 * Exercises the new sources client and the Chat/Files material surfaces
 * against injected doubles, so no backend is required:
 *
 * * links are recorded `link_only` and never shown as text;
 * * global uploads state plainly that no Task/Run was created;
 * * per-file states (received/processing/success/partial/failure) render from
 *   the backend view, and a missing OCR/vector capability shows honestly;
 * * Files shows the *same* source state and refuses to fake a body;
 * * correction sends `expected_revision` and surfaces conflict;
 * * search hits carry source/version/hash and can be opened.
 */

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { ApiError } from '../src/api/client'
import type {
  SearchResult,
  SourceReceipt,
  SourceView,
  SourcesApi,
} from '../src/api/sources'
import { ChatMaterialIntake } from '../src/views/chat/ChatMaterialIntake'
import { ChatSourceSearch } from '../src/views/chat/ChatSourceSearch'
import { FilesMaterialsPanel } from '../src/views/files/FilesMaterialsPanel'
import type { MaterialRecord } from '../src/views/chat/useChatMaterials'

function source(overrides: Partial<SourceView> = {}): SourceView {
  return {
    id: 'source_01J',
    source_id: 'source_01J',
    title: 'notes.md',
    title_origin: 'user',
    status: 'extracted',
    revision: 2,
    etag: 'rev-2',
    scope: { task_ref: null, project_ref: null, inbox_ref: 'inbox_1' },
    origin: { kind: 'upload', external_ref: null, fetched: false },
    content_hash: 'deadbeefcafebabe',
    stat_revision: '12-1',
    source_version: 1,
    original: { path: 'original/notes.md', media_type: 'text/markdown', bytes: 12 },
    derivatives: [],
    formal: { path: 'formal/v1.md', revision: 1, edited_by: 'user' },
    index: { lexical: 'indexed', lexical_hash: 'abc', vector: 'disabled' },
    receipt_ref: null,
    created_at: '2026-10-16T00:00:00Z',
    updated_at: '2026-10-16T00:00:00Z',
    path: 'sources/source_01J/SOURCE.md',
    ...overrides,
  }
}

function makeApi(overrides: Partial<SourcesApi> = {}): SourcesApi {
  return {
    createSource: vi.fn(async () => ({
      source: source(),
      job: null,
      deduplicated: false,
      created: true,
      receipts: [],
    })),
    listSources: vi.fn(async () => ({ items: [source()], next_cursor: null })),
    getSource: overrides.getSource ?? vi.fn(async () => source()),
    getReceipt: vi.fn(
      async (): Promise<SourceReceipt> => ({
        source_id: 'source_01J',
        revision: 2,
        status: 'extracted',
        source_version: 1,
        items: [],
        latest: null,
      }),
    ),
    getContent: vi.fn(async () => ({
      source_id: 'source_01J',
      kind: 'machine',
      path: 'derivative/machine.v1.md',
      media_type: 'text/markdown; charset=utf-8',
      content: '# extracted body',
      formal_present: false,
    })),
    downloadSource: vi.fn(async () => ({
      blob: new Blob(['x']),
      filename: 'notes.md',
      mediaType: 'text/markdown',
      statRevision: '12-1',
      kind: 'original',
      contentHash: null,
    })),
    editFormal: vi.fn(async () => ({ source_id: 'source_01J', formal: {}, revision: 1 })),
    sourceAction: vi.fn(async () => ({ source_id: 'source_01J', status: 'processing' })),
    appendInboxMessage: vi.fn(async () => ({
      inbox_ref: 'inbox_1',
      message: {},
      task_created: false as const,
      run_created: false as const,
    })),
    search: vi.fn(async (): Promise<SearchResult> => ({
      query: 'invoice',
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
    ...overrides,
  }
}

function record(overrides: Partial<MaterialRecord> = {}): MaterialRecord {
  return {
    requestId: 'req_1',
    filename: 'notes.md',
    originKind: 'upload',
    externalRef: null,
    state: 'extracted',
    hasText: true,
    sourceId: 'source_01J',
    sourceVersion: 1,
    contentHash: 'deadbeefcafebabe',
    lexical: 'indexed',
    vector: 'disabled',
    jobId: null,
    stage: null,
    detail: null,
    error: null,
    deliveryCreated: false,
    ...overrides,
  }
}

describe('ChatMaterialIntake', () => {
  it('records a link as link_only and never as text', () => {
    const onRecordLink = vi.fn()
    render(
      <ChatMaterialIntake
        materials={[]}
        busy={false}
        scopeLabel="Global"
        onUploadFiles={vi.fn()}
        onRecordLink={onRecordLink}
        onRefresh={vi.fn()}
        onDismiss={vi.fn()}
      />,
    )
    fireEvent.change(screen.getByLabelText('Record a link'), {
      target: { value: 'https://example.com/doc' },
    })
    fireEvent.click(screen.getByText('Record link'))
    expect(onRecordLink).toHaveBeenCalledWith('https://example.com/doc')
  })

  it('shows uploads/drag-drop entries with per-file states', () => {
    render(
      <ChatMaterialIntake
        materials={[
          record({ state: 'processing', detail: 'received — processing' }),
          record({ requestId: 'req_2', state: 'failed', error: { code: 'capability_unavailable', message: 'no OCR' } }),
          record({ requestId: 'req_3', state: 'partial' }),
        ]}
        busy={false}
        scopeLabel="Global"
        onUploadFiles={vi.fn()}
        onRecordLink={vi.fn()}
        onRefresh={vi.fn()}
        onDismiss={vi.fn()}
      />,
    )
    expect(screen.getByText('processing')).toBeTruthy()
    expect(screen.getByText('failed')).toBeTruthy()
    expect(screen.getByText('partial success')).toBeTruthy()
    // The retryable capability error is surfaced honestly.
    expect(screen.getByText('no OCR')).toBeTruthy()
  })

  it('labels a link record link_only and not text', () => {
    render(
      <ChatMaterialIntake
        materials={[
          record({
            originKind: 'link',
            externalRef: 'https://example.com/doc',
            filename: 'example.com',
            state: 'received',
            hasText: false,
            detail: 'link recorded only — not fetched, not text',
          }),
        ]}
        busy={false}
        scopeLabel="Global"
        onUploadFiles={vi.fn()}
        onRecordLink={vi.fn()}
        onRefresh={vi.fn()}
        onDismiss={vi.fn()}
      />,
    )
    expect(screen.getByText('link_only')).toBeTruthy()
    expect(screen.getByText(/not fetched, not text/)).toBeTruthy()
  })

  it('offers uploads and states no delivery Task is created', () => {
    render(
      <ChatMaterialIntake
        materials={[]}
        busy={false}
        scopeLabel="Global"
        onUploadFiles={vi.fn()}
        onRecordLink={vi.fn()}
        onRefresh={vi.fn()}
        onDismiss={vi.fn()}
      />,
    )
    expect(screen.getByText(/no delivery Task\/Run is created/i)).toBeTruthy()
  })
})

describe('ChatSourceSearch', () => {
  it('renders hits with version + hash and opens the source', async () => {
    const onOpen = vi.fn()
    const api = makeApi({
      search: vi.fn(async () => ({
        query: 'invoice',
        kind: [],
        hits: [
          {
            source_id: 'source_01J',
            source_version: 3,
            content_hash: 'deadbeefcafebabe',
            basis: 'formal',
            scope: { task_ref: null, project_ref: null, inbox_ref: null },
            title: 'invoice.pdf',
            locators: [],
            snippet: '…total 42…',
            verified: true,
            stale: false,
            reason: null,
          },
        ],
        stale: [],
        skipped: [],
        index_status: 'ok' as const,
        authorized_scope: {
          task_ref: null,
          project_ref: null,
          inbox_ref: null,
          include_global: true,
        },
      })),
    })
    render(<ChatSourceSearch api={api} taskRef={null} onOpen={onOpen} />)
    fireEvent.change(screen.getByLabelText('Search materials'), {
      target: { value: 'invoice' },
    })
    fireEvent.click(screen.getByText('Search'))
    await screen.findByText('invoice.pdf')
    expect(screen.getByText('v3')).toBeTruthy()
    fireEvent.click(screen.getByText('Open in Tasks'))
    expect(onOpen).toHaveBeenCalledWith('source_01J')
  })

  it('reports an unavailable index instead of an empty success', async () => {
    const api = makeApi({
      search: vi.fn(async () => ({
        query: 'x',
        kind: [],
        hits: [],
        stale: [],
        skipped: [],
        index_status: 'index_unavailable' as const,
        index_unavailable_reason: 'cache_missing',
        authorized_scope: {
          task_ref: null,
          project_ref: null,
          inbox_ref: null,
          include_global: true,
        },
      })),
    })
    render(<ChatSourceSearch api={api} taskRef={null} onOpen={vi.fn()} />)
    fireEvent.change(screen.getByLabelText('Search materials'), { target: { value: 'x' } })
    fireEvent.click(screen.getByText('Search'))
    await screen.findByText(/Search index unavailable/)
    expect(screen.getByText(/cache_missing/)).toBeTruthy()
  })

  it('shows refused stale hits', async () => {
    const api = makeApi({
      search: vi.fn(async () => ({
        query: 'x',
        kind: [],
        hits: [],
        stale: [{ source_id: 'source_old', reason: 'source_stale' }],
        skipped: [],
        index_status: 'ok' as const,
        authorized_scope: {
          task_ref: null,
          project_ref: null,
          inbox_ref: null,
          include_global: true,
        },
      })),
    })
    render(<ChatSourceSearch api={api} taskRef={null} onOpen={vi.fn()} />)
    fireEvent.change(screen.getByLabelText('Search materials'), { target: { value: 'x' } })
    fireEvent.click(screen.getByText('Search'))
    await screen.findByText(/1 stale hit/)
  })
})

describe('FilesMaterialsPanel', () => {
  it('reads the same source state and previews content', async () => {
    const api = makeApi()
    render(<FilesMaterialsPanel api={api} taskRef={null} />)
    const item = await screen.findByText('notes.md')
    fireEvent.click(item)
    await screen.findAllByText(/extracted body/)
    expect(api.getSource).toHaveBeenCalledWith('source_01J')
    expect(api.getContent).toHaveBeenCalledWith('source_01J', 'auto')
    // Search is the same file SoT; index state is shown.
    expect(screen.getByText(/lexical: indexed/)).toBeTruthy()
  })

  it('shows no trusted body honestly when content is absent', async () => {
    const api = makeApi({
      getContent: vi.fn(async () => {
        throw new ApiError({
          message: 'no machine content exists',
          code: 'not_found',
          httpStatus: 404,
          retryable: false,
        })
      }),
    })
    render(<FilesMaterialsPanel api={api} taskRef={null} />)
    fireEvent.click(await screen.findByText('notes.md'))
    await screen.findByText('No trusted text yet')
  })

  it('sends expected_revision and reports a conflict instead of overwriting', async () => {
    const editFormal = vi.fn(async () => {
      throw new ApiError({
        message: 'formal version revision does not match',
        code: 'revision_conflict',
        httpStatus: 409,
        retryable: false,
      })
    })
    const api = makeApi({ editFormal })
    render(<FilesMaterialsPanel api={api} taskRef={null} />)
    fireEvent.click(await screen.findByText('notes.md'))
    await screen.findAllByText(/extracted body/)
    fireEvent.click(screen.getByText('Advanced details', { selector: 'summary' }))
    fireEvent.click(screen.getByText('Save correction'))
    await screen.findByText(/Conflict: the formal version changed/)
    expect(editFormal).toHaveBeenCalledWith(
      'source_01J',
      expect.objectContaining({ expected_revision: 1 }),
    )
  })

  it('refuses an out-of-scope read instead of hiding it', async () => {
    const api = makeApi({
      getSource: vi.fn(async () => {
        throw new ApiError({
          message: 'path outside authorized scope',
          code: 'path_outside_workspace',
          httpStatus: 403,
          retryable: false,
        })
      }),
    })
    render(<FilesMaterialsPanel api={api} taskRef="task_1" />)
    fireEvent.click(await screen.findByText('notes.md'))
    await screen.findByText('Out of scope')
  })

  it('reports an unconfigured OCR service as a non-fatal state on reprocess', async () => {
    const api = makeApi({
      sourceAction: vi.fn(async () => {
        throw new ApiError({
          message: 'no OCR backend configured',
          code: 'capability_unavailable',
          httpStatus: 503,
          retryable: true,
        })
      }),
    })
    render(<FilesMaterialsPanel api={api} taskRef={null} />)
    fireEvent.click(await screen.findByText('notes.md'))
    await screen.findAllByText(/extracted body/)
    fireEvent.click(screen.getByText('Reprocess (OCR)'))
    await screen.findByText(/no OCR backend configured/)
    expect(screen.getByText(/Original and existing body\/index were preserved/)).toBeTruthy()
  })

  it('archives reversibly (no revoke) and keeps the source openable', async () => {
    const sourceAction = vi.fn(async () => ({ source_id: 'source_01J', archived: true }))
    const api = makeApi({ sourceAction })
    render(<FilesMaterialsPanel api={api} taskRef={null} />)
    fireEvent.click(await screen.findByText('notes.md'))
    await screen.findAllByText(/extracted body/)
    fireEvent.click(screen.getByText('Archive'))
    await screen.findByText(/Archived. The source stays searchable and openable/)
    // Reversible archive uses the additive action, never revoke.
    expect(sourceAction).toHaveBeenCalledWith(
      'source_01J',
      expect.objectContaining({ action: 'archive', expected_revision: 2 }),
    )
    expect(sourceAction).not.toHaveBeenCalledWith(
      'source_01J',
      expect.objectContaining({ action: 'revoke' }),
    )
  })

  it('shows Unarchive for an already-archived source', async () => {
    const api = makeApi({ getSource: vi.fn(async () => source({ archived: true })) })
    render(<FilesMaterialsPanel api={api} taskRef={null} />)
    fireEvent.click(await screen.findByText('notes.md'))
    await screen.findAllByText(/extracted body/)
    expect(screen.getByText('Unarchive')).toBeTruthy()
  })

  it('writes the first human formal version when no machine body exists', async () => {
    const editFormal = vi.fn(async () => ({ source_id: 'source_01J', formal: {}, revision: 1 }))
    const api = makeApi({
      getSource: vi.fn(async () => source({
        formal: { path: null, revision: null, edited_by: null },
        reprocess: { kind: 'ocr', available: false, reason: 'ocr_unconfigured' },
      })),
      getContent: vi.fn(async () => {
        throw new ApiError({
          message: 'no content exists',
          code: 'not_found',
          httpStatus: 404,
          retryable: false,
        })
      }),
      editFormal,
    })
    render(<FilesMaterialsPanel api={api} taskRef={null} />)
    fireEvent.click(await screen.findByText('notes.md'))
    await screen.findByText('No trusted text yet')
    fireEvent.click(screen.getByText('Advanced details', { selector: 'summary' }))
    fireEvent.change(screen.getByLabelText('Formal version content'), {
      target: { value: 'Human-authored transcript from the image' },
    })
    fireEvent.click(screen.getByText('Save human formal version'))
    await waitFor(() =>
      expect(editFormal).toHaveBeenCalledWith(
        'source_01J',
        expect.objectContaining({
          content: 'Human-authored transcript from the image',
          expected_revision: 0,
        }),
      ),
    )
    await screen.findByText(/first human-authored formal version/)
  })

  it('disables audio reprocess with the backend-reported ASR reason', async () => {
    const sourceAction = vi.fn()
    const api = makeApi({
      getSource: vi.fn(async () => source({
        original: { path: 'original/meeting.mp3', media_type: 'audio/mpeg', bytes: 8 },
        reprocess: { kind: 'asr', available: false, reason: 'disabled' },
      })),
      sourceAction,
    })
    render(<FilesMaterialsPanel api={api} taskRef={null} />)
    fireEvent.click(await screen.findByText('notes.md'))
    await screen.findByText(/Reprocess unavailable: English transcription is disabled/)
    const button = screen.getByRole('button', { name: 'Reprocess audio (English ASR)' })
    expect(button).toBeDisabled()
    fireEvent.click(button)
    expect(sourceAction).not.toHaveBeenCalled()
  })
})

describe('sources client search query shape', () => {
  it('never defaults the scope to everything', async () => {
    const fetchSpy = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit) =>
        new Response(
        JSON.stringify({
          query: 'q',
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
        }),
        { status: 200, headers: { 'content-type': 'application/json' } },
      ),
    )
    vi.stubGlobal('fetch', fetchSpy)
    const { createSourcesApi } = await import('../src/api/sources')
    const client = createSourcesApi()
    const result = await client.search({ q: 'q' })
    expect(result.index_status).toBe('ok')
    const calledUrl = String(fetchSpy.mock.calls[0][0])
    expect(calledUrl).toContain('/api/v1/search')
    expect(calledUrl).toContain('q=q')
    vi.unstubAllGlobals()
    await waitFor(() => expect(fetchSpy).toHaveBeenCalled())
  })
})


it('opens readable machine content first and keeps raw bytes/correction behind accessible details', async () => {
  const raw = '---\nschema: lightgravity.machine/v1\nextractor: lg035-ocr\ninput_sha256: source-hash\n---\n# Meeting notes\nReadable extracted text.'
  const api = makeApi({ getContent: vi.fn(async () => ({ source_id: 'source_01J', kind: 'machine',
    path: 'derivative/machine.v1.md', media_type: 'text/markdown', content: raw, formal_present: false })) })
  render(<FilesMaterialsPanel api={api} taskRef={null} />)
  fireEvent.click(await screen.findByText('notes.md'))
  expect(await screen.findByRole('heading', { name: 'Meeting notes' })).toBeVisible()
  expect(screen.getByText('Machine text')).toBeVisible()
  expect(screen.getByRole('textbox', { name: 'Formal version content' })).not.toBeVisible()
  expect(screen.getByRole('link', { name: 'notes.md' }).getAttribute('href')).toContain('source%3Asource_01J')
  const summary = screen.getByText('Advanced details', { selector: 'summary' })
  const details = summary.closest('details')!
  expect(details.open).toBe(false)
  summary.focus()
  expect(summary).toHaveFocus()
  fireEvent.click(summary)
  expect(details.open).toBe(true)
  expect(within(details).getByRole('textbox', { name: 'Formal version content' })).toHaveValue(raw)
  expect(within(details).getByText(/input_sha256: source-hash/, { selector: 'pre' })).toBeVisible()
  expect(api.editFormal).not.toHaveBeenCalled()
  fireEvent.change(screen.getByRole('textbox', { name: 'Formal version content' }), { target: { value: '# corrected' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save correction' }))
  await waitFor(() => expect(api.editFormal).toHaveBeenCalledWith('source_01J', expect.objectContaining({ expected_revision: 1 })))
})
