/**
 * SSE event subscription client (LG-013; docs/08 §4.4).
 *
 * `GET /api/v1/events/stream` is a *subscription*, never a control channel.
 * This wrapper only reads: on reconnect it passes the last opaque cursor via
 * `?cursor=` (also set as `Last-Event-ID` by the browser EventSource) so the
 * server replays gap-free. A browser disconnect never cancels backend work, so
 * the caller keeps rendering the last known state and does not fabricate a new
 * phase from the disconnect.
 */

import { API_PREFIX } from './types'
import type { TaskEventRecord } from './tasks'

export interface EventStreamHandlers {
  onEvent: (event: TaskEventRecord, cursor: string) => void
  onError?: (error: Event) => void
  onOpen?: () => void
}

export interface EventStreamHandle {
  close: () => void
  readonly cursor: string | null
}

export interface EventStreamOptions {
  /** Start cursor `v1:<stream_id>:<seq>`; omit to receive only new events. */
  cursor?: string | null
  handlers: EventStreamHandlers
}

/**
 * Open a live event subscription. Returns a handle whose `cursor` tracks the
 * last delivered frame so a caller-driven reconnect resumes without gaps.
 */
export function openEventStream({ cursor, handlers }: EventStreamOptions): EventStreamHandle {
  const state = { cursor: cursor ?? null }
  if (typeof EventSource === 'undefined') {
    // No EventSource (e.g. jsdom): report honestly instead of faking a stream.
    throw new Error('EventSource is not available in this environment')
  }
  const url = new URL(`${API_PREFIX}/events/stream`, window.location.origin)
  if (state.cursor) url.searchParams.set('cursor', state.cursor)
  const source = new EventSource(url.toString())

  source.onopen = () => handlers.onOpen?.()

  // Named event types arrive via `addEventListener`; a generic `message`
  // handler catches any untyped frame. Both parse the same JSON envelope.
  const deliver = (raw: MessageEvent) => {
    if (typeof raw.data !== 'string') return
    let parsed: TaskEventRecord
    try {
      parsed = JSON.parse(raw.data) as TaskEventRecord
    } catch {
      return
    }
    const frameCursor = raw.lastEventId || state.cursor
    if (frameCursor) state.cursor = frameCursor
    handlers.onEvent(parsed, state.cursor ?? '')
  }

  source.onmessage = deliver
  // The frozen event types are sent as the SSE `event:` name, so register the
  // known set explicitly; unknown types are still delivered via `message`.
  for (const type of KNOWN_EVENT_TYPES) {
    source.addEventListener(type, deliver as EventListener)
  }

  source.onerror = (error) => handlers.onError?.(error)

  return {
    close: () => source.close(),
    get cursor() {
      return state.cursor
    },
  }
}

/** Event types frozen in docs/08 §5.1; unknown types are ignored, not fatal. */
export const KNOWN_EVENT_TYPES: readonly string[] = [
  'task.created',
  'task.phase_changed',
  'task.status_changed',
  'task.requirements_changed',
  'queue.enqueued',
  'queue.claimed',
  'queue.released',
  'run.created',
  'run.state_changed',
  'subtask.state_changed',
  'member.recruited',
  'member.state_changed',
  'member.released',
  'message.appended',
  'decision.requested',
  'decision.resolved',
  'artifact.produced',
  'cleanup.updated',
  'notification.created',
  'error.recorded',
]
