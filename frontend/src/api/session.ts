/**
 * Session-expiry signal (LG-219).
 *
 * `apiRequest` is the single request boundary shared by Board, Tasks/Files,
 * Team, Settings, Chat and the resource views.  When it observes a `401` that
 * means the server session (team mode) or the runtime local token (single
 * user) is no longer valid, it emits one signal here.  The auth gate
 * (`AuthProvider`) is the only subscriber:
 *
 * * team mode  → return to the login gate with a "Session expired" notice;
 * * single mode → stay in the workspace and ask the user to refresh the page
 *   (the runtime token is re-injected by the page that serves the app).
 *
 * Keeping the signal separate from `client.ts` and `AuthProvider.tsx` keeps
 * this integration surface small and stable: shell/chat owners can also
 * subscribe without changing the request layer. No token, cookie or request
 * body is ever placed in the detail.
 */

export interface SessionExpiredDetail {
  /** HTTP status that triggered the signal (always `401` today). */
  httpStatus: 401
  /** Contract error code, e.g. `unauthorized`. */
  code: string
  /** Contract-relative path, e.g. `/tasks`; never a full URL. */
  path: string
  /** Safe error envelope details (for example `reason`), never secrets. */
  details: Record<string, unknown>
}

export type SessionExpiredListener = (detail: SessionExpiredDetail) => void

const listeners = new Set<SessionExpiredListener>()

/**
 * Subscribe to session-expiry signals. Returns an unsubscribe function.
 * Listeners are isolated: one throwing subscriber cannot suppress the others.
 */
export function onSessionExpired(listener: SessionExpiredListener): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

/** Emit a session-expiry signal to the current subscribers. */
export function emitSessionExpired(detail: SessionExpiredDetail): void {
  for (const listener of [...listeners]) {
    try {
      listener(detail)
    } catch {
      /* Never let a UI subscriber break the failed request path. */
    }
  }
}

/**
 * Decide whether a failed request is a session expiry.
 *
 * `/auth/*` failures are authentication attempts or discovery, not an expired
 * session: a wrong login password must stay a form error and `/auth/me` is
 * handled by the startup probe.  A wrong *current* password on
 * `/account/password` is a `401` by contract but does not invalidate the
 * session, so it is excluded too.  Every other `401` means the caller is no
 * longer authorized and the auth gate must take over.
 */
export function isSessionExpiry(
  path: string,
  httpStatus: number,
  details: Record<string, unknown> | undefined,
): boolean {
  if (httpStatus !== 401) return false
  const cleanPath = path.split('?')[0] ?? path
  if (cleanPath === '/auth' || cleanPath.startsWith('/auth/')) return false
  if (
    cleanPath === '/account/password' &&
    details?.reason === 'invalid_current_password'
  ) {
    return false
  }
  return true
}
