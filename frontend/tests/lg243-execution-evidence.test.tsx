import { cleanup, render, screen, within } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import type { AcceptanceSnapshot } from '../src/api/tasks'
import type { TaskDetail, TaskExecutionEvidence } from '../src/api/types'
import { ExecutionEvidenceSection } from '../src/views/board/ExecutionEvidenceSection'

function evidence(): TaskExecutionEvidence {
  return { task_id: 'task_1', schema: 'lightgravity.execution-evidence/v1',
    run: { id: 'run_1', state: 'awaiting_acceptance', candidate_ref: 'run_1', requirements_revision: 2, plan_hash: 'plan_1' },
    worker: { role: 'worker', connection_id: 'worker_old', name: 'Original worker', provider: 'openai-compat', model: 'same-model',
      status: 'recorded', source: 'run_default_pin', stage: 'planned', evidence_kind: 'frozen_run_connection', captured_at: 'worker-time', reason: null },
    reviewer: { role: 'reviewer', connection_id: 'reviewer_old', name: 'Original reviewer', provider: 'openai-compat', model: 'same-model',
      status: 'recorded', source: 'resolved_reviewer_support', stage: 'review_execution', evidence_kind: 'resolved_reviewer_support', captured_at: 'review-time', reason: null },
    review: { outcome: 'passed', reviewer_kind: 'model', candidate_ref: 'run_1',
      candidate_binding: { run_id: 'run_1', candidate_ref: 'run_1', requirements_revision: 2, plan_hash: 'plan_1' },
      findings: [], unsubstantiated: [], model_calls: 1, usage: { unknown: ['usage'] }, reviewed_at: 'review-time', reason: '' },
    connections_distinct: true, missing: [],
  }
}
function task(execution: TaskExecutionEvidence | null = evidence()): TaskDetail {
  return { task_id: 'task_1', requirements_revision: 2, execution, acceptance: { candidate_ref: 'run_1' },
    run: { id: 'run_1', state: 'awaiting_acceptance', plan_hash: 'plan_1' } } as unknown as TaskDetail
}
const snapshot = { task_id: 'task_1', requirements_revision: 2, acceptance: { candidate_ref: 'run_1' },
  candidate: { run_id: 'run_1', plan_hash: 'plan_1' } } as unknown as AcceptanceSnapshot
