import { AppShell } from './app/AppShell'
import { AuthProvider, useAuth } from './app/AuthProvider'
import { ShellProvider } from './app/ShellProvider'
import { ErrorState } from './components/ErrorState'
import { LoginView } from './views/auth/LoginView'

/**
 * Application entry (LG-011; team login gate LG-050).
 *
 * The shell owns navigation, layout and UI state.  In team mode an
 * unauthenticated session is replaced by the login gate; single-user mode and
 * older backends keep the exact existing workspace.
 *
 * The `checking` and `error` states are explicit: while `/auth/me` is unknown
 * the shell is not mounted (so it can never optimistically bypass the gate),
 * and a network/server failure offers an honest retry instead of degrading to
 * single-user mode.
 */
function AuthGate() {
  const { status, identity, error, refresh } = useAuth()

  if (status === 'checking') {
    return (
      <div className="lg-auth" role="status" aria-label="Checking authentication">
        <p className="lg-auth__subtitle">Loading…</p>
      </div>
    )
  }

  if (status === 'error') {
    return (
      <div className="lg-auth" role="main" aria-label="Authentication unavailable">
        <ErrorState
          title="Cannot reach the server"
          message={error?.message ?? 'The authentication check failed.'}
          code={error?.code ?? undefined}
          retryable
          onRetry={() => {
            void refresh()
          }}
        />
      </div>
    )
  }

  if (identity.mode === 'team' && !identity.authenticated) {
    return <LoginView />
  }

  return (
    <ShellProvider>
      <AppShell />
    </ShellProvider>
  )
}

export function App() {
  return (
    <AuthProvider>
      <AuthGate />
    </AuthProvider>
  )
}
