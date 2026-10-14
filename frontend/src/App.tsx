import { AppShell } from './app/AppShell'
import { ShellProvider } from './app/ShellProvider'

/**
 * Application entry (LG-011).
 *
 * The shell owns navigation, layout and UI state; each business view is
 * mounted by `src/views/registry.tsx` and implemented by its own task.
 */
export function App() {
  return (
    <ShellProvider>
      <AppShell />
    </ShellProvider>
  )
}