function verdict() { return screen.getByRole('region', { name: 'Reviewer verdict' }) }
afterEach(cleanup)
it('separates frozen worker configuration from an actual returned reviewer snapshot and current verdict', () => {
  const fetch = vi.spyOn(globalThis, 'fetch')
  render(<ExecutionEvidenceSection task={task()} snapshot={snapshot} />)
  expect(screen.getByRole('region', { name: 'Pinned worker connection' })).toHaveTextContent('worker_old')
  expect(screen.getByRole('region', { name: 'Reviewer connection' })).toHaveTextContent('reviewer_old')
  expect(screen.getByText(/Frozen configuration for this Run/)).toBeInTheDocument()
  expect(screen.getByText('Connection IDs differ.')).toBeInTheDocument()
  expect(within(verdict()).getByText('Passed')).toHaveClass('lg-status-badge--success')
  expect(within(verdict()).getByText(/Reviewed candidate: run_1/)).toHaveTextContent('requirements 2 · plan: plan_1')
  expect(within(verdict()).getByText('Usage: Unknown')).toBeInTheDocument()
  // The two real connection IDs can use the same model; neither is replaced by current defaults.
  expect(screen.getAllByText(/model: same-model/)).toHaveLength(2)
  expect(fetch).not.toHaveBeenCalled()
  fetch.mockRestore()
})
it('keeps missing historical evidence unknown without inventing a reviewer or default connection', () => {
  const history = evidence()
  history.reviewer = { ...history.reviewer, connection_id: null, name: null, model: null, provider: null,
    status: 'unknown', source: 'missing', evidence_kind: 'missing', captured_at: null }
  history.review = null
  history.connections_distinct = null
  render(<ExecutionEvidenceSection task={task(history)} snapshot={snapshot} />)
  expect(within(verdict()).getByText('Unknown')).toBeInTheDocument()
  expect(within(verdict()).getByText('No review result recorded for this Run.')).toBeInTheDocument()
  expect(screen.queryByText('Passed')).not.toBeInTheDocument()
  expect(screen.getByText('Connection comparison unknown.')).toBeInTheDocument()
})
it('does not present worker planning alone as completed model execution or review', () => {
  const history = evidence()
  history.run!.state = 'planning'
  history.review = null
  history.reviewer.status = 'unknown'
  render(<ExecutionEvidenceSection task={task(history)} snapshot={null} />)
  expect(screen.getByText(/Frozen configuration for this Run/)).toBeInTheDocument()
  expect(screen.queryByText('Passed')).not.toBeInTheDocument()
})
it('shows an unavailable actual attempt and its reason honestly', () => {
  const history = evidence()
  history.review!.outcome = 'unavailable'
  history.review!.reason = 'Reviewer connection was not available.'
  history.reviewer.status = 'unavailable'
  render(<ExecutionEvidenceSection task={task(history)} snapshot={snapshot} />)
  expect(within(verdict()).getByText('Unavailable')).toBeInTheDocument()
  expect(within(verdict()).getByText('Reviewer connection was not available.')).toBeInTheDocument()
  expect(screen.queryByText('Passed')).not.toBeInTheDocument()
})
it.each(['run', 'candidate', 'requirements', 'plan'] as const)('marks mismatched %s binding stale', (field) => {
  const history = evidence()
  const binding = history.review!.candidate_binding
  if (field === 'run') binding.run_id = 'run_old'
  if (field === 'candidate') binding.candidate_ref = 'candidate_old'
  if (field === 'requirements') binding.requirements_revision = 1
  if (field === 'plan') binding.plan_hash = 'plan_old'
  render(<ExecutionEvidenceSection task={task(history)} snapshot={snapshot} />)
  expect(within(verdict()).getByText('Stale review')).toBeInTheDocument()
  expect(screen.queryByText('Passed')).not.toBeInTheDocument()
})
it('keeps a program-only pass separate from independent model review', () => {
  const history = evidence()
  history.review!.reviewer_kind = 'program'
  history.review!.model_calls = 0
  render(<ExecutionEvidenceSection task={task(history)} snapshot={snapshot} />)
  expect(within(verdict()).getByText('Independent model review unconfirmed')).toBeInTheDocument()
  expect(screen.queryByText('Passed')).not.toBeInTheDocument()
})
it('shows validated findings and dropped finding IDs for a real changes-requested report', () => {
  const history = evidence()
  history.review!.outcome = 'rework'
  history.review!.findings = [{ finding_id: 'finding_1', severity: 'blocking', summary: 'Source detail missing',
    evidence_ref: 'evidence:run_1/brief.md@sha256:abc', candidate_ref: 'run_1', rework_target: 'brief.md', detail: 'Include the source date.' }]
  history.review!.unsubstantiated = ['dropped_1']
  render(<ExecutionEvidenceSection task={task(history)} snapshot={snapshot} />)
  expect(within(verdict()).getByText('Changes requested')).toBeInTheDocument()
  expect(within(verdict()).getByText('blocking: Source detail missing')).toBeInTheDocument()
  expect(within(verdict()).getByText('Include the source date.')).toBeInTheDocument()
  expect(within(verdict()).getByText('Unsubstantiated finding IDs: dropped_1')).toBeInTheDocument()
})
it('does not leak a different Task projection and treats older backends as unavailable', () => {
  const history = evidence()
  history.task_id = 'task_other'
  const view = render(<ExecutionEvidenceSection task={task(history)} snapshot={snapshot} />)
  expect(screen.getByText(/Execution history unavailable/)).toBeInTheDocument()
  expect(screen.queryByText(/reviewer_old/)).not.toBeInTheDocument()
  view.rerender(<ExecutionEvidenceSection task={task(null)} snapshot={snapshot} />)
  expect(screen.getByText(/Execution history unavailable/)).toBeInTheDocument()
})
it('can show a bound completed last Run without requiring an active Run', () => {
  const current = task()
  current.run = null
  current.execution!.run!.state = 'completed'
  render(<ExecutionEvidenceSection task={current} snapshot={snapshot} />)
  expect(within(verdict()).getByText('Passed')).toBeInTheDocument()
})
