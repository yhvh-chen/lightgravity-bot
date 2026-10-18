import { useCallback, useEffect, useRef, useState } from 'react'

import { ApiError } from '../api/client'
import type { SearchResult, SourcesApi } from '../api/sources'
import type { SearchApi, VectorStatusView } from '../api/search'
import { searchApi as defaultSearchApi } from '../api/search'

/** Keyword is the default; Semantic is a separate list, never score-mixed. */
export type MaterialSearchMode = 'keyword' | 'semantic'

export interface MaterialSearchOptions {
  /** Injected vector/search client (defaults to the real `/vector/*` client). */
  searchApi?: SearchApi
  /** Runtime capability gate (`supportsSemanticSearch`); false keeps Keyword only. */
  semanticEnabled?: boolean
}

/** Shared state for one real material search. */
export interface MaterialSearchController {
  draft: string
  setDraft: (value: string) => void
  /** Result for the active mode only; keyword and semantic are kept separate. */
  result: SearchResult | null
  loading: boolean
  error: ApiError | null
  run: () => void

  mode: MaterialSearchMode
  setMode: (mode: MaterialSearchMode) => void
  keywordResult: SearchResult | null
  semanticResult: SearchResult | null

  /** Read-only `/vector/status` read performed on explicit Semantic entry. */
  vectorStatus: VectorStatusView | null
  statusLoading: boolean
  statusError: ApiError | null

  /** Explicit user action: switch to Keyword and run that query. */
  fallbackToKeyword: () => void
}

/**
 * Keeps the current Task scope plus shared materials, last-response-wins, and a
 * Task/API change aborts and clears stale results. Typing alone never searches
 * or polls; callers invoke `run()` on the existing Enter/search action.
 */
