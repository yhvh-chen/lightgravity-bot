import { useMemo, useState, type FormEvent } from 'react'

import { createAccountsApi, type AccountApi } from '../../api/accounts'
import { useAuth } from '../../app/AuthProvider'
import { DetailHeader } from '../../components/DetailHeader'
import { ErrorState } from '../../components/ErrorState'
import { StatusBadge } from '../../components/StatusBadge'
import { toApiError } from './apiError'

export interface MyAccountPanelProps {
  /** Injected client for tests/embedding; defaults to the real endpoints. */
  api?: AccountApi
}

/**
 * My Account (LG-062, all team users incl. members).
 *
 * The only account action a member needs; it never loads Models/Connections or
 * the admin account list.  Identity is the server session, so a member can only
 * change their own password.  On success every session for the account is
 * invalidated (the backend bumps the credential revision) and the UI returns
 * to the login gate with a clear notice.
 */
export function MyAccountPanel({ api: injected }: MyAccountPanelProps) {
  const { identity, requireLogin } = useAuth()
  const api = useMemo(() => injected ?? createAccountsApi(), [injected])
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<ReturnType<typeof toApiError> | null>(null)
  const [changed, setChanged] = useState(false)

  const clearPasswords = () => {
    setCurrentPassword('')
    setNewPassword('')
    setConfirmation('')
  }

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (submitting) return
    setError(null)
    if (!currentPassword || !newPassword) {
      setError(
        toApiError(new Error('Enter your current and new password.')),
      )
      return
    }
    if (newPassword !== confirmation) {
      setError(
        toApiError(new Error('New password and confirmation do not match.')),
      )
      clearPasswords()
      return
    }
    setSubmitting(true)
    try {
      await api.changeOwnPassword({
        current_password: currentPassword,
        new_password: newPassword,
        confirmation,
      })
      clearPasswords()
      setChanged(true)
      requireLogin('Password changed. Sign in again with your new password.')
    } catch (cause) {
      clearPasswords()
      setError(toApiError(cause))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="lg-settings-section" aria-label="My Account">
      <DetailHeader
        title="My Account"
        badges={<StatusBadge kind="accent">Personal</StatusBadge>}
        meta={[
          { label: 'username', value: identity.username ?? 'unknown' },
          { label: 'role', value: identity.role ?? 'unknown' },
        ]}
      />

      <section className="lg-panel" aria-label="Change password">
        <h3 className="lg-section-card__title">Change password</h3>
        <p className="lg-field__hint">
          Use your current password once, then choose a new one. Existing
          sessions for your account are signed out immediately.
        </p>

        {error ? (
          <ErrorState
            title="Could not change password"
            message={error.message}
            code={error.code}
            retryable={false}
          />
        ) : null}
        {changed ? (
          <p className="lg-notice" role="status">
            Password changed. Sign in again with your new password.
          </p>
        ) : null}

        <form className="lg-form" onSubmit={handleSubmit}>
          <label className="lg-field">
            <span className="lg-field__label">Current password</span>
            <input
              className="lg-input"
              type="password"
              name="current_password"
              autoComplete="current-password"
              value={currentPassword}
              disabled={submitting}
              onChange={(event) => setCurrentPassword(event.target.value)}
            />
          </label>
          <label className="lg-field">
            <span className="lg-field__label">New password</span>
            <input
              className="lg-input"
              type="password"
              name="new_password"
              autoComplete="new-password"
              value={newPassword}
              disabled={submitting}
              onChange={(event) => setNewPassword(event.target.value)}
            />
          </label>
          <label className="lg-field">
            <span className="lg-field__label">Confirm new password</span>
            <input
              className="lg-input"
              type="password"
              name="confirmation"
              autoComplete="new-password"
              value={confirmation}
              disabled={submitting}
              onChange={(event) => setConfirmation(event.target.value)}
            />
          </label>
          <div className="lg-form__actions">
            <button
              type="submit"
              className="lg-button lg-button--primary"
              disabled={submitting || !currentPassword || !newPassword}
            >
              {submitting ? 'Changing…' : 'Change password'}
            </button>
          </div>
        </form>
      </section>
    </div>
  )
}

export default MyAccountPanel
