import { useCallback, useEffect, useRef, useState } from 'react'

import { NotificationList, type NotificationListItem } from '../components/NotificationList'
import { Icon } from '../components/icons'
import { MaterialSearch } from '../components/MaterialSearch'
import { useAuth } from './AuthProvider'
import { useShell } from './ShellProvider'
import { useNotifications } from './useNotifications'
import { NOTIFICATION_REFRESH_TYPES, useEventStream } from './useEventStream'

export interface TopBarProps {
  compact: boolean
  mobile: boolean
  railActive: boolean
  chatActive: boolean
  onToggleRail: () => void
  onToggleChat: () => void
}

/**
 * Top bar: brand, real material search, account, optional Chat and notifications.
 */
export function TopBar({
  compact,
  mobile,
  railActive,
  chatActive,
  onToggleRail,
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

  const notifications = useNotifications()
  const { status: streamStatus } = useEventStream({
    filterTypes: NOTIFICATION_REFRESH_TYPES,
    onEvent: () => notifications.refresh(),
  })
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

      <MaterialSearch />

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
