/**
 * Deterministic display mapping for grouped Recruited teams (LG-125).
 *
 * Every value here is derived from persisted Task/Run/Member/Subtask facts
 * returned by `GET /team/groups`; there is no parallel display-state store.
 * The R2 release rule (docs/08 §19.5) is authoritative: a terminal phase alone
 * never proves that worker/reviewer sessions and the Task slot were released.
 */

import type { StatusKind } from '../../components/StatusBadge'
import type {
  TeamGroup,
  TeamGroupMember,
  TeamGroupRun,
  TeamGroupSubtask,
} from '../../api/teamGroups'

const HISTORY_PHASES = new Set(['awaiting_acceptance', 'completed', 'failed', 'cancelled'])
const STOP_PHASES = new Set([
  'awaiting_acceptance',
  'completed',
  'failed',
  'cancelled',
  'pausing',
  'cancelling',
])

const ACTIVE_PHASE_RANK: Record<string, number> = {
  executing: 0,
  verifying: 1,
  repairing: 2,
  recruiting: 3,
  planning: 4,
  queued: 5,
  waiting_dependencies: 6,
  waiting_user: 7,
  pausing: 8,
  cancelling: 9,
  paused: 10,
  intake: 11,
  recovery_required: 12,
}

export type GroupBucket = 'active' | 'history'

export interface ReleaseFacts {
  released: boolean
  workerStopped: boolean
  reviewerStopped: boolean
  membersTerminal: boolean
  slotFree: boolean
  stopUnconfirmed: boolean
}

export interface StatusDisplay {
  label: string
  kind: StatusKind
  detail: string | null
}

export function runById(group: TeamGroup, runRef: string | null | undefined): TeamGroupRun | null {
  if (!runRef) return null
  return group.runs.find((run) => run.id === runRef) ?? null
}

export function activeRun(group: TeamGroup): TeamGroupRun | null {
  return group.active_run ?? runById(group, group.task.active_run)
}

export function lastRun(group: TeamGroup): TeamGroupRun | null {
  const pointer = runById(group, group.task.last_run)
  if (pointer) return pointer
  if (group.runs.length === 0) return null
  return [...group.runs].sort((a, b) => b.attempt - a.attempt || a.id.localeCompare(b.id))[0]
}

/** Current run for the group, falling back to the last persisted run for History. */
export function displayRun(group: TeamGroup): TeamGroupRun | null {
  return activeRun(group) ?? lastRun(group)
}

/**
 * Current members come only from the active Run's `team_refs`.  Old Run
 * members are never mixed into the current team.
 */
export function membersForRun(group: TeamGroup, run: TeamGroupRun | null): TeamGroupMember[] {
  if (!run) return []
  const refs = Array.isArray(run.team_refs) ? new Set(run.team_refs) : new Set<string>()
  return group.members.filter((member) => member.run_ref === run.id && refs.has(member.id))
}

export function currentMembers(group: TeamGroup): TeamGroupMember[] {
  return membersForRun(group, activeRun(group))
}

export function historyMembers(group: TeamGroup): TeamGroupMember[] {
  return membersForRun(group, displayRun(group))
}

export function releaseFacts(group: TeamGroup): ReleaseFacts {
  const run = displayRun(group)
  const phase = group.task.phase
  const workerStopped =
    !run ||
    (Array.isArray(run.session_refs) && run.session_refs.length === 0) ||
    run.cleanup?.status === 'done' ||
    phase === 'awaiting_acceptance' ||
    phase === 'completed'
  const reviewerStopped =
    !run ||
    !run.reviewer_cleanup ||
    run.reviewer_cleanup.confirmed === true
  const refs = run && Array.isArray(run.team_refs) ? run.team_refs : []
  const membersTerminal =
    refs.length === 0 ||
    refs.every((memberRef) => {
      const member = group.members.find((candidate) => candidate.id === memberRef)
      return member?.state === 'released' || member?.state === 'failed'
    })
  const slotFree = !group.task.queue || group.task.queue.state === 'not_queued'
  const released = workerStopped && reviewerStopped && membersTerminal && slotFree
  return {
    released,
    workerStopped,
    reviewerStopped,
    membersTerminal,
    slotFree,
    stopUnconfirmed: !released && STOP_PHASES.has(phase),
  }
}

