import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  type Dispatch,
  type ReactNode,
} from 'react'

import { useAuth } from './AuthProvider'

import {
  createInitialState,
  routeFromUrl,
  routeQuery,
  savePrefs,
  shellReducer,
  type ShellAction,
  type ShellState,
} from './uiState'

interface ShellContextValue {
  state: ShellState
  dispatch: Dispatch<ShellAction>
}

const ShellContext = createContext<ShellContextValue | null>(null)

/**
 * Shell state provider (LG-011). Owns the reducer, URL route sync and session
 * preference persistence. UI-only state — no business data.
 */
export function ShellProvider({ children }: { children: ReactNode }) {
  const { identity, isTeam, status } = useAuth()
  if (status !== 'ready' || (isTeam && !identity.authenticated)) return null
  const owner = isTeam ? identity.username ?? 'anonymous' : undefined
  // Identity changes discard mounted conversation state; legacy unowned prefs
  // are never imported as somebody's private drafts.
  return <ShellSessionProvider key={owner ? `team:${owner}` : 'single'} owner={owner} isTeam={isTeam}>{children}</ShellSessionProvider>
}

function ShellSessionProvider({ children, owner, isTeam }: { children: ReactNode; owner?: string; isTeam: boolean }) {
  const [state, reduce] = useReducer(shellReducer, owner, createInitialState)
  const dispatch = useCallback((action: ShellAction) => {
    if (action.type === 'openTaskConversation' || action.type === 'selectTask') {
      reduce({ ...action, channel: isTeam ? 'team' : 'personal' })
    } else if (action.type === 'setChatChannel' && !isTeam) {
      reduce({ ...action, channel: 'personal' })
    } else {
      reduce(action)
    }
  }, [isTeam])
  useEffect(() => {
    if (!isTeam && state.chatChannel === 'team') reduce({ type: 'setChatChannel', channel: 'personal' })
  }, [isTeam, state.chatChannel])
  const prevQuery = useRef<string | null>(null)

  // Mirror the route-bearing state into the URL for deep-link refresh.
  useEffect(() => {
    if (typeof window === 'undefined') return
    const query = routeQuery({
      view: state.view,
      taskRef: state.taskRef,
      runRef: state.runRef,
      selectedItemRef: state.selectedItemRef,
      chatChannel: state.chatChannel,
    })
    if (window.location.search === query) {
      prevQuery.current = query
      return
    }
    const currentView = routeFromUrl(window.location.search).view
    if (prevQuery.current !== null && state.view !== currentView) {
      window.history.pushState(null, '', query)
    } else {
      window.history.replaceState(null, '', query)
    }
    prevQuery.current = query
  }, [state.view, state.taskRef, state.runRef, state.selectedItemRef, state.chatChannel])

  // Back/forward restores the route without recreating any panel state.
  useEffect(() => {
    if (typeof window === 'undefined') return
    const handler = () => dispatch({ type: 'hydrate', patch: routeFromUrl() })
    window.addEventListener('popstate', handler)
    return () => window.removeEventListener('popstate', handler)
  }, [])

  // Persist UI preferences (drafts, panel sizes/visibility).
  useEffect(() => {
    savePrefs(state, owner)
  }, [
    state.drafts,
    state.chatOpen,
    state.chatWidth,
    state.notificationsRead,
    state.chatChannel,
    owner,
  ])

  const value = useMemo<ShellContextValue>(() => ({ state, dispatch }), [state])
  return <ShellContext.Provider value={value}>{children}</ShellContext.Provider>
}

export function useShell(): ShellContextValue {
  const value = useContext(ShellContext)
  if (!value) {
    throw new Error('useShell must be used within a ShellProvider')
  }
  return value
}
