import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { App } from '../src/App'
import { setViewport } from './setup'

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
  vi.mocked(globalThis.fetch).mockClear()
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
  it('preserves task/run scope, selected item and chat draft, with one chat', () => {
    renderShell()

    fireEvent.change(screen.getByLabelText('Scope'), {
      target: { value: 'mock-task-1' },
    })
    const composer = screen.getByLabelText('Message for mock-task-1')
    fireEvent.change(composer, { target: { value: 'draft text' } })
    expect(composer).toHaveValue('draft text')

    fireEvent.click(screen.getByRole('button', { name: 'Board' }))
    expect(screen.getByLabelText('Scope')).toHaveValue('mock-task-1')

    const contextItem = screen.getByRole('button', {
      name: /Add login to the example site/,
    })
    fireEvent.click(contextItem)
    expect(contextItem).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByLabelText('Message for mock-task-1')).toHaveValue('draft text')

    fireEvent.click(screen.getByRole('button', { name: 'Files' }))
    expect(screen.getByLabelText('Scope')).toHaveValue('mock-task-1')

    fireEvent.click(screen.getByRole('button', { name: 'Board' }))
    expect(
      screen.getByRole('button', { name: /Add login to the example site/ }),
    ).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getAllByRole('textbox')).toHaveLength(1)
  })

  it('renders a single Chat surface and disables the rail toggle on the Chat view', () => {
    renderShell()
    expect(screen.getAllByRole('textbox')).toHaveLength(1)
    expect(screen.getAllByLabelText('Chat workspace')).toHaveLength(1)
    expect(screen.getByRole('button', { name: 'Toggle chat panel' })).toBeDisabled()

    fireEvent.click(screen.getByRole('button', { name: 'Board' }))
    expect(screen.getAllByLabelText('Chat panel')).toHaveLength(1)
    expect(screen.getAllByRole('textbox')).toHaveLength(1)
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

describe('LG-011 shell: empty, error and mock states', () => {
  it('shows explicit empty states when the layout mock is off', async () => {
    renderShell()
    fireEvent.click(screen.getByRole('button', { name: 'Toggle layout mock data' }))
    fireEvent.click(screen.getByRole('button', { name: 'Board' }))
    expect(
      screen.getByText('No tasks yet — create one from Chat.'),
    ).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Chat' }))
    expect(await screen.findByText('No messages yet')).toBeInTheDocument()
  })

  it('labels the layout mock and never fakes a sent message', async () => {
    renderShell()
    expect(
      screen.getAllByText('MOCK LAYOUT DATA — not from backend').length,
    ).toBeGreaterThan(0)

    const composer = screen.getByLabelText('Message for Global')
    fireEvent.change(composer, { target: { value: 'hello there' } })
    fireEvent.keyDown(composer, { key: 'Enter' })
    expect(await screen.findByText(/Not sent: message delivery is not implemented/)).toBeInTheDocument()
    // Draft is kept and no message element was created from it.
    expect(composer).toHaveValue('hello there')
    expect(
      screen.queryAllByText('hello there', { selector: '.lg-message__bubble' }),
    ).toHaveLength(0)
  })

  it('renders a real not-connected state when the backend is unreachable', async () => {
    vi.mocked(globalThis.fetch).mockRejectedValueOnce(new Error('Connection refused'))
    renderShell()
    expect(await screen.findByText('Backend not connected')).toBeInTheDocument()
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
