import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  type Dispatch,
  type ReactNode,
} from 'react'

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
  const [state, dispatch] = useReducer(shellReducer, undefined, createInitialState)
  const prevQuery = useRef<string | null>(null)

  // Mirror the route-bearing state into the URL for deep-link refresh.
  useEffect(() => {
    if (typeof window === 'undefined') return
    const query = routeQuery({
      view: state.view,
      taskRef: state.taskRef,
      runRef: state.runRef,
      selectedItemRef: state.selectedItemRef,
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
  }, [state.view, state.taskRef, state.runRef, state.selectedItemRef])

  // Back/forward restores the route without recreating any panel state.
  useEffect(() => {
    if (typeof window === 'undefined') return
    const handler = () => dispatch({ type: 'hydrate', patch: routeFromUrl() })
    window.addEventListener('popstate', handler)
    return () => window.removeEventListener('popstate', handler)
  }, [])

  // Persist UI preferences (drafts, panel sizes/visibility, mock toggle).
  useEffect(() => {
    savePrefs(state)
  }, [
    state.drafts,
    state.contextOpen,
    state.chatOpen,
    state.contextWidth,
    state.chatWidth,
    state.showLayoutMock,
    state.notificationsRead,
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
