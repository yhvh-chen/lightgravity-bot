import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { ShellProvider, useShell } from '../src/app/ShellProvider'
import { TopBar } from '../src/app/TopBar'

const { markRead } = vi.hoisted(() => ({ markRead: vi.fn() }))
vi.mock('../src/app/AuthProvider', () => ({ useAuth: () => ({
  status: 'ready', isTeam: false, isAdmin: true,
  identity: { authenticated: true, username: null, role: 'admin' },
}) }))
vi.mock('../src/components/MaterialSearch', () => ({ MaterialSearch: () => null }))
vi.mock('../src/api/useBackendStatus', () => ({ useBackendStatus: () => ({ health: null }) }))
vi.mock('../src/app/useEventStream', () => ({ NOTIFICATION_REFRESH_TYPES: [], useEventStream: () => ({ status: 'open' }) }))
vi.mock('../src/app/useNotifications', () => ({ useNotifications: () => ({
  items: [{ notification_id: 'notif_1', title: 'Review delivery', at: 'now', task_ref: 'task_1', run_ref: 'run_1', read: false }],
  connected: true, markRead, refresh: vi.fn(),
}) }))
function Probe() {
  const { state, dispatch } = useShell()
  return <>
    <button onClick={() => dispatch({ type: 'setDraft', key: 'saved', value: 'Keep my draft' })}>Save draft</button>
    <output data-testid="shell">{JSON.stringify(state)}</output>
  </>
}
beforeEach(() => { localStorage.clear(); history.replaceState(null, '', '?view=team&task=task_old&run=run_old'); markRead.mockClear() })
afterEach(cleanup)
it('notification opens the exact Board Task/Run and preserves drafts', async () => {
  render(<ShellProvider><TopBar compact={false} mobile={false} railActive={false} chatActive={true}
    onToggleRail={() => {}} onToggleChat={() => {}} /><Probe /></ShellProvider>)
  fireEvent.click(screen.getByRole('button', { name: 'Save draft' }))
  fireEvent.click(screen.getByRole('button', { name: 'Notifications (1 unread)' }))
  fireEvent.click(screen.getByRole('button', { name: /Review delivery/ }))
  await waitFor(() => expect(new URLSearchParams(location.search).get('view')).toBe('board'))
  const state = JSON.parse(screen.getByTestId('shell').textContent!)
  expect(state.taskRef).toBe('task_1')
  expect(state.runRef).toBe('run_1')
  expect(state.drafts.saved).toBe('Keep my draft')
  expect(markRead).toHaveBeenCalledWith(['notif_1'])
  expect(screen.queryByRole('dialog', { name: 'Notifications' })).not.toBeInTheDocument()
})
