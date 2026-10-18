/**
 * Chat selected-material state (LG-044; docs/10 §2, §3, §8).
 *
 * The user may manually pick up to **3 already-ingested** materials to send as
 * optional context (docs/10 §1). The selection is UI state scoped to one Chat
 * scope (global or the current Task):
 *
 * * it defaults to **none**;
 * * switching Task **clears** it — a selection is never carried across Tasks
 *   (docs/10 §1, §8);
 * * at most `MAX_SELECTED_SOURCES` (3) refs are kept; the 4th is refused in the
 *   UI (the server validates independently — docs/10 §5);
 * * each ref carries the source's real `source_version`/`content_hash` from the
 *   actual source view/API, never an invented hash prefix (docs/10 §2).
 *
 * The refs are only ever serialised into the message request when the scope
 * matches; the selection itself grants no execution permission (docs/10 §2).
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'

import type { SelectedSourceRef } from '../../api/chat'
import type { SourceView } from '../../api/sources'

/** Frozen maximum number of selectable sources (docs/10 §3). */
export const MAX_SELECTED_SOURCES = 3

/** A selected material plus the display fields the picker/context needs. */
export interface SelectedMaterial extends SelectedSourceRef {
  /** Human label captured at selection time (not a fact the server re-reads). */
  title: string | null
  /** Scope marker from the real source view; used for display only. */
  scope: 'global' | 'task'
  status: string
  /** True when the picker saw a usable ingested body at selection time. */
  selectable: boolean
}

export interface UseChatSelectionResult {
  /** Current selection for the active scope (empty when none). */
  selection: SelectedMaterial[]
  /** True while the selection has reached the frozen limit. */
  atLimit: boolean
  /** Toggle one source into/out of the selection (bounded to 3). */
  toggle: (source: SourceView, scope: 'global' | 'task') => void
  /** Remove one source by id. */
  remove: (sourceId: string) => void
  /** Clear the whole selection. */
  clear: () => void
  /**
   * The wire refs for the current scope, or `undefined` when nothing is
   * selected so the request omits `selected_sources` entirely.
   */
  requestRefs: SelectedSourceRef[] | undefined
}

function refFromSource(source: SourceView): SelectedMaterial {
  const scope: 'global' | 'task' = source.scope.task_ref ? 'task' : 'global'
  return {
    source_id: source.source_id,
    source_version: source.source_version,
    // Only the real content hash from the source API; never a fabricated one.
    ...(source.content_hash ? { content_hash: source.content_hash } : {}),
    title: source.title,
    scope,
    status: source.status,
    selectable: true,
  }
}

export function useChatSelection(taskRef: string | null): UseChatSelectionResult {
  const [selection, setSelection] = useState<SelectedMaterial[]>([])
  const scopeRef = useRef<string>(taskRef ?? 'global')

  // Clear on any scope change: a selection never crosses Task boundaries.
  useEffect(() => {
    scopeRef.current = taskRef ?? 'global'
    setSelection([])
  }, [taskRef])

  const toggle = useCallback((source: SourceView, scope: 'global' | 'task') => {
    setSelection((current) => {
      const existing = current.find((item) => item.source_id === source.source_id)
      if (existing) {
        return current.filter((item) => item.source_id !== source.source_id)
      }
      if (current.length >= MAX_SELECTED_SOURCES) return current
      return [...current, { ...refFromSource(source), scope }]
    })
  }, [])

  const remove = useCallback((sourceId: string) => {
    setSelection((current) => current.filter((item) => item.source_id !== sourceId))
  }, [])

  const clear = useCallback(() => setSelection([]), [])

  return useMemo(() => {
    const requestRefs =
      selection.length === 0
        ? undefined
        : selection.map((item) => ({
            source_id: item.source_id,
            ...(typeof item.source_version === 'number'
              ? { source_version: item.source_version }
              : {}),
            ...(item.content_hash ? { content_hash: item.content_hash } : {}),
          }))
    return {
      selection,
      atLimit: selection.length >= MAX_SELECTED_SOURCES,
      toggle,
      remove,
      clear,
      requestRefs,
    }
  }, [selection, toggle, remove, clear])
}

const SharedChatSelectionContext = createContext<UseChatSelectionResult | null>(null)

/**
 * LG-204: the Tasks workspace and the right Bot Chat must share one bounded
 * selection (same version/hash and 3-source limit) without carrying it across
 * Task scopes. The provider owns the single hook instance; consumers rendered
 * standalone in tests fall back to local state.
 */
export function ChatSelectionProvider({
  taskRef,
  children,
}: {
  taskRef: string | null
  children: ReactNode
}) {
  const selection = useChatSelection(taskRef)
  return (
    <SharedChatSelectionContext.Provider value={selection}>
      {children}
    </SharedChatSelectionContext.Provider>
  )
}

export function useSharedChatSelection(taskRef: string | null): UseChatSelectionResult {
  const shared = useContext(SharedChatSelectionContext)
  // Hook order is unconditional so a standalone consumer still gets real state.
  const local = useChatSelection(taskRef)
  return shared ?? local
}
