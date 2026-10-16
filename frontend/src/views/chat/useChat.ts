/**
 * Chat scope hook (LG-013; team polling LG-050).
 *
 * Loads one real conversation (global or a Task) from the backend and sends
 * user messages through the frozen endpoints. It never fabricates a message:
 * on failure the local draft is kept and the real error is surfaced.
 *
 * Idempotency: the `message_id` is generated once per submit attempt and reused
 * on retry, so a double send cannot create duplicate messages/runs. When a
 * send first creates a Task (global delivery), the returned `task_id` is
 * reported so the caller can switch scope.
 *
 * Team mode (LG-050 §7): the *global* conversation is polled on a light timer
 * with the `after` cursor, deduplicated by `message_id`, and paused while the
 * page is hidden.  Polling never touches the draft; it only appends genuinely
 * new messages.  A `401` on a poll reports an expired session to the gate.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { ApiError } from '../../api/client'
import {
  chatApi,
  newRuntimeId,
  type ChatApi,
  type ChatMessage,
  type ChatScope,
  type ChatSubmitResult,
  type ResolvedSourceBindingsData,
  type SelectedSourceRef,
} from '../../api/chat'
import type { Attachment } from '../../api/types'

export interface ChatSendOutcome {
  /** Newly created Task id, when the message started one. */
  createdTaskRef: string | null
  reply: string | null
  /** Additive selected-material outcome for this reply (docs/10 §4). */
  resolvedSources: ResolvedSourceBindingsData | null
  /**
   * Server response `kind`.  Team-mode plain messages are `recorded` — the
   * server only persists them and does not start a bot reply.
   */
  kind: string | null
}

export interface UseChatOptions {
  /**
   * Poll interval for the global conversation in team mode.  Omitted (the
   * single-user default) means no polling and byte-identical behavior.
   */
  pollIntervalMs?: number
  /** Called when a poll/send observes an expired session (`401`). */
  onUnauthorized?: () => void
}

/** Read the additive selected-material fields off a submit result `data`. */
export function resolvedSourcesFromResult(
  result: ChatSubmitResult,
): ResolvedSourceBindingsData | null {
  const data = result.data as ResolvedSourceBindingsData | undefined
  if (!data) return null
  const bindings = Array.isArray(data.resolved_source_bindings)
    ? data.resolved_source_bindings
    : undefined
  const hasContextFlag = typeof data.context_truncated === 'boolean'
  const hasNote = typeof data.provided_context_note === 'string'
  if (!bindings && !hasContextFlag && !hasNote) return null
  return {
    ...(bindings ? { resolved_source_bindings: bindings } : {}),
    ...(hasContextFlag ? { context_truncated: data.context_truncated } : {}),
    ...(hasNote ? { provided_context_note: data.provided_context_note } : {}),
  }
}

export interface UseChatResult {
  messages: ChatMessage[]
  loading: boolean
  error: ApiError | null
  sending: boolean
  sendError: ApiError | null
  refresh: () => void
  send: (
    content: string,
    attachments?: Attachment[],
    selectedSources?: SelectedSourceRef[],
  ) => Promise<ChatSendOutcome>
  clearSendError: () => void
}

function asApiError(cause: unknown): ApiError {
  if (cause instanceof ApiError) return cause
  return new ApiError({
    message: cause instanceof Error ? cause.message : 'Request failed',
    code: 'network_error',
    httpStatus: null,
    retryable: true,
  })
}

/** Merge new page items into the existing list, deduplicating by message id. */
export function mergeMessages(
  current: ChatMessage[],
  incoming: ChatMessage[],
): ChatMessage[] {
  if (incoming.length === 0) return current
  const seen = new Set(current.map((message) => message.message_id))
  const additions = incoming.filter((message) => !seen.has(message.message_id))
  return additions.length > 0 ? [...current, ...additions] : current
}

