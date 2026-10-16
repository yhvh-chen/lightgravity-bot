/**
 * Fixed primary navigation (LG-011).
 *
 * design.md §2 and docs/05 §3 freeze five work entries plus a Settings gear at
 * the bottom. This module is the single source for labels, order and the view
 * owner so later view tasks can replace a view without touching the shell.
 */
import type { IconName } from '../components/icons'

export type ViewId = 'chat' | 'board' | 'files' | 'team' | 'resources' | 'settings'

export interface NavItem {
  id: ViewId
  label: string
  icon: IconName
  /** Owning task for the view body; shell only provides the mount point. */
  ownerTask: string
}

export const WORK_NAV_ITEMS: readonly NavItem[] = [
  { id: 'chat', label: 'Chat', icon: 'chat', ownerTask: 'LG-013' },
  { id: 'board', label: 'Board', icon: 'board', ownerTask: 'LG-013' },
  { id: 'files', label: 'Files', icon: 'files', ownerTask: 'LG-014' },
  { id: 'team', label: 'Team', icon: 'team', ownerTask: 'LG-015' },
  { id: 'resources', label: 'Resources', icon: 'resources', ownerTask: 'LG-015' },
] as const

export const SETTINGS_NAV_ITEM: NavItem = {
  id: 'settings',
  label: 'Settings',
  icon: 'settings',
  ownerTask: 'LG-026',
}

export const ALL_NAV_ITEMS: readonly NavItem[] = [
  ...WORK_NAV_ITEMS,
  SETTINGS_NAV_ITEM,
]

export function navItemFor(view: ViewId): NavItem {
  const found = ALL_NAV_ITEMS.find((item) => item.id === view)
  if (!found) {
    throw new Error(`Unknown view: ${view}`)
  }
  return found
}

export const VIEW_IDS: readonly ViewId[] = ALL_NAV_ITEMS.map((item) => item.id)

export function isViewId(value: string | null | undefined): value is ViewId {
  return value != null && (VIEW_IDS as readonly string[]).includes(value)
}
