import { useCallback, useEffect, useRef, useState } from 'react'

import { NotificationList, type NotificationListItem } from '../components/NotificationList'
import { Icon } from '../components/icons'
import { MOCK_NOTIFICATIONS, MOCK_TASKS, MOCK_RUNS_BY_TASK } from './layoutMock'
import { useAuth } from './AuthProvider'
import { useShell } from './ShellProvider'
import { useNotifications } from './useNotifications'
import { NOTIFICATION_REFRESH_TYPES, useEventStream } from './useEventStream'

export interface TopBarProps {
  compact: boolean
  mobile: boolean
  railActive: boolean
  contextActive: boolean
  chatActive: boolean
  onToggleRail: () => void
  onToggleContext: () => void
  onToggleChat: () => void
}

/**
 * Shell top bar (docs/05 §2, design.md §2): brand, global/current Task + Run
 * scope, panel visibility controls and notifications. Deliberately no
 * primary top tabs — those live only in the navigation rail.
 */
export function TopBar({
  compact,
  mobile,
  railActive,
  contextActive,
  chatActive,
  onToggleRail,
  onToggleContext,
  onToggleChat,
}: TopBarProps) {
  const { state, dispatch } = useShell()
  const { isTeam, identity, logout } = useAuth()
  const [notifOpen, setNotifOpen] = useState(false)
  const notifButtonRef = useRef<HTMLButtonElement>(null)
  const popoverRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!notifOpen) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setNotifOpen(false)
        notifButtonRef.current?.focus()
      }
    }
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target as Node
      if (popoverRef.current?.contains(target) || notifButtonRef.current?.contains(target)) {
        return
      }
      setNotifOpen(false)
    }
    window.addEventListener('keydown', onKey)
    window.addEventListener('pointerdown', onPointerDown)
    return () => {
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('pointerdown', onPointerDown)
    }
  }, [notifOpen])

  const taskIds = new Set(MOCK_TASKS.map((task) => task.id))
  if (state.taskRef) taskIds.add(state.taskRef)
  const taskOptions = Array.from(taskIds).sort()

  const runOptions = new Set(state.taskRef ? (MOCK_RUNS_BY_TASK[state.taskRef] ?? []) : [])
  if (state.runRef) runOptions.add(state.runRef)

  // Real notifications from the backend projection. The layout mock toggle is a
  // separate, clearly-labelled sample; it never claims to be business truth.
  const notifications = useNotifications()
  const { status: streamStatus } = useEventStream({
    filterTypes: NOTIFICATION_REFRESH_TYPES,
    onEvent: () => notifications.refresh(),
  })
  const mockItems: NotificationListItem[] = state.showLayoutMock
    ? MOCK_NOTIFICATIONS.map((item) => ({
        id: item.id,
        title: item.title,
        at: item.at,
        mock: true,
      }))
    : []
  const unread = notifications.items.filter((item) => !item.read)
  const hasUnread = unread.length > 0
  const openNotification = useCallback(
    (item: NotificationListItem) => {
      if (item.mock || !item.taskRef) return
      // Return to the exact Task/Run and persist the read flag on the backend.
      dispatch({ type: 'selectTask', taskRef: item.taskRef })
      if (item.runRef) dispatch({ type: 'selectRun', runRef: item.runRef })
      void notifications.markRead([item.id])
      setNotifOpen(false)
    },
    [dispatch, notifications],
  )

  const toggleNotifications = () => {
    setNotifOpen((open) => !open)
  }

  return (
    <header className="lg-topbar">
      {mobile ? (
        <button
          id="lg-toggle-nav"
          type="button"
          className="lg-icon-button"
          aria-label="Toggle navigation"
          aria-expanded={railActive}
          onClick={onToggleRail}
        >
          <Icon name="menu" />
        </button>
      ) : null}

      <div className="lg-topbar__brand">
        <span className="lg-topbar__mark" aria-hidden="true">
          LG
        </span>
        <h1 className="lg-topbar__title">LightGravity Bot</h1>
      </div>

      <div className="lg-topbar__scope">
        <div className="lg-scope-field">
          <label className="lg-scope-field__label" htmlFor="lg-scope-task">
            Scope
          </label>
          <select
            id="lg-scope-task"
            className="lg-select"
            value={state.taskRef ?? ''}
            onChange={(event) =>
              dispatch({ type: 'selectTask', taskRef: event.target.value || null })
            }
          >
            <option value="">Global</option>
            {taskOptions.map((taskId) => (
              <option key={taskId} value={taskId}>
                {taskId}
              </option>
            ))}
          </select>
        </div>
        <div className="lg-scope-field">
          <label className="lg-scope-field__label" htmlFor="lg-scope-run">
            Run
          </label>
          <select
            id="lg-scope-run"
            className="lg-select"
            value={state.runRef ?? ''}
            disabled={!state.taskRef || runOptions.size === 0}
            onChange={(event) =>
              dispatch({ type: 'selectRun', runRef: event.target.value || null })
            }
          >
            <option value="">—</option>
            {Array.from(runOptions).map((runRef) => (
              <option key={runRef} value={runRef}>
                {runRef}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="lg-topbar__spacer" />

      <div className="lg-topbar__actions">
        {isTeam ? (
          <div className="lg-topbar__identity" aria-label="Signed-in identity">
            <span className="lg-topbar__identity-user">
              {identity.username ?? 'Unknown'}
            </span>
            <span className="lg-topbar__identity-role">{identity.role ?? 'member'}</span>
            <button
              type="button"
              className="lg-button lg-button--subtle lg-topbar__logout"
              onClick={() => void logout()}
            >
              Sign out
            </button>
          </div>
        ) : null}
        <button
          type="button"
          className="lg-icon-button lg-topbar__mock-toggle"
          aria-pressed={state.showLayoutMock}
          aria-label="Toggle layout mock data"
          title="Layout mock data — not backend facts"
          onClick={() =>
            dispatch({ type: 'setShowLayoutMock', value: !state.showLayoutMock })
          }
        >
          <Icon name="info" />
        </button>
        <button
          id="lg-toggle-context"
          type="button"
          className="lg-icon-button"
          aria-pressed={contextActive}
          aria-label="Toggle context panel"
          title="Context panel"
          onClick={onToggleContext}
        >
          <Icon name="panel-left" />
        </button>
        <button
          id="lg-toggle-chat"
          type="button"
          className="lg-icon-button"
          aria-pressed={state.view === 'chat' || chatActive}
          aria-label="Toggle chat panel"
          title={state.view === 'chat' ? 'Chat is already the main view' : 'Chat panel'}
          disabled={state.view === 'chat'}
          onClick={onToggleChat}
        >
          <Icon name="panel-right" />
        </button>
        <button
          ref={notifButtonRef}
          type="button"
          className="lg-icon-button"
          aria-label={
            hasUnread ? `Notifications (${unread.length} unread)` : 'Notifications'
          }
          aria-haspopup="dialog"
          aria-expanded={notifOpen}
          onClick={toggleNotifications}
        >
          <Icon name="bell" />
          {hasUnread ? (
            <span className="lg-icon-button__badge" aria-hidden="true">
              {unread.length > 99 ? '99+' : unread.length}
            </span>
          ) : null}
        </button>
      </div>

      {notifOpen ? (
        <div className="lg-popover" role="dialog" aria-label="Notifications" ref={popoverRef}>
          <div className="lg-popover__header">
            <span>Notifications</span>
            <span
              className="lg-popover__status"
              data-state={streamStatus}
              title={`Event stream: ${streamStatus}`}
            >
              {notifications.connected
                ? streamStatus === 'open'
                  ? 'Live'
                  : `Reconnecting (${streamStatus})`
                : 'Offline'}
            </span>
          </div>
          <NotificationList
            items={[
              ...notifications.items.map((item) => ({
                id: item.notification_id,
                title: item.title,
                at: item.at,
                taskRef: item.task_ref,
                runRef: item.run_ref,
                severity: item.severity,
                read: item.read,
              })),
              ...mockItems,
            ]}
            emptyMessage="No notifications. Failures, waiting-for-user and pending acceptance appear here."
            onSelect={openNotification}
          />
        </div>
      ) : null}

      <span className="lg-visually-hidden" aria-live="polite">
        {compact ? 'Compact layout' : 'Wide layout'}
      </span>
    </header>
  )
}