export function useMaterialSearch(
  api: SourcesApi,
  taskRef: string | null,
  options: MaterialSearchOptions = {},
): MaterialSearchController {
  const semanticEnabled = options.semanticEnabled === true
  const searchApi = options.searchApi ?? defaultSearchApi

  const [draft, setDraft] = useState('')
  const [mode, setModeState] = useState<MaterialSearchMode>('keyword')
  const [keywordResult, setKeywordResult] = useState<SearchResult | null>(null)
  const [semanticResult, setSemanticResult] = useState<SearchResult | null>(null)
  const [keywordLoading, setKeywordLoading] = useState(false)
  const [semanticLoading, setSemanticLoading] = useState(false)
  const [keywordError, setKeywordError] = useState<ApiError | null>(null)
  const [semanticError, setSemanticError] = useState<ApiError | null>(null)
  const [vectorStatus, setVectorStatus] = useState<VectorStatusView | null>(null)
  const [statusLoading, setStatusLoading] = useState(false)
  const [statusError, setStatusError] = useState<ApiError | null>(null)

  const activeKeyword = useRef<AbortController | null>(null)
  const activeSemantic = useRef<AbortController | null>(null)
  const generation = useRef(0)

  const clearSearchState = useCallback(() => {
    generation.current += 1
    activeKeyword.current?.abort()
    activeSemantic.current?.abort()
    setKeywordResult(null)
    setSemanticResult(null)
    setKeywordError(null)
    setSemanticError(null)
    setKeywordLoading(false)
    setSemanticLoading(false)
  }, [])

  useEffect(() => {
    clearSearchState()
    return () => {
      generation.current += 1
      activeKeyword.current?.abort()
      activeSemantic.current?.abort()
    }
  }, [api, taskRef, searchApi, clearSearchState])

  useEffect(() => {
    if (semanticEnabled) return
    setModeState('keyword')
    setSemanticResult(null)
    setSemanticError(null)
    setSemanticLoading(false)
    setVectorStatus(null)
    setStatusError(null)
    setStatusLoading(false)
    activeSemantic.current?.abort()
  }, [semanticEnabled])

  // Status is read once per explicit Semantic entry (no interval/polling).
  useEffect(() => {
    if (mode !== 'semantic' || !semanticEnabled) {
      setVectorStatus(null)
      setStatusError(null)
      setStatusLoading(false)
      return
    }
    const controller = new AbortController()
    setStatusLoading(true)
    setStatusError(null)
    void (async () => {
      try {
        const status = await searchApi.getVectorStatus(controller.signal)
        if (controller.signal.aborted) return
        setVectorStatus(status)
      } catch (cause) {
        if (controller.signal.aborted) return
        setVectorStatus(null)
        setStatusError(asApiError(cause))
      } finally {
        if (!controller.signal.aborted) setStatusLoading(false)
      }
    })()
    return () => controller.abort()
  }, [mode, semanticEnabled, searchApi])

  const executeKeyword = useCallback(() => {
    const q = draft.trim()
    if (!q) return
    activeKeyword.current?.abort()
    const controller = new AbortController()
    activeKeyword.current = controller
    const requestGeneration = ++generation.current
    setKeywordResult(null)
    setKeywordLoading(true)
    setKeywordError(null)
    void (async () => {
      try {
        // No `rebuild_if_missing`: default/omitted search is read-only.
        const found = await api.search(
          {
            q,
            task_ref: taskRef ?? undefined,
            include_global: true,
            limit: 20,
          },
          controller.signal,
        )
        if (requestGeneration !== generation.current || controller.signal.aborted) return
        setKeywordResult(found)
      } catch (cause) {
        if (requestGeneration !== generation.current || controller.signal.aborted) return
        setKeywordResult(null)
        setKeywordError(asApiError(cause))
      } finally {
        if (requestGeneration === generation.current && !controller.signal.aborted) {
          setKeywordLoading(false)
        }
      }
    })()
  }, [api, draft, taskRef])

  const executeSemantic = useCallback(() => {
    const q = draft.trim()
    if (!q || !semanticEnabled) return
    activeSemantic.current?.abort()
    const controller = new AbortController()
    activeSemantic.current = controller
    const requestGeneration = ++generation.current
    setSemanticResult(null)
    setSemanticLoading(true)
    setSemanticError(null)
    void (async () => {
      try {
        const found = await searchApi.searchSemantic(
          {
            q,
            task_ref: taskRef ?? undefined,
            include_global: true,
            limit: 20,
          },
          controller.signal,
        )
        if (requestGeneration !== generation.current || controller.signal.aborted) return
        setSemanticResult(found)
      } catch (cause) {
        if (requestGeneration !== generation.current || controller.signal.aborted) return
        setSemanticResult(null)
        setSemanticError(asApiError(cause))
      } finally {
        if (requestGeneration === generation.current && !controller.signal.aborted) {
          setSemanticLoading(false)
        }
      }
    })()
  }, [draft, searchApi, semanticEnabled, taskRef])

  const run = useCallback(() => {
    if (mode === 'semantic') executeSemantic()
    else executeKeyword()
  }, [executeKeyword, executeSemantic, mode])

  const setMode = useCallback(
    (next: MaterialSearchMode) => {
      if (next === 'semantic' && !semanticEnabled) return
      setModeState(next)
      if (next === 'keyword') {
        setKeywordError(null)
        setSemanticError(null)
      }
    },
    [semanticEnabled],
  )

  const fallbackToKeyword = useCallback(() => {
    setModeState('keyword')
    setKeywordError(null)
    setSemanticError(null)
    executeKeyword()
  }, [executeKeyword])

  return {
    draft,
    setDraft,
    result: mode === 'semantic' ? semanticResult : keywordResult,
    loading: mode === 'semantic' ? semanticLoading : keywordLoading,
    error: mode === 'semantic' ? semanticError : keywordError,
    run,
    mode,
    setMode,
    keywordResult,
    semanticResult,
    vectorStatus,
    statusLoading,
    statusError,
    fallbackToKeyword,
  }
}

function asApiError(cause: unknown): ApiError {
  if (cause instanceof ApiError) return cause
  return new ApiError({
    message: cause instanceof Error ? cause.message : 'Search failed',
    code: 'internal_error',
    httpStatus: null,
    retryable: false,
  })
}
