import { useState, type FormEvent } from 'react'

import { ApiError } from '../../api/client'
import { useAuth } from '../../app/AuthProvider'
import './auth.css'

/**
 * Team login gate (LG-050 §3/§7).
 *
 * Shown only when the server reports `mode: "team"` and no valid session.  The
 * form posts credentials to `/auth/login`; on success the server sets the
 * HttpOnly cookie and the provider reveals the workspace.  The password is
 * cleared on failure and never persisted in storage or the URL.  English UI,
 * matching the rest of the shell (design.md §1).
 */
export function LoginView() {
  const { login } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!username.trim() || !password || submitting) return
    setSubmitting(true)
    setError(null)
    try {
      await login(username.trim(), password)
    } catch (cause) {
      const message =
        cause instanceof ApiError && cause.httpStatus === 401
          ? 'Invalid username or password.'
          : cause instanceof Error
            ? cause.message
            : 'Sign-in failed. Please try again.'
      setError(message)
      setPassword('')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="lg-auth" role="main" aria-label="Sign in">
      <form className="lg-auth__card" onSubmit={handleSubmit}>
        <div className="lg-auth__brand">
          <span className="lg-auth__mark" aria-hidden="true">
            LG
          </span>
          <div>
            <h1 className="lg-auth__title">LightGravity Bot</h1>
            <p className="lg-auth__subtitle">Shared workspace · sign in to continue</p>
          </div>
        </div>

        {error ? (
          <p className="lg-notice lg-notice--error" role="alert">
            {error}
          </p>
        ) : null}

        <label className="lg-auth__field">
          <span className="lg-auth__label">Username</span>
          <input
            className="lg-input"
            type="text"
            name="username"
            autoComplete="username"
            autoFocus
            value={username}
            disabled={submitting}
            onChange={(event) => setUsername(event.target.value)}
          />
        </label>

        <label className="lg-auth__field">
          <span className="lg-auth__label">Password</span>
          <input
            className="lg-input"
            type="password"
            name="password"
            autoComplete="current-password"
            value={password}
            disabled={submitting}
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>

        <button
          type="submit"
          className="lg-button lg-button--primary lg-auth__submit"
          disabled={submitting || !username.trim() || !password}
        >
          {submitting ? 'Signing in…' : 'Sign in'}
        </button>
        <p className="lg-auth__hint">
          Accounts are managed by an administrator on the server.
        </p>
      </form>
    </div>
  )
}
