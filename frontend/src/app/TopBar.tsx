import { useEffect, useRef, useState } from 'react'

import { NotificationList } from '../components/NotificationList'
import { Icon } from '../components/icons'
import { MOCK_NOTIFICATIONS, MOCK_TASKS, MOCK_RUNS_BY_TASK } from './layoutMock'
import { useShell } from './ShellProvider'

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

  const notifications = state.showLayoutMock ? MOCK_NOTIFICATIONS : []
  const hasUnread = notifications.length > 0 && !state.notificationsRead

  const toggleNotifications = () => {
    setNotifOpen((open) => {
      if (!open && hasUnread) {
        dispatch({ type: 'markNotificationsRead' })
      }
      return !open
    })
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
          aria-label="Notifications"
          aria-haspopup="dialog"
          aria-expanded={notifOpen}
          onClick={toggleNotifications}
        >
          <Icon name="bell" />
          {hasUnread ? <span className="lg-icon-button__dot" aria-hidden="true" /> : null}
        </button>
      </div>

      {notifOpen ? (
        <div className="lg-popover" role="dialog" aria-label="Notifications" ref={popoverRef}>
          <NotificationList
            items={notifications.map((item) => ({
              id: item.id,
              title: item.title,
              at: item.at,
              mock: item.mock,
            }))}
            emptyMessage="Notifications are implemented by LG-019."
          />
        </div>
      ) : null}

      <span className="lg-visually-hidden" aria-live="polite">
        {compact ? 'Compact layout' : 'Wide layout'}
      </span>
    </header>
  )
}
