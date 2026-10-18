/**
 * Sources + lexical-search API client (LG-038; docs/08 §4.3, §6.6).
 *
 * This is the *only* new frontend wiring module for the unified material
 * experience: it calls the already-frozen, already-implemented endpoints
 *
 * * `POST /sources` — register one intake request (idempotent `request_id`);
 *   stores the original first and does **not** create a Task/Run/team.
 * * `GET /sources` / `GET /sources/{id}` / `.../receipt` — the same file state
 *   Files reads, so Chat receipts and Files never diverge.
 * * `GET /sources/{id}/content` / `.../download` — preview/download the
 *   original or the formal/machine version through the authorized resolver.
 * * `POST /sources/{id}/formal` — human correction with `expected_revision`
 *   (conflict is reported, never silently overwritten).
 * * `POST /sources/{id}/actions` — `reprocess`/`cancel`/`revoke`/`delete`.
 * * `POST /inbox/messages` — controlled inbox for global uploads (no Task).
 * * `GET /search` — lexical-first search; every hit is re-verified against the
 *   file SoT and carries `source_id`/`source_version`/`content_hash`.
 *
 * Boundaries kept deliberately (per LG-038 owner scope):
 * * No endpoint semantics are invented here. Where a capability is missing
 *   (`archive`/`tag`/`link` as a first-class action) the client does not
 *   fabricate it — see `probes/lg038/INTEGRATION.md`.
 * * `link` origins are records only: `fetched` stays `false` and the UI never
 *   claims a link became text.
 * * A missing/unconfigured OCR or vector service is surfaced honestly as the
 *   backend reports it (`capability_unavailable` / `index_unavailable`); the
 *   client never turns an embedding into text.
 * * The runtime token is injected, never persisted; upload is a protected
 *   write and fails honestly with `unauthorized` when none is available.
 */

import { newRuntimeId } from './chat'
import { ApiError, apiRequest } from './client'
import {
  API_PREFIX,
  type IntakeJobBudget,
  type IntakeWaitingReason,
  type SourceHitKind,
  type SourceIntakeMode,
  type SourceReceipt,
  type SourceReceiptEntry,
  type SourceReceiptV2,
  type SourceScope,
  type SourceSearchHit,
  type SourceSearchLocator,
  type SourceTextBranchState,
} from './types'

/* docs/08 §20 shared types stay in `types.ts` (LG-146 adapter seam). Re-export
 * them here so existing `from './sources'` imports keep working unchanged. */
export type {
  IntakeJobBudget,
  IntakeWaitingReason,
  SemanticSearchHit,
  SourceBranchState,
  SourceHitKind,
  SourceIntakeMode,
  SourceKeywordBranch,
  SourceKeywordBranchState,
  SourceReceipt,
  SourceReceiptEntry,
  SourceReceiptV2,
  SourceReceiptV2Item,
  SourceRef,
  SourceRefInput,
  SourceScope,
  SourceSemanticBranch,
  SourceSemanticBranchState,
  SourceSemanticKind,
  SourceSearchHit,
  SourceSearchLocator,
  SourceTextBranch,
  SourceTextBranchState,
  SourceTextMachineProvenance,
  SourceTranscriptTimestamp,
} from './types'

/* ------------------------------------------------------------- wire shapes */

export type SourceStatus =
  | 'received'
  | 'processing'
  | 'extracted'
  | 'attributed'
  | 'indexed'
  | 'archived'
  | 'partial'
  | 'failed'

export type LexicalState = 'not_indexed' | 'indexed' | 'stale' | 'failed'
export type VectorState = 'disabled' | 'not_indexed' | 'indexed' | 'stale' | 'failed'

export interface SourceOrigin {
  kind: string
  external_ref: string | null
  fetched: boolean
}

/**
 * LG-222 additive read-time routing projection for the explicit Reprocess
 * action. `kind` says which existing extractor would run; `available` is false
 * when that capability is unconfigured. It never implies an extraction already
 * ran and never contains model output.
 */
