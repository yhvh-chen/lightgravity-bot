import { ApiError } from '../../api/client'

/** Normalize any thrown value into an {@link ApiError} for consistent display. */
export function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error
  return new ApiError({
    message: error instanceof Error ? error.message : 'Unexpected error',
    code: 'internal_error',
    httpStatus: null,
    retryable: false,
  })
}
