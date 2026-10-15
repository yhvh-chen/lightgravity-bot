import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { App } from '../src/App'
import { backendFetch, setViewport } from './setup'

function renderShell() {
  return render(<App />)
}

beforeEach(() => {
  window.sessionStorage.clear()
  window.history.replaceState(null, '', '/')
  setViewport(1440)
})

afterEach(() => {
  cleanup()
  vi.mocked(globalThis.fetch).mockReset()
  vi.mocked(globalThis.fetch).mockImplementation(
    backendFetch as unknown as (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>,
  )
})

describe('LG-011 shell: navigation', () => {
  it('renders the five work entries then Settings, with Chat active by default', () => {
    renderShell()
    const nav = screen.getByRole('navigation', { name: 'Primary navigation' })
    const labels = within(nav)
      .getAllByRole('button')
      .map((button) => button.getAttribute('aria-label'))
    expect(labels).toEqual([
      'Chat',
      'Board',
      'Files',
      'Team',
      'Resources',
      'Settings',
    ])
    expect(within(nav).getByRole('button', { name: 'Chat' })).toHaveAttribute(
      'aria-current',
      'page',
    )
    // Settings is the last entry (bottom), not a work entry.
    expect(labels[labels.length - 1]).toBe('Settings')
  })

  it('keeps primary navigation out of the top bar', () => {
    renderShell()
    const banner = screen.getByRole('banner')
    for (const label of ['Chat', 'Board', 'Files', 'Team', 'Resources']) {
      expect(within(banner).queryByRole('button', { name: label })).toBeNull()
    }
    // Exactly one Chat control exists and it lives in the rail.
    expect(screen.getAllByRole('button', { name: 'Chat' })).toHaveLength(1)
  })

  it('moves aria-current with the active view', () => {
    renderShell()
    fireEvent.click(screen.getByRole('button', { name: 'Team' }))
    expect(screen.getByRole('button', { name: 'Team' })).toHaveAttribute(
      'aria-current',
      'page',
    )
    expect(screen.getByRole('button', { name: 'Chat' })).not.toHaveAttribute(
      'aria-current',
    )
  })
})

describe('LG-011 shell: scope, selection and drafts survive view switches', () => {
  it('preserves task/run scope and chat draft, with one conversation session', () => {
    renderShell()

    fireEvent.change(screen.getByLabelText('Scope'), {
      target: { value: 'mock-task-1' },
    })
    const composer = screen.getByLabelText('Message for mock-task-1')
    fireEvent.change(composer, { target: { value: 'draft text' } })
    expect(composer).toHaveValue('draft text')

    fireEvent.click(screen.getByRole('button', { name: 'Board' }))
    expect(screen.getByLabelText('Scope')).toHaveValue('mock-task-1')
    // The rail and the Chat panel share one active draft for the same scope.
    expect(screen.getByLabelText('Message for mock-task-1')).toHaveValue('draft text')

    fireEvent.click(screen.getByRole('button', { name: 'Files' }))
    expect(screen.getByLabelText('Scope')).toHaveValue('mock-task-1')

    fireEvent.click(screen.getByRole('button', { name: 'Board' }))
    // Exactly one Chat conversation surface (one composer) across the shell.
    expect(screen.getAllByLabelText(/^Message for /)).toHaveLength(1)
  })

  it('renders a single Chat surface and disables the rail toggle on the Chat view', () => {
    renderShell()
    expect(screen.getAllByLabelText(/^Message for /)).toHaveLength(1)
    expect(screen.getAllByLabelText('Chat workspace')).toHaveLength(1)
    expect(screen.getByRole('button', { name: 'Toggle chat panel' })).toBeDisabled()

    fireEvent.click(screen.getByRole('button', { name: 'Board' }))
    expect(screen.getAllByLabelText('Chat panel')).toHaveLength(1)
    expect(screen.getAllByLabelText(/^Message for /)).toHaveLength(1)
  })
})

describe('LG-011 shell: panel controls', () => {
  it('collapses and restores the context and chat panels', () => {
    renderShell()
    const contextToggle = screen.getByRole('button', { name: 'Toggle context panel' })
    expect(contextToggle).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('complementary', { name: 'Context' })).toBeInTheDocument()

    fireEvent.click(contextToggle)
    expect(contextToggle).toHaveAttribute('aria-pressed', 'false')
    expect(screen.queryByRole('complementary', { name: 'Context' })).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: 'Board' }))
    const chatToggle = screen.getByRole('button', { name: 'Toggle chat panel' })
    expect(chatToggle).toHaveAttribute('aria-pressed', 'true')
    fireEvent.click(chatToggle)
    expect(screen.queryByLabelText('Chat panel')).toBeNull()
    expect(screen.queryByRole('textbox')).toBeNull()
  })

  it('resizes the context panel from the keyboard', () => {
    renderShell()
    const separator = screen.getByRole('separator', {
      name: 'Resize context panel',
    })
    expect(separator).toHaveAttribute('aria-valuenow', '240')
    fireEvent.keyDown(separator, { key: 'ArrowRight' })
    expect(separator).toHaveAttribute('aria-valuenow', '256')
    fireEvent.keyDown(separator, { key: 'Home' })
    expect(separator).toHaveAttribute('aria-valuenow', '200')
  })
})

