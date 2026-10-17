import { useCallback, useEffect, useRef, useState } from 'react'

import { ApiError } from '../api/client'
import type { SearchResult, SourcesApi } from '../api/sources'

/** Shared state for one real lexical material search (LG-038 `/search`). */
export interface MaterialSearchController {
  draft: string
  setDraft: (value: string) => void
  result: SearchResult | null
  loading: boolean
  error: ApiError | null
  run: () => void
}

/**
 * Keeps the existing source-search semantics: the current Task scope plus
 * shared materials, the last response wins, and a Task/API change aborts and
 * clears stale results. No universal or invented search results are added.
 */
export function useMaterialSearch(
  api: SourcesApi,
  taskRef: string | null,
): MaterialSearchController {
  const [draft, setDraft] = useState('')
  const [result, setResult] = useState<SearchResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)

  const active = useRef<AbortController | null>(null)
  const generation = useRef(0)

  useEffect(() => {
    generation.current += 1
    active.current?.abort()
    setResult(null)
    setError(null)
    setLoading(false)
    return () => {
      generation.current += 1
      active.current?.abort()
    }
  }, [api, taskRef])

  const run = useCallback(() => {
    const q = draft.trim()
    if (!q) return
    active.current?.abort()
    const controller = new AbortController()
    active.current = controller
    const requestGeneration = ++generation.current
    setResult(null)
    setLoading(true)
    setError(null)
    void (async () => {
      try {
        const found = await api.search(
          {
            q,
            task_ref: taskRef ?? undefined,
            include_global: true,
            limit: 20,
            rebuild_if_missing: true,
          },
          controller.signal,
        )
        if (requestGeneration !== generation.current || controller.signal.aborted) return
        setResult(found)
      } catch (cause) {
        if (requestGeneration !== generation.current || controller.signal.aborted) return
        setResult(null)
        setError(asApiError(cause))
      } finally {
        if (requestGeneration === generation.current && !controller.signal.aborted) {
          setLoading(false)
        }
      }
    })()
  }, [api, draft, taskRef])

  return { draft, setDraft, result, loading, error, run }
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
