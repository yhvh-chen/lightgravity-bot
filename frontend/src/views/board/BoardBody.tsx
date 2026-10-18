import { useCallback, useEffect, useMemo, useState } from 'react'

import type { TaskApi } from '../../api/tasks'
import type { TaskDetail, TaskSummary } from '../../api/types'
import { useShell } from '../../app/ShellProvider'
import { openTaskDestination } from '../../app/taskDestination'
import { routeQuery } from '../../app/uiState'
import { EmptyState } from '../../components/EmptyState'
import { ErrorState } from '../../components/ErrorState'
import { StatusBadge } from '../../components/StatusBadge'
import { TaskCard } from '../../components/TaskCard'
import { phaseBadge, isActivePhase, isPendingPhase } from './phase'
import {
  BOARD_AUTO_REFRESH_MS,
  useBoardAutoRefresh,
  useControlAction,
  useTaskDetail,
  useTaskList,
} from './useBoard'

export interface BoardBodyProps {
  /** Injectable for tests; defaults to the real `/tasks` endpoints. */
  api?: TaskApi
  /** Bounded automatic refresh interval; tests use a short value. */
  autoRefreshMs?: number
}

interface BoardGroups {
  active: TaskSummary[]
  pending: TaskSummary[]
  closed: TaskSummary[]
}

function groupTasks(tasks: TaskSummary[]): BoardGroups {
  const groups: BoardGroups = { active: [], pending: [], closed: [] }
  for (const task of tasks) {
    if (isActivePhase(task.phase)) groups.active.push(task)
    else if (isPendingPhase(task.phase)) groups.pending.push(task)
    else groups.closed.push(task)
  }
  return groups
}

/**
 * Board body (LG-013; docs/08 §4.3/§6, design.md §5 Board).
 *
 * The main card is the Task with its real phase and Run state. Subtasks/Run
 * expand in the detail, not on the main board. Control requests show a pending
 * state and only paint a confirmed result after the backend confirms; a
 * cancelled/failed Task is never shown as running.
 */
