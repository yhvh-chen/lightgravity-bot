import { createRoot, type Root } from 'react-dom/client'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react/pure'
import { afterEach, expect, it } from 'vitest'
import type { AvailableAgent } from '../src/api/team'
import { AvailablePanel } from '../src/views/team/AvailablePanel'

function makeAgents(): AvailableAgent[] {
  return Array.from({ length: 60 }, (_, index): AvailableAgent => ({
    id: `role-${index}`, kind: 'agent', title: `Role ${index}`, enabled: true,
    revision: 0, connection_ref: null, skill_refs: [],
    role_category: index % 2 === 0 ? 'engineering' : 'marketing',
    capabilities: index % 2 === 0 ? ['implementation'] : ['writing'],
    recruitable: true, executable: false, availability: { state: 'missing_dependency', reasons: [] },
  }))
}

let root: Root | null = null
let container: HTMLDivElement | null = null
afterEach(() => { act(() => root?.unmount()); cleanup(); container?.remove(); root = null; container = null })
it('retains a Next click delivered immediately after the first role catalog commit', async () => {
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  const agents = makeAgents()
  await new Promise<void>((resolve) => {
    // Observe the async catalog commit before passive effects drain, the same
    // boundary at which findByText can resume a waiting caller.
    const observer = new MutationObserver(() => {
      const next = Array.from(container!.querySelectorAll('button')).find((button) => button.textContent === 'Next')
      if (!next || next.disabled) return
      observer.disconnect()
      next.click()
      resolve()
    })
    observer.observe(container!, { childList: true, subtree: true })
    root!.render(<AvailablePanel agents={agents} selectedId={null} onSelect={() => {}} />)
  })
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)) })
  expect(container.textContent).toContain('Page 2 of 3')
})


it.each(['Search roles', 'Category', 'Capability'])('resets to the first page when %s changes after paging', (label) => {
  const agents = makeAgents()
  render(<AvailablePanel agents={agents} selectedId={null} onSelect={() => {}} />)
  fireEvent.click(screen.getByRole('button', { name: 'Next' }))
  expect(screen.getByText('Page 2 of 3')).toBeInTheDocument()
  const value = label === 'Category' ? 'engineering' : label === 'Capability' ? 'implementation' : 'Role 1'
  fireEvent.change(screen.getByLabelText(label), { target: { value } })
  expect(screen.getByText(/Page 1 of/)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Previous' })).toBeDisabled()
})


it('preserves the page for a search edit with the same normalized query', () => {
  render(<AvailablePanel agents={makeAgents()} selectedId={null} onSelect={() => {}} />)
  fireEvent.change(screen.getByLabelText('Search roles'), { target: { value: 'Role' } })
  fireEvent.click(screen.getByRole('button', { name: 'Next' }))
  expect(screen.getByText('Page 2 of 3')).toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('Search roles'), { target: { value: ' role ' } })
  expect(screen.getByText('Page 2 of 3')).toBeInTheDocument()
})
