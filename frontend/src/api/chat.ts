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
import type { Attachment, SourceRef, SourceRefInput } from './types'

/* ------------------------------------------- selected-material (LG-044) contract
 *
 * Additive, optional, non-secret shapes frozen by LG-042 in
 * `docs/10-selected-material-prototype.md` §2/§4/§9. Copied verbatim from §9 so
 * the frontend request/response wire matches the backend owner (LG-043) exactly.
 */

/** One selected, already-ingested source ref request item (docs/10 §2). */
export interface SelectedSourceRef {
  source_id: string
  source_version?: number
  content_hash?: string
}

/** One program-resolved source binding returned by the backend (docs/10 §4). */
export interface ResolvedSourceBinding {
  source_id: string
  source_version: number
  content_hash: string
  layer: 'formal' | 'machine'
  locator: string
  char_count: number
  truncated: boolean
  truncation: null | {
    reason: string
    original_char_count: number
    kept_char_count: number
    max_total: number
  }
}

/** Additive result `data` fields for a reply (docs/10 §4/§9). */
export interface ResolvedSourceBindingsData {
  resolved_source_bindings?: ResolvedSourceBinding[]
  context_truncated?: boolean
  provided_context_note?: string
}

export interface ChatAuthor {
  kind: string
  username: string | null
  role: string | null
}

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
  /**
   * Additive server-author field (LG-050 §5).  Present on team-mode global
   * messages; absent on legacy/single-user rows, where the view shows
   * "Unknown" rather than inventing a speaker.
   */
  author?: ChatAuthor | null
  /** Additive resource-proposal outcome written back by the coordinator. */
  resource_result?: { status?: string } | null
  /**
   * Additive selected-material outcome (docs/10 §4). Persisted assistant
   * messages MAY carry the resolved bindings; absent on legacy responses, in
   * which case the view renders exactly as before.
   */
  data?: ResolvedSourceBindingsData | null
  /**
   * Additive 1.19.0 receipt/traceability refs (docs/08 §20.3). They are a
   * persisted snapshot, never model context and never an authorization grant.
   * Absent on legacy rows and on 1.18 backends.
   */
  source_refs?: SourceRef[]
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
  author?: ChatAuthor | null
  resource_result?: { status?: string } | null
  /** Additive selected-material fields (docs/10 §4); absent on legacy rows. */
  resolved_source_bindings?: ResolvedSourceBinding[] | null
  context_truncated?: boolean | null
  provided_context_note?: string | null
  data?: ResolvedSourceBindingsData | null
  /** Additive 1.19.0 persisted source refs (docs/08 §20.3). */
  source_refs?: SourceRef[] | null
}

/** Extract the additive selected-material fields from either envelope shape. */
function normalizeBindingsData(
  wire: ChatMessageWire,
  inner: Partial<ChatMessage>,
): ResolvedSourceBindingsData | null {
  const nestedData = (inner.data ?? wire.data) as ResolvedSourceBindingsData | null | undefined
  const nestedBindings = Array.isArray(nestedData?.resolved_source_bindings)
    ? nestedData?.resolved_source_bindings
    : null
  const flatBindings = Array.isArray(wire.resolved_source_bindings)
    ? wire.resolved_source_bindings
    : null
  const bindings = nestedBindings ?? flatBindings
  const contextTruncated =
    typeof nestedData?.context_truncated === 'boolean'
      ? nestedData.context_truncated
      : typeof wire.context_truncated === 'boolean'
        ? wire.context_truncated
        : undefined
  const note =
    typeof nestedData?.provided_context_note === 'string'
      ? nestedData.provided_context_note
      : typeof wire.provided_context_note === 'string'
        ? wire.provided_context_note
        : undefined
  if (!bindings && contextTruncated === undefined && note === undefined) return null
  return {
    ...(bindings ? { resolved_source_bindings: bindings } : {}),
    ...(contextTruncated !== undefined ? { context_truncated: contextTruncated } : {}),
    ...(note !== undefined ? { provided_context_note: note } : {}),
  }
}

