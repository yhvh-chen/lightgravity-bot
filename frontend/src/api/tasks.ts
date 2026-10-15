/**
 * Task / Board API client (LG-013; docs/08 §4.3, §6, §9).
 *
 * Owns the read + control surface the Board and Chat views need:
 *
 * * `GET  /tasks`                       — list (phase/status/archived filters)
 * * `GET  /tasks/{id}`                  — detail with active Run/Subtask/Member
 * * `GET  /tasks/{id}/events`           — persisted event read (cursor replay)
 * * `POST /tasks/{id}/actions`          — control actions
 * * `GET  /tasks/{id}/acceptance`       — read-only candidate/acceptance snapshot
 * * `GET  /tasks/{id}/artifacts`        — candidate/evidence references
 *
 * Control actions are asynchronous by contract (docs/08 §9): a `confirmed=false`
 * response is *pending*, never rendered as the new state. `accept`/`reject`
 * carry `expected_requirements_revision`/`expected_deliverable_revision` so the
 * decision binds the current candidate; a repeat `request_id` is idempotent.
 */

import { apiRequest } from './client'
import type { TaskDetail, TaskPhase, TaskStatus, TaskSummary } from './types'

export interface TaskListQuery {
  phase?: TaskPhase | null
  status?: TaskStatus | null
  archived?: boolean | null
  limit?: number
  cursor?: string | null
}

export interface TaskListPage {
  items: TaskSummary[]
  next_cursor: string | null
}

export interface AcceptanceSnapshot {
  task_id: string
  phase: TaskPhase
  status: TaskStatus
  revision: number
  requirements_revision: number
  deliverable_revision: number
  acceptance: Record<string, unknown>
  candidate: Record<string, unknown> | null
  checks: Record<string, unknown> | null
}

export interface ArtifactEntry {
  name: string
  path?: string | null
  ref?: string | null
  evidence_ref?: string | null
  media_type?: string | null
  size?: number | null
  run_ref?: string | null
  [key: string]: unknown
}

export interface TaskArtifacts {
  task_id: string
  task_revision: number
  requirements_revision: number | null
  deliverable_revision: number | null
  candidate_ref: string | null
  evidence_refs: string[]
  check_records: Array<Record<string, unknown>>
  workspace_ref: string | null
  categories: Record<string, ArtifactEntry[]>
  note: string | null
  evidence: ArtifactEntry[]
}

export type ControlAction =
  | 'enqueue'
  | 'pause'
  | 'resume'
  | 'cancel'
  | 'retry'
  | 'accept'
  | 'reject'
  | 'reopen'

export interface ControlActionRequest {
  action: ControlAction
  request_id: string
  expected_revision?: number | null
  target_run_id?: string | null
  decision?: string | null
  note?: string | null
  expected_requirements_revision?: number | null
  expected_deliverable_revision?: number | null
}

export interface ControlActionResult {
  action: string
  /** `requested` | `confirmed` | `unconfirmed` (docs/08 §4.3). */
  state: string
  confirmed: boolean
  task_id: string
  phase?: string
  acceptance?: Record<string, unknown>
  request_id?: string | null
  candidate_ref?: string | null
  messages?: string[]
  candidate?: Record<string, unknown> | null
  checks?: Record<string, unknown> | null
  stop?: Record<string, unknown> | null
}

export interface TaskEventRecord {
  event_id: string
  stream_id: string
  seq: number
  type: string
  at: string
  actor: string
  task_ref?: string | null
  run_ref?: string | null
  payload: Record<string, unknown>
}

export interface TaskEventPage {
  items: TaskEventRecord[]
  next_cursor: string | null
}

export interface TaskApi {
  listTasks(query?: TaskListQuery, signal?: AbortSignal): Promise<TaskListPage>
  getTask(taskId: string, signal?: AbortSignal): Promise<TaskDetail>
  readEvents(
    taskId: string,
    cursor?: string | null,
    signal?: AbortSignal,
  ): Promise<TaskEventPage>
  act(taskId: string, body: ControlActionRequest, signal?: AbortSignal): Promise<ControlActionResult>
  getAcceptance(taskId: string, signal?: AbortSignal): Promise<AcceptanceSnapshot>
  getArtifacts(taskId: string, signal?: AbortSignal): Promise<TaskArtifacts>
}

function withQuery(path: string, params: Record<string, string | number | boolean | null | undefined>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined || value === '') continue
    search.set(key, String(value))
  }
  const query = search.toString()
  return query ? `${path}?${query}` : path
}

export function createTaskApi(): TaskApi {
  return {
    listTasks(query = {}, signal) {
      return apiRequest<TaskListPage>(
        withQuery('/tasks', {
          phase: query.phase,
          status: query.status,
          archived: query.archived,
          limit: query.limit,
          cursor: query.cursor,
        }),
        { signal },
      )
    },
    getTask(taskId, signal) {
      return apiRequest<TaskDetail>(`/tasks/${encodeURIComponent(taskId)}`, { signal })
    },
    readEvents(taskId, cursor, signal) {
      return apiRequest<TaskEventPage>(
        withQuery(`/tasks/${encodeURIComponent(taskId)}/events`, { cursor }),
        { signal },
      )
    },
    act(taskId, body, signal) {
      return apiRequest<ControlActionResult>(
        `/tasks/${encodeURIComponent(taskId)}/actions`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
          signal,
        },
      )
    },
    getAcceptance(taskId, signal) {
      return apiRequest<AcceptanceSnapshot>(
        `/tasks/${encodeURIComponent(taskId)}/acceptance`,
        { signal },
      )
    },
    getArtifacts(taskId, signal) {
      return apiRequest<TaskArtifacts>(
        `/tasks/${encodeURIComponent(taskId)}/artifacts`,
        { signal },
      )
    },
  }
}

export const taskApi: TaskApi = createTaskApi()