export function groupBucket(group: TeamGroup): GroupBucket {
  return releaseFacts(group).released && HISTORY_PHASES.has(group.task.phase)
    ? 'history'
    : 'active'
}

export function formatWaitingReason(reason: string | null | undefined): string | null {
  switch (reason) {
    case 'active_task_limit':
      return 'Capacity reached'
    case 'global_session_limit':
      return 'Waiting for session capacity'
    case 'workspace_write_conflict':
      return 'Waiting for workspace write lock'
    case 'reviewer_limit':
      return 'Waiting for reviewer capacity'
    case null:
    case undefined:
    case '':
      return null
    default:
      return reason.replaceAll('_', ' ')
  }
}

function releaseDetail(facts: ReleaseFacts): string | null {
  if (facts.released) return null
  if (!facts.workerStopped) return 'Worker stop is not confirmed'
  if (!facts.reviewerStopped) return 'Reviewer stop is not confirmed'
  if (!facts.membersTerminal) return 'Members are still held'
  if (!facts.slotFree) return 'Task slot is still held'
  return null
}

/** Group headline from the authoritative Task phase + R2 release facts. */
export function groupStatus(group: TeamGroup): StatusDisplay {
  const phase = group.task.phase
  const facts = releaseFacts(group)
  const run = displayRun(group)
  const detail = releaseDetail(facts)

  const cleanupConfirmed = facts.workerStopped && facts.reviewerStopped

  if (phase === 'recovery_required') {
    return {
      label: 'Recovery required',
      kind: 'error',
      detail: 'Recovery cleanup alone is not treated as released.',
    }
  }

  if (groupBucket(group) === 'history') {
    switch (phase) {
      case 'awaiting_acceptance':
        return { label: 'Awaiting acceptance · Released', kind: 'accent', detail: null }
      case 'completed':
        return { label: 'Completed · Released', kind: 'success', detail: null }
      case 'failed':
        return { label: 'Failed · Released', kind: 'error', detail: null }
      case 'cancelled':
        return { label: 'Cancelled · Released', kind: 'warning', detail: null }
      default:
        return { label: 'Released', kind: 'neutral', detail: null }
    }
  }

  switch (phase) {
    case 'intake':
      return { label: 'Intake', kind: 'neutral', detail: null }
    case 'queued': {
      const wait = formatWaitingReason(group.task.queue?.waiting_reason)
      return {
        label: wait ? `Queued · ${wait}` : 'Queued',
        kind: 'warning',
        detail: group.task.queue?.waiting_reason ?? null,
      }
    }
    case 'waiting_dependencies':
      return { label: 'Waiting for dependency', kind: 'warning', detail: null }
    case 'planning':
    case 'recruiting':
      return { label: 'Assembling', kind: 'accent', detail: null }
    case 'executing':
      return { label: 'Running', kind: 'accent', detail: null }
    case 'verifying': {
      const wait = formatWaitingReason(run?.waiting_reason)
      return {
        label: wait ? `Verifying · ${wait}` : 'Verifying',
        kind: 'accent',
        detail: run?.waiting_reason ?? null,
      }
    }
    case 'repairing':
      return { label: 'Repairing', kind: 'warning', detail: null }
    case 'pausing':
    case 'cancelling':
      return { label: 'Releasing · Stop unconfirmed', kind: 'warning', detail }
    case 'paused':
      return {
        label: facts.released ? 'Paused · Released' : 'Paused',
        kind: 'warning',
        detail,
      }
    case 'waiting_user':
      return { label: 'Waiting for you', kind: 'warning', detail: null }
    case 'awaiting_acceptance':
      return {
        label: cleanupConfirmed
          ? 'Awaiting acceptance · Release unconfirmed'
          : 'Awaiting acceptance · Stop unconfirmed',
        kind: 'warning',
        detail,
      }
    case 'failed':
      return {
        label: cleanupConfirmed ? 'Failed · Release unconfirmed' : 'Failed · Cleanup unconfirmed',
        kind: 'error',
        detail,
      }
    case 'cancelled':
      return {
        label: cleanupConfirmed
          ? 'Cancelled · Release unconfirmed'
          : 'Cancelled · Cleanup unconfirmed',
        kind: 'error',
        detail,
      }
    case 'completed':
      return {
        label: cleanupConfirmed ? 'Completed · Release unconfirmed' : 'Completed · Cleanup unconfirmed',
        kind: 'warning',
        detail,
      }
    default:
      return { label: phase, kind: 'neutral', detail: null }
  }
}