export function BoardBody({ api, autoRefreshMs = BOARD_AUTO_REFRESH_MS }: BoardBodyProps) {
  const { state, dispatch } = useShell()
  const list = useTaskList(api)
  const detail = useTaskDetail(state.taskRef, api)
  const control = useControlAction(api)
  const [note, setNote] = useState<string | null>(null)

  const groups = useMemo(() => groupTasks(list.tasks), [list.tasks])

  // LG-220: keep the real board phase and the selected Task detail current
  // without a manual Refresh. Silent re-reads leave the mounted controls,
  // selection, chat scope and keyboard focus in place.
  const refreshBoard = useCallback(() => {
    list.refreshTasksSilently()
    if (state.taskRef) detail.refreshSilently()
  }, [detail, list, state.taskRef])
  useBoardAutoRefresh({
    enabled: !list.tasksLoading && !detail.loading,
    intervalMs: autoRefreshMs,
    onRefresh: refreshBoard,
  })

  useEffect(() => {
    if (control.outcome) {
      setNote(control.outcome.message ?? `Applied ${control.outcome.action}.`)
    }
  }, [control.outcome])

  const runControl = async (action: Parameters<typeof control.run>[1]) => {
    if (!state.taskRef) return
    const outcome = await control.run(state.taskRef, action, {
      acceptance: detail.acceptance,
      runRef: detail.detail?.run?.id ?? null,
    })
    if (outcome.confirmed) detail.refresh()
  }

  const handleDecide = async (action: 'accept' | 'reject') => {
    if (!state.taskRef) return
    const outcome = await control.run(state.taskRef, action, {
      acceptance: detail.acceptance,
      runRef: detail.detail?.run?.id ?? null,
    })
    if (outcome.confirmed) {
      detail.refresh()
      list.refreshTasks()
    }
  }

  return (
    <section className="lg-board" aria-label="Task board">
      <header className="lg-board__header">
        <div>
          <h2 className="lg-board__title">Board</h2>
          <span className="lg-chat__subtitle">
            Real phase and Run state from the backend, updated automatically. Active{' '}
            {groups.active.length} · pending {groups.pending.length} · closed{' '}
            {groups.closed.length}
          </span>
        </div>
        <button type="button" className="lg-button" onClick={list.refreshTasks}>
          Refresh
        </button>
      </header>

      <div className="lg-board__columns">
        {list.tasksError ? (
          <ErrorState
            title="Could not load tasks"
            message={list.tasksError.message}
            code={list.tasksError.code}
            retryable={list.tasksError.retryable}
            requestId={list.tasksError.requestId}
            onRetry={list.refreshTasks}
          />
        ) : null}

        {!list.tasksError && !list.tasksLoading && list.tasks.length === 0 ? (
          <EmptyState title="No tasks yet">
            Create one from Chat by describing a goal. Plain questions are answered without a
            task.
          </EmptyState>
        ) : null}

        <BoardColumn
          title="Active"
          tasks={groups.active}
          selected={state.taskRef}
          onOpen={(taskRef) => dispatch({ type: 'selectTask', taskRef })}
        />
        <BoardColumn
          title="Pending / blocked"
          tasks={groups.pending}
          selected={state.taskRef}
          onOpen={(taskRef) => dispatch({ type: 'selectTask', taskRef })}
        />
        <BoardColumn
          title="Closed"
          tasks={groups.closed}
          selected={state.taskRef}
          onOpen={(taskRef) => dispatch({ type: 'selectTask', taskRef })}
        />
      </div>

      {state.taskRef ? (
        <TaskDetailPanel
          taskRef={state.taskRef}
          detail={detail.detail}
          loading={detail.loading}
          error={detail.error}
          artifacts={detail.artifacts}
          acceptance={detail.acceptance}
          controlPending={control.pending}
          note={note}
          onRetry={detail.refresh}
          onPause={() => runControl('pause')}
          onCancel={() => runControl('cancel')}
          onRetryRun={() => runControl('retry')}
          onAccept={() => handleDecide('accept')}
          onReject={() => handleDecide('reject')}
        />
      ) : (
        <p className="lg-notice">Select a Task to review its Run, Subtasks and artifacts.</p>
      )}
    </section>
  )
}