export interface SourceReprocessCapability {
  kind: 'ocr' | 'asr' | 'text' | 'none' | string
  available: boolean
  reason: string | null
  configured?: boolean | null
  enabled?: boolean | null
  /** PDFs use the text layer first; false means the OCR fallback is absent. */
  ocr_configured?: boolean | null
}

export interface SourceView {
  id: string
  source_id: string
  title: string | null
  title_origin: string | null
  status: SourceStatus | string
  /**
   * Reversible organizational archive flag (distinct from `status: archived`,
   * which the invalidating `revoke` sets). An archived source stays searchable
   * and openable; only revoke/delete make it unavailable.
   */
  archived?: boolean
  /** Additive 1.19.0 intake mode; absent on older sources (treat as `sync`). */
  intake_mode?: SourceIntakeMode
  /**
   * Additive 1.20.0 projection of the text branch: `"en"` only when a machine
   * English transcript is ready, otherwise `null`. It is not a second state
   * store and must not be inferred from a media vector hit.
   */
  language?: string | null
  /** Additive 1.20.0 text branch state (same enum as receipt `text.status`). */
  text_status?: SourceTextBranchState | string | null
  /** Read-time projection of actual selected-context text, independent of vectors. */
  context_selectable?: boolean
  context_unavailable_reason?: string | null
  revision: number
  etag: string
  scope: SourceScope
  origin: SourceOrigin
  content_hash: string | null
  /** Stat-based change token; explicitly NOT a cryptographic hash. */
  stat_revision: string | null
  source_version: number
  original: {
    path?: string | null
    media_type?: string | null
    bytes?: number | null
    archived_at?: string | null
  } | null
  derivatives: Array<Record<string, unknown>>
  formal: {
    path?: string | null
    revision?: number | null
    edited_by?: string | null
    /** Additive LG-223 human provenance; absent on legacy formal records. */
    origin?: string | null
  } | null
  index: { lexical?: string | null; lexical_hash?: string | null; vector?: string | null } | null
  /** Additive LG-222; absent on older backends (legacy fallback stays honest). */
  reprocess?: SourceReprocessCapability | null
  receipt_ref: string | null
  created_at: string | null
  updated_at: string | null
  path: string
}

export interface JobView {
  id: string
  job_id: string
  source_ref: string
  status: string
  revision: number
  request_id: string
  stage: string
  attempt?: number | null
  cancel?: { requested?: boolean; confirmed?: boolean } | null
  fail_reason?: string | null
  /** Additive 1.19.0 deferred-job fields (docs/08 §20.5); absent on sync jobs. */
  intake_mode?: SourceIntakeMode
  queued_at?: string | null
  started_at?: string | null
  finished_at?: string | null
  deadline_at?: string | null
  waiting_reason?: IntakeWaitingReason | null
  budget?: IntakeJobBudget | null
  created_at: string | null
  updated_at: string | null
}

export interface SourceListPage {
  items: SourceView[]
  next_cursor: string | null
}

export interface SourceContentView {
  source_id: string
  kind: 'formal' | 'machine' | string
  path: string | null
  media_type: string
  content: string
  formal_present: boolean
}

export interface SourceDownload {
  blob: Blob
  filename: string
  mediaType: string
  /** Stat revision of the served layer (documents/formal return the entity revision). */
  statRevision: string | null
  kind: string
  contentHash: string | null
}

export type SearchLocator = SourceSearchLocator

export interface SearchHit extends SourceSearchHit {
  /** Semantic hits only; legacy lexical hits omit it. */
  kind?: SourceHitKind | string
}

export interface SearchStaleEntry {
  source_id?: string
  reason?: string
  [key: string]: unknown
}