describe('LG-011 shell: empty, error and real-data states', () => {
  it('shows explicit empty states instead of inventing tasks or messages', async () => {
    renderShell()
    // The rail is backend-driven now; mocked fetch has no /tasks, so the rail
    // must say so rather than render layout-mock tasks.
    fireEvent.click(screen.getByRole('button', { name: 'Board' }))
    // The backend has no /tasks under test, so the board reports the real error
    // rather than rendering layout-mock tasks.
    expect(await screen.findByText('Could not load tasks')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Chat' }))
    expect(await screen.findByText('Scope not found')).toBeInTheDocument()
  })

  it('never fabricates a sent message and keeps the draft on a real failure', async () => {
    renderShell()
    const composer = screen.getByLabelText('Message for Global')
    fireEvent.change(composer, { target: { value: 'hello there' } })
    fireEvent.keyDown(composer, { key: 'Enter' })
    // The mocked backend returns 404 for the global conversation, so the send
    // fails honestly and the draft is preserved.
    expect(await screen.findByText(/Send failed:/)).toBeInTheDocument()
    expect(composer).toHaveValue('hello there')
    expect(
      screen.queryAllByText('hello there', { selector: '.lg-message__bubble' }),
    ).toHaveLength(0)
  })

  it('renders a real not-connected state when the backend is unreachable', async () => {
    vi.mocked(globalThis.fetch).mockRejectedValue(new Error('Connection refused'))
    renderShell()
    expect(await screen.findByText(/Could not load messages|Scope not found/)).toBeInTheDocument()
    expect(screen.getByText(/network_error/)).toBeInTheDocument()
  })
})

describe('LG-011 shell: deep links', () => {
  it('restores view and task scope from the URL', () => {
    window.history.replaceState(null, '', '/?view=board&task=mock-task-1')
    renderShell()
    expect(screen.getByRole('button', { name: 'Board' })).toHaveAttribute(
      'aria-current',
      'page',
    )
    expect(screen.getByLabelText('Scope')).toHaveValue('mock-task-1')
  })
})

describe('LG-011 shell: compact layout', () => {
  it('turns panels into keyboard-dismissable drawers on narrow screens', () => {
    setViewport(390)
    renderShell()

    expect(screen.queryByRole('navigation', { name: 'Primary navigation' })).toBeNull()

    const contextToggle = screen.getByRole('button', { name: 'Toggle context panel' })
    fireEvent.click(contextToggle)
    expect(screen.getByRole('dialog', { name: 'Context panel' })).toBeInTheDocument()
    expect(contextToggle).toHaveAttribute('aria-pressed', 'true')

    fireEvent.keyDown(window, { key: 'Escape' })
    expect(screen.queryByRole('dialog', { name: 'Context panel' })).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: 'Toggle navigation' }))
    expect(screen.getByRole('dialog', { name: 'Navigation' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Board' }))
    expect(screen.queryByRole('dialog', { name: 'Navigation' })).toBeNull()
    expect(screen.getByRole('heading', { name: 'Board', level: 2 })).toBeInTheDocument()
  })
})
