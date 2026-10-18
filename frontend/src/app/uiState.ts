/**
 * Shell UI state (LG-011).
 *
 * Only UI preferences live here: active view, task/run/item selection, chat
 * drafts and panel layout. The selection/route is mirrored into the URL so a
 * deep-link refresh restores it (docs/05 §6); panel sizes, drafts and mock
 * visibility are session preferences. No business state is stored here — the
 * authoritative Task/Run state comes from the backend (docs/08 §7).
 */
import { CONNECTION_CATEGORY_ID, NAV_RESOURCE_CATEGORIES } from '../api/resources'
import { isViewId, type ViewId } from './navigation'

export type DrawerId = 'nav' | 'chat'

/**
 * Chat channel (LG-054).  `personal` is the private, chat-only conversation;
 * `team` is the shared global/Task conversation.  `null` means "derive from the
 * authenticated mode" (single-user => personal, team => team).
 */
export type ChatChannel = 'personal' | 'team'

export interface ShellState {
  view: ViewId
  taskRef: string | null
  runRef: string | null
  selectedItemRef: string | null
  /** Draft text keyed by chat scope, e.g. `chat:global` or `chat:team:task_x`. */
  drafts: Record<string, string>
  chatOpen: boolean
  chatWidth: number
  notificationsRead: boolean
  openDrawer: DrawerId | null
  /** Explicit channel choice; `null` derives it from the auth mode. */
  chatChannel: ChatChannel | null
}

export const CHAT_WIDTH_MIN = 320
export const CHAT_WIDTH_MAX = 480

export const DEFAULT_CHAT_WIDTH = 360

export function clampChatWidth(width: number): number {
  return Math.min(CHAT_WIDTH_MAX, Math.max(CHAT_WIDTH_MIN, Math.round(width)))
}

export function draftKey(taskRef: string | null, channel: ChatChannel | null = null): string {
  const scope = taskRef ?? 'global'
  // LG-054: team-mode channels are namespaced so a private draft can never be
  // rendered into the shared Team composer (or vice versa).  Single-user mode
  // and legacy callers keep the historical key so old drafts are not lost.
  if (channel === 'team') return `chat:team:${scope}`
  if (channel === 'personal') return `chat:personal:${scope}`
  return `chat:${scope}`
}

/** In-app reference to one Connection record opened inside Settings. */
export function settingsConnectionRef(connectionId: string): string {
  return `settings:connection:${connectionId}`
}

/** Parse a Settings Connection reference, or `null` when not one. */
export function parseSettingsConnectionRef(ref: string | null | undefined): string | null {
  if (!ref || !ref.startsWith('settings:connection:')) return null
  const id = ref.slice('settings:connection:'.length)
  return id || null
}

const LEGACY_CONNECTION_ITEM_PREFIX = 'resources:connection:'

/**
 * Resolve a Connection id from either the current Settings reference or the
 * legacy Resources Connection detail reference (LG-103).  The id is the stable
 * server entity id; it is never a secret.
 */
export function connectionIdFromRef(ref: string | null | undefined): string | null {
  const settingsId = parseSettingsConnectionRef(ref)
  if (settingsId) return settingsId
  if (!ref) return null
  if (ref === LEGACY_CONNECTION_ITEM_PREFIX.slice(0, -1)) return null
  if (!ref.startsWith(LEGACY_CONNECTION_ITEM_PREFIX)) return null
  return ref.slice(LEGACY_CONNECTION_ITEM_PREFIX.length) || null
}

export type ShellAction =
  | { type: 'setView'; view: ViewId }
  | { type: 'openTaskConversation'; taskRef: string; channel?: ChatChannel }
  | {
      type: 'openTaskDestination'
      view: ViewId
      taskRef: string
      runRef: string | null
      itemRef: string | null
    }
  | { type: 'selectTask'; taskRef: string | null; channel?: ChatChannel }
  | { type: 'selectRun'; runRef: string | null }
  | { type: 'selectItem'; itemRef: string | null }
  | { type: 'setDraft'; key: string; value: string }
  | { type: 'toggleChat' }
  | { type: 'setChatWidth'; width: number }
  | { type: 'setOpenDrawer'; drawer: DrawerId | null }
  | { type: 'setChatChannel'; channel: ChatChannel | null }
  | { type: 'markNotificationsRead' }
  | { type: 'hydrate'; patch: Partial<ShellState> }

