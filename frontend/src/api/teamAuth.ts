/**
 * Team authentication client (LG-050; `/tmp/lg-team-interface-20261016.md` §3/§7).
 *
 * Additive endpoints, effective only when the backend runs in team mode:
 *
 * * `GET  /auth/me`  — anonymous; reports `mode` and the server-resolved session
 *   identity.  The frontend uses it to decide whether to show the login gate,
 *   never guessing from a local token.
 * * `POST /auth/login`  — sets the HttpOnly `lg_session` cookie.
 * * `POST /auth/logout` — clears it.
 *
 * Identity comes only from the server session (cookie); this module never
 * reads/writes a username or role from request bodies and never treats
 * `X-LG-Token` as a team identity.  Requests go through `apiRequest`, which
 * sends `credentials: 'include'` so the same-origin cookie travels along.
 */

import { apiRequest } from './client'

export interface AuthMeResponse {
  mode: string
  authenticated: boolean
  username: string | null
  role: string | null
}

export interface LoginResponse {
  username: string
  role: string
}

/** Server-resolved auth state; `mode` distinguishes team from single-user. */
export function fetchAuthMe(signal?: AbortSignal): Promise<AuthMeResponse> {
  return apiRequest<AuthMeResponse>('/auth/me', { signal })
}

/** Exchange credentials for an HttpOnly session cookie. */
export function login(
  username: string,
  password: string,
  signal?: AbortSignal,
): Promise<LoginResponse> {
  return apiRequest<LoginResponse>('/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
    signal,
  })
}

/** Clear the server session.  Repeated logout is idempotent (204). */
export function logout(signal?: AbortSignal): Promise<void> {
  return apiRequest<void>('/auth/logout', { method: 'POST', signal })
}
