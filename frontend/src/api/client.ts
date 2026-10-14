import {
  API_PREFIX,
  type ErrorEnvelope,
  type HealthResponse,
  type VersionResponse,
} from './types'

/**
 * Thin fetch boundary for the frozen `/api/v1` contract (docs/08 §4).
 *
 * The shell only needs the meta endpoints today; business endpoints that are
 * not implemented yet return a real error/404, which the UI renders as an
 * empty/not-connected state rather than fabricating data.
 */
export class ApiError extends Error {
  readonly code: string
  readonly httpStatus: number | null
  readonly retryable: boolean
  readonly details: Record<string, unknown>
  readonly requestId: string | null

  constructor(options: {
    message: string
    code: string
    httpStatus: number | null
    retryable: boolean
    details?: Record<string, unknown>
    requestId?: string | null
  }) {
    super(options.message)
    this.name = 'ApiError'
    this.code = options.code
    this.httpStatus = options.httpStatus
    this.retryable = options.retryable
    this.details = options.details ?? {}
    this.requestId = options.requestId ?? null
  }
}

function isErrorEnvelope(value: unknown): value is ErrorEnvelope {
  if (!value || typeof value !== 'object') return false
  const candidate = value as { error?: unknown }
  return Boolean(candidate.error && typeof candidate.error === 'object')
}

export async function apiRequest<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_PREFIX}${path}`, {
      headers: { Accept: 'application/json' },
      ...init,
    })
  } catch (cause) {
    throw new ApiError({
      message:
        cause instanceof Error ? cause.message : 'Network request failed',
      code: 'network_error',
      httpStatus: null,
      retryable: true,
    })
  }

  const contentType = response.headers.get('content-type') ?? ''
  const payload: unknown = contentType.includes('application/json')
    ? await response.json().catch(() => null)
    : null

  if (!response.ok) {
    if (isErrorEnvelope(payload)) {
      const body = payload.error
      throw new ApiError({
        message: body.message,
        code: body.code,
        httpStatus: response.status,
        retryable: body.retryable,
        details: body.details,
        requestId: body.request_id,
      })
    }
    throw new ApiError({
      message: `Request failed with status ${response.status}`,
      code: 'internal_error',
      httpStatus: response.status,
      retryable: response.status >= 500,
    })
  }

  return payload as T
}

export function fetchHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return apiRequest<HealthResponse>('/health', { signal })
}

export function fetchVersion(signal?: AbortSignal): Promise<VersionResponse> {
  return apiRequest<VersionResponse>('/version', { signal })
}