export interface SearchResult {
  query: string
  kind: string[]
  hits: SearchHit[]
  stale: SearchStaleEntry[]
  skipped: SearchStaleEntry[]
  index_status: 'ok' | 'index_unavailable' | string
  index_unavailable_reason?: string
  authorized_scope: {
    task_ref: string | null
    project_ref: string | null
    inbox_ref: string | null
    include_global: boolean
  }
}

export interface SourceCreateInput {
  request_id: string
  filename: string
  /** Exactly one of `path` (workspace-relative) or `content_base64` must be set. */
  path?: string
  content_base64?: string
  media_type?: string | null
  title?: string | null
  title_origin?: 'user' | 'derived'
  scope?: Partial<SourceScope>
  origin?: { kind?: string; external_ref?: string | null; fetched?: boolean }
  payload_hash?: string | null
  /**
   * Additive 1.19.0 field (docs/08 §20.4). Omit/`sync` for the 1.18 path;
   * `deferred` requires the `material_intake_v2` gate. It is sent as part of
   * the normal POST /sources body, so no separate runtime call is needed.
   */
  intake_mode?: SourceIntakeMode
}

export interface SourceCreateResult {
  source: SourceView
  job: JobView | null
  deduplicated: boolean
  created: boolean
  receipts: SourceReceiptEntry[]
  /** Echoed by 1.19.0 deferred responses; absent on the 1.18 sync path. */
  intake_mode?: SourceIntakeMode
}

export interface SourceSearchQuery {
  q: string
  task_ref?: string | null
  project_ref?: string | null
  inbox_ref?: string | null
  include_global?: boolean
  limit?: number
  rebuild_if_missing?: boolean
}

export interface InboxMessageResult {
  inbox_ref: string
  message: Record<string, unknown>
  task_created: false
  run_created: false
}

export interface IntakeJobActionResult {
  job_id: string
  action: string
  status: string
  confirmed: boolean
  [key: string]: unknown
}

export interface SourcesRuntimeConfig {
  apiToken?: string | null
  getApiToken?: () => string | null
}

/* ------------------------------------------------------------------ client */

export interface SourcesApi {
  createSource(input: SourceCreateInput, signal?: AbortSignal): Promise<SourceCreateResult>
  listSources(
    filter?: {
      task_ref?: string | null
      project_ref?: string | null
      inbox_ref?: string | null
      limit?: number
      cursor?: string | null
    },
    signal?: AbortSignal,
  ): Promise<SourceListPage>
  getSource(sourceId: string, signal?: AbortSignal): Promise<SourceView>
  /**
   * Existing 1.18 read endpoint; 1.19.0 responses may additionally satisfy
   * `SourceReceiptV2` (check with `isSourceReceiptV2`).
   */
  getReceipt(sourceId: string, signal?: AbortSignal): Promise<SourceReceipt>
  /** `GET /intake/jobs/{id}`; job fields are additive in 1.19.0. */
  getIntakeJob?(jobId: string, signal?: AbortSignal): Promise<JobView>
  /** `POST /intake/jobs/{id}/actions` (`cancel`/`retry`, docs/08 §20.9). */
  intakeJobAction?(
    jobId: string,
    body: { action: 'cancel' | 'retry'; confirmed?: boolean; note?: string | null },
    signal?: AbortSignal,
  ): Promise<IntakeJobActionResult>
  getContent(
    sourceId: string,
    kind: 'auto' | 'formal' | 'machine',
    signal?: AbortSignal,
  ): Promise<SourceContentView>
  downloadSource(
    sourceId: string,
    kind: 'original' | 'formal' | 'machine',
    signal?: AbortSignal,
  ): Promise<SourceDownload>
  editFormal(
    sourceId: string,
    body: { content: string; edited_by?: string; expected_revision?: number | null },
    signal?: AbortSignal,
  ): Promise<{ source_id: string; formal: unknown; revision: number }>
  sourceAction(
    sourceId: string,
    body: {
      action: string
      job_id?: string | null
      confirmed?: boolean
      note?: string | null
      expected_revision?: number | null
    },
    signal?: AbortSignal,
  ): Promise<Record<string, unknown>>
  appendInboxMessage(
    body: {
      message_id: string
      content: string
      inbox_ref?: string | null
      attachment_base64?: string | null
      attachment_filename?: string | null
      media_type?: string | null
    },
    signal?: AbortSignal,
  ): Promise<InboxMessageResult>
  search(query: SourceSearchQuery, signal?: AbortSignal): Promise<SearchResult>
}

