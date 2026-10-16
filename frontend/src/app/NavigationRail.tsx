import {
  SETTINGS_NAV_ITEM,
  WORK_NAV_ITEMS,
  type NavItem,
  type ViewId,
} from './navigation'
import { categoryById, categoryByKind, isResourceKind } from '../api/resources'
import { Icon } from '../components/icons'

export interface NavigationRailProps {
  current: ViewId
  selectedItemRef?: string | null
  onNavigate: (view: ViewId, itemRef?: string) => void
  /** `drawer` renders inside the compact-screen drawer rather than in-flow. */
  variant?: 'inline' | 'drawer'
}

/**
 * One readable primary navigation including resource categories.
 * Work entries scroll independently; Settings stays at the bottom.
 */
export function NavigationRail({ current, selectedItemRef, onNavigate, variant = 'inline' }: NavigationRailProps) {
  // LG-062: Settings is reachable by every signed-in user because it now hosts
  // the personal "My Account" password section.  Admin-only subareas (Models &
  // Providers, Accounts) are hidden in the view and enforced by the backend
  // (403), never by disabling the entry point.
  const kind = selectedItemRef?.startsWith('resources:') ? selectedItemRef.split(':')[1] : null
  const category = (kind && isResourceKind(kind) ? categoryByKind(kind) : categoryById(selectedItemRef ?? null))?.id ?? 'connections'
  const renderItem = (item: NavItem) => (
      <li key={item.id}>
        <button
          type="button"
          className="lg-rail__item"
          aria-current={current === item.view && (item.view !== 'resources' || category === item.id) ? 'page' : undefined}
          aria-label={item.label}
          title={item.label}
          onClick={() => onNavigate(item.view, item.itemRef)}
        >
          <Icon name={item.icon} />
          <span className="lg-rail__label" aria-hidden="true">
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
