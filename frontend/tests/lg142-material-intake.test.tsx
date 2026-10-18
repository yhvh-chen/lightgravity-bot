/**
 * LG-142 Chat material-intake tests (docs/08 §20.3/§20.6).
 *
 * Local component tests against injected clients. They must not be read as
 * backend/media acceptance evidence:
 *  * file picks create local drafts only (no POST /sources before Send);
 *  * Send uses deferred intake once per draft then posts `source_refs`;
 *  * a failed intake blocks the message and keeps the draft;
 *  * a failed message send reuses accepted sources without another intake;
 *  * persisted message refs restore authoritative receipt v2 branches;
 *  * audio says Transcription unavailable even when semantic media succeeds;
 *  * task/scope changes drop drafts and never route private files to shared intake;
 *  * a 1.18 backend keeps the legacy path and never sends v2 fields.
 */

import { cleanup, configure, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { AttachmentsApi } from '../src/api/attachments'
import { createChatApi, type ChatApi, type ChatMessage, type ChatScope, type ChatSubmitResult } from '../src/api/chat'
import { ApiError } from '../src/api/client'
import type {
  SourceReceiptV2,
  SourceView,
  SourcesApi,
} from '../src/api/sources'
import type { AuthMeResponse } from '../src/api/teamAuth'
import { AuthProvider } from '../src/app/AuthProvider'
import { ShellProvider } from '../src/app/ShellProvider'
import { ChatBody } from '../src/views/chat/ChatBody'
import { HEALTH_FIXTURE, backendFetch } from './setup'

configure({ asyncUtilTimeout: 3000 })

const TEAM_PROBE = async (): Promise<AuthMeResponse> => ({
  mode: 'team',
  authenticated: true,
  username: 'alice',
  role: 'member',
})

function jsonResponse(body: unknown): Response {
  return {
    ok: true,
    status: 200,
    headers: {
      get: (name: string) =>
        name.toLowerCase() === 'content-type' ? 'application/json' : null,
    },
    json: async () => body,
  } as unknown as Response
}

function setHealth(capabilities: Record<string, boolean>, version = '1.19.0') {
  vi.mocked(fetch).mockImplementation((async (input: RequestInfo | URL) => {
    if (String(input).endsWith('/api/v1/health')) {
      return jsonResponse({
        ...HEALTH_FIXTURE,
        contract_version: version,
        capabilities: { ...HEALTH_FIXTURE.capabilities, ...capabilities },
      })
    }
    return backendFetch(input)
  }) as typeof fetch)
}

function source(id: string): SourceView {
  return {
    id,
    source_id: id,
    title: 'meeting.mp3',
    title_origin: 'user',
    status: 'received',
    intake_mode: 'deferred',
    revision: 1,
    etag: 'rev-1',
    scope: { task_ref: null, project_ref: null, inbox_ref: null },
    origin: { kind: 'upload', external_ref: null, fetched: false },
    content_hash: `${id}-hash`,
    stat_revision: null,
    source_version: 1,
    original: { path: 'original/meeting.mp3', media_type: 'audio/mpeg', bytes: 4 },
    derivatives: [],
    formal: { path: null, revision: null, edited_by: null },
    index: { lexical: 'not_indexed', vector: 'not_indexed' },
    receipt_ref: 'receipt.jsonl',
    created_at: null,
    updated_at: null,
    path: `sources/${id}/SOURCE.md`,
  }
}

function receipt(id: string): SourceReceiptV2 {
  return {
    source_id: id,
    revision: 2,
    status: 'extracted',
    source_version: 1,
    receipt_version: 2,
    partial: true,
    items: [
      {
        source_id: id,
        filename: 'meeting.mp3',
        status: 'extracted',
        stage: 'done',
        error_code: 'capability_unavailable',
        text: {
          status: 'unavailable',
          reason: 'asr_unavailable',
          error_code: 'capability_unavailable',
        },
        keyword: { status: 'no_text', reason: 'no_trusted_body', error_code: null },
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
}

function makeSourcesApi(options: {
  createSource?: ReturnType<typeof vi.fn>
  getReceipt?: ReturnType<typeof vi.fn>
  getSource?: ReturnType<typeof vi.fn>
} = {}): SourcesApi {
  return {
    createSource: options.createSource ?? vi.fn(async (input: { request_id: string }) => ({
      source: source(`source_${input.request_id.slice(-6)}`),
      job: { job_id: 'job_1' },
      deduplicated: false,
      created: true,
      receipts: [],
      intake_mode: 'deferred',
    })),
    listSources: vi.fn(async () => ({ items: [], next_cursor: null })),
    getSource: options.getSource ?? vi.fn(async (id: string) => source(id)),
    getReceipt: options.getReceipt ?? vi.fn(async (id: string) => receipt(id)),
    getContent: vi.fn(async () => {
      throw new ApiError({ message: 'no body', code: 'not_found', httpStatus: 404, retryable: false })
    }),
    downloadSource: vi.fn(),
    editFormal: vi.fn(),
    sourceAction: vi.fn(),
    appendInboxMessage: vi.fn(),
    search: vi.fn(),
  } as unknown as SourcesApi
}

function makeChatApi(options: {
  read?: (scope: ChatScope) => ChatMessage[]
  send?: (
    scope: ChatScope,
    body: { message_id: string; content: string; source_refs?: Array<{ source_id: string }> },
  ) => ChatSubmitResult
} = {}): ChatApi & {
  sent: Array<{ scope: ChatScope; body: Record<string, unknown> }>
} {
  const sent: Array<{ scope: ChatScope; body: Record<string, unknown> }> = []
  return {
    sent,
    readMessages: vi.fn(async (scope: ChatScope) => ({
      items: options.read?.(scope) ?? [],
      next_cursor: null,
    })),
    sendMessage: vi.fn(async (scope, body) => {
      sent.push({ scope, body: body as unknown as Record<string, unknown> })
      return options.send?.(scope, body) ?? { kind: 'recorded' }
    }),
    createTask: vi.fn(async () => ({ kind: 'create_task' })),
  } as unknown as ChatApi & { sent: typeof sent }
}

function renderChat(api: ChatApi, sourcesApi: SourcesApi, attachmentsApi?: AttachmentsApi, probe = TEAM_PROBE) {
  return render(
    <AuthProvider probe={probe}>
      <ShellProvider>
        <ChatBody
          variant="main"
          api={api}
          sourcesApi={sourcesApi}
          attachmentsApi={attachmentsApi}
        />
      </ShellProvider>
    </AuthProvider>,
  )
}

async function waitForTeamReady() {
  await waitFor(() =>
    expect(screen.getByRole('tab', { name: 'Team' })).toHaveAttribute('aria-selected', 'true'),
  )
}

async function chooseFile(name = 'meeting.mp3', type = 'audio/mpeg') {
  await waitForTeamReady()
  fireEvent.change(await screen.findByLabelText('Upload file for Global'), {
    target: { files: [new File(['data'], name, { type })] },
  })
}

async function submitText(value: string) {
  const composer = screen.getByLabelText('Message for Global')
  fireEvent.change(composer, { target: { value } })
  fireEvent.keyDown(composer, { key: 'Enter' })
}

beforeEach(() => {
  window.sessionStorage.clear()
  window.history.replaceState(null, '', '/')
  setHealth({ material_intake_v2: true, media_direct_embedding: true })
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.mocked(fetch).mockImplementation(backendFetch as typeof fetch)
})

describe('LG-142 Chat send-time intake', () => {
  it('keeps picks local until Send, then uses deferred intake and source_refs', async () => {
    const getReceipt = vi.fn(async (id: string) => receipt(id))
    const sourcesApi = makeSourcesApi({ getReceipt })
    const persisted: ChatMessage[] = []
    const api = makeChatApi({
      read: () => persisted,
      send: (_scope, body) => {
        persisted.push({
          message_id: body.message_id,
          role: 'user',
          content: body.content,
          attachments: [],
          source_refs: (body.source_refs ?? []).map((ref, index) => ({
            source_id: ref.source_id,
            source_version: 1,
            content_hash: `hash-${index}`,
            scope: { task_ref: null, project_ref: null, inbox_ref: null },
          })),
        })
        return { kind: 'recorded' }
      },
    })
    renderChat(api, sourcesApi)

    await chooseFile()
    expect(await screen.findByText('meeting.mp3')).toBeInTheDocument()
    expect(screen.getByText(/Draft — starts on Send/)).toBeInTheDocument()
    expect(sourcesApi.createSource).not.toHaveBeenCalled()
    expect(api.sent).toHaveLength(0)

    await submitText('summarize this audio')

    await waitFor(() => expect(sourcesApi.createSource).toHaveBeenCalledTimes(1))
    const input = vi.mocked(sourcesApi.createSource).mock.calls[0][0] as {
      intake_mode?: string
      request_id?: string
      content_base64?: string
    }
    expect(input.intake_mode).toBe('deferred')
    expect(input.request_id).toMatch(/^req_[0-9A-Z]{26}$/)
    expect(input.content_base64).not.toBe('')

    await waitFor(() => expect(api.sent).toHaveLength(1))
    expect(api.sent[0].body.source_refs).toEqual([
      { source_id: expect.stringMatching(/^source_/) },
    ])
    await waitFor(() => expect(screen.queryByText('Draft — starts on Send')).toBeNull())
    expect(getReceipt).toHaveBeenCalledTimes(1)
  })

  it.each([
    { mode: 'team', taskRef: null },
    { mode: 'team', taskRef: 'task_a' },
    { mode: 'single', taskRef: null },
    { mode: 'single', taskRef: 'task_a' },
  ])('sends attachment-only drafts once with retry and persisted receipts in $mode/$taskRef', async ({ mode, taskRef }) => {
    if (taskRef) window.history.replaceState(null, '', `/?view=chat&task=${taskRef}`)
    const sourcesApi = makeSourcesApi()
    let failSend = true
    const persisted: ChatMessage[] = []
    const api = makeChatApi({
      read: () => persisted,
      send: (_scope, body) => {
        if (failSend) throw new ApiError({ message: 'store unavailable', code: 'internal_error', httpStatus: 500, retryable: true })
        persisted.push({
          message_id: body.message_id, role: 'user', content: body.content, attachments: [],
          source_refs: (body.source_refs ?? []).map((ref) => ({
            source_id: ref.source_id, source_version: 1, content_hash: 'stored-hash',
            scope: { task_ref: taskRef, project_ref: null, inbox_ref: null },
          })),
        })
        return { kind: 'recorded' }
      },
    })
    const probe = mode === 'team' ? TEAM_PROBE : async (): Promise<AuthMeResponse> => ({ mode: 'single', authenticated: true, username: null, role: 'admin' })
    const mounted = renderChat(api, sourcesApi, undefined, probe)
    const scopeLabel = taskRef ?? 'Global'
    await screen.findByLabelText(`Message for ${scopeLabel}`)
    await waitFor(() => expect(screen.getByRole('button', { name: 'Upload file' })).toBeEnabled())
    fireEvent.change(screen.getByLabelText(`Upload file for ${scopeLabel}`), {
      target: { files: [new File(['data'], 'implement-a-feature.txt', { type: 'text/plain' })] },
    })
    expect(await screen.findByText('Draft — starts on Send')).toBeInTheDocument()
    expect(sourcesApi.createSource).not.toHaveBeenCalled()
    const send = screen.getByRole('button', { name: 'Send message' })
    fireEvent.click(send)
    fireEvent.click(send)
    expect(await screen.findByText(/Send failed:/)).toBeInTheDocument()
    expect(api.sent).toHaveLength(1)
    expect(screen.getByText('Stored')).toBeInTheDocument()
    expect(api.sent[0].body.content).toBe('Attached materials.')
    expect(api.sent[0].scope).toEqual({ taskRef, personal: false })
    expect(api.sent[0].body.source_refs).toHaveLength(1)
    expect(api.sent[0].body.selected_sources).toBeUndefined()
    expect(sourcesApi.createSource).toHaveBeenCalledWith(expect.objectContaining({
      intake_mode: 'deferred', scope: taskRef ? { task_ref: taskRef } : {},
    }))
    failSend = false
    fireEvent.click(send)
    await waitFor(() => expect(persisted).toHaveLength(1))
    expect(api.sent).toHaveLength(2)
    expect(api.sent[1].body.message_id).toBe(api.sent[0].body.message_id)
    expect(api.sent[1].body.source_refs).toEqual(api.sent[0].body.source_refs)
    expect(sourcesApi.createSource).toHaveBeenCalledTimes(1)
    expect(api.createTask).not.toHaveBeenCalled()
    await waitFor(() => expect(screen.queryByRole('list', { name: 'Draft files' })).toBeNull())
    mounted.unmount()
    renderChat(api, sourcesApi, undefined, probe)
    expect(await screen.findByText('Transcription unavailable')).toBeInTheDocument()
    expect(screen.getByText(/not model context/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }))
    expect(api.sent).toHaveLength(2)
  })

  it('restores receipt v2 branches from persisted message refs after refresh', async () => {
    const sourcesApi = makeSourcesApi()
    const api = makeChatApi({
      read: () => [
        {
          message_id: 'msg_hist',
          role: 'user',
          content: 'audio attached',
          attachments: [],
          source_refs: [
            {
              source_id: 'source_hist',
              source_version: 1,
              content_hash: 'hist-hash',
              scope: { task_ref: null, project_ref: null, inbox_ref: null },
            },
          ],
        },
      ],
    })
    renderChat(api, sourcesApi)

    expect(await screen.findByText('Transcription unavailable')).toBeInTheDocument()
    expect(screen.getByText('No text')).toBeInTheDocument()
    expect(screen.getByText('Searchable')).toBeInTheDocument()
    expect(screen.getByText('Partial')).toBeInTheDocument()
    expect(screen.getByText('media vector: audio')).toBeInTheDocument()
    expect(sourcesApi.getReceipt).toHaveBeenCalledWith('source_hist', expect.anything())
    // Receipts are traceability only, not an implicit selection.
    expect(screen.getByText(/not model context/)).toBeInTheDocument()
  })

  it('blocks Send on intake failure, keeps the draft, and retries without duplicates', async () => {
    let failSecond = true
    const createSource = vi.fn(async (input: { request_id: string; filename: string }) => {
      if (input.filename === 'two.txt' && failSecond) {
        throw new ApiError({
          message: 'intake rejected',
          code: 'validation_failed',
          httpStatus: 422,
          retryable: false,
        })
      }
      return {
        source: source(`source_${input.request_id.slice(-6)}`),
        job: { job_id: 'job_1' },
        deduplicated: false,
        created: true,
        receipts: [],
        intake_mode: 'deferred',
      }
    })
    const sourcesApi = makeSourcesApi({ createSource })
    const api = makeChatApi()
    renderChat(api, sourcesApi)

    await waitForTeamReady()
    fireEvent.change(await screen.findByLabelText('Upload file for Global'), {
      target: { files: [new File(['one'], 'one.txt', { type: 'text/plain' }), new File(['two'], 'two.txt', { type: 'text/plain' })] },
    })
    expect(await screen.findByText('one.txt')).toBeInTheDocument()
    expect(screen.getByText('two.txt')).toBeInTheDocument()

    await submitText('use both')
    expect(await screen.findByText(/Not sent — two\.txt: intake rejected/)).toBeInTheDocument()
    expect(api.sent).toHaveLength(0)
    expect(screen.getByText('Intake failed')).toBeInTheDocument()
    // The first file was accepted and stays reusable.
    expect(screen.getByText('Stored')).toBeInTheDocument()

    failSecond = false
    await submitText('use both')
    await waitFor(() => expect(api.sent).toHaveLength(1))
    // one call for the successful file, two for the failed-then-retried file.
    expect(createSource).toHaveBeenCalledTimes(3)
    expect((api.sent[0].body.source_refs as unknown[]).length).toBe(2)
  })

  it('reuses accepted sources when the message send fails, without another intake', async () => {
    const sourcesApi = makeSourcesApi()
    let failSend = true
    const api = makeChatApi({
      send: () => {
        if (failSend) {
          throw new ApiError({
            message: 'message store unavailable',
            code: 'internal_error',
            httpStatus: 500,
            retryable: true,
          })
        }
        return { kind: 'recorded' }
      },
    })
    renderChat(api, sourcesApi)

    await chooseFile()
    expect(await screen.findByText('meeting.mp3')).toBeInTheDocument()
    await submitText('first attempt')
    await waitFor(() => expect(api.sent).toHaveLength(1))
    expect(await screen.findByText(/Send failed:/)).toBeInTheDocument()
    expect(screen.getByText('Stored')).toBeInTheDocument()

    failSend = false
    await submitText('second attempt')
    await waitFor(() => expect(api.sent).toHaveLength(2))
    expect(sourcesApi.createSource).toHaveBeenCalledTimes(1)
    expect(api.sent[1].body.source_refs).toEqual(api.sent[0].body.source_refs)
  })

  it('clears local drafts on a Task/scope change and creates no source', async () => {
    window.history.replaceState(null, '', '/?view=chat&task=task_a')
    const sourcesApi = makeSourcesApi()
    const api = makeChatApi()
    renderChat(api, sourcesApi)

    expect(await screen.findByLabelText('Message for task_a')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Upload file for task_a'), {
      target: { files: [new File(['x'], 'task-a.txt', { type: 'text/plain' })] },
    })
    expect(await screen.findByText('task-a.txt')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Team conversation' }))
    expect(await screen.findByLabelText('Message for Global')).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByText('task-a.txt')).toBeNull())
    expect(sourcesApi.createSource).not.toHaveBeenCalled()
  })

  it('keeps Personal on the private attachment path under a v2 backend', async () => {
    setHealth({
      material_intake_v2: true,
      media_direct_embedding: true,
      private_attachments: true,
    })
    const attachmentsApi = {
      upload: vi.fn(async (file: File) => ({
        attachment_id: 'att_01J9Z0000000000000000000AA',
        filename: file.name,
        media_type: file.type,
        size: file.size,
        sha256: 'a'.repeat(64),
        status: 'stored',
        created_at: null,
      })),
      read: vi.fn(),
      content: vi.fn(),
      remove: vi.fn(),
    } as unknown as AttachmentsApi
    const sourcesApi = makeSourcesApi()
    const api = makeChatApi()
    renderChat(api, sourcesApi, attachmentsApi)

    fireEvent.click(await screen.findByRole('tab', { name: 'Personal' }))
    const input = await screen.findByLabelText('Upload file for Personal')
    await waitFor(() => expect(screen.getByRole('button', { name: 'Upload file' })).toBeEnabled())
    fireEvent.change(input, {
      target: { files: [new File(['private'], 'private.txt', { type: 'text/plain' })] },
    })
    await waitFor(() => expect(attachmentsApi.upload).toHaveBeenCalledTimes(1))
    expect(sourcesApi.createSource).not.toHaveBeenCalled()
    expect(screen.queryByText(/starts on Send/)).toBeNull()
    await waitFor(() => expect(screen.getByRole('button', { name: 'Send message' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }))
    expect(api.sent).toHaveLength(0)
    expect(sourcesApi.createSource).not.toHaveBeenCalled()
  })

  it('keeps the 1.18 legacy path and never sends v2 fields', async () => {
    setHealth({}, '1.18.0')
    const sourcesApi = makeSourcesApi()
    const api = makeChatApi()
    renderChat(api, sourcesApi)

    await chooseFile('legacy.txt', 'text/plain')
    await waitFor(() => expect(sourcesApi.createSource).toHaveBeenCalledTimes(1))
    const input = vi.mocked(sourcesApi.createSource).mock.calls[0][0] as {
      intake_mode?: string
    }
    expect(input.intake_mode).toBeUndefined()

    await submitText('legacy send')
    await waitFor(() => expect(api.sent).toHaveLength(1))
    expect(api.sent[0].body.source_refs).toBeUndefined()
    expect(screen.queryByText('Stored')).toBeNull()
    expect(screen.queryByText(/Draft — starts on Send/)).toBeNull()
  })
})

describe('LG-142 Chat wire adapter', () => {
  it('serializes source_refs only when present and restores the persisted snapshot', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ kind: 'recorded' }))
      .mockResolvedValueOnce(
        jsonResponse({
          items: [
            {
              message_id: 'msg_wire',
              message: {
                role: 'user',
                content: 'wire',
                source_refs: [
                  {
                    source_id: 'source_wire',
                    source_version: 2,
                    content_hash: 'wire-hash',
                    scope: { task_ref: 'task_a', project_ref: null, inbox_ref: null },
                  },
                ],
              },
            },
          ],
          next_cursor: null,
        }),
      )
      .mockResolvedValueOnce(jsonResponse({ kind: 'recorded' }))
    vi.stubGlobal('fetch', fetchMock)
    try {
      const api = createChatApi()
      await api.sendMessage(
        { taskRef: 'task_a' },
        {
          message_id: 'msg_wire',
          content: 'wire',
          source_refs: [{ source_id: 'source_wire' }],
        },
      )
      const requestBody = JSON.parse(
        String((fetchMock.mock.calls[0][1] as RequestInit).body),
      ) as Record<string, unknown>
      expect(requestBody.source_refs).toEqual([{ source_id: 'source_wire' }])

      const page = await api.readMessages({ taskRef: 'task_a' })
      expect(page.items[0].source_refs).toEqual([
        {
          source_id: 'source_wire',
          source_version: 2,
          content_hash: 'wire-hash',
          scope: { task_ref: 'task_a', project_ref: null, inbox_ref: null },
        },
      ])

      await api.sendMessage({ taskRef: null }, { message_id: 'msg_plain', content: 'plain' })
      const legacyBody = JSON.parse(
        String((fetchMock.mock.calls[2][1] as RequestInit).body),
      ) as Record<string, unknown>
      expect(legacyBody).not.toHaveProperty('source_refs')
    } finally {
      vi.unstubAllGlobals()
    }
  })
})