const TOKEN_HEADER = 'X-LG-Token'

function runtimeToken(runtime: SourcesRuntimeConfig | undefined): string | null {
  if (!runtime) return null
  const value = runtime.getApiToken ? runtime.getApiToken() : runtime.apiToken
  return typeof value === 'string' && value.length > 0 ? value : null
}

function authHeaders(runtime: SourcesRuntimeConfig | undefined): Record<string, string> {
  const token = runtimeToken(runtime)
  return token ? { [TOKEN_HEADER]: token } : {}
}

function query(params: Record<string, string | number | boolean | null | undefined>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue
    search.set(key, String(value))
  }
  const text = search.toString()
  return text ? `?${text}` : ''
}

function parseFilename(header: string | null, fallback: string): string {
  if (!header) return fallback
  const starred = /filename\*=UTF-8''([^;]+)/i.exec(header)
  if (starred) {
    try {
      return decodeURIComponent(starred[1])
    } catch {
      /* fall through to the plain form */
    }
  }
  const plain = /filename="([^"]+)"/i.exec(header)
  return plain ? plain[1] : fallback
}

function isErrorEnvelope(
  value: unknown,
): value is {
  error: {
    code: string
    message: string
    retryable?: boolean
    details?: Record<string, unknown>
    request_id?: string | null
  }
} {
  if (!value || typeof value !== 'object') return false
  const candidate = value as { error?: unknown }
  return Boolean(candidate.error && typeof candidate.error === 'object')
}

async function toApiError(response: Response): Promise<ApiError> {
  const contentType = response.headers.get('content-type') ?? ''
  const payload: unknown = contentType.includes('application/json')
    ? await response.json().catch(() => null)
    : null
  if (isErrorEnvelope(payload)) {
    return new ApiError({
      message: payload.error.message,
      code: payload.error.code,
      httpStatus: response.status,
      retryable: payload.error.retryable ?? false,
      details: payload.error.details,
      requestId: payload.error.request_id,
    })
  }
  return new ApiError({
    message: `Request failed with status ${response.status}`,
    code: 'internal_error',
    httpStatus: response.status,
    retryable: response.status >= 500,
  })
}

