/**
 * Shell UI state (LG-011).
 *
 * Only UI preferences live here: active view, task/run/item selection, chat
 * drafts and panel layout. The selection/route is mirrored into the URL so a
 * deep-link refresh restores it (docs/05 §6); panel sizes, drafts and mock
 * visibility are session preferences. No business state is stored here — the
 * authoritative Task/Run state comes from the backend (docs/08 §7).
 */
import { isViewId, type ViewId } from './navigation'

export type DrawerId = 'nav' | 'context' | 'chat'

export interface ShellState {
  view: ViewId
  taskRef: string | null
  runRef: string | null
  selectedItemRef: string | null
  /** Draft text keyed by chat scope, e.g. `chat:global` or `chat:task_x`. */
  drafts: Record<string, string>
  contextOpen: boolean
  chatOpen: boolean
  contextWidth: number
  chatWidth: number
  /** clearly-labelled layout mock; never business truth (design.md §8). */
  showLayoutMock: boolean
  notificationsRead: boolean
  openDrawer: DrawerId | null
}

export const CONTEXT_WIDTH_MIN = 200
export const CONTEXT_WIDTH_MAX = 320
export const CHAT_WIDTH_MIN = 320
export const CHAT_WIDTH_MAX = 480

export const DEFAULT_CONTEXT_WIDTH = 240
export const DEFAULT_CHAT_WIDTH = 360

export function clampContextWidth(width: number): number {
  return Math.min(CONTEXT_WIDTH_MAX, Math.max(CONTEXT_WIDTH_MIN, Math.round(width)))
}

export function clampChatWidth(width: number): number {
  return Math.min(CHAT_WIDTH_MAX, Math.max(CHAT_WIDTH_MIN, Math.round(width)))
}

export function draftKey(taskRef: string | null): string {
  return `chat:${taskRef ?? 'global'}`
}

export type ShellAction =
  | { type: 'setView'; view: ViewId }
  | { type: 'selectTask'; taskRef: string | null }
  | { type: 'selectRun'; runRef: string | null }
  | { type: 'selectItem'; itemRef: string | null }
  | { type: 'setDraft'; key: string; value: string }
  | { type: 'toggleContext' }
  | { type: 'toggleChat' }
  | { type: 'setContextWidth'; width: number }
  | { type: 'setChatWidth'; width: number }
  | { type: 'setShowLayoutMock'; value: boolean }
  | { type: 'setOpenDrawer'; drawer: DrawerId | null }
  | { type: 'markNotificationsRead' }
  | { type: 'hydrate'; patch: Partial<ShellState> }

export function createInitialState(): ShellState {
  const route = routeFromUrl()
  const prefs = loadPrefs()
  return {
    view: route.view,
    taskRef: route.taskRef,
    runRef: route.runRef,
    selectedItemRef: route.selectedItemRef,
    drafts: prefs.drafts ?? {},
    contextOpen: prefs.contextOpen ?? true,
    chatOpen: prefs.chatOpen ?? true,
    contextWidth: clampContextWidth(prefs.contextWidth ?? DEFAULT_CONTEXT_WIDTH),
    chatWidth: clampChatWidth(prefs.chatWidth ?? DEFAULT_CHAT_WIDTH),
    showLayoutMock: prefs.showLayoutMock ?? true,
    notificationsRead: prefs.notificationsRead ?? false,
    openDrawer: null,
  }
}

export function shellReducer(state: ShellState, action: ShellAction): ShellState {
  switch (action.type) {
    case 'setView':
      // Switching views keeps task_ref, run_ref and the selected item
      // (LG-011 acceptance; docs/05 §3).
      return { ...state, view: action.view }
    case 'selectTask':
      return { ...state, taskRef: action.taskRef, runRef: null, selectedItemRef: null }
    case 'selectRun':
      return { ...state, runRef: action.runRef }
    case 'selectItem':
      return { ...state, selectedItemRef: action.itemRef }
    case 'setDraft':
      return { ...state, drafts: { ...state.drafts, [action.key]: action.value } }
    case 'toggleContext':
      return { ...state, contextOpen: !state.contextOpen }
    case 'toggleChat':
      return { ...state, chatOpen: !state.chatOpen }
    case 'setContextWidth':
      return { ...state, contextWidth: clampContextWidth(action.width) }
    case 'setChatWidth':
      return { ...state, chatWidth: clampChatWidth(action.width) }
    case 'setShowLayoutMock':
      return { ...state, showLayoutMock: action.value }
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
}

const ROUTE_PARAMS = ['view', 'task', 'run', 'item'] as const

export function routeFromUrl(search?: string): ShellRoute {
  const raw = search ?? (typeof window === 'undefined' ? '' : window.location.search)
  const params = new URLSearchParams(raw)
  const viewParam = params.get('view')
  return {
    view: isViewId(viewParam) ? viewParam : 'chat',
    taskRef: params.get('task'),
    runRef: params.get('run'),
    selectedItemRef: params.get('item'),
  }
}

export function routeQuery(route: ShellRoute): string {
  const params = new URLSearchParams()
  params.set('view', route.view)
  if (route.taskRef) params.set('task', route.taskRef)
  if (route.runRef) params.set('run', route.runRef)
  if (route.selectedItemRef) params.set('item', route.selectedItemRef)
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
  contextOpen?: boolean
  chatOpen?: boolean
  contextWidth?: number
  chatWidth?: number
  showLayoutMock?: boolean
  notificationsRead?: boolean
}

function storage(): Storage | null {
  try {
    if (typeof window === 'undefined' || !window.sessionStorage) return null
    return window.sessionStorage
  } catch {
    return null
  }
}

export function loadPrefs(): ShellPrefs {
  const store = storage()
  if (!store) return {}
  try {
    const raw = store.getItem(PREFS_KEY)
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

export function savePrefs(state: ShellState): void {
  const store = storage()
  if (!store) return
  const prefs: ShellPrefs = {
    drafts: state.drafts,
    contextOpen: state.contextOpen,
    chatOpen: state.chatOpen,
    contextWidth: state.contextWidth,
    chatWidth: state.chatWidth,
    showLayoutMock: state.showLayoutMock,
    notificationsRead: state.notificationsRead,
  }
  try {
    store.setItem(PREFS_KEY, JSON.stringify(prefs))
  } catch {
    /* Persisting preferences is best effort; ignore quota/security errors. */
  }
}