export function sortGroups(groups: TeamGroup[]): TeamGroup[] {
  return [...groups].sort((a, b) => {
    const bucketA = groupBucket(a)
    const bucketB = groupBucket(b)
    if (bucketA !== bucketB) return bucketA === 'active' ? -1 : 1
    if (bucketA === 'active') {
      const rankA = ACTIVE_PHASE_RANK[a.task.phase] ?? 99
      const rankB = ACTIVE_PHASE_RANK[b.task.phase] ?? 99
      if (rankA !== rankB) return rankA - rankB
      const orderA = a.task.queue?.order ?? Number.MAX_SAFE_INTEGER
      const orderB = b.task.queue?.order ?? Number.MAX_SAFE_INTEGER
      if (orderA !== orderB) return orderA - orderB
    }
    return a.task.id.localeCompare(b.task.id)
  })
}

export function shortTaskId(id: string): string {
  return id.length > 15 ? `${id.slice(0, 14)}…` : id
}

export function runHeading(run: TeamGroupRun | null, current: boolean): string {
  if (!run) return 'No Run'
  return `${current ? 'Run' : 'Last run'} ${run.attempt} · ${run.state}`
}

export function assignedSubtasks(group: TeamGroup, member: TeamGroupMember): TeamGroupSubtask[] {
  const byId = new Map(group.subtasks.map((subtask) => [subtask.id, subtask]))
  const listed =
    member.assigned_subtasks && member.assigned_subtasks.length > 0
      ? member.assigned_subtasks
      : group.subtasks.filter((subtask) => subtask.assignee_member_ref === member.id)
  const merged: TeamGroupSubtask[] = []
  const seen = new Set<string>()
  for (const subtask of listed) {
    if (seen.has(subtask.id)) continue
    seen.add(subtask.id)
    merged.push(byId.get(subtask.id) ?? subtask)
  }
  return merged
}

export function hasUnmetDependency(group: TeamGroup, subtask: TeamGroupSubtask): boolean {
  if ((subtask.blocked_by?.length ?? 0) > 0) return true
  const deps = subtask.depends_on ?? []
  if (deps.length === 0) return false
  const byId = new Map(group.subtasks.map((candidate) => [candidate.id, candidate]))
  return deps.some((dep) => byId.get(dep)?.state !== 'passed')
}

