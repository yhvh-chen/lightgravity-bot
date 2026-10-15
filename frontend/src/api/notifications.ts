/**
 * Notification API client (LG-019; docs/08 §4.3, docs/04 §8).
 *
 * Owns the frozen notification surface the shell needs:
 *
 * * `GET  /notifications`  — projected list + honest unread count
 * * `POST /notifications`  — mark one or more read (durable on the backend)
 *
 * Read state is persisted by the backend, so it survives a browser refresh and
 * is not re-derived from a session-only flag. Each item carries accurate
 * Task/Run/candidate/requirements/deliverable refs so a click returns the user
 * to the exact place instead of a generic list.
 */

import { apiRequest } from './client'

export type NotificationSeverity = 'info' | 'success' | 'warning' | 'error'

export interface NotificationRecord {
  notification_id: string
  kind: string
  title: string
  body: string
  at: string
  severity: NotificationSeverity
  task_ref: string
  run_ref: string | null
  event_id: string | null
  stream_id: string | null
  seq: number | null
  candidate_ref: string | null
  requirements_revision: number | null
  deliverable_revision: number | null
  reason: string | null
  read: boolean
  read_at: string | null
}

export interface NotificationListResponse {
  items: NotificationRecord[]
  next_cursor: string | null
  unread: number
}

export interface MarkReadResponse {
  marked_read: string[]
  unknown: string[]
  unread: number
}

export interface NotificationApi {
  list(options?: {
    unreadOnly?: boolean
    taskRef?: string | null
    limit?: number
    signal?: AbortSignal
  }): Promise<NotificationListResponse>
  markRead(notificationIds: string[], signal?: AbortSignal): Promise<MarkReadResponse>
}

export function createNotificationApi(): NotificationApi {
  return {
    async list(options = {}) {
      const params = new URLSearchParams()
      if (options.unreadOnly) params.set('unread_only', 'true')
      if (options.taskRef) params.set('task_ref', options.taskRef)
      if (options.limit) params.set('limit', String(options.limit))
      const query = params.toString()
      return apiRequest<NotificationListResponse>(
        `/notifications${query ? `?${query}` : ''}`,
        { signal: options.signal },
      )
    },
    async markRead(notificationIds, signal) {
      return apiRequest<MarkReadResponse>('/notifications', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({ notification_ids: notificationIds }),
        signal,
      })
    },
  }
}

export const notificationApi: NotificationApi = createNotificationApi()

/**
 * Deep-link target for a notification: the shell task/run scope plus the
 * candidate/version binding. Returning the exact refs (not just a Task) is what
 * makes an old reply unable to act on a newer version.
 */
export interface NotificationTarget {
  taskRef: string
  runRef: string | null
  candidateRef: string | null
  requirementsRevision: number | null
  deliverableRevision: number | null
}

export function notificationTarget(record: NotificationRecord): NotificationTarget {
  return {
    taskRef: record.task_ref,
    runRef: record.run_ref,
    candidateRef: record.candidate_ref,
    requirementsRevision: record.requirements_revision,
    deliverableRevision: record.deliverable_revision,
  }
}
