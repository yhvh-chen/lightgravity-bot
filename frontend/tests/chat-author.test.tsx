import { cleanup, fireEvent, render, renderHook, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { createChatApi, type ChatApi, type ChatMessage, type ChatSubmitResult } from '../src/api/chat'
import { ApiError } from '../src/api/client'
import { AuthProvider } from '../src/app/AuthProvider'
import { ShellProvider } from '../src/app/ShellProvider'
import { ChatBody } from '../src/views/chat/ChatBody'
import { useChat } from '../src/views/chat/useChat'

/**
 * LG-050 chat: server `author` rendering (with Unknown history), recorded
 * team messages, and the global incremental polling contract (dedupe,
 * visibility pause, 401 → re-login).
 */

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers({ 'content-type': 'application/json' }),
    json: async () => body,
  } as unknown as Response
}

function makeApi(overrides: Partial<ChatApi> = {}): ChatApi & {
  sent: Array<{ body: Record<string, unknown> }>
} {
  const sent: Array<{ body: Record<string, unknown> }> = []
  return {
    sent,
    readMessages: vi.fn(async () => ({ items: [], next_cursor: null })),
    sendMessage: vi.fn(async (_scope, body) => {
      sent.push({ body: body as unknown as Record<string, unknown> })
      return { kind: 'answer', reply: 'ok' }
    }),
    createTask: vi.fn(async () => ({ kind: 'create_task' })),
    ...overrides,
  }
}

function makeMessage(overrides: Partial<ChatMessage> = {}): ChatMessage {
  return {
    message_id: 'msg_1',
    role: 'user',
    content: 'hello',
    attachments: [],
    ...overrides,
  }
}

beforeEach(() => {
  window.sessionStorage.clear()
  window.history.replaceState(null, '', '/')
})

afterEach(() => {
  cleanup()
  Object.defineProperty(document, 'hidden', { configurable: true, value: false })
  vi.restoreAllMocks()
})

