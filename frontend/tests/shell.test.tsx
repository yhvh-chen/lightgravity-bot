import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { App } from '../src/App'
import { HEALTH_FIXTURE, backendFetch, setViewport } from './setup'

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
      'Board', 'Tasks', 'Team', 'Session Profiles', 'Hooks', 'MCP', 'Tools', 'Triggers', 'Skills', 'Settings',
    ])
    expect(within(nav).queryByRole('button', { name: 'Chat' })).toBeNull()
    expect(within(nav).getByRole('button', { name: 'Tasks' })).toHaveAttribute('aria-current', 'page')
    expect(screen.queryByLabelText('Scope')).toBeNull()
    expect(screen.queryByLabelText('Run')).toBeNull()
    expect(screen.queryByRole('complementary', { name: 'Context' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Toggle context panel' })).toBeNull()
    expect(screen.queryByRole('separator', { name: 'Resize context panel' })).toBeNull()
  })
  it('does not expose a standalone Connections entry but keeps the six other categories direct', async () => {
    window.history.replaceState(null, '', '/?view=resources&item=connections&task=task_real&run=run_real')
    await renderShell()
    const nav = screen.getByRole('navigation', { name: 'Primary navigation' })
    expect(within(nav).queryByRole('button', { name: 'Connections' })).toBeNull()
    expect(within(nav).getByRole('button', { name: 'Settings' })).toHaveAttribute('aria-current', 'page')
    await waitFor(() => expect(window.location.search).toContain('view=settings'))
    expect(window.location.search).toContain('task=task_real')
    expect(window.location.search).toContain('run=run_real')
    expect(window.location.search).not.toContain('item=connections')
  })
  it('transparently redirects a legacy Connection detail link to the same Settings target', async () => {
    window.history.replaceState(null, '', '/?view=resources&item=resources:connection:deepseek&task=task_real')
    await renderShell()
    expect(screen.getByRole('button', { name: 'Settings' })).toHaveAttribute('aria-current', 'page')
    await waitFor(() => expect(window.location.search).toContain('view=settings'))
    expect(window.location.search).toContain('item=settings%3Aconnection%3Adeepseek')
    expect(window.location.search).toContain('task=task_real')
    // Settings owns the same record; the legacy Resources page is not mounted.
    expect(screen.queryByRole('heading', { name: 'Resources' })).toBeNull()
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
  it('renders an editable material search input in the top bar and leaves navigation in the sidebar', async () => {
    await renderShell()
    const banner = screen.getByRole('banner')
    const input = within(banner).getByRole('searchbox', { name: 'Search' })
    expect(input.tagName).toBe('INPUT')
    expect(input).toHaveAttribute('type', 'search')
    expect(within(banner).queryByText(/Shared materials.*Text search/)).toBeNull()
    fireEvent.change(input, { target: { value: 'findme' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(within(banner).getByText(/Shared materials.*Text search/)).toBeInTheDocument()
    expect(await screen.findByText('Search failed')).toBeInTheDocument()
    expect(within(banner).queryByRole('button', { name: 'Tasks' })).toBeNull()
    fireEvent.keyDown(input, { key: 'Escape' })
    expect(screen.queryByLabelText('Search materials panel')).toBeNull()
    expect(input).toHaveFocus()
    expect(input).toHaveValue('findme')
  })
  it('passes live health capabilities into the top-bar search seam', async () => {
    const health = {
      ...HEALTH_FIXTURE,
      contract_version: '1.19.0',
      capabilities: {
        ...HEALTH_FIXTURE.capabilities,
        material_intake_v2: true,
        semantic_search: true,
        media_direct_embedding: true,
      },
    }
    vi.mocked(globalThis.fetch).mockImplementation((input: RequestInfo | URL) => {
      const url =
        typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
      if (url.endsWith('/api/v1/health')) {
        return Promise.resolve(
          new Response(JSON.stringify(health), {
            status: 200,
            headers: { 'content-type': 'application/json' },
          }),
        )
      }
      return backendFetch(input)
    })
    await renderShell()
    const input = within(screen.getByRole('banner')).getByRole('searchbox', {
      name: 'Search',
    })
    fireEvent.change(input, { target: { value: 'findme' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(await screen.findByRole('tab', { name: 'Semantic' })).toBeInTheDocument()
  })

  it('dismisses search on navigation so Tasks controls are not covered', async () => {
    await renderShell()
    const input = screen.getByRole('searchbox', { name: 'Search' })
    fireEvent.change(input, { target: { value: 'findme' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(screen.getByLabelText('Search materials panel')).toBeInTheDocument()
    expect(await screen.findByText('Search failed')).toBeInTheDocument()
    // A click without pointerdown also models keyboard activation.
    fireEvent.click(screen.getByRole('button', { name: 'Board' }))
    expect(screen.queryByLabelText('Search materials panel')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Tasks' }))
    expect(screen.getByRole('heading', { name: 'Tasks' })).toBeInTheDocument()
    expect(input).toHaveAttribute('aria-expanded', 'false')
  })
  it('keeps search open for inside pointers and dismisses outside pointers', async () => {
    await renderShell()
    const input = screen.getByRole('searchbox', { name: 'Search' })
    fireEvent.change(input, { target: { value: 'findme' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    fireEvent.pointerDown(input)
    expect(screen.getByLabelText('Search materials panel')).toBeInTheDocument()
    expect(await screen.findByText('Search failed')).toBeInTheDocument()
    fireEvent.pointerDown(screen.getByLabelText('Chat panel'))
    expect(screen.queryByLabelText('Search materials panel')).toBeNull()
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(await screen.findByText('Search failed')).toBeInTheDocument()
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(screen.queryByLabelText('Search materials panel')).toBeNull()
    expect(input).toHaveFocus()
    expect(input).toHaveValue('findme')
  })
  it('updates the active navigation entry', async () => {
    await renderShell()
    fireEvent.click(screen.getByRole('button', { name: 'Team' }))
    expect(screen.getByRole('button', { name: 'Team' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('button', { name: 'Tasks' })).not.toHaveAttribute('aria-current')
  })
})

describe('Task state and one conversation', () => {
  it('preserves deep-linked task/run and its draft while changing views', async () => {
    window.history.replaceState(null, '', '/?view=chat&task=task_real&run=run_real')
    await renderShell()
    fireEvent.change(screen.getByLabelText('Message for task_real'), { target: { value: 'draft text' } })
    expect(window.location.search).toContain('view=tasks')
    expect(window.location.search).not.toContain('view=chat')
    for (const view of ['Board', 'Tasks', 'Skills']) {
      fireEvent.click(screen.getByRole('button', { name: view }))
      expect(window.location.search).toContain('task=task_real')
      expect(window.location.search).toContain('run=run_real')
      expect(screen.getByLabelText('Message for task_real')).toHaveValue('draft text')
      expect(screen.getAllByLabelText(/^Message for /)).toHaveLength(1)
    }
  })
  it('can hide the optional right chat without creating another conversation', async () => {
    await renderShell()
    expect(screen.getByRole('button', { name: 'Toggle chat panel' })).toBeEnabled()
    expect(screen.getAllByLabelText('Chat panel')).toHaveLength(1)
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
    const panel = screen.getByLabelText('Chat panel')
    expect(await within(panel).findByText('Could not load messages')).toBeInTheDocument()
    expect(within(panel).getByText(/network_error/)).toBeInTheDocument()
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
