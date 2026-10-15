import { EmptyState } from './EmptyState'
import { MockBadge, StatusBadge, type StatusKind } from './StatusBadge'

export interface NotificationListItem {
  id: string
  title: string
  at: string
  mock?: boolean
  /** Accurate Task/Run targeting; a click returns to this exact place. */
  taskRef?: string | null
  runRef?: string | null
  severity?: 'info' | 'success' | 'warning' | 'error'
  read?: boolean
  body?: string
}

export interface NotificationListProps {
  items: readonly NotificationListItem[]
  emptyMessage?: string
  onSelect?: (item: NotificationListItem) => void
}

const SEVERITY_TONE: Record<string, StatusKind> = {
  success: 'success',
  warning: 'warning',
  error: 'error',
  info: 'neutral',
}

/**
 * Shared NotificationList (design.md §4, §6). The badge count reflects real
 * unread records from the backend projection; this component only renders.
 */
export function NotificationList({
  items,
  emptyMessage = 'No notifications yet.',
  onSelect,
}: NotificationListProps) {
  if (items.length === 0) {
    return <EmptyState title="No notifications" compact>{emptyMessage}</EmptyState>
  }
  return (
    <ul className="lg-notification-list">
      {items.map((item) => (
        <li key={item.id}>
          <button
            type="button"
            className="lg-notification"
            data-read={item.read ? 'true' : 'false'}
            onClick={() => onSelect?.(item)}
            disabled={!onSelect}
          >
            <span className="lg-card__meta">
              {item.mock ? <MockBadge /> : null}
              {item.severity ? (
                <StatusBadge kind={SEVERITY_TONE[item.severity] ?? 'neutral'}>
                  {item.severity}
                </StatusBadge>
              ) : null}
              <span>{item.title}</span>
            </span>
            {item.taskRef ? (
              <span className="lg-notification__meta">
                {item.taskRef}
                {item.runRef ? ` · ${item.runRef}` : ''}
              </span>
            ) : null}
            <span className="lg-notification__meta">{item.at}</span>
          </button>
        </li>
      ))}
    </ul>
  )
}
