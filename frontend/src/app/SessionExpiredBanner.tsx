import './session-expired.css'

/**
 * Single-user session-expiry notice (LG-219).
 *
 * Single-user mode has no login gate: the runtime local access token is
 * injected into the page at startup, so after a backend restart the open page
 * keeps a stale token and protected writes fail with `401`.  The honest
 * recovery is a page refresh (which receives the new token), not a login
 * form.  This banner is non-blocking and leaves every draft untouched; it is
 * rendered by `AuthProvider`, so no shell/App wiring is required.
 */
export interface SessionExpiredBannerProps {
  onRefresh?: () => void
}

export function reloadPage(): void {
  if (typeof window !== 'undefined') window.location.reload()
}

export function SessionExpiredBanner({
  onRefresh = reloadPage,
}: SessionExpiredBannerProps) {
  return (
    <div className="lg-session-expired" role="alert">
      <p className="lg-session-expired__message">
        <strong>Session expired.</strong> Refresh the page to continue. Your
        unsent draft is kept.
      </p>
      <button
        type="button"
        className="lg-button lg-button--primary lg-session-expired__action"
        onClick={onRefresh}
      >
        Refresh page
      </button>
    </div>
  )
}
