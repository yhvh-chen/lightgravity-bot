/**
 * Search / vector wire client (LG-143; docs/08 §20.10).
 *
 * This module is the new search API surface consumed by the Keyword/Semantic
 * panel. It deliberately uses the shared LG-146 types (`SourceSearchHit`,
 * `SemanticSearchHit`, `SourceHitKind`) instead of forking another hit shape.
 *
 * Boundaries:
 * * `GET /search` and `GET /vector/search` are read-only. New UI calls never
 *   send the deprecated `rebuild_if_missing=true`; a missing/mismatched cache
 *   is reported for an explicit protected rebuild in Settings.
 * * `POST /vector/rebuild` is the only full-rebuild wire method. It is exposed
 *   here for Settings/integration (LG-144) behind the protected token/session;
 *   the search panel never calls it.
 * * `GET /vector/status` is a non-sensitive, read-only status read.
 */

import { ApiError, apiRequest } from './client'
import type {
  SearchResult,
  SearchStaleEntry,
  SourceSearchHit,
} from './sources'
import type { SemanticSearchHit, SourceHitKind } from './types'

export const TOKEN_HEADER = 'X-LG-Token'

/** Search inputs shared by the lexical and semantic endpoints. */
export interface MaterialSearchQuery {
  q: string
  task_ref?: string | null
  project_ref?: string | null
  inbox_ref?: string | null
  include_global?: boolean
  limit?: number
}

/** Semantic hits carry `kind`; scores remain backend-internal and unmixed. */
export interface SemanticSearchResult
  extends Omit<SearchResult, 'hits'> {
  hits: SemanticSearchHit[]
}

/** `GET /vector/status` projection (never a model call). */
export interface VectorStatusView {
  enabled: boolean
  backend?: {
    configured?: boolean
    model?: string | null
    source?: string | null
  } | null
  cache?: {
    exists?: boolean
    readable?: boolean
    documents?: number
    cache_version?: number | null
    model?: string | null
    dim?: number | null
    compatible?: boolean | null
    reason?: string | null
    vector_model?: string | null
  } | null
  model_mismatch_rebuild_required?: boolean
  reason?: string | null
}

export interface VectorRebuildResult {
  rebuilt: boolean
  indexed: string[]
  not_indexed: string[]
  documents: number
  model?: string | null
  dim?: number | null
  states?: Array<Record<string, unknown>>
  vector?: string
  [key: string]: unknown
}

export interface SearchRuntimeConfig {
  apiToken?: string | null
  getApiToken?: () => string | null
}

export interface SearchApi {
  searchKeyword(
    query: MaterialSearchQuery,
    signal?: AbortSignal,
  ): Promise<SearchResult>
  searchSemantic(
    query: MaterialSearchQuery,
    signal?: AbortSignal,
  ): Promise<SemanticSearchResult>
  getVectorStatus(signal?: AbortSignal): Promise<VectorStatusView>
  /** Explicit protected full rebuild; never called by search rendering. */
  rebuildVector(signal?: AbortSignal): Promise<VectorRebuildResult>
}

function tokenOf(runtime: SearchRuntimeConfig | undefined): string | null {
  if (!runtime) return null
  const value = runtime.getApiToken ? runtime.getApiToken() : runtime.apiToken
  return typeof value === 'string' && value.length > 0 ? value : null
}

function queryString(
  params: Record<string, string | number | boolean | null | undefined>,
): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue
    search.set(key, String(value))
  }
  const text = search.toString()
  return text ? `?${text}` : ''
}

function searchParams(query: MaterialSearchQuery) {
  return {
    q: query.q,
    task_ref: query.task_ref ?? undefined,
    project_ref: query.project_ref ?? undefined,
    inbox_ref: query.inbox_ref ?? undefined,
    include_global: query.include_global,
    limit: query.limit,
  }
}

export function createSearchApi(runtime: SearchRuntimeConfig = {}): SearchApi {
  return {
    searchKeyword(query, signal) {
      return apiRequest<SearchResult>(`/search${queryString(searchParams(query))}`, {
        signal,
      })
    },

    searchSemantic(query, signal) {
      // No `rebuild_if_missing`: semantic search is read-only from the UI.
      return apiRequest<SemanticSearchResult>(
        `/vector/search${queryString(searchParams(query))}`,
        { signal },
      )
    },

    getVectorStatus(signal) {
      return apiRequest<VectorStatusView>('/vector/status', { signal })
    },

    rebuildVector(signal) {
      const token = tokenOf(runtime)
      return apiRequest<VectorRebuildResult>('/vector/rebuild', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { [TOKEN_HEADER]: token } : {}),
        },
        body: '{}',
        signal,
      })
    },
  }
}

/** Default client (session-cookie auth for protected rebuild when in team mode). */
export const searchApi = createSearchApi()

/** Small helpers kept here so the panel and tests agree on honest labels. */

export function isSemanticHit(hit: SourceSearchHit): hit is SemanticSearchHit {
  const kind = (hit as { kind?: unknown }).kind
  return kind === 'text' || kind === 'image' || kind === 'audio'
}

export function hitKind(hit: SourceSearchHit): SourceHitKind | null {
  return isSemanticHit(hit) ? hit.kind : null
}

export function unavailableReason(
  result: Pick<SearchResult, 'index_unavailable_reason'> | null,
): string | null {
  return result?.index_unavailable_reason ?? null
}

/** A stale entry keeps its backend reason; callers must not invent success. */
export function staleReason(entry: SearchStaleEntry): string {
  return typeof entry.reason === 'string' && entry.reason ? entry.reason : 'source_stale'
}

/** Normalize an unknown failure into the shared ApiError shape for rendering. */
export function asSearchError(cause: unknown): ApiError {
  if (cause instanceof ApiError) return cause
  return new ApiError({
    message: cause instanceof Error ? cause.message : 'Search failed',
    code: 'internal_error',
    httpStatus: null,
    retryable: false,
  })
}
