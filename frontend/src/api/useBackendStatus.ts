import { useCallback, useEffect, useState } from 'react'

import { ApiError, fetchHealth } from './client'
import { assertBackendCompatible } from './backendCompatibility'
import type { HealthResponse } from './types'

export type BackendState = 'loading' | 'connected' | 'unavailable'

export interface BackendStatus {
  state: BackendState
  health: HealthResponse | null
  error: ApiError | null
  refresh: () => void
}

/**
 * Real connectivity probe against `GET /api/v1/health` (LG-002 frozen
 * endpoint). The shell uses it to distinguish "connected" from
 * "not connected" instead of pretending the backend is up (design.md §6).
 */
export function useBackendStatus(): BackendStatus {
  const [state, setState] = useState<BackendState>('loading')
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [nonce, setNonce] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    let active = true
    setState('loading')
    fetchHealth(controller.signal)
      .then((result) => {
        if (!active) return
        assertBackendCompatible(result)
        setHealth(result)
        setError(null)
        setState('connected')
      })
      .catch((cause: unknown) => {
        if (!active || controller.signal.aborted) return
        setHealth(null)
        setError(
          cause instanceof ApiError
            ? cause
            : new ApiError({
                message: cause instanceof Error ? cause.message : 'Unknown error',
                code: 'internal_error',
                httpStatus: null,
                retryable: true,
              }),
        )
        setState('unavailable')
      })
    return () => {
      active = false
      controller.abort()
    }
  }, [nonce])

  const refresh = useCallback(() => setNonce((value) => value + 1), [])
  return { state, health, error, refresh }
}
