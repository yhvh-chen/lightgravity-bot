/**
 * Team authentication state (LG-050 §7).
 *
 * On startup the provider probes `GET /auth/me` and keeps an explicit tri-state
 * so the UI never assumes single-user to bypass the login experience:
 *
 * * `checking` — the probe is in flight; the gate renders Loading, never the
 *   workspace and never a login form it cannot yet justify;
 * * `error` — discovery failed (network, 5xx, malformed body or a missing
 *   authentication endpoint); the gate renders a retryable
 *   error instead of silently dropping into single-user mode;
 * * `ready` — the probe resolved. `mode: "single"` opens the existing
 *   single-user workspace;
 *   `mode: "team"`, unauthenticated ⇒ the login gate; authenticated ⇒ the
 *   workspace plus identity/logout.
 *
 * Only an explicit `mode: "single"` is treated as single-user. Identity is
 * always the server-resolved session — a local
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
import { ApiError, fetchHealth } from '../api/client'
import {
  backendIncompatible,
  assertBackendCompatible,
  supportsAccounts,
  supportsPersonalChat,
} from '../api/backendCompatibility'
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
  personalChatAvailable: boolean
  /** LG-062: backend advertises the account-management surface (team only). */
  accountsAvailable: boolean
  /** Optional login-gate notice (e.g. after a password change signed you out). */
  notice: string | null
  login: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
  /** Re-run the `/auth/me` probe (used by the retryable error state). */
  refresh: () => Promise<void>
  /**
   * Hand control back to the login gate (e.g. after a `401`).  An optional
   * notice explains why (e.g. a successful own-password change logs you out).
   */
  requireLogin: (notice?: string) => void
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
  const [personalChatAvailable, setPersonalChatAvailable] = useState(false)
  const [accountsAvailable, setAccountsAvailable] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const cancelled = useRef(false)
  const refreshGeneration = useRef(0)

  const applyIdentity = useCallback((next: TeamIdentity) => {
    setIdentity(next)
    if (next.mode === 'team') {
      // Team roles come only from the HttpOnly session cookie; never a token.
      setRuntimeToken(null)
    }
  }, [])

  const refresh = useCallback(async () => {
    const requestGeneration = ++refreshGeneration.current
    setStatus('checking')
    setError(null)
    try {
      const me = await probe()
      // Private chat is optional on supported 1.13 shared backends. Discover it
      // before mounting the team shell, rather than advertising an endpoint
      // that does not exist. Single mode uses the legacy global/Task APIs.
      if (me.mode === 'team') {
        const health = await fetchHealth()
        assertBackendCompatible(health)
        if (cancelled.current || requestGeneration !== refreshGeneration.current) return
        setPersonalChatAvailable(supportsPersonalChat(health))
        setAccountsAvailable(supportsAccounts(health))
      } else {
        setPersonalChatAvailable(false)
        // Account management is team-only; single-user mode keeps Models.  An
        // old single-user backend must never advertise an account surface.
        setAccountsAvailable(false)
      }
      if (cancelled.current || requestGeneration !== refreshGeneration.current) return
      applyIdentity(normalizeIdentity(me))
      setStatus('ready')
    } catch (cause) {
      if (cancelled.current || requestGeneration !== refreshGeneration.current) return
      // Missing authentication discovery cannot establish single-user identity.
      // In particular, the old metadata-only skeleton must not open the shell.
      if (cause instanceof ApiError && cause.httpStatus === 404) {
        setError(failureFrom(backendIncompatible('authentication discovery /auth/me is missing')))
        setStatus('error')
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
      setNotice(null)
      setError(null)
      setStatus('ready')
    },
    [applyIdentity],
  )

  const logout = useCallback(async () => {
    refreshGeneration.current += 1
    try {
      await authLogout()
    } catch {
      /* Even if the request fails, drop the local gate immediately and honestly. */
    }
    applyIdentity({ ...TEAM_ANONYMOUS })
    setStatus('ready')
  }, [applyIdentity])

  const requireLogin = useCallback((message?: string) => {
    refreshGeneration.current += 1
    setNotice(message ?? null)
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
      personalChatAvailable,
      accountsAvailable,
      notice,
      login,
      logout,
      refresh,
      requireLogin,
    }),
    [
      status,
      identity,
      error,
      personalChatAvailable,
      accountsAvailable,
      notice,
      login,
      logout,
      refresh,
      requireLogin,
    ],
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
  personalChatAvailable: false,
  accountsAvailable: false,
  notice: null,
  login: async () => undefined,
  logout: async () => undefined,
  refresh: async () => undefined,
  requireLogin: () => undefined,
}

export function useAuth(): AuthContextValue {
  return useContext(AuthContext) ?? DEFAULT_AUTH
}
