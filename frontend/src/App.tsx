import { AppShell } from './app/AppShell'
import { AuthProvider, useAuth } from './app/AuthProvider'
import { ShellProvider } from './app/ShellProvider'
import { LoginView } from './views/auth/LoginView'

/**
 * Application entry (LG-011; team login gate LG-050).
 *
 * The shell owns navigation, layout and UI state.  In team mode an
 * unauthenticated session is replaced by the login gate; single-user mode and
 * older backends keep the exact existing workspace.
 */
function AuthGate() {
  const { status, identity } = useAuth()
  if (status === 'ready' && identity.mode === 'team' && !identity.authenticated) {
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
