import { useCallback, useEffect, useRef } from 'react'

import { ChatPanel } from '../components/ChatPanel'
import { PanelResizer } from '../components/SplitPane'
import { VIEW_DEFINITIONS } from '../views/registry'
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
 * Regions: top bar, single navigation, main content and optional right Chat.
 * On compact screens Chat becomes an overlay drawer; on phones the
 * rail does too. Exactly one ChatPanel is mounted at any time. The shell only
 * routes views — each business view is owned by its own task.
 */
export function AppShell() {
  const { state, dispatch } = useShell()
  const compact = useIsCompact()
  const mobile = useIsMobile()
  const definition = VIEW_DEFINITIONS[state.view]
  const Main = definition.Main
  const drawerRef = useRef<HTMLDivElement>(null)

  const closeDrawer = useCallback(
    () => dispatch({ type: 'setOpenDrawer', drawer: null }),
    [dispatch],
  )

  const chatRailShown =
    state.view !== 'chat' && (compact ? state.openDrawer === 'chat' : state.chatOpen)
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

  const openDrawer = state.view === 'chat' && state.openDrawer === 'chat' ? null : state.openDrawer

  return (
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
                drawer: openDrawer === 'chat' ? null : 'chat',
              })
            : dispatch({ type: 'toggleChat' })
        }
      />

      <div className="lg-workspace">
        {!mobile ? (
          <NavigationRail current={state.view} selectedItemRef={state.selectedItemRef} onNavigate={handleNavigate} />
        ) : null}

        <main className="lg-main">
          <div className={`lg-view${state.view === 'chat' ? ' lg-view--chat' : ''}`}>
            <Main />
          </div>
        </main>

        {!compact && state.view !== 'chat' && state.chatOpen ? (
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

      {compact && openDrawer && (openDrawer !== 'nav' || mobile) ? (
        <>
          <button
            type="button"
            className="lg-drawer-backdrop"
            aria-label={`Close ${DRAWER_LABELS[openDrawer].toLowerCase()}`}
            onClick={closeDrawer}
          />
          <div
            ref={drawerRef}
            className={`lg-drawer lg-drawer--${
              openDrawer === 'chat' ? 'right' : 'left'
            } lg-drawer--${openDrawer}`}
            role="dialog"
            aria-modal="true"
            aria-label={DRAWER_LABELS[openDrawer]}
            tabIndex={-1}
          >
            {openDrawer === 'nav' ? (
              <NavigationRail
                current={state.view}
                selectedItemRef={state.selectedItemRef}
                onNavigate={handleNavigate}
                variant="drawer"
              />
            ) : null}
            {openDrawer === 'chat' ? renderChatRail(closeDrawer) : null}
          </div>
        </>
      ) : null}
    </div>
  )
}
