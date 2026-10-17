/** Shared view routes and direct primary navigation targets. */
import { RESOURCE_CATEGORIES } from '../api/resources'
import type { IconName } from '../components/icons'

export type ViewId = 'chat' | 'board' | 'files' | 'team' | 'resources' | 'settings'

export interface NavItem {
  id: string
  view: ViewId
  itemRef?: string
  label: string
  icon: IconName
  /** Owning task for the view body; shell only provides the mount point. */
  ownerTask: string
}

// LG-102: one semantic outline glyph per resource category; the generic cube
// stays only as a defensive fallback for future categories.
const RESOURCE_ICONS: Record<string, IconName> = {
  connections: 'connection',
  'session-profiles': 'session-profile',
  hooks: 'hook',
  mcp: 'mcp',
  tools: 'tool',
  triggers: 'trigger',
  skills: 'skill',
}

export const WORK_NAV_ITEMS: readonly NavItem[] = [
  { id: 'chat', view: 'chat', label: 'Chat', icon: 'chat', ownerTask: 'LG-013' },
  { id: 'board', view: 'board', label: 'Board', icon: 'board', ownerTask: 'LG-013' },
  { id: 'files', view: 'files', label: 'Files', icon: 'files', ownerTask: 'LG-014' },
  { id: 'team', view: 'team', label: 'Team', icon: 'team', ownerTask: 'LG-015' },
  ...RESOURCE_CATEGORIES.map(({ id, label }) => ({
    id, label, view: 'resources' as const, itemRef: id, icon: RESOURCE_ICONS[id] ?? 'resources', ownerTask: 'LG-015',
  })),
] as const

export const SETTINGS_NAV_ITEM: NavItem = {
  id: 'settings',
  view: 'settings',
  label: 'Settings',
  icon: 'settings',
  ownerTask: 'LG-026',
}

export const ALL_NAV_ITEMS: readonly NavItem[] = [
  ...WORK_NAV_ITEMS,
  SETTINGS_NAV_ITEM,
]

export function navItemFor(view: ViewId): NavItem {
  const found = ALL_NAV_ITEMS.find((item) => item.view === view)
  if (!found) {
    throw new Error(`Unknown view: ${view}`)
  }
  return found
}

export const VIEW_IDS: readonly ViewId[] = ['chat', 'board', 'files', 'team', 'resources', 'settings']

export function isViewId(value: string | null | undefined): value is ViewId {
  return value != null && (VIEW_IDS as readonly string[]).includes(value)
}
