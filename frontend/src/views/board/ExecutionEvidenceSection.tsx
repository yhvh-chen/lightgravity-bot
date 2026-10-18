import type { AcceptanceSnapshot } from '../../api/tasks'
import type { ExecutionConnectionEvidence, TaskDetail } from '../../api/types'
import { StatusBadge } from '../../components/StatusBadge'

function ConnectionSnapshot({ title, connection }: { title: string; connection: ExecutionConnectionEvidence }) {
  return <section aria-label={title}>
    <h5 className="lg-section__title">{title}</h5>
    <StatusBadge kind={connection.status === 'recorded' ? 'neutral' : 'warning'}>{connection.status}</StatusBadge>
    <p className="lg-chat__subtitle">Connection ID: {connection.connection_id || 'Unknown'} · name: {connection.name || 'Unknown'}</p>
    <p className="lg-chat__subtitle">Provider: {connection.provider || 'Unknown'} · model: {connection.model || 'Unknown'}</p>
    {connection.captured_at ? <p className="lg-chat__subtitle">Recorded at {connection.captured_at}</p> : null}
    {connection.reason ? <p className="lg-chat__subtitle">{connection.reason}</p> : null}
  </section>
}

/** Task-scoped historical facts only. Settings defaults cannot fill evidence gaps. */
export function ExecutionEvidenceSection({ task, snapshot }: { task: TaskDetail; snapshot: AcceptanceSnapshot | null }) {
  const execution = task.execution
  if (!execution || execution.task_id !== task.task_id || execution.schema !== 'lightgravity.execution-evidence/v1') {
    return <section aria-label="Execution evidence"><h4 className="lg-section__title">Execution evidence</h4>
      <p className="lg-chat__subtitle">Execution history unavailable. No recorded reviewer connection or verdict.</p>
    </section>
  }
  const { run, review, worker, reviewer } = execution
  const snapshotMatches = snapshot?.task_id === task.task_id
  const candidateRef = snapshotMatches && typeof snapshot?.acceptance.candidate_ref === 'string'
    ? snapshot.acceptance.candidate_ref : typeof task.acceptance?.candidate_ref === 'string' ? task.acceptance.candidate_ref : null
  const candidate = snapshotMatches ? snapshot?.candidate : null
  const binding = review?.candidate_binding
  const current = Boolean(run && review && binding && candidateRef && run.candidate_ref === candidateRef &&
    (!task.run || task.run.id === run.id) && run.requirements_revision === task.requirements_revision &&
    (!snapshot || (snapshotMatches && snapshot.requirements_revision === task.requirements_revision)) &&
    binding.run_id === run.id && binding.candidate_ref === candidateRef && review.candidate_ref === candidateRef &&
    binding.requirements_revision === task.requirements_revision && binding.plan_hash && binding.plan_hash === run.plan_hash &&
    (typeof task.run?.plan_hash !== 'string' || task.run.plan_hash === binding.plan_hash) &&
    (!candidate || ((typeof candidate.run_id !== 'string' || candidate.run_id === run.id) &&
      (typeof candidate.plan_hash !== 'string' || candidate.plan_hash === binding.plan_hash))))
  const actualModelReview = reviewer.status === 'recorded' && reviewer.stage === 'review_execution' &&
    reviewer.evidence_kind === 'resolved_reviewer_support' && review?.reviewer_kind === 'model' && review.model_calls > 0
  const passed = current && actualModelReview && review?.outcome === 'passed'
  const verdict = !review ? 'Unknown' : review.outcome === 'unavailable' ? 'Unavailable'
    : !current ? 'Stale review' : !actualModelReview ? 'Independent model review unconfirmed'
    : review.outcome === 'rework' ? 'Changes requested' : passed ? 'Passed' : 'Unknown'
  const usage = review ? Object.entries(review.usage).filter(([, value]) => typeof value === 'number') : []
  return <section className="lg-board__execution" aria-label="Execution evidence">
    <h4 className="lg-section__title">Execution evidence</h4>
    <p className="lg-chat__subtitle">Recorded Run: {run?.id || 'Unknown'} · state: {run?.state || 'Unknown'}</p>
    <ConnectionSnapshot title="Pinned worker connection" connection={worker} />
    <p className="lg-chat__subtitle">Frozen configuration for this Run. Invocation evidence is not recorded here.</p>
    <ConnectionSnapshot title="Reviewer connection" connection={reviewer} />
    <p className="lg-chat__subtitle">{execution.connections_distinct === true ? 'Connection IDs differ.'
      : execution.connections_distinct === false ? 'Same connection ID.' : 'Connection comparison unknown.'}</p>
    <section aria-label="Reviewer verdict">
      <h5 className="lg-section__title">Reviewer verdict</h5>
      <StatusBadge kind={passed ? 'success' : verdict === 'Changes requested' ? 'error' : 'warning'}>{verdict}</StatusBadge>
      {review ? <>
        <p className="lg-chat__subtitle">Recorded outcome: {review.outcome} · review kind: {review.reviewer_kind} · model calls: {review.model_calls}</p>
        {!current ? <p className="lg-chat__subtitle">The recorded review is not confirmed for the current candidate.</p> : null}
        <p className="lg-chat__subtitle">Reviewed candidate: {review.candidate_ref || 'Unknown'} · Run: {binding?.run_id || 'Unknown'} · requirements{' '}
          {binding?.requirements_revision ?? 'Unknown'} · plan: {binding?.plan_hash || 'Unknown'}</p>
        {review.reviewed_at ? <p className="lg-chat__subtitle">Reviewed at {review.reviewed_at}</p> : null}
        {review.reason ? <p className="lg-chat__subtitle">{review.reason}</p> : null}
        <h6 className="lg-section__title">Validated findings ({review.findings.length})</h6>
        {review.findings.length === 0 ? <p className="lg-chat__subtitle">No validated findings recorded.</p> : (
          <ul className="lg-board__list">{review.findings.map((finding) => <li key={finding.finding_id}>
            <strong>{finding.severity}: {finding.summary}</strong>
            {finding.detail ? <p className="lg-chat__subtitle">{finding.detail}</p> : null}
            <p className="lg-card__path">Evidence: {finding.evidence_ref} · target: {finding.rework_target}</p>
          </li>)}</ul>
        )}
        {review.unsubstantiated.length > 0 ? <p className="lg-chat__subtitle">Unsubstantiated finding IDs: {review.unsubstantiated.join(', ')}</p> : null}
        <p className="lg-chat__subtitle">Usage: {usage.length > 0 ? usage.map(([key, value]) => `${key}: ${value}`).join(' · ') : 'Unknown'}</p>
      </> : <p className="lg-chat__subtitle">No review result recorded for this Run.</p>}
    </section>
  </section>
}
