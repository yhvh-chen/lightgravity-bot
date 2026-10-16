import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { App } from '../src/App'
import { backendFetch, setViewport } from './setup'

async function renderShell() {
  const result = render(<App />)
  await screen.findByRole('heading', { name: 'LightGravity Bot' })
  return result
}
beforeEach(() => {
  window.sessionStorage.clear()
  window.history.replaceState(null, '', '/')
  setViewport(1440)
})
afterEach(() => {
  cleanup()
  vi.mocked(globalThis.fetch).mockReset()
  vi.mocked(globalThis.fetch).mockImplementation(backendFetch as typeof fetch)
})

describe('Single navigation shell', () => {
  it('provides resource categories directly and pins Settings after work entries', async () => {
    await renderShell()
    const nav = screen.getByRole('navigation', { name: 'Primary navigation' })
    expect(within(nav).getAllByRole('button').map((b) => b.getAttribute('aria-label'))).toEqual([
      'Chat', 'Board', 'Files', 'Team', 'Connections', 'Session Profiles', 'Hooks', 'MCP', 'Tools', 'Triggers', 'Skills', 'Settings',
    ])
    expect(within(nav).getByRole('button', { name: 'Chat' })).toHaveAttribute('aria-current', 'page')
    expect(screen.queryByLabelText('Scope')).toBeNull()
    expect(screen.queryByLabelText('Run')).toBeNull()
    expect(screen.queryByRole('complementary', { name: 'Context' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Toggle context panel' })).toBeNull()
    expect(screen.queryByRole('separator', { name: 'Resize context panel' })).toBeNull()
  })
  it('opens resources from navigation and restores the selected category on refresh', async () => {
    await renderShell()
    fireEvent.click(screen.getByRole('button', { name: 'Skills' }))
    expect(screen.getByRole('button', { name: 'Skills' })).toHaveAttribute('aria-current', 'page')
    expect(window.location.search).toContain('item=skills')
    expect(screen.queryByRole('region', { name: 'Resource categories' })).toBeNull()
    cleanup()
    await renderShell()
    expect(screen.getByRole('button', { name: 'Skills' })).toHaveAttribute('aria-current', 'page')
  })
  it('places material search in the top bar and leaves navigation in the sidebar', async () => {
    await renderShell()
    const banner = screen.getByRole('banner')
    fireEvent.click(within(banner).getByRole('button', { name: 'Search materials' }))
    expect(within(banner).getByLabelText('Search materials')).toBeInTheDocument()
    expect(within(banner).getByText(/Shared materials.*Text search/)).toBeInTheDocument()
    expect(within(banner).queryByRole('button', { name: 'Files' })).toBeNull()
    fireEvent.keyDown(screen.getByLabelText('Search materials'), { key: 'Escape' })
    expect(screen.queryByLabelText('Search materials panel')).toBeNull()
  })
  it('dismisses search on navigation so Files task controls are not covered', async () => {
    await renderShell()
    fireEvent.click(screen.getByRole('button', { name: 'Search materials' }))
    expect(screen.getByLabelText('Search materials panel')).toBeInTheDocument()
    // A click without pointerdown also models keyboard activation.
    fireEvent.click(screen.getByRole('button', { name: 'Files' }))
    expect(screen.queryByLabelText('Search materials panel')).toBeNull()
    expect(screen.getByRole('heading', { name: 'Tasks /' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Search materials' })).toHaveAttribute('aria-expanded', 'false')
  })
  it('keeps search open for inside pointers and dismisses outside pointers without stealing focus', async () => {
    await renderShell()
    const trigger = screen.getByRole('button', { name: 'Search materials' })
    fireEvent.click(trigger)
    fireEvent.pointerDown(screen.getByRole('textbox', { name: 'Search materials' }))
    expect(screen.getByLabelText('Search materials panel')).toBeInTheDocument()
    fireEvent.pointerDown(screen.getByRole('heading', { name: 'Chat' }))
    expect(screen.queryByLabelText('Search materials panel')).toBeNull()
    fireEvent.click(trigger)
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(screen.queryByLabelText('Search materials panel')).toBeNull()
    expect(trigger).toHaveFocus()
  })
  it('updates the active navigation entry', async () => {
    await renderShell()
    fireEvent.click(screen.getByRole('button', { name: 'Team' }))
    expect(screen.getByRole('button', { name: 'Team' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('button', { name: 'Chat' })).not.toHaveAttribute('aria-current')
  })
})

describe('Task state and one conversation', () => {
  it('preserves deep-linked task/run and its draft while changing views', async () => {
    window.history.replaceState(null, '', '/?view=chat&task=task_real&run=run_real')
    await renderShell()
    fireEvent.change(screen.getByLabelText('Message for task_real'), { target: { value: 'draft text' } })
    for (const view of ['Board', 'Files', 'Chat']) {
      fireEvent.click(screen.getByRole('button', { name: view }))
      expect(window.location.search).toContain('task=task_real')
      expect(window.location.search).toContain('run=run_real')
      expect(screen.getByLabelText('Message for task_real')).toHaveValue('draft text')
      expect(screen.getAllByLabelText(/^Message for /)).toHaveLength(1)
    }
  })
  it('can hide the optional right chat without creating another conversation', async () => {
    await renderShell()
    expect(screen.getByRole('button', { name: 'Toggle chat panel' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Board' }))
    expect(screen.getAllByLabelText('Chat panel')).toHaveLength(1)
    fireEvent.click(screen.getByRole('button', { name: 'Toggle chat panel' }))
    expect(screen.queryByLabelText('Chat panel')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Toggle chat panel' }))
    expect(screen.getAllByLabelText(/^Message for /)).toHaveLength(1)
  })
  it('keeps advanced attachment inputs collapsed until requested', async () => {
    await renderShell()
    expect(screen.getByLabelText('Attach file path')).not.toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'Add attachments and materials' }))
    expect(screen.getByLabelText('Attach file path')).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'Add attachments and materials' }))
    expect(screen.getByLabelText('Attach file path')).not.toBeVisible()
  })
})

describe('Recoverable failures', () => {
  it('reports a missing global endpoint without blaming a task scope', async () => {
    await renderShell()
    expect(await screen.findByText('Conversation service unavailable')).toBeInTheDocument()
    expect(screen.queryByText('Scope not found')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Board' }))
    expect(await screen.findByText('Could not load tasks')).toBeInTheDocument()
    expect(screen.queryByText('Mock delivery task')).toBeNull()
  })
  it('keeps a stale task draft recoverable when returning to the global conversation', async () => {
    window.history.replaceState(null, '', '/?task=task_deleted')
    await renderShell()
    fireEvent.change(screen.getByLabelText('Message for task_deleted'), { target: { value: 'keep task draft' } })
    fireEvent.click(await screen.findByRole('button', { name: 'Return to conversation' }))
    expect(screen.getByLabelText('Message for Global')).toHaveValue('')
    expect(JSON.parse(window.sessionStorage.getItem('lg011.shell-prefs')!).drafts['chat:task_deleted']).toBe('keep task draft')
  })
  it('preserves the unsent draft on a real request failure', async () => {
    await renderShell()
    const composer = screen.getByLabelText('Message for Global')
    fireEvent.change(composer, { target: { value: 'hello there' } })
    fireEvent.keyDown(composer, { key: 'Enter' })
    expect(await screen.findByText(/Send failed:/)).toBeInTheDocument()
    expect(composer).toHaveValue('hello there')
    expect(screen.queryAllByText('hello there', { selector: '.lg-message__bubble' })).toHaveLength(0)
  })
  it('shows network failures after an explicit single-user identity response', async () => {
    vi.mocked(globalThis.fetch).mockImplementation((async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
      if (url.endsWith('/api/v1/auth/me')) return { ok: true, status: 200, headers: { get: () => 'application/json' }, json: async () => ({ mode: 'single', authenticated: true, username: null, role: null }) } as unknown as Response
      throw new Error('Connection refused')
    }) as typeof fetch)
    await renderShell()
    expect(await screen.findByText('Could not load messages')).toBeInTheDocument()
    expect(screen.getByText(/network_error/)).toBeInTheDocument()
  })
})

describe('Narrow layout', () => {
  it('uses one keyboard-dismissable navigation drawer and has no context drawer', async () => {
    setViewport(390)
    await renderShell()
    expect(screen.queryByRole('navigation', { name: 'Primary navigation' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Toggle context panel' })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Toggle navigation' }))
    expect(screen.getByRole('dialog', { name: 'Navigation' })).toBeInTheDocument()
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(screen.queryByRole('dialog', { name: 'Navigation' })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Toggle navigation' }))
    fireEvent.click(screen.getByRole('button', { name: 'Board' }))
    expect(screen.queryByRole('dialog', { name: 'Navigation' })).toBeNull()
    expect(screen.getByRole('heading', { name: 'Board', level: 2 })).toBeInTheDocument()
  })
})
