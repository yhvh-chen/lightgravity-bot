/**
 * Live event subscription hook (LG-019; docs/08 §4.4, docs/04 §8).
 *
 * Wraps {@link openEventStream} with the durable reconnect cursor and an honest
 * connection status. A disconnect only closes the *subscription* — it never
 * cancels resident backend work; on reconnect the persisted cursor replays
 * strictly after the last acknowledged frame so nothing is lost or duplicated.
 *
 * Consumers receive deduplicated events keyed by `(stream_id, seq)` and can
 * trigger a real re-read (e.g. notifications) instead of trusting in-memory
 * deltas.
 */

import { useEffect, useMemo, useRef, useState } from 'react'

import { openEventStream, type EventStreamHandle } from '../api/events'
import type { TaskEventRecord } from '../api/tasks'
import { loadCursor, saveCursor } from './cursorStore'

export type ConnectionStatus = 'connecting' | 'open' | 'closed' | 'unavailable'

export interface UseEventStreamOptions {
  enabled?: boolean
  onEvent?: (event: TaskEventRecord) => void
  /** Only refresh-subscribed event types are surfaced; others are ignored. */
  filterTypes?: readonly string[]
}

export interface EventStreamState {
  status: ConnectionStatus
  lastEvent: TaskEventRecord | null
  cursor: string | null
}

export function useEventStream(options: UseEventStreamOptions = {}): EventStreamState {
  const { enabled = true, onEvent, filterTypes } = options
  const [status, setStatus] = useState<ConnectionStatus>('connecting')
  const [lastEvent, setLastEvent] = useState<TaskEventRecord | null>(null)
  const [cursor, setCursor] = useState<string | null>(null)
  const seenRef = useRef<Set<string>>(new Set())
  const onEventRef = useRef(onEvent)
  onEventRef.current = onEvent
  const filterRef = useRef(filterTypes)
  filterRef.current = filterTypes

  useEffect(() => {
    if (!enabled) {
      setStatus('closed')
      return
    }
    if (typeof window === 'undefined' || typeof EventSource === 'undefined') {
      setStatus('unavailable')
      return
    }
    let handle: EventStreamHandle | null = null
    try {
      handle = openEventStream({
        cursor: loadCursor(),
        handlers: {
          onOpen: () => setStatus('open'),
          onError: () => setStatus('closed'),
          onEvent: (event, frameCursor) => {
            const key = `${event.stream_id}:${event.seq}`
            if (seenRef.current.has(key)) return
            seenRef.current.add(key)
            // Bound the dedupe set so a long-lived session cannot grow forever.
            if (seenRef.current.size > 5000) {
              seenRef.current = new Set([...seenRef.current].slice(-2500))
            }
            if (frameCursor) {
              saveCursor(frameCursor)
              setCursor(frameCursor)
            }
            const filter = filterRef.current
            if (filter && !filter.includes(event.type)) return
            setLastEvent(event)
            onEventRef.current?.(event)
          },
        },
      })
    } catch {
      setStatus('unavailable')
      return
    }
    return () => {
      handle?.close()
      setStatus('closed')
    }
  }, [enabled])

  return useMemo(() => ({ status, lastEvent, cursor }), [status, lastEvent, cursor])
}

/** Event types that should trigger a notification re-read. */
export const NOTIFICATION_REFRESH_TYPES: readonly string[] = [
  'notification.created',
  'task.phase_changed',
  'task.status_changed',
  'decision.requested',
  'decision.resolved',
  'error.recorded',
]
