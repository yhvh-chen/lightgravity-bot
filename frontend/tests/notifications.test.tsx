/**
 * Notification store + cursor persistence tests (LG-019; docs/08 §4.3/§4.4).
 *
 * Covers the behaviour the acceptance criteria name: deduplication by stable id,
 * durable read state driven by the backend, accurate Task/Run/version targeting,
 * and the reconnect cursor surviving a reload. These use an injected API double
 * (unit evidence); real HTTP/SSE is the separate smoke test.
 */

import { act, cleanup, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type {
  NotificationApi,
  NotificationListResponse,
  NotificationRecord,
} from '../src/api/notifications'
import { notificationTarget } from '../src/api/notifications'
import { loadCursor, saveCursor } from '../src/app/cursorStore'
import { dedupeNotifications, useNotifications } from '../src/app/useNotifications'

afterEach(cleanup)

beforeEach(() => {
  window.localStorage.clear()
})

function record(overrides: Partial<NotificationRecord> = {}): NotificationRecord {
  return {
    notification_id: 'notif_A',
    kind: 'task.failed',
    title: 'Task failed',
    body: 'boom',
    at: '2026-10-16T00:00:00Z',
    severity: 'error',
    task_ref: 'task_1',
    run_ref: 'run_1',
    event_id: 'evt_1',
    stream_id: 'task_1',
    seq: 3,
    candidate_ref: null,
    requirements_revision: 2,
    deliverable_revision: 1,
    reason: 'boom',
    read: false,
    read_at: null,
    ...overrides,
  }
}

function makeApi(pages: NotificationListResponse[]): NotificationApi & {
  markCalls: string[][]
} {
  const markCalls: string[][] = []
  let index = 0
  return {
    markCalls,
    list: vi.fn(async () => {
      const page = pages[Math.min(index, pages.length - 1)]
      index += 1
      return page
    }),
    markRead: vi.fn(async (ids: string[]) => {
      markCalls.push(ids)
      return { marked_read: ids, unknown: [], unread: 0 }
    }),
  }
}

describe('dedupeNotifications', () => {
  it('keeps one copy per notification_id, newest first', () => {
    const older = record({ notification_id: 'a', at: '2026-10-15T00:00:00Z' })
    const newer = record({ notification_id: 'b', at: '2026-10-16T00:00:00Z' })
    const merged = dedupeNotifications([older], [newer, older])
    expect(merged.map((item) => item.notification_id)).toEqual(['b', 'a'])
  })
})

describe('useNotifications', () => {
  it('loads the backend list and exposes the honest unread count', async () => {
    const api = makeApi([
      { items: [record()], next_cursor: null, unread: 1 },
    ])
    const { result } = renderHook(() => useNotifications({ api }))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.items).toHaveLength(1)
    expect(result.current.unreadCount).toBe(1)
    expect(result.current.connected).toBe(true)
    expect(result.current.error).toBeNull()
  })

  it('marks read through the backend and updates the count', async () => {
    const api = makeApi([
      { items: [record()], next_cursor: null, unread: 1 },
      { items: [record({ read: true })], next_cursor: null, unread: 0 },
    ])
    const { result } = renderHook(() => useNotifications({ api }))
    await waitFor(() => expect(result.current.loading).toBe(false))
    await act(async () => {
      await result.current.markRead(['notif_A'])
    })
    expect(api.markCalls).toEqual([['notif_A']])
    expect(result.current.unreadCount).toBe(0)
    expect(result.current.items[0].read).toBe(true)
  })

  it('reports an error instead of fabricating an empty success', async () => {
    const api: NotificationApi = {
      list: vi.fn(async () => {
        throw new Error('network down')
      }),
      markRead: vi.fn(async () => ({ marked_read: [], unknown: [], unread: 0 })),
    }
    const { result } = renderHook(() => useNotifications({ api }))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.connected).toBe(false)
    expect(result.current.error?.message).toBe('network down')
  })
})

describe('notificationTarget', () => {
  it('returns the exact Task/Run/candidate/version binding', () => {
    const target = notificationTarget(
      record({
        notification_id: 'notif_X',
        task_ref: 'task_9',
        run_ref: 'run_9',
        candidate_ref: 'run_9',
        requirements_revision: 4,
        deliverable_revision: 3,
      }),
    )
    expect(target).toEqual({
      taskRef: 'task_9',
      runRef: 'run_9',
      candidateRef: 'run_9',
      requirementsRevision: 4,
      deliverableRevision: 3,
    })
  })
})

describe('cursorStore', () => {
  it('persists and restores the SSE reconnect cursor across a reload', () => {
    expect(loadCursor()).toBeNull()
    saveCursor('v1:task_1:7')
    expect(loadCursor()).toBe('v1:task_1:7')
    saveCursor(null)
    expect(loadCursor()).toBeNull()
  })
})
