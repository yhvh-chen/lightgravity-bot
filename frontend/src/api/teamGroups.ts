/**
 * Grouped Recruited read model (LG-125; docs/13 §2–3, docs/08 §19.2/§19.5).
 *
 * `GET /api/v1/team/groups` is a read-only projection over persisted
 * Task/Run/Member/Subtask facts.  This module only declares the additive wire
 * shape and client; it never invents a Task/Run state or a second status
 * source.  The route is capability-gated by `team_groups`, so callers must
 * check `supportsTeamGroups()` before making the request.
 */

import { getRuntimeToken, runtimeTokenHeaders } from './auth'
import { apiRequest, fetchHealth } from './client'
import type {
  HealthResponse,
  QueueProjection,
  RunState,
  SubtaskState,
  TaskPhase,
  TaskStatus,
} from './types'

export type TeamGroupsView = 'all' | 'active' | 'history'

/** Additive R2 field; an absent reason means no current scheduling wait. */
export interface TeamGroupQueue extends QueueProjection {
  waiting_reason?: string | null
}

export interface TeamGroupTask {
  id: string
  title: string
  status: TaskStatus
  phase: TaskPhase
  revision: number
  requirements_revision: number
  deliverable_revision: number
  archived: boolean
  active_run: string | null
  last_run: string | null
  queue: TeamGroupQueue
}

export interface TeamGroupCleanup {
  status: 'pending' | 'running' | 'done' | 'failed' | string
  [key: string]: unknown
}

export interface TeamGroupReviewerCleanup {
  confirmed?: boolean | null
  status?: string | null
  [key: string]: unknown
}

export interface TeamGroupRun {
  id: string
  state: RunState | string
  attempt: number
  plan_source?: string | null
  plan_hash?: string | null
  team_refs: string[]
  cleanup: TeamGroupCleanup
  reviewer_cleanup?: TeamGroupReviewerCleanup | null
  /**
   * Authoritative stop evidence used by the R2 Released rule.  The contract's
   * example omits it, so it is optional; when absent the UI relies on
   * `cleanup.status`/terminal phase and does not claim a confirmed stop.
   */
  session_refs?: string[]
  ended_at?: string | null
  fail_reason?: string | null
  waiting_reason?: string | null
}

export interface TeamGroupSubtask {
  id: string
  key?: string | null
  capability?: string | null
  state: SubtaskState | string
  depends_on?: string[]
  blocked_by?: string[]
  assignee_member_ref?: string | null
  waiting_reason?: string | null
  acceptance?: { status?: string | null } | null
  fail_reason?: string | null
}

export interface TeamGroupMember {
  id: string
  run_ref: string
  role_ref: string | null
  state: string | null
  template_version?: string | null
  connection_ref?: string | null
  skill_refs?: string[]
  capabilities?: string[]
  assigned_subtask_refs?: string[]
  assigned_subtasks?: TeamGroupSubtask[]
  config_hash?: string | null
  fail_reason?: string | null
}

export interface TeamGroup {
  task: TeamGroupTask
  active_run: TeamGroupRun | null
  runs: TeamGroupRun[]
  members: TeamGroupMember[]
  subtasks: TeamGroupSubtask[]
}

export interface TeamGroupsPage {
  items: TeamGroup[]
  next_cursor: string | null
}

export interface TeamGroupsQuery {
  view?: TeamGroupsView
  taskRef?: string | null
  limit?: number
  cursor?: string | null
}

export interface TeamGroupsApi {
  listGroups(query?: TeamGroupsQuery, signal?: AbortSignal): Promise<TeamGroupsPage>
}

export function createTeamGroupsApi(
  getToken: () => string | null = getRuntimeToken,
): TeamGroupsApi {
  return {
    async listGroups(query = {}, signal) {
      const params = new URLSearchParams()
      params.set('view', query.view ?? 'all')
      if (query.taskRef) params.set('task_ref', query.taskRef)
      if (query.limit) params.set('limit', String(query.limit))
      if (query.cursor) params.set('cursor', query.cursor)
      return apiRequest<TeamGroupsPage>(`/team/groups?${params.toString()}`, {
        headers: runtimeTokenHeaders(getToken()),
        signal,
      })
    },
  }
}

/**
 * Capability gate from `GET /health`.  The route is additive in 1.18.0; a
 * missing/false capability means "do not call the route", never "probe for 404".
 */
export function supportsTeamGroups(health: HealthResponse | null | undefined): boolean {
  if (!health) return false
  const version = /^(\d+)\.(\d+)\.(\d+)$/.exec(health.contract_version ?? '')
  return Boolean(
    version &&
      Number(version[1]) === 1 &&
      Number(version[2]) >= 18 &&
      health.capabilities?.team_groups === true,
  )
}

/** Read health only; this is not a probe request to the grouped-teams route. */
export async function fetchTeamGroupsCapability(signal?: AbortSignal): Promise<boolean> {
  return supportsTeamGroups(await fetchHealth(signal))
}
