import { EmptyState } from './EmptyState'
import { MockBadge } from './StatusBadge'

export interface NotificationListItem {
  id: string
  title: string
  at: string
  mock?: boolean
}

export interface NotificationListProps {
  items: readonly NotificationListItem[]
  emptyMessage?: string
  onSelect?: (item: NotificationListItem) => void
}

/**
 * Shared NotificationList (design.md §4, §6). The badge count must reflect
 * real unread records; the shell only renders the labelled layout mock or an
 * explicit empty state until LG-019 wires notifications.
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
            onClick={() => onSelect?.(item)}
            disabled={!onSelect}
          >
            <span className="lg-card__meta">
              {item.mock ? <MockBadge /> : null}
              <span>{item.title}</span>
            </span>
            <span className="lg-notification__meta">{item.at}</span>
          </button>
        </li>
      ))}
    </ul>
  )
}
