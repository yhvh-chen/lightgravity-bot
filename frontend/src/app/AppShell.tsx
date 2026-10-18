import { useCallback, useEffect, useRef } from 'react'

import { ChatPanel } from '../components/ChatPanel'
import { PanelResizer } from '../components/SplitPane'
import { ChatSelectionProvider } from '../views/chat/useChatSelection'
import { VIEW_DEFINITIONS } from '../views/registry'
import { useAuth } from './AuthProvider'
import { NavigationRail } from './NavigationRail'
import { useShell } from './ShellProvider'
import { TopBar } from './TopBar'
import { useIsCompact, useIsMobile } from './useMediaQuery'
import {
  CHAT_WIDTH_MAX,
  CHAT_WIDTH_MIN,
} from './uiState'
import type { ViewId } from './navigation'

const DRAWER_LABELS: Record<'nav' | 'chat', string> = {
  nav: 'Navigation',
  chat: 'Chat panel',
}

/**
 * Unified application shell (LG-011).
 *
 * Regions: top bar, single navigation, main content and the right Bot Chat.
 * On compact screens Chat becomes an overlay drawer; on phones the
 * rail does too. Exactly one ChatPanel is mounted at any time. The shell only
 * routes views — each business view is owned by its own task.
 *
 * LG-202: the former Chat main view is gone. Bot Chat is the only conversation
 * surface and binds the shell's current Task (Global when no Task is selected).
 */
export function AppShell() {
  const { state, dispatch } = useShell()
  const { isTeam, personalChatAvailable } = useAuth()
  const compact = useIsCompact()
  const mobile = useIsMobile()
  const definition = VIEW_DEFINITIONS[state.view]
  const Main = definition.Main
  const drawerRef = useRef<HTMLDivElement>(null)
  // LG-204: Tasks selection and the single right Chat share one store. A
  // private Personal conversation never inherits the shared Task selection.
  const selectionTaskRef =
    isTeam && state.chatChannel === 'personal' && personalChatAvailable ? null : state.taskRef

  const closeDrawer = useCallback(
    () => dispatch({ type: 'setOpenDrawer', drawer: null }),
    [dispatch],
  )

  const chatRailShown =
    compact ? state.openDrawer === 'chat' : state.chatOpen
  const railDrawerOpen = mobile && state.openDrawer === 'nav'

  const handleNavigate = useCallback(
    (view: ViewId, itemRef?: string) => {
      dispatch({ type: 'setView', view })
      if (itemRef !== undefined) dispatch({ type: 'selectItem', itemRef })
      if (compact) closeDrawer()
    },
    [compact, closeDrawer, dispatch],
  )

  // Move focus into an open drawer and return it on Escape (design.md §7).
  useEffect(() => {
    if (state.openDrawer && drawerRef.current) {
      drawerRef.current.focus()
    }
  }, [state.openDrawer])

  useEffect(() => {
    if (!state.openDrawer) return
    const handler = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      const drawer = state.openDrawer
      dispatch({ type: 'setOpenDrawer', drawer: null })
      requestAnimationFrame(() => {
        document.getElementById(`lg-toggle-${drawer}`)?.focus()
      })
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [state.openDrawer, dispatch])

  const renderChatRail = (onClose: () => void) => (
    <ChatPanel variant="rail" onRequestClose={onClose} />
  )

  return (
    <ChatSelectionProvider taskRef={selectionTaskRef}>
    <div className="lg-app">
      <TopBar
        compact={compact}
        mobile={mobile}
        railActive={railDrawerOpen}
        chatActive={chatRailShown}
        onToggleRail={() =>
          dispatch({
            type: 'setOpenDrawer',
            drawer: railDrawerOpen ? null : 'nav',
          })
        }
        onToggleChat={() =>
          compact
            ? dispatch({
                type: 'setOpenDrawer',
                drawer: state.openDrawer === 'chat' ? null : 'chat',
              })
            : dispatch({ type: 'toggleChat' })
        }
      />

      <div className="lg-workspace">
        {!mobile ? (
          <NavigationRail current={state.view} selectedItemRef={state.selectedItemRef} onNavigate={handleNavigate} />
        ) : null}

        <main className="lg-main">
          <div className="lg-view">
            <Main />
          </div>
        </main>

        {!compact && state.chatOpen ? (
          <>
            <PanelResizer
              label="Resize chat panel"
              side="right"
              value={state.chatWidth}
              min={CHAT_WIDTH_MIN}
              max={CHAT_WIDTH_MAX}
              onChange={(width) => dispatch({ type: 'setChatWidth', width })}
            />
            <div className="lg-chat-rail" style={{ width: state.chatWidth }}>
              {renderChatRail(() => dispatch({ type: 'toggleChat' }))}
            </div>
          </>
        ) : null}
      </div>

      {compact && state.openDrawer && (state.openDrawer !== 'nav' || mobile) ? (
        <>
          <button
            type="button"
            className="lg-drawer-backdrop"
            aria-label={`Close ${DRAWER_LABELS[state.openDrawer].toLowerCase()}`}
            onClick={closeDrawer}
          />
          <div
            ref={drawerRef}
            className={`lg-drawer lg-drawer--${
              state.openDrawer === 'chat' ? 'right' : 'left'
            } lg-drawer--${state.openDrawer}`}
            role="dialog"
            aria-modal="true"
            aria-label={DRAWER_LABELS[state.openDrawer]}
            tabIndex={-1}
          >
            {state.openDrawer === 'nav' ? (
              <NavigationRail
                current={state.view}
                selectedItemRef={state.selectedItemRef}
                onNavigate={handleNavigate}
                variant="drawer"
              />
            ) : null}
            {state.openDrawer === 'chat' ? renderChatRail(closeDrawer) : null}
          </div>
        </>
      ) : null}
    </div>
    </ChatSelectionProvider>
  )
}
