/**
 * Durable event-cursor persistence (LG-019; docs/08 §4.4, design.md §6).
 *
 * The SSE reconnect cursor is a *transport* position, not business state, so it
 * lives in `localStorage` (survives a tab reload) under a versioned key. A
 * browser disconnect never cancels backend work; on reconnect we send the last
 * acknowledged `v1:<stream_id>:<seq>` so the server replays strictly after it
 * and nothing is duplicated or skipped.
 */

const CURSOR_KEY = 'lg019.event-cursor.v1'

function storage(): Storage | null {
  try {
    if (typeof window === 'undefined' || !window.localStorage) return null
    return window.localStorage
  } catch {
    return null
  }
}

export function loadCursor(): string | null {
  const store = storage()
  if (!store) return null
  try {
    const raw = store.getItem(CURSOR_KEY)
    return raw && raw.startsWith('v1:') ? raw : null
  } catch {
    return null
  }
}

export function saveCursor(cursor: string | null): void {
  const store = storage()
  if (!store) return
  try {
    if (cursor) store.setItem(CURSOR_KEY, cursor)
    else store.removeItem(CURSOR_KEY)
  } catch {
    /* Best effort; a missing cursor still replays from the server default. */
  }
}