export function createSourcesApi(runtime: SourcesRuntimeConfig = {}): SourcesApi {
  return {
    createSource(input, signal) {
      return apiRequest<SourceCreateResult>('/sources', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders(runtime) },
        body: JSON.stringify(input),
        signal,
      })
    },

    listSources(filter = {}, signal) {
      return apiRequest<SourceListPage>(
        `/sources${query({
          task_ref: filter.task_ref ?? undefined,
          project_ref: filter.project_ref ?? undefined,
          inbox_ref: filter.inbox_ref ?? undefined,
          limit: filter.limit,
          cursor: filter.cursor ?? undefined,
        })}`,
        { signal },
      )
    },

    getSource(sourceId, signal) {
      return apiRequest<SourceView>(`/sources/${encodeURIComponent(sourceId)}`, { signal })
    },

    getReceipt(sourceId, signal) {
      return apiRequest<SourceReceipt>(
        `/sources/${encodeURIComponent(sourceId)}/receipt`,
        { signal },
      )
    },

    getIntakeJob(jobId, signal) {
      return apiRequest<JobView>(`/intake/jobs/${encodeURIComponent(jobId)}`, { signal })
    },

    intakeJobAction(jobId, body, signal) {
      return apiRequest<IntakeJobActionResult>(
        `/intake/jobs/${encodeURIComponent(jobId)}/actions`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', ...authHeaders(runtime) },
          body: JSON.stringify({
            action: body.action,
            confirmed: body.confirmed ?? false,
            note: body.note ?? null,
          }),
          signal,
        },
      )
    },

    getContent(sourceId, kind, signal) {
      return apiRequest<SourceContentView>(
        `/sources/${encodeURIComponent(sourceId)}/content${query({ kind })}`,
        { signal },
      )
    },

    async downloadSource(sourceId, kind, signal) {
      const response = await fetch(
        `${API_PREFIX}/sources/${encodeURIComponent(sourceId)}/download${query({ kind })}`,
        {
          // Same-origin session cookie for team mode (LG-050 §7).
          credentials: 'include',
          headers: { Accept: '*/*', ...authHeaders(runtime) },
          signal,
        },
      ).catch((cause: unknown) => {
        throw new ApiError({
          message: cause instanceof Error ? cause.message : 'Network request failed',
          code: 'network_error',
          httpStatus: null,
          retryable: true,
        })
      })
      if (!response.ok) throw await toApiError(response)
      return {
        blob: await response.blob(),
        filename: parseFilename(response.headers.get('content-disposition'), 'source.bin'),
        mediaType: response.headers.get('content-type') ?? 'application/octet-stream',
        statRevision: response.headers.get('x-lg-stat-revision') || null,
        kind: response.headers.get('x-lg-kind') || kind,
        contentHash: null,
      }
    },

    editFormal(sourceId, body, signal) {
      return apiRequest<{ source_id: string; formal: unknown; revision: number }>(
        `/sources/${encodeURIComponent(sourceId)}/formal`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', ...authHeaders(runtime) },
          body: JSON.stringify({
            content: body.content,
            edited_by: body.edited_by ?? 'user',
            expected_revision: body.expected_revision ?? null,
          }),
          signal,
        },
      )
    },

    sourceAction(sourceId, body, signal) {
      return apiRequest<Record<string, unknown>>(
        `/sources/${encodeURIComponent(sourceId)}/actions`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', ...authHeaders(runtime) },
          body: JSON.stringify({
            action: body.action,
            job_id: body.job_id ?? null,
            confirmed: body.confirmed ?? false,
            note: body.note ?? null,
            expected_revision: body.expected_revision ?? null,
          }),
          signal,
        },
      )
    },

    appendInboxMessage(body, signal) {
      return apiRequest<InboxMessageResult>('/inbox/messages', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders(runtime) },
        body: JSON.stringify(body),
        signal,
      })
    },

    search(queryInput, signal) {
      return apiRequest<SearchResult>(
        `/search${query({
          q: queryInput.q,
          task_ref: queryInput.task_ref ?? undefined,
          project_ref: queryInput.project_ref ?? undefined,
          inbox_ref: queryInput.inbox_ref ?? undefined,
          include_global: queryInput.include_global,
          limit: queryInput.limit,
          rebuild_if_missing: queryInput.rebuild_if_missing,
        })}`,
        { signal },
      )
    },
  }
}

/** Default (token-less) client: reads work; protected writes fail honestly. */
export const sourcesApi = createSourcesApi()

/**
 * Narrow a receipt read to the 1.19.0 v2 shape. Only call consumers behind the
 * `material_intake_v2` capability gate; a legacy 1.18 receipt returns false.
 */
export function isSourceReceiptV2(
  receipt: SourceReceipt | null | undefined,
): receipt is SourceReceiptV2 {
  return Boolean(
    receipt &&
      receipt.receipt_version === 2 &&
      typeof receipt.partial === 'boolean' &&
      receipt.items.every(
        (item) => Boolean(item.text && item.keyword && item.semantic),
      ),
  )
}

/** A stable, well-formed intake request id (`req_<ULID>`). */
export function newIntakeRequestId(): string {
  return newRuntimeId('req')
}
