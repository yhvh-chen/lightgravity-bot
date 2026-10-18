/**
 * Shared API wire types aligned to docs/08-interface-contract.md v1.0.0.
 *
 * Only the frozen shapes needed by the shell (error envelope + meta endpoints)
 * are declared here. View tasks (LG-013/014/015/026) extend this module with
 * the endpoints they own; do not fork a second copy of contract types.
 */

import type { EnglishAsrModelRef } from './englishAsr'

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

/* --------------------------------------- Material intake v2 (docs/08 §20, 1.19.0)
 *
 * Contract-only shapes: docs/08 §20 freezes these as additive 1.19.0 fields,
 * but the running product is still 1.18.0. Consumers must not use them unless
 * the matching health capability is true (see backendCompatibility.ts), and
 * old responses/backends omit every one of them.
 */

/** One source scope. `null` refs mean the global/shared scope. */
export interface SourceScope {
  task_ref: string | null
  project_ref: string | null
  inbox_ref: string | null
}

/** `POST /sources` intake mode; omitted/`sync` keeps the 1.18 behavior. */
export type SourceIntakeMode = 'sync' | 'deferred'

/** One `source_refs` request item: only the stable source id is accepted. */
export interface SourceRefInput {
  source_id: string
}

/**
 * Server-normalized, persisted message `source_refs` snapshot (docs/08 §20.3).
 * Receipt/traceability only: it never becomes model context and never
 * replaces the explicit `selected_sources` selector.
 */
export interface SourceRef {
  source_id: string
  source_version: number
  content_hash: string
  scope: SourceScope
}

/** Maximum unique refs in one message submission (docs/08 §20.3). */
export const MESSAGE_SOURCE_REFS_MAX = 10

/** Receipt v2 discriminator (docs/08 §20.6). */
export const SOURCE_RECEIPT_VERSION_V2 = 2

/* Frozen intake bounds (docs/08 §20.5/§20.8); values are contract facts. */
export const INTAKE_MAX_ORIGINAL_BYTES = 10_000_000
export const INTAKE_MAX_NATIVE_TEXT_BYTES = 2_000_000
export const INTAKE_MAX_OCR_PAGES = 100
export const INTAKE_MAX_TOKENS_PER_PAGE = 2000
export const INTAKE_MAX_EMBEDDING_CALLS = 2
export const INTAKE_MAX_RETRIES = 1
export const INTAKE_TIMEOUT_SECONDS = 900
export const INTAKE_MAX_CONCURRENT_JOBS = 2

/** `intake_job.budget`, additive in 1.19.0; old jobs omit the new keys. */
export interface IntakeJobBudget {
  max_model_calls?: number | null
  timeout_seconds?: number | null
  max_retries?: number | null
  max_original_bytes?: number | null
  max_native_text_bytes?: number | null
  max_ocr_pages?: number | null
  max_tokens_per_page?: number | null
  max_embedding_calls?: number | null
  max_media_embedding_bytes?: number | null
  [key: string]: unknown
}

/** Why a deferred job is waiting; absent/null means not waiting. */
export type IntakeWaitingReason = 'worker_limit' | 'cancelling'

/** Independent text branch states (docs/08 §20.6). */
export type SourceTextBranchState =
  | 'pending'
  | 'extracting'
  | 'ready'
  | 'unavailable'
  | 'failed'

/** Independent lexical/keyword branch states (docs/08 §20.6). */
export type SourceKeywordBranchState =
  | 'pending'
  | 'indexing'
  | 'searchable'
  | 'no_text'
  | 'failed'

/** Independent semantic/vector branch states (docs/08 §20.6). */
export type SourceSemanticBranchState =
  | 'pending'
  | 'indexing'
  | 'searchable'
  | 'disabled'
  | 'unsupported'
  | 'failed'

/** Any receipt branch state; branch-specific meaning stays in the object. */
export type SourceBranchState =
  | SourceTextBranchState
  | SourceKeywordBranchState
  | SourceSemanticBranchState

/** `unsupported` is never used for a vendor rejection/timeout. */
export type SourceSemanticKind = 'text' | 'image' | 'audio'

/** One verified machine timestamp (future decoder output; never fabricated). */
export interface SourceTranscriptTimestamp {
  start_seconds: number
  end_seconds: number
  text: string
}

/**
 * Additive 1.20.0 machine ASR provenance on a ready text branch. It is
 * provenance only: the transcript body is read from the existing machine
 * content endpoint. `timestamps` is `null` when the decoder has no alignment.
 */
export interface SourceTextMachineProvenance {
  engine?: string | null
  encoder?: EnglishAsrModelRef | null
  reader?: EnglishAsrModelRef | null
  runtime?: string | null
  model_version?: string | null
  content_variant?: string | null
  generated_at?: string | null
  [key: string]: unknown
}

