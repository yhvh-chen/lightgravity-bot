/**
 * Team authentication state (LG-050 §7).
 *
 * On startup the provider probes `GET /auth/me`:
 *
 * * `mode: "single"` (or an older backend that does not implement the endpoint)
 *   ⇒ the existing single-user workspace, byte-for-byte unchanged;
 * * `mode: "team"`, unauthenticated ⇒ the login gate;
 * * `mode: "team"`, authenticated ⇒ the workspace plus identity/logout.
 *
 * The initial state is the optimistic single-user workspace so the shell mounts
 * exactly as before while the probe is in flight; if the server reports a team
 * session that is not authenticated, the gate replaces it.  Identity is always
 * the server-resolved session — a local runtime token is explicitly cleared in
 * team mode so it can never act as a role/backdoor (interface §6).
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
import {
  fetchAuthMe,
  login as authLogin,
  logout as authLogout,
  type AuthMeResponse,
} from '../api/teamAuth'

export interface TeamIdentity {
  mode: 'team' | 'single'
  authenticated: boolean
  username: string | null
  role: string | null
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
  status: 'checking' | 'ready'
  identity: TeamIdentity
  isTeam: boolean
  isAdmin: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
  refresh: () => Promise<void>
  /** Hand control back to the login gate (e.g. after a `401`). */
  requireLogin: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

function normalizeIdentity(me: AuthMeResponse): TeamIdentity {
  if (me.mode !== 'team') return { ...SINGLE_IDENTITY }
  return {
    mode: 'team',
    authenticated: Boolean(me.authenticated),
    username: me.username ?? null,
    role: me.role ?? null,
  }
}

export interface AuthProviderProps {
  children: ReactNode
  /** Injectable probe for tests; defaults to `GET /auth/me`. */
  probe?: (signal?: AbortSignal) => Promise<AuthMeResponse>
}

export function AuthProvider({ children, probe = fetchAuthMe }: AuthProviderProps) {
  const [status, setStatus] = useState<'checking' | 'ready'>('checking')
  // Optimistic single-user default keeps the pre-LG-050 shell intact until the
  // real server state is known (and for single-user backends, forever).
  const [identity, setIdentity] = useState<TeamIdentity>(SINGLE_IDENTITY)
  const cancelled = useRef(false)

  const applyIdentity = useCallback((next: TeamIdentity) => {
    setIdentity(next)
    if (next.mode === 'team') {
      // Team roles come only from the HttpOnly session cookie; never a token.
      setRuntimeToken(null)
    }
  }, [])

  const refresh = useCallback(async () => {
    try {
      const me = await probe()
      if (!cancelled.current) applyIdentity(normalizeIdentity(me))
    } catch {
      // Older/single-user backends return 404 and an unreachable server errors
      // out; both must keep the existing single-user behavior rather than
      // forcing a login gate that cannot work.
      if (!cancelled.current) applyIdentity({ ...SINGLE_IDENTITY })
    } finally {
      if (!cancelled.current) setStatus('ready')
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
  }, [applyIdentity])

  const requireLogin = useCallback(() => {
    setIdentity((previous) =>
      previous.mode === 'team' ? { ...TEAM_ANONYMOUS } : previous,
    )
  }, [])

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      identity,
      isTeam: identity.mode === 'team',
      isAdmin: identity.role === 'admin',
      login,
      logout,
      refresh,
      requireLogin,
    }),
    [status, identity, login, logout, refresh, requireLogin],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

/** Safe default for components rendered without a provider (unit tests). */
const DEFAULT_AUTH: AuthContextValue = {
  status: 'ready',
  identity: { ...SINGLE_IDENTITY },
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
