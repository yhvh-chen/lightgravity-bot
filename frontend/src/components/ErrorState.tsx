export interface ErrorStateProps {
  title?: string
  message: string
  /** Frozen error code from docs/08 §4.2, when known. */
  code?: string
  retryable?: boolean
  requestId?: string | null
  onRetry?: () => void
}

/**
 * Field-level error state (design.md §6). Errors stay in place rather than
 * living only in a toast, and show the real code/request id when available.
 */
export function ErrorState({
  title = 'Something went wrong',
  message,
  code,
  retryable = false,
  requestId,
  onRetry,
}: ErrorStateProps) {
  return (
    <div className="lg-state lg-state--error" role="alert">
      <p className="lg-state__title">{title}</p>
      <p className="lg-state__body">
        {message}
        {code ? (
          <>
            {' '}
            <span className="lg-card__path">({code})</span>
          </>
        ) : null}
      </p>
      {requestId ? (
        <p className="lg-state__body">
          request_id: <span className="lg-card__path">{requestId}</span>
        </p>
      ) : null}
      {retryable && onRetry ? (
        <button type="button" className="lg-button" onClick={onRetry}>
          Retry
        </button>
      ) : null}
    </div>
  )
}
