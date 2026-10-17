import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'

import {
  createAccountsApi,
  type AccountApi,
  type AccountRole,
  type AccountView,
} from '../../api/accounts'
import { ApiError } from '../../api/client'
import { useAuth } from '../../app/AuthProvider'
import { DetailHeader } from '../../components/DetailHeader'
import { EmptyState } from '../../components/EmptyState'
import { ErrorState } from '../../components/ErrorState'
import { StatusBadge } from '../../components/StatusBadge'
import { toApiError } from './apiError'

export interface AccountsPanelProps {
  /** Injected client for tests/embedding; defaults to the real endpoints. */
  api?: AccountApi
}

/**
 * Accounts (LG-062, administrator only; the backend enforces the role).
 *
 * Lists/enables/disables/creates accounts and changes roles or resets
 * passwords.  The last active administrator is protected server-side; a
 * rejected action surfaces the real actionable error.  Password values are
 * transient form state, cleared after submit and never persisted.
 */
export function AccountsPanel({ api: injected }: AccountsPanelProps) {
  const { identity, requireLogin } = useAuth()
  const api = useMemo(() => injected ?? createAccountsApi(), [injected])

  const [accounts, setAccounts] = useState<AccountView[] | null>(null)
  const [initialising, setInitialising] = useState(true)
  const [loadError, setLoadError] = useState<ReturnType<typeof toApiError> | null>(null)
  const [actionError, setActionError] = useState<ReturnType<typeof toApiError> | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const [creating, setCreating] = useState(false)
  const [busy, setBusy] = useState<string | null>(null)

  const [newUsername, setNewUsername] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [newRole, setNewRole] = useState<AccountRole>('member')
  const [resetTarget, setResetTarget] = useState<string | null>(null)
  const [resetPassword, setResetPassword] = useState('')

  useEffect(() => {
    let cancelled = false
    const controller = new AbortController()
    setLoadError(null)
    api
      .listAccounts(controller.signal)
      .then((list) => {
        if (!cancelled) setAccounts(list)
      })
      .catch((cause: unknown) => {
        if (cancelled || controller.signal.aborted) return
        setLoadError(toApiError(cause))
      })
      .finally(() => {
        if (!cancelled) setInitialising(false)
      })
    return () => {
      cancelled = true
      controller.abort()
    }
  }, [api, refreshKey])

  const reload = useCallback(() => setRefreshKey((key) => key + 1), [])

  const applyUpdated = useCallback((updated: AccountView) => {
    setAccounts((previous) =>
      previous
        ? previous.map((account) =>
            account.username === updated.username ? updated : account,
          )
        : [updated],
    )
  }, [])

  const handleFailure = useCallback(
    (cause: unknown) => {
      const error = toApiError(cause)
      setActionError(error)
      // A stale revision means someone else changed the account first; reload
      // so the next attempt uses the current revision.
      if (error instanceof ApiError && error.code === 'revision_conflict') {
        reload()
      }
    },
    [reload],
  )

  const handleCreate = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (busy || !newUsername.trim() || !newPassword) return
    setBusy('__create__')
    setActionError(null)
    try {
      const created = await api.createAccount({
        username: newUsername.trim(),
        password: newPassword,
        role: newRole,
      })
      setAccounts((previous) => (previous ? [...previous, created] : [created]))
      setNewUsername('')
      setNewPassword('')
      setNewRole('member')
      setCreating(false)
    } catch (cause) {
      handleFailure(cause)
    } finally {
      setBusy(null)
      setNewPassword('')
    }
  }

  const handleToggleEnabled = async (account: AccountView) => {
    setBusy(account.username)
    setActionError(null)
    try {
      const updated = await api.updateAccount(account.username, {
        enabled: !account.enabled,
        expected_revision: account.revision,
      })
      applyUpdated(updated)
    } catch (cause) {
      handleFailure(cause)
    } finally {
      setBusy(null)
    }
  }

  const handleRoleChange = async (account: AccountView, role: AccountRole) => {
    if (role === account.role) return
    setBusy(account.username)
    setActionError(null)
    try {
      const updated = await api.updateAccount(account.username, {
        role,
        expected_revision: account.revision,
      })
      applyUpdated(updated)
    } catch (cause) {
      handleFailure(cause)
    } finally {
      setBusy(null)
    }
  }

  const handleResetSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!resetTarget || !resetPassword) return
    const target = resetTarget
    setBusy(target)
    setActionError(null)
    try {
      const updated = await api.resetAccountPassword(target, {
        password: resetPassword,
      })
      applyUpdated(updated)
      setResetTarget(null)
      // A self reset invalidates this admin's own session too.
      if (target === identity.username) {
        requireLogin('Password reset. Sign in again with your new password.')
      }
    } catch (cause) {
      handleFailure(cause)
    } finally {
      setBusy(null)
      setResetPassword('')
    }
  }

  const isSelf = (account: AccountView) => account.username === identity.username

  return (
    <div className="lg-settings-section" aria-label="Accounts">
      <DetailHeader
        title="Accounts"
        badges={<StatusBadge kind="accent">Administrator</StatusBadge>}
        meta={[{ label: 'source', value: 'GET /api/v1/accounts' }]}
      />

      <section className="lg-panel" aria-label="Account list">
        <div className="lg-settings__list-head">
          <h3 className="lg-section-card__title">
            {accounts ? `${accounts.length} account${accounts.length === 1 ? '' : 's'}` : 'Accounts'}
          </h3>
          <button
            type="button"
            className="lg-button lg-button--primary"
            onClick={() => {
              setCreating((value) => !value)
              setActionError(null)
            }}
          >
            {creating ? 'Cancel' : 'New account'}
          </button>
        </div>

        {actionError ? (
          <ErrorState
            title="Account action failed"
            message={actionError.message}
            code={actionError.code}
            retryable={actionError.retryable}
            requestId={actionError.requestId}
          />
        ) : null}

        {creating ? (
          <form className="lg-form lg-form--inline" onSubmit={handleCreate} aria-label="Create account">
            <label className="lg-field">
              <span className="lg-field__label">Username</span>
              <input
                className="lg-input"
                type="text"
                name="username"
                autoComplete="off"
                value={newUsername}
                disabled={busy !== null}
                onChange={(event) => setNewUsername(event.target.value)}
              />
            </label>
            <label className="lg-field">
              <span className="lg-field__label">Temporary password</span>
              <input
                className="lg-input"
                type="password"
                name="password"
                autoComplete="new-password"
                value={newPassword}
                disabled={busy !== null}
                onChange={(event) => setNewPassword(event.target.value)}
              />
            </label>
            <label className="lg-field">
              <span className="lg-field__label">Role</span>
              <select
                className="lg-input"
                name="role"
                value={newRole}
                disabled={busy !== null}
                onChange={(event) => setNewRole(event.target.value as AccountRole)}
              >
                <option value="member">member</option>
                <option value="admin">admin</option>
              </select>
            </label>
            <div className="lg-form__actions">
              <button
                type="submit"
                className="lg-button lg-button--primary"
                disabled={busy !== null || !newUsername.trim() || !newPassword}
              >
                {busy === '__create__' ? 'Creating…' : 'Create account'}
              </button>
            </div>
          </form>
        ) : null}

        {loadError ? (
          <ErrorState
            title="Could not load accounts"
            message={loadError.message}
            code={loadError.code}
            retryable={loadError.retryable}
            requestId={loadError.requestId}
            onRetry={reload}
          />
        ) : initialising && accounts === null ? (
          <p className="lg-field__hint" role="status">
            Loading accounts…
          </p>
        ) : accounts && accounts.length === 0 ? (
          <EmptyState title="No accounts">
            <p>Create the first account to let someone sign in.</p>
          </EmptyState>
        ) : (
          <table className="lg-accounts-table">
            <thead>
              <tr>
                <th scope="col">Username</th>
                <th scope="col">Role</th>
                <th scope="col">Status</th>
                <th scope="col">Actions</th>
              </tr>
            </thead>
            <tbody>
              {(accounts ?? []).map((account) => {
                const self = isSelf(account)
                const rowBusy = busy === account.username
                return (
                  <tr key={account.username} className={self ? 'is-self' : undefined}>
                    <td>
                      <span className="lg-accounts-table__username">{account.username}</span>
                      {self ? <StatusBadge kind="neutral">you</StatusBadge> : null}
                    </td>
                    <td>
                      <label className="lg-field">
                        <span className="lg-visually-hidden">
                          Role for {account.username}
                        </span>
                        <select
                          className="lg-input"
                          aria-label={`Role for ${account.username}`}
                          value={account.role}
                          disabled={rowBusy || self}
                          onChange={(event) =>
                            void handleRoleChange(account, event.target.value as AccountRole)
                          }
                        >
                          <option value="member">member</option>
                          <option value="admin">admin</option>
                        </select>
                      </label>
                    </td>
                    <td>
                      <StatusBadge kind={account.enabled ? 'success' : 'warning'}>
                        {account.enabled ? 'enabled' : 'disabled'}
                      </StatusBadge>
                    </td>
                    <td className="lg-accounts-table__actions">
                      <button
                        type="button"
                        className="lg-button"
                        disabled={rowBusy || self}
                        title={self ? 'Manage your own account from My Account' : undefined}
                        onClick={() => void handleToggleEnabled(account)}
                      >
                        {account.enabled ? 'Disable' : 'Enable'}
                      </button>
                      <button
                        type="button"
                        className="lg-button"
                        disabled={rowBusy}
                        onClick={() => {
                          setResetTarget(account.username)
                          setResetPassword('')
                          setActionError(null)
                        }}
                      >
                        Reset password
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </section>

      {resetTarget ? (
        <section className="lg-panel" aria-label={`Reset password for ${resetTarget}`}>
          <h3 className="lg-section-card__title">Reset password for {resetTarget}</h3>
          <form className="lg-form lg-form--inline" onSubmit={handleResetSubmit}>
            <label className="lg-field">
              <span className="lg-field__label">New temporary password</span>
              <input
                className="lg-input"
                type="password"
                name="reset_password"
                autoComplete="new-password"
                value={resetPassword}
                disabled={busy !== null}
                onChange={(event) => setResetPassword(event.target.value)}
              />
            </label>
            <div className="lg-form__actions">
              <button
                type="submit"
                className="lg-button lg-button--primary"
                disabled={busy !== null || !resetPassword}
              >
                {busy === resetTarget ? 'Resetting…' : 'Set new password'}
              </button>
              <button
                type="button"
                className="lg-button"
                disabled={busy !== null}
                onClick={() => {
                  setResetTarget(null)
                  setResetPassword('')
                }}
              >
                Cancel
              </button>
            </div>
          </form>
        </section>
      ) : null}
    </div>
  )
}

export default AccountsPanel