export function subtaskStatus(group: TeamGroup, subtask: TeamGroupSubtask): StatusDisplay {
  switch (subtask.state) {
    case 'running':
    case 'verifying':
      return { label: 'Working', kind: 'accent', detail: subtask.capability ?? null }
    case 'passed':
      return { label: 'Passed', kind: 'success', detail: subtask.capability ?? null }
    case 'failed':
      return {
        label: 'Failed',
        kind: 'error',
        detail: subtask.fail_reason ?? subtask.capability ?? null,
      }
    case 'cancelled':
      return { label: 'Cancelled', kind: 'warning', detail: subtask.capability ?? null }
    case 'repairing':
      return { label: 'Repairing', kind: 'warning', detail: subtask.capability ?? null }
    case 'waiting_user':
      return { label: 'Waiting for you', kind: 'warning', detail: subtask.capability ?? null }
    case 'paused':
      return { label: 'Paused', kind: 'warning', detail: subtask.capability ?? null }
    default: {
      const capacity = formatWaitingReason(subtask.waiting_reason)
      if (capacity) return { label: `Waiting · ${capacity}`, kind: 'warning', detail: subtask.waiting_reason ?? null }
      if (hasUnmetDependency(group, subtask)) {
        return { label: 'Waiting · dependency', kind: 'warning', detail: subtask.capability ?? null }
      }
      return {
        label: subtask.state === 'ready' ? 'Waiting · ready' : 'Pending',
        kind: 'neutral',
        detail: subtask.capability ?? null,
      }
    }
  }
}

/**
 * Member status uses assigned Subtasks, not `member.state` alone: the graph
 * leaves a member `ready` while its node is actually executing.
 */
export function memberStatus(group: TeamGroup, member: TeamGroupMember): StatusDisplay {
  if (member.state === 'released') return { label: 'Released', kind: 'neutral', detail: null }
  if (member.state === 'failed') {
    return { label: 'Failed', kind: 'error', detail: member.fail_reason ?? null }
  }
  const subtasks = assignedSubtasks(group, member)
  if (subtasks.some((subtask) => subtask.state === 'running' || subtask.state === 'verifying')) {
    return { label: 'Working', kind: 'accent', detail: member.state ?? null }
  }
  if (subtasks.some((subtask) => subtask.state === 'failed')) {
    const failed = subtasks.find((subtask) => subtask.state === 'failed')
    return { label: 'Failed', kind: 'error', detail: failed?.fail_reason ?? null }
  }
  if (subtasks.some((subtask) => subtask.state === 'cancelled')) {
    return { label: 'Cancelled', kind: 'warning', detail: null }
  }
  if (subtasks.some((subtask) => subtask.state === 'repairing')) {
    return { label: 'Repairing', kind: 'warning', detail: null }
  }
  if (subtasks.length > 0 && subtasks.every((subtask) => subtask.state === 'passed')) {
    return { label: 'Finished', kind: 'success', detail: null }
  }
  if (
    subtasks.some(
      (subtask) =>
        (subtask.state === 'pending' || subtask.state === 'ready') &&
        (subtask.waiting_reason === 'global_session_limit' ||
          subtask.waiting_reason === 'workspace_write_conflict'),
    )
  ) {
    const waiting = subtasks.find(
      (subtask) =>
        (subtask.state === 'pending' || subtask.state === 'ready') &&
        (subtask.waiting_reason === 'global_session_limit' ||
          subtask.waiting_reason === 'workspace_write_conflict'),
    )
    return {
      label: `Waiting · ${formatWaitingReason(waiting?.waiting_reason) ?? 'capacity'}`,
      kind: 'warning',
      detail: waiting?.waiting_reason ?? null,
    }
  }
  if (
    subtasks.some(
      (subtask) =>
        (subtask.state === 'pending' || subtask.state === 'ready') &&
        hasUnmetDependency(group, subtask),
    )
  ) {
    return { label: 'Waiting · dependency', kind: 'warning', detail: member.state ?? null }
  }
  if (subtasks.some((subtask) => subtask.state === 'waiting_user')) {
    return { label: 'Waiting for you', kind: 'warning', detail: null }
  }
  if (subtasks.some((subtask) => subtask.state === 'paused')) {
    return { label: 'Paused', kind: 'warning', detail: null }
  }
  if (member.state === 'recruiting') return { label: 'Recruiting', kind: 'warning', detail: null }
  if (member.state === 'ready') {
    return {
      label: 'Waiting · ready',
      kind: 'neutral',
      detail: 'Member is ready; no assigned Subtask is executing.',
    }
  }
  return { label: member.state ?? 'Waiting', kind: 'neutral', detail: null }
}
