/**
 * Team authentication state (LG-050 §7).
 *
 * On startup the provider probes `GET /auth/me` and keeps an explicit tri-state
 * so the UI never assumes single-user to bypass the login experience:
 *
 * * `checking` — the probe is in flight; the gate renders Loading, never the
 *   workspace and never a login form it cannot yet justify;
 * * `error` — the probe failed for a reason that is *not* a legacy backend
 *   (network unreachable, 5xx, malformed body); the gate renders a retryable
 *   error instead of silently dropping into single-user mode;
 * * `ready` — the probe resolved.  `mode: "single"` (or a legacy 404 from a
 *   backend without `/auth/me`) ⇒ the existing single-user workspace;
 *   `mode: "team"`, unauthenticated ⇒ the login gate; authenticated ⇒ the
 *   workspace plus identity/logout.
 *
 * Only an explicit `mode: "single"` or a legacy `404` is treated as
 * single-user.  Identity is always the server-resolved session — a local
 * runtime token is explicitly cleared in team mode so it can never act as a
 * role/backdoor (interface §6).
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'

import { setRuntimeToken } from '../api/auth'
import { ApiError } from '../api/client'
import {
  fetchAuthMe,
  login as authLogin,
  logout as authLogout,
  type AuthMeResponse,
} from '../api/teamAuth'

export type AuthStatus = 'checking' | 'ready' | 'error'

export interface TeamIdentity {
  mode: 'team' | 'single'
  authenticated: boolean
  username: string | null
  role: string | null
}

export interface AuthFailure {
  message: string
  code: string | null
  retryable: boolean
}

const SINGLE_IDENTITY: TeamIdentity = {
  mode: 'single',
  authenticated: true,
  username: null,
  role: 'admin',
}

const TEAM_ANONYMOUS: TeamIdentity = {
  mode: 'team',
  authenticated: false,
  username: null,
  role: null,
}

export interface AuthContextValue {
  status: AuthStatus
  identity: TeamIdentity
  /** Non-null while `status === 'error'`. */
  error: AuthFailure | null
  isTeam: boolean
  isAdmin: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
  /** Re-run the `/auth/me` probe (used by the retryable error state). */
  refresh: () => Promise<void>
  /** Hand control back to the login gate (e.g. after a `401`). */
  requireLogin: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

/**
 * Map a `/auth/me` response to a concrete identity.
 *
 * Only the two contract modes are accepted; an unexpected mode is an error
 * rather than an implicit single-user fallback, so a broken server cannot
 * silently bypass the gate.
 */
function normalizeIdentity(me: AuthMeResponse): TeamIdentity {
  if (me.mode === 'single') return { ...SINGLE_IDENTITY }
  if (me.mode === 'team') {
    return {
      mode: 'team',
      authenticated: Boolean(me.authenticated),
      username: me.username ?? null,
      role: me.role ?? null,
    }
  }
  throw new Error(`unexpected auth mode: ${String(me.mode)}`)
}

function failureFrom(cause: unknown): AuthFailure {
  if (cause instanceof ApiError) {
    return {
      message: cause.message,
      code: cause.code,
      retryable: cause.retryable,
    }
  }
  return {
    message: cause instanceof Error ? cause.message : 'Authentication probe failed',
    code: null,
    retryable: true,
  }
}

export interface AuthProviderProps {
  children: ReactNode
  /** Injectable probe for tests; defaults to `GET /auth/me`. */
  probe?: (signal?: AbortSignal) => Promise<AuthMeResponse>
}

export function AuthProvider({ children, probe = fetchAuthMe }: AuthProviderProps) {
  const [status, setStatus] = useState<AuthStatus>('checking')
  // Placeholder identity; it is only observed by the shell once status is
  // 'ready', and by then it has been replaced by the real server state.
  const [identity, setIdentity] = useState<TeamIdentity>(SINGLE_IDENTITY)
  const [error, setError] = useState<AuthFailure | null>(null)
  const cancelled = useRef(false)

  const applyIdentity = useCallback((next: TeamIdentity) => {
    setIdentity(next)
    if (next.mode === 'team') {
      // Team roles come only from the HttpOnly session cookie; never a token.
      setRuntimeToken(null)
    }
  }, [])

  const refresh = useCallback(async () => {
    setStatus('checking')
    setError(null)
    try {
      const me = await probe()
      if (cancelled.current) return
      applyIdentity(normalizeIdentity(me))
      setStatus('ready')
    } catch (cause) {
      if (cancelled.current) return
      // A backend that predates `/auth/me` answers 404 (single-user product);
      // that is the only failure that may fall back to single-user mode.
      if (cause instanceof ApiError && cause.httpStatus === 404) {
        applyIdentity({ ...SINGLE_IDENTITY })
        setStatus('ready')
        return
      }
      // Network errors and server errors must be surfaced, not hidden behind a
      // single-user workspace that would let an anonymous team user in.
      setError(failureFrom(cause))
      setStatus('error')
    }
  }, [applyIdentity, probe])

  useEffect(() => {
    cancelled.current = false
    void refresh()
    return () => {
      cancelled.current = true
    }
  }, [refresh])

  const login = useCallback(
    async (username: string, password: string) => {
      const result = await authLogin(username, password)
      applyIdentity({
        mode: 'team',
        authenticated: true,
        username: result.username,
        role: result.role,
      })
      setError(null)
      setStatus('ready')
    },
    [applyIdentity],
  )

  const logout = useCallback(async () => {
    try {
      await authLogout()
    } catch {
      /* Even if the request fails, drop the local gate immediately and honestly. */
    }
    applyIdentity({ ...TEAM_ANONYMOUS })
    setStatus('ready')
  }, [applyIdentity])

  const requireLogin = useCallback(() => {
    setIdentity((previous) =>
      previous.mode === 'team' ? { ...TEAM_ANONYMOUS } : previous,
    )
    setStatus('ready')
  }, [])

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      identity,
      error,
      isTeam: identity.mode === 'team',
      isAdmin: identity.role === 'admin',
      login,
      logout,
      refresh,
      requireLogin,
    }),
    [status, identity, error, login, logout, refresh, requireLogin],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

/** Safe default for components rendered without a provider (unit tests). */
const DEFAULT_AUTH: AuthContextValue = {
  status: 'ready',
  identity: { ...SINGLE_IDENTITY },
  error: null,
  isTeam: false,
  isAdmin: true,
  login: async () => undefined,
  logout: async () => undefined,
  refresh: async () => undefined,
  requireLogin: () => undefined,
}

export function useAuth(): AuthContextValue {
  return useContext(AuthContext) ?? DEFAULT_AUTH
}
