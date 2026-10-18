import { cleanup, render, screen, within } from '@testing-library/react'
import { afterEach, expect, it } from 'vitest'
import type { AcceptanceSnapshot } from '../src/api/tasks'
import type { TaskDetail } from '../src/api/types'
import { MachineChecksSection } from '../src/views/board/MachineChecksSection'

const task = { task_id: 'task_1', requirements_revision: 2,
  run: { id: 'run_1', plan_hash: 'plan_1', state: 'awaiting_acceptance' },
} as unknown as TaskDetail
function snapshot(overrides: Record<string, unknown> = {}): AcceptanceSnapshot {
  return { task_id: 'task_1', requirements_revision: 2, phase: 'awaiting_acceptance', status: 'in-progress',
    revision: 3, deliverable_revision: 1, acceptance: {}, candidate: null, checks: {
    status: 'passed', satisfied: true, required: ['evidence-present', 'artifacts-in-workspace'],
    results: [{ check_id: 'evidence-present', status: 'passed', detail: 'Evidence exists.' },
      { check_id: 'artifacts-in-workspace', status: 'passed', detail: 'Artifact paths are contained.' }],
    checked_at: '2026-10-18T00:00:00Z', binding: { run_id: 'run_1', requirements_revision: 2, plan_hash: 'plan_1' },
    ...overrides,
  } } as AcceptanceSnapshot
}
afterEach(cleanup)
it('shows recorded real check results and current candidate binding before claiming pass', () => {
  render(<MachineChecksSection task={task} snapshot={snapshot()} />)
  const section = screen.getByRole('region', { name: 'Machine checks' })
  expect(within(section).getByText('Passed')).toHaveClass('lg-status-badge--success')
  expect(within(section).getByText('Evidence exists.')).toBeInTheDocument()
  expect(within(section).getByText(/Recorded Run: run_1/)).toHaveTextContent('requirements 2 · plan plan_1')
})
it.each(['stale', 'not_run', 'not_configured', 'failed'])('does not claim pass for %s', (status) => {
  render(<MachineChecksSection task={task} snapshot={snapshot({ status, satisfied: false })} />)
  expect(screen.queryByText('Passed')).not.toBeInTheDocument()
  expect(document.querySelector('.lg-status-badge--success')).toBeNull()
})
it('does not treat legacy vacuous satisfied or empty results as real check evidence', () => {
  render(<MachineChecksSection task={task} snapshot={snapshot({ status: undefined, required: [], results: [] })} />)
  expect(screen.getByText('Not run')).toBeInTheDocument()
  expect(screen.getByText('No individual check results recorded.')).toBeInTheDocument()
  expect(screen.queryByText('Passed')).not.toBeInTheDocument()
})
it.each([{ run_id: 'run_old', requirements_revision: 2, plan_hash: 'plan_1' },
  { run_id: 'run_1', requirements_revision: 1, plan_hash: 'plan_1' },
  { run_id: 'run_1', requirements_revision: 2, plan_hash: 'plan_old' }])('shows stale when the recorded binding differs', (binding) => {
  render(<MachineChecksSection task={task} snapshot={snapshot({ binding })} />)
  expect(screen.getByText('Stale')).toBeInTheDocument()
  expect(screen.queryByText('Passed')).not.toBeInTheDocument()
})
it('shows missing or skipped required results without painting a successful gate', () => {
  render(<MachineChecksSection task={task} snapshot={snapshot({
    results: [{ check_id: 'evidence-present', status: 'skipped', detail: 'Not executed.' }],
  })} />)
  expect(screen.getByText('Stale')).toBeInTheDocument()
  expect(screen.getByText('skipped')).toBeInTheDocument()
  expect(screen.getByText('Not executed.')).toBeInTheDocument()
  expect(document.querySelector('.lg-status-badge--success')).toBeNull()
})