export function createInitialState(owner?: string): ShellState {
  const route = routeFromUrl()
  const prefs = loadPrefs(owner)
  return {
    view: route.view,
    taskRef: route.taskRef,
    runRef: route.runRef,
    selectedItemRef: route.selectedItemRef,
    drafts: prefs.drafts ?? {},
    chatOpen: prefs.chatOpen ?? true,
    chatWidth: clampChatWidth(prefs.chatWidth ?? DEFAULT_CHAT_WIDTH),
    notificationsRead: prefs.notificationsRead ?? false,
    openDrawer: null,
    chatChannel: route.chatChannel ?? prefs.chatChannel ?? null,
  }
}

export function shellReducer(state: ShellState, action: ShellAction): ShellState {
  switch (action.type) {
    case 'setView':
      // Switching views keeps task_ref, run_ref and the selected item
      // (LG-011 acceptance; docs/05 §3).
      return { ...state, view: action.view }
    case 'openTaskConversation':
      // The provider derives the channel from authenticated deployment mode.
      // LG-202: there is no Chat main view; opening a Task conversation now
      // means the Tasks workspace with the right Bot Chat bound to that Task.
      return { ...state, view: 'tasks', taskRef: action.taskRef, runRef: null, selectedItemRef: null, chatOpen: true, openDrawer: 'chat', chatChannel: action.channel ?? state.chatChannel }
    case 'openTaskDestination':
      // LG-220: one explicit destination keeps the selected Task/Run together
      // while leaving the already-open chat, its channel and drafts untouched.
      return {
        ...state,
        view: action.view,
        taskRef: action.taskRef,
        runRef: action.runRef,
        selectedItemRef: action.itemRef,
      }
    case 'selectTask':
      return {
        ...state,
        taskRef: action.taskRef,
        runRef: null,
        selectedItemRef: null,
        chatChannel: action.taskRef ? action.channel ?? state.chatChannel : state.chatChannel,
      }
    case 'selectRun':
      return { ...state, runRef: action.runRef }
    case 'selectItem':
      return { ...state, selectedItemRef: action.itemRef }
    case 'setChatChannel':
      return { ...state, chatChannel: action.channel }
    case 'setDraft':
      return { ...state, drafts: { ...state.drafts, [action.key]: action.value } }
    case 'toggleChat':
      return { ...state, chatOpen: !state.chatOpen }
    case 'setChatWidth':
      return { ...state, chatWidth: clampChatWidth(action.width) }
    case 'setOpenDrawer':
      return { ...state, openDrawer: action.drawer }
    case 'markNotificationsRead':
      return { ...state, notificationsRead: true }
    case 'hydrate':
      return { ...state, ...action.patch }
    default:
      return state
  }
}

/* ------------------------------------------------------------- URL route */

export interface ShellRoute {
  view: ViewId
  taskRef: string | null
  runRef: string | null
  selectedItemRef: string | null
  chatChannel: ChatChannel | null
}

const ROUTE_PARAMS = ['view', 'task', 'run', 'item', 'channel'] as const

/**
 * Legacy view ids from before LG-202.  `chat` was the retired main conversation
 * page and `files` is the same workspace that is now called Tasks; both must
 * resolve to the real Tasks workspace while preserving task/run/item state.
 */
const LEGACY_VIEW_ALIASES: Readonly<Record<string, ViewId>> = {
  chat: 'tasks',
  files: 'tasks',
}

function canonicalView(value: string | null): ViewId {
  if (isViewId(value)) return value
  if (value) {
    const aliased = LEGACY_VIEW_ALIASES[value]
    if (aliased) return aliased
  }
  return 'tasks'
}

function parseChannel(value: string | null): ChatChannel | null {
  return value === 'personal' || value === 'team' ? value : null
}