export interface SourceTextBranch {
  status: SourceTextBranchState
  reason: string | null
  error_code: string | null
  /** Additive 1.20.0: `"en"` only while a machine English transcript is ready. */
  language?: string | null
  /** Additive 1.20.0 provenance for a machine English transcript. */
  machine?: SourceTextMachineProvenance | null
  /** Additive 1.20.0; `null` means no verified alignment, so no seek markers. */
  timestamps?: SourceTranscriptTimestamp[] | null
}

export interface SourceKeywordBranch {
  status: SourceKeywordBranchState
  reason: string | null
  error_code: string | null
}

export interface SourceSemanticBranch {
  status: SourceSemanticBranchState
  reason: string | null
  error_code: string | null
  model: string | null
  /** Only kinds actually written to the vector cache. */
  kinds: SourceSemanticKind[]
  /** Kinds that were attempted and failed; may be non-empty while searchable. */
  failed_kinds: SourceSemanticKind[]
}

/**
 * Legacy receipt entry (1.18 fields). The branch objects are additive and may
 * be absent on old backends or non-v2 receipts.
 */
export interface SourceReceiptEntry {
  status?: string
  stage?: string
  message?: string
  text?: SourceTextBranch
  keyword?: SourceKeywordBranch
  semantic?: SourceSemanticBranch
  [key: string]: unknown
}

/** Legacy receipt projection; `receipt_version`/`partial` are additive. */
export interface SourceReceipt {
  source_id: string
  revision: number
  status: string
  source_version: number
  receipt_version?: number
  partial?: boolean
  items: SourceReceiptEntry[]
  latest: SourceReceiptEntry | null
}

/** One v2 receipt item: all three branch objects are present. */
export interface SourceReceiptV2Item extends SourceReceiptEntry {
  text: SourceTextBranch
  keyword: SourceKeywordBranch
  semantic: SourceSemanticBranch
}

/** `GET /sources/{id}/receipt` receipt_version=2 projection. */
export interface SourceReceiptV2 extends SourceReceipt {
  receipt_version: typeof SOURCE_RECEIPT_VERSION_V2
  partial: boolean
  items: SourceReceiptV2Item[]
  latest: SourceReceiptV2Item | null
}

/* ------------------------------------------- Shared search hit shapes (LG-143) */

export interface SourceSearchLocator {
  kind?: string
  page?: number | null
  offset?: number | null
  [key: string]: unknown
}

/** Common verified hit fields; lexical and semantic hits share them. */
export interface SourceSearchHit {
  source_id: string
  source_version: number
  content_hash: string | null
  basis: string
  scope: SourceScope
  title: string | null
  locators: SourceSearchLocator[]
  snippet: string
  verified: boolean
  stale: boolean
  reason: string | null
}

/** `GET /vector/search` additive hit kind (docs/08 §20.10). */
export type SourceHitKind = 'text' | 'image' | 'audio'

/** Semantic hit: `kind` says which vector basis matched, not that a transcript exists. */
export interface SemanticSearchHit extends SourceSearchHit {
  kind: SourceHitKind
}

/* ------------------------------------------------------- Task wire shapes (docs/08 §6) */

/** Shared Task/Team message attachment reference (docs/08 §5.2): no bytes. */
export interface PathAttachment {
  path: string
  media_type?: string | null
}

/**
 * LG-119 Personal-only private attachment.  The request shape is exactly
 * `{attachment_id}`; the server expands the canonical persisted snapshot
 * (filename/size/hash/status/context fields) after owner validation.  A client
 * can never supply filename/size/hash as authority.
 */
export interface PrivateAttachmentRef {
  attachment_id: string
  filename?: string
  media_type?: string | null
  size?: number
  sha256?: string
  status?: 'stored' | 'attached'
  created_at?: string
  message_id?: string | null
  context_status?:
    | 'included'
    | 'truncated'
    | 'unsupported_type'
    | 'binary_unsupported'
    | 'too_large'
    | 'unavailable'
  context_chars?: number
}

/** Discriminated by `attachment_id`: Personal private vs Task/Team path. */
export type Attachment = PathAttachment | PrivateAttachmentRef

export function isPrivateAttachment(
  attachment: Attachment,
): attachment is PrivateAttachmentRef {
  return 'attachment_id' in attachment
}

/** Queue projection embedded in a Task summary/detail (docs/08 §6.1). */
export interface QueueProjection {
  state: QueueState
  owner?: string | null
  lease_expires_at?: string | null
  order?: number | null
  queued_at?: string | null
  /** Additive R2 scheduling fact (docs/08 §19.5); absent means no wait. */
  waiting_reason?: string | null
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