export function useChat(
  scope: ChatScope,
  api: ChatApi = chatApi,
  options: UseChatOptions = {},
): UseChatResult {
  const { pollIntervalMs, onUnauthorized } = options
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<ApiError | null>(null)
  const [sending, setSending] = useState(false)
  const [sendError, setSendError] = useState<ApiError | null>(null)
  const [reloadKey, setReloadKey] = useState(0)
  const taskRef = scope.taskRef
  const pendingId = useRef<string | null>(null)
  const cursorRef = useRef<string | null>(null)
  const unauthorizedRef = useRef(onUnauthorized)
  unauthorizedRef.current = onUnauthorized

  useEffect(() => {
    const controller = new AbortController()
    let cancelled = false
    setLoading(true)
    setError(null)
    cursorRef.current = null
    api
      .readMessages({ taskRef }, null, controller.signal)
      .then((page) => {
        if (cancelled) return
        setMessages(page.items)
        cursorRef.current = page.next_cursor ?? null
        setLoading(false)
      })
      .catch((cause) => {
        if (cancelled || controller.signal.aborted) return
        const apiError = asApiError(cause)
        if (apiError.httpStatus === 401) unauthorizedRef.current?.()
        setMessages([])
        setError(apiError)
        setLoading(false)
      })
    return () => {
      cancelled = true
      controller.abort()
    }
  }, [api, taskRef, reloadKey])

  // Team-mode incremental polling of the global conversation (LG-050 §7).
  useEffect(() => {
    if (!pollIntervalMs || pollIntervalMs <= 0 || taskRef !== null) return
    let stopped = false
    let inFlight = false

    const poll = async () => {
      if (stopped || inFlight) return
      if (typeof document !== 'undefined' && document.hidden) return
      inFlight = true
      try {
        const page = await api.readMessages({ taskRef: null }, cursorRef.current)
        if (stopped) return
        cursorRef.current = page.next_cursor ?? cursorRef.current
        setMessages((current) => mergeMessages(current, page.items))
      } catch (cause) {
        if (stopped) return
        const apiError = asApiError(cause)
        if (apiError.httpStatus === 401) {
          // Session expired/revoked: hand back to the login gate.  Keep the
          // already-loaded history and the draft untouched.
          unauthorizedRef.current?.()
        }
      } finally {
        inFlight = false
      }
    }

    const timer = setInterval(() => void poll(), pollIntervalMs)
    return () => {
      stopped = true
      clearInterval(timer)
    }
  }, [api, pollIntervalMs, taskRef])

  const send = useCallback(
    async (
      content: string,
      attachments: Attachment[] = [],
      selectedSources?: SelectedSourceRef[],
    ): Promise<ChatSendOutcome> => {
      const trimmed = content.trim()
      if (!trimmed) {
        return { createdTaskRef: null, reply: null, resolvedSources: null, kind: null }
      }
      const messageId = pendingId.current ?? newRuntimeId('msg')
      pendingId.current = messageId
      setSending(true)
      setSendError(null)
      try {
        const result = await api.sendMessage(
          { taskRef },
          {
            message_id: messageId,
            content: trimmed,
            attachments,
            ...(selectedSources && selectedSources.length > 0
              ? { selected_sources: selectedSources }
              : {}),
          },
        )
        pendingId.current = null
        const createdTaskRef =
          typeof result.task_id === 'string' && result.task_id
            ? result.task_id
            : typeof result.data?.task_id === 'string'
              ? (result.data.task_id as string)
              : null
        setReloadKey((key) => key + 1)
        return {
          createdTaskRef,
          reply: result.reply ?? null,
          resolvedSources: resolvedSourcesFromResult(result),
          kind: result.kind ?? null,
        }
      } catch (cause) {
        const apiError = asApiError(cause)
        if (apiError.httpStatus === 401) unauthorizedRef.current?.()
        // Keep the same id so an explicit retry is idempotent server-side.
        setSendError(apiError)
        throw cause
      } finally {
        setSending(false)
      }
    },
    [api, taskRef],
  )

  return useMemo(
    () => ({
      messages,
      loading,
      error,
      sending,
      sendError,
      refresh: () => setReloadKey((key) => key + 1),
      send,
      clearSendError: () => setSendError(null),
    }),
    [messages, loading, error, sending, sendError, send],
  )
}
