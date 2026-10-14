/**
 * Team API client (LG-015; docs/05 §5).
 *
 * * Available = agent templates (`GET /team/available`) with a compiled
 *   availability state.  A template is not an idle worker and does not occupy
 *   execution capacity.
 * * Recruited = Member instances (`GET /team/members`) for the current
 *   Task/Run, plus released history.  Released members are history, never
 *   counted as the current team.
 *
 * Both endpoints are additive reads introduced by LG-015; docs/08 §4.3 does not
 * list them yet, so the shell/integration layer must register them.
 */

import { getRuntimeToken, runtimeTokenHeaders } from './auth'
import { apiRequest } from './client'
import type { ResourceAvailability, ResourceDiagnostic } from './resources'

export interface AvailableAgent {
  id: string
  kind: 'agent'
  title: string
  enabled: boolean
  revision: number | null
  revision_etag?: string
  template_version?: string
  connection_ref: string | null
  conversation_ref?: string | null
  skill_refs: string[]
  skills_source?: string
  tool_refs?: string[]
  hook_refs?: string[]
  mcp_refs?: string[]
  trigger_refs?: string[]
  availability: ResourceAvailability
  executable?: boolean
  body?: string
  diagnostics?: ResourceDiagnostic[]
}

export interface TeamMember {
  id: string
  kind: 'member'
  title: string
  state: string | null
  released: boolean
  revision: number | null
  run_ref: string | null
  role_ref: string | null
  template_version?: string | null
  connection_ref: string | null
  skill_refs: string[]
  tool_policy: Record<string, unknown>
  assigned_subtask_refs: string[]
  session_ref?: string | null
  config_hash?: string | null
  budget: Record<string, unknown>
  fail_reason?: string | null
  availability: ResourceAvailability
  body?: string
  diagnostics?: ResourceDiagnostic[]
}

export interface MemberQuery {
  taskRef?: string | null
  runRef?: string | null
  includeReleased?: boolean
}

export interface TeamApi {
  listAvailable(signal?: AbortSignal): Promise<AvailableAgent[]>
  listMembers(query?: MemberQuery, signal?: AbortSignal): Promise<TeamMember[]>
}

export function createTeamApi(getToken: () => string | null = getRuntimeToken): TeamApi {
  return {
    async listAvailable(signal) {
      const body = await apiRequest<{ items: AvailableAgent[] }>('/team/available', {
        headers: runtimeTokenHeaders(getToken()),
        signal,
      })
      return body.items
    },
    async listMembers(query = {}, signal) {
      const params = new URLSearchParams()
      if (query.taskRef) params.set('task_ref', query.taskRef)
      if (query.runRef) params.set('run_ref', query.runRef)
      params.set('include_released', query.includeReleased === false ? 'false' : 'true')
      const body = await apiRequest<{ items: TeamMember[] }>(
        `/team/members?${params.toString()}`,
        { headers: runtimeTokenHeaders(getToken()), signal },
      )
      return body.items
    },
  }
}

export function isReleased(member: TeamMember): boolean {
  return member.released || member.state === 'released'
}

export function isFailed(member: TeamMember): boolean {
  return member.state === 'failed'
}
