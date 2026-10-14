import {
  SETTINGS_NAV_ITEM,
  WORK_NAV_ITEMS,
  type NavItem,
  type ViewId,
} from './navigation'
import { Icon } from '../components/icons'

export interface NavigationRailProps {
  current: ViewId
  onNavigate: (view: ViewId) => void
  /** `drawer` renders inside the compact-screen drawer rather than in-flow. */
  variant?: 'inline' | 'drawer'
}

/**
 * Fixed primary navigation (docs/05 §3, design.md §2). Five work entries in
 * order, Settings pinned to the bottom. Icon-only with hover/focus tooltips,
 * an accessible name per button and `aria-current` on the active entry.
 */
export function NavigationRail({ current, onNavigate, variant = 'inline' }: NavigationRailProps) {
  const renderItem = (item: NavItem) => (
    <li key={item.id}>
      <button
        type="button"
        className="lg-rail__item"
        aria-current={current === item.id ? 'page' : undefined}
        aria-label={item.label}
        title={item.label}
        onClick={() => onNavigate(item.id)}
      >
        <Icon name={item.icon} />
        <span className="lg-rail__tooltip" aria-hidden="true">
          {item.label}
        </span>
      </button>
    </li>
  )

  return (
    <nav
      className="lg-rail"
      aria-label={variant === 'drawer' ? 'Primary navigation (drawer)' : 'Primary navigation'}
    >
      <ul className="lg-rail__list">{WORK_NAV_ITEMS.map(renderItem)}</ul>
      <div className="lg-rail__spacer" />
      <ul className="lg-rail__list">{renderItem(SETTINGS_NAV_ITEM)}</ul>
    </nav>
  )
}