/**
 * Normalize routes that predate LG-103.
 *
 * The old app exposed Connections as a Resources category/detail.  Those
 * bookmarks now open Settings → Models & Providers at the same stable
 * Connection id (or its default selection for the category link), while the
 * Task/Run/channel return context is preserved.  A bare legacy Resources route
 * defaults to the first remaining category rather than the old Connections
 * page, so a stale link cannot reach a second connection management surface.
 */
function normalizeRoute(route: ShellRoute): ShellRoute {
  let next = route
  if (route.view === 'resources') {
    if (!route.selectedItemRef) {
      next = {
        ...route,
        selectedItemRef: NAV_RESOURCE_CATEGORIES[0]?.id ?? null,
      }
    } else if (route.selectedItemRef === CONNECTION_CATEGORY_ID) {
      next = { ...route, view: 'settings', selectedItemRef: null }
    } else {
      const id = connectionIdFromRef(route.selectedItemRef)
      if (id || route.selectedItemRef === LEGACY_CONNECTION_ITEM_PREFIX.slice(0, -1)) {
        next = {
          ...route,
          view: 'settings',
          selectedItemRef: id ? settingsConnectionRef(id) : null,
        }
      }
    }
  }
  if (next.view === 'settings') {
    const id = connectionIdFromRef(next.selectedItemRef)
    if (id) {
      next = { ...next, selectedItemRef: settingsConnectionRef(id) }
    } else if (next.selectedItemRef === CONNECTION_CATEGORY_ID) {
      next = { ...next, selectedItemRef: null }
    }
  }
  return next
}

export function routeFromUrl(search?: string): ShellRoute {
  const raw = search ?? (typeof window === 'undefined' ? '' : window.location.search)
  const params = new URLSearchParams(raw)
  return normalizeRoute({
    view: canonicalView(params.get('view')),
    taskRef: params.get('task'),
    runRef: params.get('run'),
    selectedItemRef: params.get('item'),
    chatChannel: parseChannel(params.get('channel')),
  })
}

export function routeQuery(route: ShellRoute): string {
  const params = new URLSearchParams()
  params.set('view', route.view)
  if (route.taskRef) params.set('task', route.taskRef)
  if (route.runRef) params.set('run', route.runRef)
  if (route.selectedItemRef) params.set('item', route.selectedItemRef)
  if (route.chatChannel) params.set('channel', route.chatChannel)
  return `?${params.toString()}`
}

export function hasRouteParams(search: string): boolean {
  const params = new URLSearchParams(search)
  return ROUTE_PARAMS.some((key) => params.has(key))
}

/* ----------------------------------------------------- Session prefs I/O */

const PREFS_KEY = 'lg011.shell-prefs'

interface ShellPrefs {
  drafts?: Record<string, string>
  chatOpen?: boolean
  chatWidth?: number
  notificationsRead?: boolean
  chatChannel?: ChatChannel
}

function storage(): Storage | null {
  try {
    if (typeof window === 'undefined' || !window.sessionStorage) return null
    return window.sessionStorage
  } catch {
    return null
  }
}

export function loadPrefs(owner?: string): ShellPrefs {
  const store = storage()
  if (!store) return {}
  try {
    const raw = store.getItem(owner ? `${PREFS_KEY}:team:${encodeURIComponent(owner)}` : PREFS_KEY)
    if (!raw) return {}
    const parsed: unknown = JSON.parse(raw)
    if (parsed && typeof parsed === 'object') {
      return parsed as ShellPrefs
    }
    return {}
  } catch {
    return {}
  }
}

export function savePrefs(state: ShellState, owner?: string): void {
  const store = storage()
  if (!store) return
  const prefs: ShellPrefs = {
    drafts: state.drafts,
    chatOpen: state.chatOpen,
    chatWidth: state.chatWidth,
    notificationsRead: state.notificationsRead,
    ...(state.chatChannel ? { chatChannel: state.chatChannel } : {}),
  }
  try {
    store.setItem(owner ? `${PREFS_KEY}:team:${encodeURIComponent(owner)}` : PREFS_KEY, JSON.stringify(prefs))
  } catch {
    /* Persisting preferences is best effort; ignore quota/security errors. */
  }
}
