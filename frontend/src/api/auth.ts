/**
 * Runtime local access token helper (LG-026; docs/08 §4.1).
 *
 * Sensitive settings writes (`POST`/`PUT`/`PATCH`/`DELETE` under
 * `/api/v1/settings`) are default-denied by the backend until a local access
 * token is injected. The token is a *runtime* value:
 *
 * - it is never persisted: not in `localStorage`, `sessionStorage`,
 *   IndexedDB, cookies, the URL, chat, drafts or Markdown;
 * - it lives only in this module's memory, sourced either from an explicit
 *   `setRuntimeToken(...)` call made during startup (owned by LG-020) or from
 *   a non-persistent `window.__LG_RUNTIME_TOKEN__` global injected into a
 *   trusted local page by whatever serves it;
 * - when it is absent, `getRuntimeToken()` returns `null` and callers must let
 *   the real request fail with `unauthorized`. This module never fabricates a
 *   token or a successful write.
 *
 * LG-014 may import `getRuntimeToken` / `runtimeTokenHeaders` for its own
 * requests; the first-startup handshake itself remains LG-020's.
 */

declare global {
  interface Window {
    /** Non-persistent bootstrap global; set by a trusted local page, never stored. */
    __LG_RUNTIME_TOKEN__?: string
  }
}

/** Explicit override set by startup/tests; `null` means "no token, ignore global". */
let explicitToken: { value: string | null } | null = null

function readBootstrapToken(): string | null {
  if (typeof window === 'undefined') return null
  const value = window.__LG_RUNTIME_TOKEN__
  return typeof value === 'string' && value.length > 0 ? value : null
}

/** Inject the runtime token in memory (startup integration / tests). */
export function setRuntimeToken(token: string | null): void {
  explicitToken = { value: token && token.length > 0 ? token : null }
}

/** Forget any token (explicit or bootstrap) for the current page lifetime. */
export function clearRuntimeToken(): void {
  explicitToken = { value: null }
}

/** The optional runtime token; `null` when none is configured. */
export function getRuntimeToken(): string | null {
  if (explicitToken) return explicitToken.value
  return readBootstrapToken()
}

export function hasRuntimeToken(): boolean {
  return getRuntimeToken() !== null
}

/**
 * Build request headers including `X-LG-Token` when a token is available.
 * Never logs or stores the token.
 */
export function runtimeTokenHeaders(
  token: string | null = getRuntimeToken(),
  extra?: Record<string, string>,
): Record<string, string> {
  const headers: Record<string, string> = { ...(extra ?? {}) }
  if (token) headers['X-LG-Token'] = token
  return headers
}
