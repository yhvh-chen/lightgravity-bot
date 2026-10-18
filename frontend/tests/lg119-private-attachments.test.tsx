import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { AttachmentsApi, PrivateAttachment } from '../src/api/attachments'
import type { ChatApi, ChatMessage, ChatScope, ChatSubmitResult } from '../src/api/chat'
import type { SourcesApi } from '../src/api/sources'
import type { AuthMeResponse } from '../src/api/teamAuth'
import { AuthProvider } from '../src/app/AuthProvider'
import { ShellProvider } from '../src/app/ShellProvider'
import { ChatBody } from '../src/views/chat/ChatBody'
import { HEALTH_FIXTURE, backendFetch } from './setup'

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

function privateAttachment(id = 'att_01J9Z0000000000000000000AA'): PrivateAttachment {
  return {
    attachment_id: id,
    filename: 'notes.txt',
    media_type: 'text/plain',
    size: 18,
    sha256: 'a'.repeat(64),
    status: 'stored',
    created_at: '2026-10-18T00:00:00Z',
  }
}

function makeChatApi(): ChatApi & {
  sent: Array<{ scope: ChatScope; body: { message_id: string; content: string; attachments?: unknown[] } }>
} {
  const sent: Array<{ scope: ChatScope; body: { message_id: string; content: string; attachments?: unknown[] } }> = []
  return {
    sent,
    readMessages: vi.fn(async () => ({ items: [] as ChatMessage[], next_cursor: null })),
    sendMessage: vi.fn(async (scope, body) => {
      sent.push({ scope, body })
      return { kind: 'direct', reply: 'ok' } as ChatSubmitResult
    }),
    createTask: vi.fn(async () => ({ kind: 'create_task' })),
  }
}

function makeAttachmentsApi(
  upload: ReturnType<typeof vi.fn> = vi.fn(
    async (file: File, options?: { attachmentId?: string }) => ({
      ...privateAttachment(options?.attachmentId),
      filename: file.name,
      size: file.size,
    }),
  ),
): AttachmentsApi & { upload: ReturnType<typeof vi.fn>; remove: ReturnType<typeof vi.fn> } {
  return {
    upload,
    read: vi.fn(async () => privateAttachment()),
    content: vi.fn(async () => ({
      attachment_id: privateAttachment().attachment_id,
      filename: 'notes.txt',
      media_type: 'text/plain',
      size: 18,
      encoding: 'utf-8' as const,
      content: 'PRIVATE-SENTINEL',
      revision: '18-1',
    })),
    remove: vi.fn(async () => undefined),
  } as unknown as AttachmentsApi & {
    upload: ReturnType<typeof vi.fn>
    remove: ReturnType<typeof vi.fn>
  }
}

function makeSourcesApi(): SourcesApi & { createSource: ReturnType<typeof vi.fn> } {
  const source = {
    source_id: 'source_01J',
    status: 'extracted',
    origin: { kind: 'upload', fetched: false },
    index: { lexical: 'indexed', vector: 'disabled' },
    source_version: 1,
    content_hash: 'abc',
  }
  return {
    createSource: vi.fn(async () => ({
      source,
      job: null,
      deduplicated: false,
      created: true,
      receipts: [],
    })),
    getSource: vi.fn(async () => source),
  } as unknown as SourcesApi & { createSource: ReturnType<typeof vi.fn> }
}

function renderChat(
  api: ChatApi,
  attachmentsApi: AttachmentsApi,
  sourcesApi?: SourcesApi,
) {
  return render(
    <AuthProvider probe={TEAM_PROBE}>
      <ShellProvider>
        <ChatBody
          variant="main"
          api={api}
          attachmentsApi={attachmentsApi}
          sourcesApi={sourcesApi}
        />
      </ShellProvider>
    </AuthProvider>,
  )
}

async function openPersonal() {
  fireEvent.click(await screen.findByRole('tab', { name: 'Personal' }))
  const upload = await screen.findByRole('button', { name: 'Upload file' })
  await waitFor(() => expect(upload).toBeEnabled())
  return upload
}

function file(name = 'notes.txt', body = 'PRIVATE-SENTINEL'): File {
  return new File([body], name, { type: 'text/plain' })
}