function BoardColumn({
  title,
  tasks,
  selected,
  onOpen,
}: {
  title: string
  tasks: TaskSummary[]
  selected: string | null
  onOpen: (taskRef: string) => void
}) {
  return (
    <div className="lg-board__column">
      <h3 className="lg-section__title">
        {title} <span className="lg-board__count">{tasks.length}</span>
      </h3>
      {tasks.length === 0 ? (
        <EmptyState title="Nothing here" compact />
      ) : (
        <ul className="lg-board__list">
          {tasks.map((task) => {
            const badge = phaseBadge(task.phase)
            return (
              <li key={task.id}>
                <TaskCard
                  title={task.title}
                  phase={task.phase}
                  statusLabel={badge.label}
                  statusKind={badge.kind}
                  taskRef={task.id}
                  runRef={null}
                  selected={task.id === selected}
                  onOpen={() => onOpen(task.id)}
                />
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}

interface DetailPanelProps {
  taskRef: string
  detail: TaskDetail | null
  loading: boolean
  error: import('../../api/client').ApiError | null
  artifacts: import('../../api/tasks').TaskArtifacts | null
  acceptance: import('../../api/tasks').AcceptanceSnapshot | null
  controlPending: string | null
  note: string | null
  onRetry: () => void
  onPause: () => void
  onCancel: () => void
  onRetryRun: () => void
  onAccept: () => void
  onReject: () => void
}

function TaskDetailPanel(props: DetailPanelProps) {
  const { state, dispatch } = useShell()
  const { detail, error, loading, artifacts, acceptance, controlPending } = props
  const canDecide = !loading && !error && canDecideCandidate(props.taskRef, detail, acceptance)
  const evidence = artifacts?.evidence ?? []
  const busy = controlPending !== null

  return (
    <div className="lg-board__detail" aria-label="Task detail">
      {error ? (
        <ErrorState
          title="Could not load Task detail"
          message={error.message}
          code={error.code}
          retryable={error.retryable}
          requestId={error.requestId}
          onRetry={props.onRetry}
        />
      ) : null}
      {loading ? <EmptyState title="Loading Task…" compact /> : null}
      {detail ? (
        <>
          <div className="lg-board__detail-head">
            <h3 className="lg-card__title">{detail.title}</h3>
            <StatusBadge kind={phaseBadge(detail.phase).kind}>{detail.phase}</StatusBadge>
          </div>
          <p className="lg-chat__subtitle">
            Task {detail.task_id} · revision {detail.revision} · requirements{' '}
            {detail.requirements_revision}
            {detail.run ? ` · Run ${detail.run.id} (${detail.run.state})` : ' · no active Run'}
          </p>

          <div className="lg-board__actions">
            <button type="button" className="lg-button" disabled={busy} onClick={props.onPause}>
              Pause
            </button>
            <button type="button" className="lg-button" disabled={busy} onClick={props.onCancel}>
              Cancel
            </button>
            <button type="button" className="lg-button" disabled={busy} onClick={props.onRetryRun}>
              Retry
            </button>
          </div>
          {controlPending ? (
            <p className="lg-notice" role="status">
              Requesting {controlPending}… waiting for the backend to confirm.
            </p>
          ) : null}
          {props.note ? (
            <p className="lg-notice" role="status">
              {props.note}
            </p>
          ) : null}

          <AcceptanceSection
            acceptance={acceptance}
            canDecide={canDecide}
            busy={busy}
            onAccept={props.onAccept}
            onReject={props.onReject}
          />

          <section className="lg-board__subtasks" aria-label="Subtasks">
            <h4 className="lg-section__title">Subtasks ({detail.subtasks.length})</h4>
            {detail.subtasks.length === 0 ? (
              <EmptyState title="No subtasks" compact />
            ) : (
              <ul className="lg-board__list">
                {detail.subtasks.map((subtask) => (
                  <li key={subtask.id} className="lg-board__subtask">
                    <span className="lg-card__path">{subtask.id}</span>
                    <StatusBadge kind={subtask.state === 'failed' ? 'error' : 'neutral'}>
                      {subtask.state}
                    </StatusBadge>
                    {subtask.fail_reason ? (
                      <span className="lg-chat__subtitle">reason: {subtask.fail_reason}</span>
                    ) : null}
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="lg-board__evidence" aria-label="Artifacts">
            <h4 className="lg-section__title">Artifacts ({evidence.length})</h4>
            {artifacts?.note ? <p className="lg-chat__subtitle">{artifacts.note}</p> : null}
            {evidence.length === 0 ? (
              <EmptyState title="No artifacts yet" compact />
            ) : (
              <ul className="lg-board__list">
                {evidence.map((entry) => {
                  const ref = entry.evidence_ref ?? entry.ref ?? null
                  const runRef = /^evidence:([^/]+)\//.exec(ref ?? '')?.[1] ?? entry.run_ref ?? state.runRef
                  const destination = { taskRef: props.taskRef, runRef, view: 'tasks' as const, itemRef: ref }
                  return (
                    <li key={ref ?? entry.name} className="lg-board__evidence-item">
                      <span className="lg-card__path">{entry.name}</span>
                      {ref ? (
                        <>
                          <a
                            className="lg-link-button"
                            href={routeQuery({ view: 'tasks', taskRef: props.taskRef, runRef, selectedItemRef: ref, chatChannel: state.chatChannel })}
                            onClick={(event) => {
                              if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
                              event.preventDefault()
                              dispatch(openTaskDestination(destination))
                            }}
                          >
                            Preview
                          </a>
                          <a
                            className="lg-link-button"
                            href={artifactDownloadHref(props.taskRef, ref)}
                            download
                          >
                            Download
                          </a>
                        </>
                      ) : null}
                    </li>
                  )
                })}
              </ul>
            )}
          </section>
        </>
      ) : null}
    </div>
  )
}

/** This is an affordance, not authorization: the action endpoint rechecks state.
 * awaiting_acceptance is the backend's handoff after verification and the stop
 * gate. Never infer that handoff from a pending record or artifact presence.
 */
function canDecideCandidate(
  taskRef: string,
  detail: TaskDetail | null,
  snapshot: import('../../api/tasks').AcceptanceSnapshot | null,
): boolean {
  if (!detail || !snapshot || !detail.run || !snapshot.candidate) return false
  const candidate = snapshot.candidate
  const acceptance = snapshot.acceptance
  return (
    detail.task_id === taskRef && snapshot.task_id === taskRef &&
    detail.phase === 'awaiting_acceptance' && snapshot.phase === 'awaiting_acceptance' &&
    detail.run.state === 'awaiting_acceptance' && candidate.run_state === 'awaiting_acceptance' &&
    detail.revision === snapshot.revision &&
    acceptance.status === 'awaiting' &&
    Number.isSafeInteger(snapshot.deliverable_revision) && snapshot.deliverable_revision > 0 &&
    detail.requirements_revision === snapshot.requirements_revision &&
    acceptance.requirements_revision === snapshot.requirements_revision &&
    candidate.requirements_revision === snapshot.requirements_revision &&
    acceptance.deliverable_revision === snapshot.deliverable_revision &&
    candidate.deliverable_revision === snapshot.deliverable_revision &&
    candidate.task_id === taskRef && candidate.run_id === detail.run.id &&
    candidate.candidate_ref === detail.run.id && acceptance.candidate_ref === detail.run.id &&
    typeof candidate.plan_hash === 'string' && candidate.plan_hash.length > 0 &&
    acceptance.candidate_plan_hash === candidate.plan_hash &&
    snapshot.checks?.satisfied === true
  )
}

function AcceptanceSection({
  acceptance,
  canDecide,
  busy,
  onAccept,
  onReject,
}: {
  acceptance: import('../../api/tasks').AcceptanceSnapshot | null
  canDecide: boolean
  busy: boolean
  onAccept: () => void
  onReject: () => void
}) {
  const status = String(acceptance?.acceptance?.status ?? 'pending')
  const candidateRef = acceptance?.acceptance?.candidate_ref ?? acceptance?.candidate
  return (
    <section className="lg-board__acceptance" aria-label="Acceptance">
      <h4 className="lg-section__title">Acceptance</h4>
      <p className="lg-chat__subtitle">
        status: <strong>{status}</strong> · requirements{' '}
        {acceptance?.requirements_revision ?? '—'} · deliverable{' '}
        {acceptance?.deliverable_revision ?? '—'}
      </p>
      {typeof candidateRef === 'string' ? (
        <p className="lg-card__path">candidate: {candidateRef}</p>
      ) : null}
      <div className="lg-board__actions">
        <button
          type="button"
          className="lg-button lg-button--primary"
          disabled={busy || !canDecide}
          onClick={onAccept}
        >
          Accept
        </button>
        <button
          type="button"
          className="lg-button"
          disabled={busy || !canDecide}
          onClick={onReject}
        >
          Reject
        </button>
      </div>
      {!canDecide ? (
        <p className="lg-chat__subtitle">
          Decisions are available when a candidate is awaiting acceptance.
        </p>
      ) : null}
    </section>
  )
}


/**
 * Canonical evidence download (LG-066 optional affordance).
 *
 * Uses the existing Task-scoped `/artifacts/download` endpoint, which resolves
 * the `evidence:<run>/<name>@sha256:<hex>` reference against the owning Task
 * under the authenticated session. The UI only ever passes the canonical
 * evidence ref back — no absolute path or cross-Task reference is exposed.
 */
function artifactDownloadHref(taskRef: string, evidenceRef: string): string {
  const params = new URLSearchParams({ evidence_ref: evidenceRef })
  return `/api/v1/tasks/${encodeURIComponent(taskRef)}/artifacts/download?${params.toString()}`
}