function normalizeSourceRefs(value: unknown): SourceRef[] {
  if (!Array.isArray(value)) return []
  return value.flatMap((item) => {
    if (!item || typeof item !== 'object') return []
    const candidate = item as Record<string, unknown>
    const sourceId = candidate.source_id
    const sourceVersion = candidate.source_version
    const contentHash = candidate.content_hash
    if (typeof sourceId !== 'string' || !sourceId) return []
    if (typeof sourceVersion !== 'number' || !Number.isFinite(sourceVersion)) return []
    if (typeof contentHash !== 'string' || !contentHash) return []
    const rawScope = candidate.scope
    const scope = rawScope && typeof rawScope === 'object' ? rawScope as Record<string, unknown> : {}
    return [{
      source_id: sourceId,
      source_version: sourceVersion,
      content_hash: contentHash,
      scope: {
        task_ref: typeof scope.task_ref === 'string' ? scope.task_ref : null,
        project_ref: typeof scope.project_ref === 'string' ? scope.project_ref : null,
        inbox_ref: typeof scope.inbox_ref === 'string' ? scope.inbox_ref : null,
      },
    }]
  })
}

function normalizeMessage(wire: ChatMessageWire): ChatMessage {
  const inner = wire.message ?? {}
  const role = inner.role ?? wire.role ?? 'assistant'
  const content = inner.content ?? wire.content ?? ''
  const attachments = inner.attachments ?? wire.attachments ?? []
  const sourceRefs = normalizeSourceRefs(inner.source_refs ?? wire.source_refs)
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
    author: inner.author ?? wire.author ?? null,
    seq: wire.seq,
    resource_result: inner.resource_result ?? wire.resource_result ?? null,
    data: normalizeBindingsData(wire, inner),
    ...(sourceRefs.length > 0 ? { source_refs: sourceRefs } : {}),
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
  /**
   * LG-054: when true (team mode only), read/write the private per-user
   * `/conversations/personal/messages` endpoint instead of the shared global
   * one.  Ignored whenever ``taskRef`` is set (Task conversations are shared
   * Team).  Single-user mode leaves this false and keeps the legacy global
   * endpoint (single-mode Personal IS the legacy global conversation).
   */
  personal?: boolean
}

export interface ChatApi {
  readMessages(scope: ChatScope, cursor?: string | null, signal?: AbortSignal): Promise<ChatMessagePage>
  sendMessage(
    scope: ChatScope,
    body: {
      message_id: string
      content: string
      attachments?: Attachment[]
      request_id?: string
      /** Additive, optional selected-material refs (docs/10 §2). */
      selected_sources?: SelectedSourceRef[]
      /**
       * Additive 1.19.0 receipt-only refs (docs/08 §20.3). Callers must only
       * send this behind the material_intake_v2 capability gate.
       */
      source_refs?: SourceRefInput[]
    },
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

function conversationPath(scope: ChatScope): string {
  if (scope.taskRef) {
    return `/tasks/${encodeURIComponent(scope.taskRef)}/messages`
  }
  return scope.personal
    ? '/conversations/personal/messages'
    : '/conversations/global/messages'
}

export function createChatApi(): ChatApi {
  return {
    readMessages(scope, cursor, signal) {
      const path = withQuery(conversationPath(scope), { after: cursor })
      return apiRequest<{ items: ChatMessageWire[]; next_cursor: string | null }>(path, {
        signal,
      }).then((page) => ({
        items: (page.items ?? []).map(normalizeMessage),
        next_cursor: page.next_cursor ?? null,
      }))
    },

    sendMessage(scope, body, signal) {
      const path = conversationPath(scope)
      const payload: Record<string, unknown> = {
        message_id: body.message_id,
        content: body.content,
        attachments: body.attachments ?? [],
      }
      if (body.request_id) payload.request_id = body.request_id
      // Only send the key when there is a real selection: omitting it keeps
      // the legacy request byte-identical (docs/10 §2, §8).
      if (body.selected_sources && body.selected_sources.length > 0) {
        payload.selected_sources = body.selected_sources
      }
      // Receipt refs are additive and omitted entirely when empty, keeping the
      // legacy request unchanged (docs/08 §20.3).
      if (body.source_refs && body.source_refs.length > 0) {
        payload.source_refs = body.source_refs
      }
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
