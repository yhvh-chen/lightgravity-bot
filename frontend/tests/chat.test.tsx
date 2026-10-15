import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { ChatApi, ChatMessage, ChatScope, ChatSubmitResult } from '../src/api/chat'
import { ApiError } from '../src/api/client'
import type { Attachment } from '../src/api/types'
import { ShellProvider } from '../src/app/ShellProvider'
import { ChatBody } from '../src/views/chat/ChatBody'

afterEach(cleanup)

beforeEach(() => {
  window.sessionStorage.clear()
  window.history.replaceState(null, '', '/')
})

function makeChatApi(options: {
  messages?: Record<string, ChatMessage[]>
  send?: (scope: ChatScope, body: { message_id: string; content: string; attachments?: Attachment[] }) => ChatSubmitResult
  sendError?: ApiError
} = {}): ChatApi & { sent: Array<{ scope: ChatScope; body: { message_id: string; content: string; attachments?: Attachment[] } }> } {
  const sent: Array<{ scope: ChatScope; body: { message_id: string; content: string; attachments?: Attachment[] } }> = []
  return {
    sent,
    readMessages: vi.fn(async (scope: ChatScope) => ({
      items: options.messages?.[scope.taskRef ?? 'global'] ?? [],
      next_cursor: null,
    })),
    sendMessage: vi.fn(async (scope, body) => {
      sent.push({ scope, body })
      if (options.sendError) throw options.sendError
      return options.send?.(scope, body) ?? { kind: 'answer', reply: 'ok' }
    }),
    createTask: vi.fn(async () => ({ kind: 'create_task' })),
  }
}

function renderChat(api: ChatApi) {
  return render(
    <ShellProvider>
      <ChatBody variant="main" api={api} />
    </ShellProvider>,
  )
}

describe('LG-013 Chat: real history and sending', () => {
  it('renders the global history from the backend and sends a real message', async () => {
    const api = makeChatApi({
      messages: {
        global: [
          { message_id: 'msg_1', role: 'user', content: 'hello', attachments: [], at: '2026-10-15T00:00:00Z' },
          { message_id: 'msg_2', role: 'assistant', content: 'hi there', attachments: [] },
        ],
      },
    })
    renderChat(api)

    expect(await screen.findByText('hello')).toBeInTheDocument()
    expect(screen.getByText('hi there')).toBeInTheDocument()

    const composer = screen.getByLabelText('Message for Global')
    fireEvent.change(composer, { target: { value: 'do the thing' } })
    fireEvent.keyDown(composer, { key: 'Enter' })

    await waitFor(() => expect(api.sent).toHaveLength(1))
    expect(api.sent[0].scope).toEqual({ taskRef: null })
    expect(api.sent[0].body.content).toBe('do the thing')
    // A well-formed idempotency key is generated locally.
    expect(api.sent[0].body.message_id).toMatch(/^msg_[0-9A-Z]{26}$/)
    // Draft clears only after a successful send.
    await waitFor(() => expect(composer).toHaveValue(''))
  })

  it('keeps the draft and shows the real error when the send fails', async () => {
    const api = makeChatApi({
      sendError: new ApiError({
        message: 'backend not ready',
        code: 'not_ready',
        httpStatus: 503,
        retryable: true,
      }),
    })
    renderChat(api)

    const composer = await screen.findByLabelText('Message for Global')
    fireEvent.change(composer, { target: { value: 'keep me' } })
    fireEvent.keyDown(composer, { key: 'Enter' })

    expect(await screen.findByText(/Send failed:/)).toBeInTheDocument()
    expect(composer).toHaveValue('keep me')
    // No fabricated bubble was created from the unsent draft.
    expect(screen.queryAllByText('keep me', { selector: '.lg-message__bubble' })).toHaveLength(0)
  })

  it('switches to a newly created Task returned by a delivery reply', async () => {
    const api = makeChatApi({ send: () => ({ kind: 'create_task', task_id: 'task_01ABC', reply: 'created' }) })
    renderChat(api)

    const composer = await screen.findByLabelText('Message for Global')
    fireEvent.change(composer, { target: { value: 'implement the feature' } })
    fireEvent.keyDown(composer, { key: 'Enter' })

    expect(await screen.findByText(/Created Task task_01ABC/)).toBeInTheDocument()
    // Scope switched to the created Task.
    expect(await screen.findByLabelText('Message for task_01ABC')).toBeInTheDocument()
  })

  it('sends attachment references as paths, not bytes', async () => {
    const api = makeChatApi()
    renderChat(api)

    fireEvent.change(await screen.findByLabelText('Attach file path'), {
      target: { value: 'inputs/spec.md' },
    })
    const composer = screen.getByLabelText('Message for Global')
    fireEvent.change(composer, { target: { value: 'see attached' } })
    fireEvent.keyDown(composer, { key: 'Enter' })

    await waitFor(() => expect(api.sent).toHaveLength(1))
    expect(api.sent[0].body.attachments).toEqual([
      { path: 'inputs/spec.md', media_type: 'text/markdown' },
    ])
  })
})
