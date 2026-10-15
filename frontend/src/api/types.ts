/**
 * Shared API wire types aligned to docs/08-interface-contract.md v1.0.0.
 *
 * Only the frozen shapes needed by the shell (error envelope + meta endpoints)
 * are declared here. View tasks (LG-013/014/015/026) extend this module with
 * the endpoints they own; do not fork a second copy of contract types.
 */

export const API_PREFIX = '/api/v1'
export const SCHEMA_NAMESPACE = 'lightgravity.bot/v1'

export type ErrorCode =
  | 'invalid_request'
  | 'unauthorized'
  | 'path_outside_workspace'
  | 'not_found'
  | 'revision_conflict'
  | 'lock_conflict'
  | 'not_ready'
  | 'illegal_transition'
  | 'cancellation_unconfirmed'
  | 'acceptance_stale'
  | 'config_invalid'
  | 'reference_invalid'
  | 'validation_failed'
  | 'budget_exhausted'
  | 'capability_unavailable'
  | 'internal_error'

export interface ErrorBody {
  code: ErrorCode | string
  message: string
  details: Record<string, unknown>
  retryable: boolean
  request_id: string | null
}

export interface ErrorEnvelope {
  error: ErrorBody
}

export interface HealthResponse {
  status: string
  package_version: string
  contract_version: string
  schema_version: string
  capabilities: Record<string, boolean>
}

export interface VersionResponse {
  contract_version: string
  schema_version: string
  package_version: string
  python_version: string
  platform: string
}

/* ------------------------------------------------------- Task wire shapes (docs/08 §6) */

/** Message attachment reference (docs/08 §5.2): a path + media type, no bytes. */
export interface Attachment {
  path: string
  media_type?: string | null
}

/** Queue projection embedded in a Task summary/detail (docs/08 §6.1). */
export interface QueueProjection {
  state: QueueState
  owner?: string | null
  lease_expires_at?: string | null
  order?: number | null
  queued_at?: string | null
}

/** `GET /tasks` list item (docs/08 §4.3). */
export interface TaskSummary {
  id: string
  task_id: string
  title: string
  status: TaskStatus
  phase: TaskPhase
  revision: number
  etag: string
  requirements_revision: number
  queue: QueueProjection
  archived: boolean
}

/** Subtask projection within a Task's active Run (docs/08 §6.3). */
export interface SubtaskSummary {
  id: string
  state: SubtaskState
  objective?: string | null
  capability?: string | null
  key?: string | null
  fail_reason?: string | null
  acceptance?: { status?: string | null } | null
  [key: string]: unknown
}

/** Member projection within a Task's active Run (docs/08 §6.4). */
export interface MemberSummary {
  id: string
  title?: string | null
  state: MemberState | null
  role_ref?: string | null
  [key: string]: unknown
}

/** Run projection within a Task detail (docs/08 §6.2). */
export interface RunSummary {
  id: string
  state: RunState | string
  plan_source?: string | null
  fail_reason?: string | null
  [key: string]: unknown
}

/** `GET /tasks/{task_id}` detail (docs/08 §4.3). */
export interface TaskDetail extends TaskSummary {
  run: RunSummary | null
  members: MemberSummary[]
  subtasks: SubtaskSummary[]
  body?: string | null
  acceptance?: Record<string, unknown> | null
  workspace_ref?: string | null
}

/* ------------------------------------------------------- Frozen enums (docs/08 §6) */

export type TaskStatus = 'todo' | 'in-progress' | 'done'

export type TaskPhase =
  | 'intake'
  | 'queued'
  | 'waiting_dependencies'
  | 'planning'
  | 'recruiting'
  | 'executing'
  | 'verifying'
  | 'repairing'
  | 'waiting_user'
  | 'pausing'
  | 'paused'
  | 'cancelling'
  | 'awaiting_acceptance'
  | 'recovery_required'
  | 'failed'
  | 'cancelled'
  | 'completed'

export type RunState =
  | 'planning'
  | 'recruiting'
  | 'executing'
  | 'verifying'
  | 'awaiting_acceptance'
  | 'completed'
  | 'waiting_user'
  | 'pausing'
  | 'paused'
  | 'recovery_required'
  | 'failed'
  | 'cancelling'
  | 'cancelled'

export type SubtaskState =
  | 'pending'
  | 'ready'
  | 'running'
  | 'verifying'
  | 'passed'
  | 'repairing'
  | 'waiting_user'
  | 'paused'
  | 'failed'
  | 'cancelled'

export type MemberState =
  | 'recruiting'
  | 'ready'
  | 'running'
  | 'released'
  | 'waiting_user'
  | 'failed'

export type QueueState = 'not_queued' | 'queued' | 'claimed'

/** Default single-user local port, per docs/08 §10. */
export const DEFAULT_API_ORIGIN = 'http://127.0.0.1:8000'
