import {
  SETTINGS_NAV_ITEM,
  WORK_NAV_ITEMS,
  type NavItem,
  type ViewId,
} from './navigation'
import {
  categoryById,
  categoryByKind,
  isResourceKind,
  NAV_RESOURCE_CATEGORIES,
} from '../api/resources'
import { Icon } from '../components/icons'
import { Logo } from '../components/Logo'

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
  const category =
    (kind && isResourceKind(kind) ? categoryByKind(kind) : categoryById(selectedItemRef ?? null))?.id ??
    NAV_RESOURCE_CATEGORIES[0]?.id
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
      {/* The top-bar brand is hidden on phones, so the narrow drawer carries
       * the same mark and wordmark once. The inline rail needs no duplicate. */}
      {variant === 'drawer' ? (
        <div className="lg-rail__brand">
          <Logo className="lg-rail__brand-mark" size={24} />
          <span className="lg-rail__brand-name">LightGravity Bot</span>
        </div>
      ) : null}
      <ul className="lg-rail__list">{WORK_NAV_ITEMS.map(renderItem)}</ul>
      <div className="lg-rail__spacer" />
      <ul className="lg-rail__list">{renderItem(SETTINGS_NAV_ITEM)}</ul>
    </nav>
  )
}