beforeEach(() => {
  sessionStorage.clear()
  history.replaceState(null, '', '/')
  vi.mocked(fetch).mockImplementation((async (input: RequestInfo | URL) => {
    if (String(input).endsWith('/api/v1/health')) {
      return jsonResponse({
        ...HEALTH_FIXTURE,
        contract_version: '1.18.0',
        capabilities: { ...HEALTH_FIXTURE.capabilities, private_attachments: true },
      })
    }
    return backendFetch(input)
  }) as typeof fetch)
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.mocked(fetch).mockImplementation(backendFetch as typeof fetch)
})

describe('LG-119 private Personal attachments', () => {
  it('opens the native picker directly, treats cancel as no request, and shows upload state', async () => {
    const api = makeChatApi()
    const attachmentsApi = makeAttachmentsApi()
    renderChat(api, attachmentsApi)
    const uploadButton = await openPersonal()

    const clickSpy = vi
      .spyOn(HTMLInputElement.prototype, 'click')
      .mockImplementation(() => undefined)
    fireEvent.click(uploadButton)
    expect(clickSpy).toHaveBeenCalledTimes(1)
    clickSpy.mockRestore()

    const input = screen.getByLabelText('Upload file for Personal')
    fireEvent.change(input, { target: { files: [] } })
    expect(attachmentsApi.upload).not.toHaveBeenCalled()

    fireEvent.change(input, { target: { files: [file()] } })
    expect(await screen.findByText('notes.txt')).toBeInTheDocument()
    expect(await screen.findByText('uploaded')).toBeInTheDocument()
    expect(attachmentsApi.upload).toHaveBeenCalledTimes(1)
    const [, options] = attachmentsApi.upload.mock.calls[0] as [File, { attachmentId: string }]
    expect(options.attachmentId).toMatch(/^att_[0-9A-HJKMNP-TV-Z]{26}$/)

    // No permanent instruction lines or footer hints remain.
    expect(screen.queryByText(/Enter to send/)).toBeNull()
    expect(screen.queryByText(/Private to you/)).toBeNull()
    expect(screen.queryByText(/Shared with the team/)).toBeNull()
  })

  it('shows failure honestly, retries with the same id, and removes an uploaded file', async () => {
    const first = privateAttachment('att_01J9Z0000000000000000000AB')
    const upload = vi
      .fn()
      .mockRejectedValueOnce(new Error('network down'))
      .mockResolvedValueOnce({ ...first, filename: 'notes.txt', size: 15 })
    const attachmentsApi = makeAttachmentsApi(upload)
    renderChat(makeChatApi(), attachmentsApi)
    await openPersonal()
    fireEvent.change(screen.getByLabelText('Upload file for Personal'), {
      target: { files: [file()] },
    })
    expect(await screen.findByText(/not uploaded/)).toBeInTheDocument()
    expect(screen.queryByText('uploaded')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findByText('uploaded')).toBeInTheDocument()
    const ids = upload.mock.calls.map(
      (call) => (call as [File, { attachmentId: string }])[1].attachmentId,
    )
    expect(ids).toHaveLength(2)
    expect(ids[0]).toBe(ids[1])

    fireEvent.click(screen.getByRole('button', { name: 'Remove attachment notes.txt' }))
    expect(attachmentsApi.remove).toHaveBeenCalledWith(ids[0])
    await waitFor(() => expect(screen.queryByText('notes.txt')).toBeNull())
  })

  it('sends only the private attachment_id to Personal and clears the pending chip', async () => {
    const api = makeChatApi()
    const attachmentsApi = makeAttachmentsApi()
    renderChat(api, attachmentsApi)
    await openPersonal()
    fireEvent.change(screen.getByLabelText('Upload file for Personal'), {
      target: { files: [file()] },
    })
    expect(await screen.findByText('uploaded')).toBeInTheDocument()

    const composer = screen.getByLabelText('Message for Personal')
    fireEvent.change(composer, { target: { value: 'summarize the file' } })
    fireEvent.keyDown(composer, { key: 'Enter' })

    await waitFor(() => expect(api.sent).toHaveLength(1))
    expect(api.sent[0].scope).toEqual({ taskRef: null, personal: true })
    const sentAttachment = api.sent[0].body.attachments?.[0] as { attachment_id: string }
    expect(sentAttachment.attachment_id).toMatch(/^att_[0-9A-HJKMNP-TV-Z]{26}$/)
    expect(Object.keys(sentAttachment)).toEqual(['attachment_id'])
    expect(JSON.stringify(api.sent[0].body.attachments)).not.toContain('path')
    await waitFor(() => expect(screen.queryByText('notes.txt')).toBeNull())
  })

  it('drops a late private upload after switching channels and never paints it into Team', async () => {
    let resolveUpload: (value: PrivateAttachment) => void = () => undefined
    const pending = new Promise<PrivateAttachment>((resolve) => {
      resolveUpload = resolve
    })
    const attachmentsApi = makeAttachmentsApi(vi.fn(() => pending))
    const api = makeChatApi()
    renderChat(api, attachmentsApi)
    await openPersonal()
    fireEvent.change(screen.getByLabelText('Upload file for Personal'), {
      target: { files: [file()] },
    })
    expect(await screen.findByText('uploading…')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('tab', { name: 'Team' }))
    await waitFor(() => expect(screen.getByLabelText('Message for Global')).toBeInTheDocument())
    await act(async () => {
      resolveUpload(privateAttachment())
    })
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(screen.queryByText('notes.txt')).toBeNull()
    expect(screen.queryByText('uploaded')).toBeNull()

    fireEvent.click(screen.getByRole('tab', { name: 'Personal' }))
    expect(await screen.findByLabelText('Message for Personal')).toBeInTheDocument()
    expect(screen.queryByText('notes.txt')).toBeNull()
  })

  it('Team picker reuses the shared intake and never sends a private attachment id', async () => {
    const api = makeChatApi()
    const attachmentsApi = makeAttachmentsApi()
    const sourcesApi = makeSourcesApi()
    renderChat(api, attachmentsApi, sourcesApi)

    fireEvent.change(await screen.findByLabelText('Upload file for Global'), {
      target: { files: [file('shared.md', '# shared')] },
    })
    await waitFor(() => expect(sourcesApi.createSource).toHaveBeenCalledTimes(1))
    const input = sourcesApi.createSource.mock.calls[0][0] as {
      filename: string
      content_base64: string
      origin: { kind: string }
    }
    expect(input.filename).toBe('shared.md')
    expect(input.content_base64).not.toBe('')
    expect(input.origin.kind).toBe('upload')
    expect(attachmentsApi.upload).not.toHaveBeenCalled()

    const composer = screen.getByLabelText('Message for Global')
    fireEvent.change(composer, { target: { value: '@bot use the material' } })
    fireEvent.keyDown(composer, { key: 'Enter' })
    await waitFor(() => expect(api.sent).toHaveLength(1))
    expect(api.sent[0].body.attachments).toEqual([])
  })

  it('renders persisted private attachment names and honest context status', async () => {
    const api = makeChatApi()
    api.readMessages = vi.fn(async (scope) => ({
      items: scope.personal
        ? [
            {
              message_id: 'msg_hist',
              role: 'assistant',
              content: 'I could not read the binary file.',
              attachments: [
                {
                  attachment_id: 'att_01J9Z0000000000000000000AC',
                  filename: 'photo.bin',
                  media_type: 'application/octet-stream',
                  size: 4,
                  context_status: 'binary_unsupported' as const,
                  context_chars: 0,
                },
              ],
            },
          ]
        : [],
      next_cursor: null,
    }))
    renderChat(api, makeAttachmentsApi())
    await openPersonal()
    expect(await screen.findByText('photo.bin')).toBeInTheDocument()
    expect(screen.getByText('not read — binary/non-UTF-8')).toBeInTheDocument()
  })

  it('keeps send icon/Enter/Shift+Enter/IME semantics and does not show a menu', async () => {
    const api = makeChatApi()
    const attachmentsApi = makeAttachmentsApi()
    renderChat(api, attachmentsApi)
    await openPersonal()

    const composer = screen.getByLabelText('Message for Personal')
    expect(screen.getByRole('button', { name: 'Send message' })).toBeInTheDocument()
    expect(screen.queryByRole('menu')).toBeNull()

    fireEvent.change(composer, { target: { value: 'line one' } })
    fireEvent.keyDown(composer, { key: 'Enter', shiftKey: true })
    expect(api.sent).toHaveLength(0)

    fireEvent.compositionStart(composer)
    fireEvent.keyDown(composer, { key: 'Enter' })
    expect(api.sent).toHaveLength(0)
    fireEvent.compositionEnd(composer)

    fireEvent.keyDown(composer, { key: 'Enter' })
    await waitFor(() => expect(api.sent).toHaveLength(1))
  })
})
