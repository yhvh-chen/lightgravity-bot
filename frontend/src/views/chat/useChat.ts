/**
 * Chat scope hook (LG-013).
 *
 * Loads one real conversation (global or a Task) from the backend and sends
 * user messages through the frozen endpoints. It never fabricates a message:
 * on failure the local draft is kept and the real error is surfaced.
 *
 * Idempotency: the `message_id` is generated once per submit attempt and reused
 * on retry, so a double send cannot create duplicate messages/runs. When a
 * send first creates a Task (global delivery), the returned `task_id` is
 * reported so the caller can switch scope.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { ApiError } from '../../api/client'
import { chatApi, newRuntimeId, type ChatApi, type ChatMessage, type ChatScope } from '../../api/chat'
import type { Attachment } from '../../api/types'

export interface ChatSendOutcome {
  /** Newly created Task id, when the message started one. */
  createdTaskRef: string | null
  reply: string | null
}

export interface UseChatResult {
  messages: ChatMessage[]
  loading: boolean
  error: ApiError | null
  sending: boolean
  sendError: ApiError | null
  refresh: () => void
  send: (content: string, attachments?: Attachment[]) => Promise<ChatSendOutcome>
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

export function useChat(scope: ChatScope, api: ChatApi = chatApi): UseChatResult {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<ApiError | null>(null)
  const [sending, setSending] = useState(false)
  const [sendError, setSendError] = useState<ApiError | null>(null)
  const [reloadKey, setReloadKey] = useState(0)
  const taskRef = scope.taskRef
  const pendingId = useRef<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    let cancelled = false
    setLoading(true)
    setError(null)
    api
      .readMessages({ taskRef }, null, controller.signal)
      .then((page) => {
        if (cancelled) return
        setMessages(page.items)
        setLoading(false)
      })
      .catch((cause) => {
        if (cancelled || controller.signal.aborted) return
        setMessages([])
        setError(asApiError(cause))
        setLoading(false)
      })
    return () => {
      cancelled = true
      controller.abort()
    }
  }, [api, taskRef, reloadKey])

  const send = useCallback(
    async (content: string, attachments: Attachment[] = []): Promise<ChatSendOutcome> => {
      const trimmed = content.trim()
      if (!trimmed) return { createdTaskRef: null, reply: null }
      const messageId = pendingId.current ?? newRuntimeId('msg')
      pendingId.current = messageId
      setSending(true)
      setSendError(null)
      try {
        const result = await api.sendMessage(
          { taskRef },
          { message_id: messageId, content: trimmed, attachments },
        )
        pendingId.current = null
        const createdTaskRef =
          typeof result.task_id === 'string' && result.task_id
            ? result.task_id
            : typeof result.data?.task_id === 'string'
              ? (result.data.task_id as string)
              : null
        setReloadKey((key) => key + 1)
        return { createdTaskRef, reply: result.reply ?? null }
      } catch (cause) {
        // Keep the same id so an explicit retry is idempotent server-side.
        setSendError(asApiError(cause))
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
