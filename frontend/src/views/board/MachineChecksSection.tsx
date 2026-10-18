import type { AcceptanceSnapshot } from '../../api/tasks'
import type { TaskDetail } from '../../api/types'
import { StatusBadge } from '../../components/StatusBadge'

function record(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown> : null
}
function strings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : []
}

/** Saved machine facts only; rendering does not run checks or infer a pass. */
export function MachineChecksSection({ task, snapshot }: { task: TaskDetail; snapshot: AcceptanceSnapshot | null }) {
  const checks = snapshot?.checks
  const results = Array.isArray(checks?.results)
    ? checks.results.map(record).filter((item): item is Record<string, unknown> => item !== null) : []
  const required = strings(checks?.required)
  const binding = record(checks?.binding)
  const planHash = typeof task.run?.plan_hash === 'string' ? task.run.plan_hash : snapshot?.candidate?.plan_hash
  const currentBinding = Boolean(snapshot?.task_id === task.task_id && task.run && binding &&
    binding.run_id === task.run.id && binding.requirements_revision === task.requirements_revision &&
    snapshot.requirements_revision === task.requirements_revision &&
    typeof planHash === 'string' && planHash.length > 0 && binding.plan_hash === planHash)
  const completeResults = required.length > 0 && results.length > 0 &&
    required.every((id) => results.some((result) => result.check_id === id && result.status === 'passed')) &&
    results.every((result) => result.status === 'passed')
  const claimedStatus = typeof checks?.status === 'string' ? checks.status : 'not_run'
  const passed = claimedStatus === 'passed' && checks?.satisfied === true && completeResults && currentBinding
  const status = claimedStatus === 'passed' && !passed ? 'stale' : claimedStatus
  const labels: Record<string, string> = {
    not_configured: 'Not configured', not_run: 'Not run', stale: 'Stale', passed: 'Passed', failed: 'Failed',
  }
  return <section className="lg-board__checks" aria-label="Machine checks">
    <h4 className="lg-section__title">Machine checks</h4>
    <StatusBadge kind={passed ? 'success' : status === 'failed' ? 'error' : 'warning'}>
      {labels[status] ?? 'Unavailable'}
    </StatusBadge>
    {status === 'stale' ? <p className="lg-chat__subtitle">Saved results are not confirmed for the current candidate.</p> : null}
    {results.length === 0 ? <p className="lg-chat__subtitle">No individual check results recorded.</p> : (
      <ul className="lg-board__list">{results.map((result, index) => <li key={`${String(result.check_id)}-${index}`}>
        <span className="lg-card__path">{typeof result.check_id === 'string' ? result.check_id : 'Unknown check'}</span>{' '}
        <StatusBadge kind={result.status === 'passed' && passed ? 'success' : result.status === 'failed' || result.status === 'error' ? 'error' : 'neutral'}>
          {typeof result.status === 'string' ? result.status : 'unknown'}
        </StatusBadge>
        {typeof result.detail === 'string' && result.detail ? <p className="lg-chat__subtitle">{result.detail}</p> : null}
      </li>)}</ul>
    )}
    <p className="lg-chat__subtitle">Required checks: {required.join(', ') || 'Not recorded'}</p>
    {binding ? <p className="lg-chat__subtitle">
      Recorded Run: {typeof binding.run_id === 'string' ? binding.run_id : 'Unknown'} · requirements{' '}
      {typeof binding.requirements_revision === 'number' ? binding.requirements_revision : 'Unknown'} · plan{' '}
      {typeof binding.plan_hash === 'string' ? binding.plan_hash : 'Unknown'}
    </p> : null}
    {typeof checks?.checked_at === 'string' ? <p className="lg-chat__subtitle">Checked at {checks.checked_at}</p> : null}
  </section>
}