describe('LG-050 chat: server author', () => {
  it('normalises the additive author field from the nested wire envelope', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse({
        items: [
          {
            message_id: 'msg_a',
            message: {
              role: 'user',
              content: 'hi',
              attachments: [],
              author: { kind: 'user', username: 'alice', role: 'member' },
            },
          },
        ],
        next_cursor: null,
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const page = await createChatApi().readMessages({ taskRef: null })
    expect(page.items[0].author).toEqual({ kind: 'user', username: 'alice', role: 'member' })
    vi.unstubAllGlobals()
  })

  it('shows the server author and renders authorless history as Unknown in team mode', async () => {
    const api = makeApi({
      readMessages: vi.fn(async () => ({
        items: [
          makeMessage({
            message_id: 'msg_alice',
            content: 'hello from alice',
            author: { kind: 'user', username: 'alice', role: 'member' },
          }),
          makeMessage({ message_id: 'msg_legacy', content: 'legacy row' }),
          makeMessage({
            message_id: 'msg_bot',
            role: 'assistant',
            content: 'bot reply',
            author: { kind: 'bot', username: 'bot', role: 'assistant' },
          }),
        ],
        next_cursor: null,
      })),
    })

    render(
      <AuthProvider
        probe={async () => ({ mode: 'team', authenticated: true, username: 'alice', role: 'member' })}
      >
        <ShellProvider>
          <ChatBody variant="main" api={api} />
        </ShellProvider>
      </AuthProvider>,
    )

    expect(await screen.findByText('alice')).toBeInTheDocument()
    // Historical row without a server author is not attributed to anyone.
    expect(await screen.findByText('Unknown')).toBeInTheDocument()
    expect(await screen.findByText('bot')).toBeInTheDocument()
  })
})

describe('LG-050 chat: recorded team message', () => {
  it('treats a recorded response as a plain shared message without a bot reply', async () => {
    const recorded: ChatSubmitResult = {
      kind: 'recorded',
      reply: null,
      conversation_id: 'conv_global',
      data: { intent: 'recorded', creates_task: false },
    }
    const api = makeApi({
      sendMessage: vi.fn(async (_scope, body) => {
        api.sent.push({ body: body as unknown as Record<string, unknown> })
        return recorded
      }),
    })

    render(
      <ShellProvider>
        <ChatBody variant="main" api={api} />
      </ShellProvider>,
    )

    const composer = await screen.findByLabelText('Message for Global')
    fireEvent.change(composer, { target: { value: 'plain team note' } })
    fireEvent.keyDown(composer, { key: 'Enter' })

    expect(await screen.findByText('Shared with the team.')).toBeInTheDocument()
    // The client never sends an author; the server derives it from the session.
    expect(api.sent).toHaveLength(1)
    expect(api.sent[0].body).not.toHaveProperty('author')
    expect(api.sent[0].body.content).toBe('plain team note')
  })
})

describe('LG-050 chat: global polling', () => {
  it('polls incrementally with the cursor and deduplicates by message_id', async () => {
    const cursors: Array<string | null | undefined> = []
    const msg1 = makeMessage({ message_id: 'msg_1', content: 'one' })
    const msg2 = makeMessage({ message_id: 'msg_2', content: 'two' })
    const api = makeApi({
      readMessages: vi.fn(async (_scope, cursor) => {
        cursors.push(cursor)
        if (cursors.length === 1) return { items: [msg1], next_cursor: 'c1' }
        return { items: [msg1, msg2], next_cursor: 'c2' }
      }) as unknown as ChatApi['readMessages'],
    })

    const { result } = renderHook(() =>
      useChat({ taskRef: null }, api, { pollIntervalMs: 25 }),
    )

    await waitFor(() => expect(result.current.messages).toHaveLength(2))
    expect(result.current.messages.map((message) => message.message_id)).toEqual([
      'msg_1',
      'msg_2',
    ])
    expect(cursors[1]).toBe('c1')
  })

  it('pauses polling while the page is hidden and resumes when visible', async () => {
    Object.defineProperty(document, 'hidden', { configurable: true, value: true })
    let calls = 0
    const api = makeApi({
      readMessages: vi.fn(async () => {
        calls += 1
        return { items: [], next_cursor: null }
      }) as unknown as ChatApi['readMessages'],
    })

    renderHook(() => useChat({ taskRef: null }, api, { pollIntervalMs: 20 }))
    await waitFor(() => expect(calls).toBe(1))
    await new Promise((resolve) => setTimeout(resolve, 80))
    expect(calls).toBe(1)

    Object.defineProperty(document, 'hidden', { configurable: true, value: false })
    await waitFor(() => expect(calls).toBeGreaterThan(1))
  })

  it('reports an expired session when a poll returns 401', async () => {
    let calls = 0
    const api = makeApi({
      readMessages: vi.fn(async () => {
        calls += 1
        if (calls === 1) return { items: [], next_cursor: null }
        throw new ApiError({
          message: 'authentication required',
          code: 'unauthorized',
          httpStatus: 401,
          retryable: false,
        })
      }) as unknown as ChatApi['readMessages'],
    })
    const onUnauthorized = vi.fn()

    renderHook(() =>
      useChat({ taskRef: null }, api, { pollIntervalMs: 20, onUnauthorized }),
    )

    await waitFor(() => expect(onUnauthorized).toHaveBeenCalled())
  })

  it('does not poll a Task-scoped conversation', async () => {
    let calls = 0
    const api = makeApi({
      readMessages: vi.fn(async () => {
        calls += 1
        return { items: [], next_cursor: null }
      }) as unknown as ChatApi['readMessages'],
    })

    renderHook(() => useChat({ taskRef: 'task_x' }, api, { pollIntervalMs: 20 }))
    await waitFor(() => expect(calls).toBe(1))
    await new Promise((resolve) => setTimeout(resolve, 80))
    expect(calls).toBe(1)
  })

  it('leaves single-user behavior untouched (no polling without an interval)', async () => {
    let calls = 0
    const api = makeApi({
      readMessages: vi.fn(async () => {
        calls += 1
        return { items: [], next_cursor: null }
      }) as unknown as ChatApi['readMessages'],
    })
    renderHook(() => useChat({ taskRef: null }, api))
    await waitFor(() => expect(calls).toBe(1))
    await new Promise((resolve) => setTimeout(resolve, 80))
    expect(calls).toBe(1)
  })
})
