/**
 * Chat API client (LG-013; docs/08 §4.3/§5.2).
 *
 * Owns the two conversation surfaces the Chat view reads from the backend:
 *
 * * the singleton global conversation — `GET/POST /conversations/global/messages`
 *   (idempotent on `message_id`; `request_id` is the second idempotency key for
 *   control side effects);
 * * one Task conversation — `GET/POST /tasks/{task_id}/messages`
 *   (idempotent on `message_id`).
 *
 * Attachments are carried as `{ path, media_type }` references — the browser
 * never uploads bytes here and never invents an attachment the backend did not
 * record. The client generates well-formed ULID-style ids locally so retries
 * reuse the same `message_id` and cannot create duplicate messages/runs.
 */

import { apiRequest } from './client'
import type { Attachment } from './types'

export interface ChatMessage {
  message_id: string
  role: string
  content: string
  at?: string | null
  attachments: Attachment[]
  correlation_id?: string | null
  in_reply_to?: string | null
  task_ref?: string | null
  conversation_ref?: string | null
  seq?: number
  /** Additive resource-proposal outcome written back by the coordinator. */
  resource_result?: { status?: string } | null
}

export interface ChatMessagePage {
  items: ChatMessage[]
  next_cursor: string | null
}

/**
 * Wire item returned by the frozen endpoints (docs/08 §5.2).
 *
 * The backend serialises a persisted message as
 * `{ message_id, seq, message: { role, content, attachments, ... } }` — the
 * envelope carries the cursor while the message body is nested. Older/flat
 * fixtures put the fields at the top level. `normalizeMessage` accepts both so
 * the view always renders the real stored message and never a blank bubble.
 */
export interface ChatMessageWire {
  message_id: string
  seq?: number
  message?: Partial<ChatMessage> | null
  role?: string
  content?: string
  attachments?: Attachment[] | null
  at?: string | null
  correlation_id?: string | null
  in_reply_to?: string | null
  task_ref?: string | null
  conversation_ref?: string | null
  resource_result?: { status?: string } | null
}

function normalizeMessage(wire: ChatMessageWire): ChatMessage {
  const inner = wire.message ?? {}
  const role = inner.role ?? wire.role ?? 'assistant'
  const content = inner.content ?? wire.content ?? ''
  const attachments = inner.attachments ?? wire.attachments ?? []
  return {
    message_id: wire.message_id,
    role,
    content,
    attachments: Array.isArray(attachments) ? attachments : [],
    at: inner.at ?? wire.at ?? null,
    correlation_id: inner.correlation_id ?? wire.correlation_id ?? null,
    in_reply_to: inner.in_reply_to ?? wire.in_reply_to ?? null,
    task_ref: inner.task_ref ?? wire.task_ref ?? null,
    conversation_ref: inner.conversation_ref ?? wire.conversation_ref ?? null,
    seq: wire.seq,
    resource_result: inner.resource_result ?? wire.resource_result ?? null,
  }
}

export interface ChatSubmitResult {
  kind: string
  reply?: string | null
  task_id?: string | null
  conversation_id?: string | null
  queue_state?: string | null
  candidates?: string[]
  data?: Record<string, unknown>
}

export interface ChatScope {
  /** `null` reads the singleton global conversation. */
  taskRef: string | null
}

export interface ChatApi {
  readMessages(scope: ChatScope, cursor?: string | null, signal?: AbortSignal): Promise<ChatMessagePage>
  sendMessage(
    scope: ChatScope,
    body: { message_id: string; content: string; attachments?: Attachment[]; request_id?: string },
    signal?: AbortSignal,
  ): Promise<ChatSubmitResult>
  createTask(
    body: {
      request_id: string
      title: string
      objective: string
      scope?: string | null
      acceptance_criteria?: string[]
      workspace_ref?: string | null
    },
    signal?: AbortSignal,
  ): Promise<ChatSubmitResult & { task_id?: string | null; id?: string | null }>
}

const CROCKFORD = '0123456789ABCDEFGHJKMNPQRSTVWXYZ'

/** Generate a time-ordered `<kind>_<ULID>` id for local idempotency keys. */
export function newRuntimeId(kind: string): string {
  let time = Date.now()
  const timeChars: string[] = []
  for (let index = 0; index < 10; index += 1) {
    timeChars.unshift(CROCKFORD[time % 32])
    time = Math.floor(time / 32)
  }
  let random = ''
  const cryptoObj = typeof globalThis !== 'undefined' ? globalThis.crypto : undefined
  if (cryptoObj?.getRandomValues) {
    const bytes = new Uint8Array(16)
    cryptoObj.getRandomValues(bytes)
    for (const byte of bytes) random += CROCKFORD[byte % 32]
  } else {
    for (let index = 0; index < 16; index += 1) {
      random += CROCKFORD[Math.floor(Math.random() * 32)]
    }
  }
  return `${kind}_${timeChars.join('')}${random}`
}

function withQuery(path: string, params: Record<string, string | null | undefined>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined && value !== '') search.set(key, value)
  }
  const query = search.toString()
  return query ? `${path}?${query}` : path
}

export function createChatApi(): ChatApi {
  return {
    readMessages(scope, cursor, signal) {
      const path = scope.taskRef
        ? withQuery(`/tasks/${encodeURIComponent(scope.taskRef)}/messages`, { after: cursor })
        : withQuery('/conversations/global/messages', { after: cursor })
      return apiRequest<{ items: ChatMessageWire[]; next_cursor: string | null }>(path, {
        signal,
      }).then((page) => ({
        items: (page.items ?? []).map(normalizeMessage),
        next_cursor: page.next_cursor ?? null,
      }))
    },

    sendMessage(scope, body, signal) {
      const path = scope.taskRef
        ? `/tasks/${encodeURIComponent(scope.taskRef)}/messages`
        : '/conversations/global/messages'
      const payload: Record<string, unknown> = {
        message_id: body.message_id,
        content: body.content,
        attachments: body.attachments ?? [],
      }
      if (body.request_id) payload.request_id = body.request_id
      return apiRequest<ChatSubmitResult>(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal,
      })
    },

    createTask(body, signal) {
      return apiRequest<ChatSubmitResult & { id?: string | null }>('/tasks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal,
      })
    },
  }
}

export const chatApi: ChatApi = createChatApi()
