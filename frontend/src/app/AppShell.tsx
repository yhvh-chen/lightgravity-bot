import { useCallback, useEffect, useRef } from 'react'

import { ChatPanel } from '../components/ChatPanel'
import { ContextList, type ContextItem } from '../components/ContextList'
import { PanelResizer } from '../components/SplitPane'
import { Icon } from '../components/icons'
import { VIEW_DEFINITIONS } from '../views/registry'
import { NavigationRail } from './NavigationRail'
import { useShell } from './ShellProvider'
import { TopBar } from './TopBar'
import { useIsCompact, useIsMobile } from './useMediaQuery'
import {
  CHAT_WIDTH_MAX,
  CHAT_WIDTH_MIN,
  CONTEXT_WIDTH_MAX,
  CONTEXT_WIDTH_MIN,
} from './uiState'
import type { ViewId } from './navigation'

const DRAWER_LABELS: Record<'nav' | 'context' | 'chat', string> = {
  nav: 'Navigation',
  context: 'Context panel',
  chat: 'Chat panel',
}

/**
 * Unified application shell (LG-011).
 *
 * Regions: top bar, navigation rail, context rail, main content, right Chat
 * rail. On compact screens context/Chat become overlay drawers; on phones the
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

  const contextVisible = compact ? state.openDrawer === 'context' : state.contextOpen
  const chatRailShown =
    state.view !== 'chat' && (compact ? state.openDrawer === 'chat' : state.chatOpen)
  const railDrawerOpen = mobile && state.openDrawer === 'nav'

  const handleNavigate = useCallback(
    (view: ViewId) => {
      dispatch({ type: 'setView', view })
      if (compact) closeDrawer()
    },
    [compact, closeDrawer, dispatch],
  )

  const handleContextSelect = useCallback(
    (item: ContextItem) => {
      if (item.taskRef) {
        dispatch({ type: 'selectTask', taskRef: item.taskRef })
      }
      dispatch({ type: 'selectItem', itemRef: item.id })
    },
    [dispatch],
  )

  const contextSections = definition.buildContext(state)

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

  const renderContext = (onClose: () => void, inline: boolean) => (
    <aside
      className={`lg-context${inline ? ' lg-context--inline' : ''}`}
      aria-label="Context"
      style={inline ? { width: state.contextWidth } : undefined}
    >
      <div className="lg-context__header">
        <h2 className="lg-context__title">{definition.contextTitle}</h2>
        <button
          type="button"
          className="lg-icon-button"
          aria-label="Hide context panel"
          onClick={onClose}
        >
          <Icon name="close" />
        </button>
      </div>
      <ContextList
        sections={contextSections}
        selectedId={state.selectedItemRef}
        onSelect={handleContextSelect}
        ariaLabel={definition.contextAriaLabel}
      />
    </aside>
  )

  const renderChatRail = (onClose: () => void) => (
    <ChatPanel variant="rail" onRequestClose={onClose} />
  )

  const openDrawer = state.openDrawer

  return (
    <div className="lg-app">
      <TopBar
        compact={compact}
        mobile={mobile}
        railActive={railDrawerOpen}
        contextActive={contextVisible}
        chatActive={chatRailShown}
        onToggleRail={() =>
          dispatch({
            type: 'setOpenDrawer',
            drawer: railDrawerOpen ? null : 'nav',
          })
        }
        onToggleContext={() =>
          compact
            ? dispatch({
                type: 'setOpenDrawer',
                drawer: openDrawer === 'context' ? null : 'context',
              })
            : dispatch({ type: 'toggleContext' })
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
          <NavigationRail current={state.view} onNavigate={handleNavigate} />
        ) : null}

        {!compact && state.contextOpen ? (
          <>
            {renderContext(() => dispatch({ type: 'toggleContext' }), true)}
            <PanelResizer
              label="Resize context panel"
              side="left"
              value={state.contextWidth}
              min={CONTEXT_WIDTH_MIN}
              max={CONTEXT_WIDTH_MAX}
              onChange={(width) => dispatch({ type: 'setContextWidth', width })}
            />
          </>
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
                onNavigate={handleNavigate}
                variant="drawer"
              />
            ) : null}
            {openDrawer === 'context' ? renderContext(closeDrawer, false) : null}
            {openDrawer === 'chat' ? renderChatRail(closeDrawer) : null}
          </div>
        </>
      ) : null}
    </div>
  )
}
