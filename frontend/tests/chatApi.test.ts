import { afterEach, describe, expect, it, vi } from 'vitest'

import { createChatApi, newRuntimeId } from '../src/api/chat'

/**
 * LG-013 wire-shape tests for the Chat API client.
 *
 * The frozen endpoints return the persisted envelope
 * `{ message_id, seq, message: { role, content, attachments } }`. These tests
 * stub `fetch` with that exact shape and assert the client normalises it to the
 * flat `ChatMessage` the views render — a blank bubble here would mean the real
 * history silently disappears.
 */

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers({ 'content-type': 'application/json' }),
    json: async () => body,
  } as unknown as Response
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('LG-013 chatApi', () => {
  it('normalises the nested global message envelope', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse({
        items: [
          {
            message_id: 'msg_real1',
            seq: 1,
            message: { role: 'user', content: 'nested hello', attachments: [] },
          },
          {
            message_id: 'msg_real2',
            seq: 2,
            message: {
              role: 'assistant',
              content: 'nested answer',
              attachments: [{ path: 'out/result.md', media_type: 'text/markdown' }],
            },
          },
        ],
        next_cursor: 'v1:global:2',
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const page = await createChatApi().readMessages({ taskRef: null })

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/conversations/global/messages',
      expect.objectContaining({ headers: { Accept: 'application/json' } }),
    )
    expect(page.items).toEqual([
      expect.objectContaining({
        message_id: 'msg_real1',
        role: 'user',
        content: 'nested hello',
        attachments: [],
        seq: 1,
      }),
      expect.objectContaining({
        message_id: 'msg_real2',
        role: 'assistant',
        content: 'nested answer',
        attachments: [{ path: 'out/result.md', media_type: 'text/markdown' }],
        seq: 2,
      }),
    ])
    expect(page.next_cursor).toBe('v1:global:2')
  })

  it('reads a Task conversation with the after cursor', async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ items: [], next_cursor: null }))
    vi.stubGlobal('fetch', fetchMock)

    await createChatApi().readMessages({ taskRef: 'task_ABC' }, 'v1:task_ABC:4')

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/tasks/task_ABC/messages?after=v1%3Atask_ABC%3A4',
      expect.anything(),
    )
  })

  it('generates a well-formed ULID idempotency key', () => {
    expect(newRuntimeId('msg')).toMatch(/^msg_[0-9A-Z]{26}$/)
    // Time-ordered prefix must not decrease between calls.
    const first = newRuntimeId('msg')
    const second = newRuntimeId('msg')
    expect(second.slice(4, 14) >= first.slice(4, 14)).toBe(true)
  })
})


it('preserves the persisted unavailable flag when normalizing nested assistant history', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ items: [{ message_id: 'assistant:unavailable', seq: 1, message: { role: 'assistant', content: 'Assistant unavailable.', attachments: [], data: { unavailable: true } } }], next_cursor: null })))
  const page = await createChatApi().readMessages({ taskRef: null })
  expect(page.items[0].data).toEqual({ unavailable: true })
})
