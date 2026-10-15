/**
 * Notification store hook (LG-019; docs/08 §4.3, docs/04 §8, design.md §6).
 *
 * Loads the backend-projected notifications (never fabricated), exposes the
 * honest unread count, persists read state through the backend so it is
 * independent of the projection and survives a refresh, and deduplicates by the
 * stable `notification_id` so a replay after an SSE reconnect cannot show a
 * notification twice.
 *
 * The backend is the source of truth for both the set and the read flags. This
 * hook keeps no second copy of Task/Run state.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { ApiError } from '../api/client'
import {
  notificationApi,
  notificationTarget,
  type NotificationApi,
  type NotificationRecord,
  type NotificationTarget,
} from '../api/notifications'

export interface NotificationStore {
  items: NotificationRecord[]
  unreadCount: number
  loading: boolean
  error: ApiError | null
  /** Whether the last read was backed by a real backend response. */
  connected: boolean
  markRead: (ids: string[]) => Promise<void>
  markAllRead: () => Promise<void>
  refresh: () => void
  /** Deep-link target for a notification (Task/Run/candidate/version). */
  target: (record: NotificationRecord) => NotificationTarget
}

export interface UseNotificationsOptions {
  /** Restrict to one Task scope when set (topbar keeps global scope visible). */
  taskRef?: string | null
  enabled?: boolean
  api?: NotificationApi
}

function toApiError(cause: unknown): ApiError {
  if (cause instanceof ApiError) return cause
  return new ApiError({
    message: cause instanceof Error ? cause.message : 'Failed to load notifications',
    code: 'internal_error',
    httpStatus: null,
    retryable: true,
  })
}

/** Merge two sets by `notification_id`, keeping a single copy of each. */
export function dedupeNotifications(
  current: readonly NotificationRecord[],
  incoming: readonly NotificationRecord[],
): NotificationRecord[] {
  const byId = new Map<string, NotificationRecord>()
  for (const item of current) byId.set(item.notification_id, item)
  for (const item of incoming) byId.set(item.notification_id, item)
  return Array.from(byId.values()).sort((a, b) => (a.at < b.at ? 1 : a.at > b.at ? -1 : 0))
}

export function useNotifications(options: UseNotificationsOptions = {}): NotificationStore {
  const { taskRef = null, enabled = true, api = notificationApi } = options
  const [items, setItems] = useState<NotificationRecord[]>([])
  const [unreadCount, setUnreadCount] = useState(0)
  const [loading, setLoading] = useState(enabled)
  const [error, setError] = useState<ApiError | null>(null)
  const [connected, setConnected] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)
  const mounted = useRef(true)

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])

  const load = useCallback(
    async (signal?: AbortSignal) => {
      if (!enabled) return
      setLoading(true)
      try {
        const response = await api.list({ taskRef, limit: 200, signal })
        if (signal?.aborted || !mounted.current) return
        setItems((current) => dedupeNotifications(current, response.items))
        setUnreadCount(response.unread)
        setError(null)
        setConnected(true)
      } catch (cause) {
        if (signal?.aborted || !mounted.current) return
        // A failed read must not fabricate an empty success state.
        setError(toApiError(cause))
        setConnected(false)
      } finally {
        if (!signal?.aborted && mounted.current) setLoading(false)
      }
    },
    [api, enabled, taskRef],
  )

  useEffect(() => {
    const controller = new AbortController()
    void load(controller.signal)
    return () => controller.abort()
  }, [load, reloadKey])

  const markRead = useCallback(
    async (ids: string[]) => {
      if (ids.length === 0) return
      // Optimistic only for *pending display*; the authoritative count comes
      // back from the backend response and the next list read.
      setItems((current) =>
        current.map((item) =>
          ids.includes(item.notification_id) ? { ...item, read: true } : item,
        ),
      )
      try {
        const response = await api.markRead(ids)
        if (!mounted.current) return
        setUnreadCount(response.unread)
        setConnected(true)
      } catch (cause) {
        if (!mounted.current) return
        setError(toApiError(cause))
        // Roll back the optimistic flag by re-reading the real state.
        void load()
      }
    },
    [api, load],
  )

  const markAllRead = useCallback(async () => {
    const unread = items.filter((item) => !item.read).map((item) => item.notification_id)
    await markRead(unread)
  }, [items, markRead])

  return useMemo<NotificationStore>(
    () => ({
      items,
      unreadCount,
      loading,
      error,
      connected,
      markRead,
      markAllRead,
      refresh: () => setReloadKey((key) => key + 1),
      target: notificationTarget,
    }),
    [items, unreadCount, loading, error, connected, markRead, markAllRead],
  )
}
