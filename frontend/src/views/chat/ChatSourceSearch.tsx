/**
 * Chat source search (LG-038; docs/09 §5, §7, docs/08 §20.10).
 *
 * Lets the user query materials from Chat. Every hit is already re-verified by
 * the backend against the file SoT, so this component:
 *
 * * keeps Keyword as the default and shows Semantic only behind the runtime
 *   `semantic_search` capability;
 * * keeps the two result sets separate (no score blending);
 * * shows the source id, version and content hash for each hit;
 * * lets the user open the hit in Files, where the same source state is read;
 * * surfaces stale/invalidated hits explicitly;
 * * reports `index_unavailable`, a disabled backend or a model mismatch
 *   honestly and offers an explicit switch back to Keyword;
 * * labels media hits by vector kind and never calls an audio vector a
 *   transcript.
 */

import type { SearchApi } from '../../api/search'
import type { SearchHit, SourcesApi } from '../../api/sources'
import { EmptyState } from '../../components/EmptyState'
import { ErrorState } from '../../components/ErrorState'
import { StatusBadge } from '../../components/StatusBadge'
import {
  useMaterialSearch,
  type MaterialSearchController,
  type MaterialSearchMode,
} from '../../components/useMaterialSearch'
import './search.css'

export interface ChatSourceSearchProps {
  api: SourcesApi
  taskRef: string | null
  /** Open one source's authoritative view (Files) at this id. */
  onOpen: (sourceId: string) => void
  /** Lend the search state from the top bar instead of owning a second input. */
  controller?: MaterialSearchController
  /** Set false when the caller already renders the editable top-bar input. */
  showInput?: boolean
  /** Runtime `semantic_search` capability; false renders no Semantic toggle. */
  semanticEnabled?: boolean
  /** Runtime `media_direct_embedding` capability, only used for the badge. */
  mediaDirectEmbedding?: boolean
  /** Protected rebuild availability, for honest guidance only (never a button). */
  canRebuild?: boolean
  /** Identity role from the shell seam; never inferred or hard-coded here. */
  role?: string | null
  /** Injectable vector/search client for the internal controller (tests/seam). */
  searchApi?: SearchApi
}

export function ChatSourceSearch({
  api,
  taskRef,
  onOpen,
  controller,
  showInput = true,
  semanticEnabled = false,
  mediaDirectEmbedding = false,
  canRebuild = false,
  role = null,
  searchApi,
}: ChatSourceSearchProps) {
  const internal = useMaterialSearch(api, taskRef, {
    searchApi,
    semanticEnabled,
  })
  const search = controller ?? internal
  const { draft, setDraft, result, loading, error, run, mode, setMode } = search

  return (
    <section className="lg-source-search" aria-label="Material search">
      {semanticEnabled ? (
        <div className="lg-search-modes" role="tablist" aria-label="Search mode">
          <button
            type="button"
            role="tab"
            aria-selected={mode === 'keyword'}
            className={`lg-search-mode${mode === 'keyword' ? ' lg-search-mode--active' : ''}`}
            onClick={() => setMode('keyword')}
          >
            Keyword
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={mode === 'semantic'}
            className={`lg-search-mode${mode === 'semantic' ? ' lg-search-mode--active' : ''}`}
            onClick={() => setMode('semantic')}
          >
            Semantic
          </button>
          <span className="lg-search-modes__hint">
            {mode === 'keyword'
              ? 'Lexical matches · separate from semantic results'
              : 'Vector matches · not a transcript or OCR-quality claim'}
          </span>
        </div>
      ) : null}

      {showInput ? (
        <div className="lg-source-search__row">
          <input
            type="text"
            className="lg-input"
            placeholder={
              mode === 'semantic'
                ? 'Search your materials (semantic)…'
                : 'Search your materials (lexical)…'
            }
            aria-label="Search materials"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                event.preventDefault()
                run()
              }
            }}
          />
          <button
            type="button"
            className="lg-button"
            onClick={() => run()}
            disabled={loading || !draft.trim()}
          >
            Search
          </button>
        </div>
      ) : null}

      {mode === 'semantic' ? (
        <SemanticAvailability
          search={search}
          canRebuild={canRebuild}
          role={role}
        />
      ) : null}

      {loading ? (
        <p className="lg-materials__hint">
          {mode === 'semantic' ? 'Searching semantic index…' : 'Searching…'}
        </p>
      ) : null}

      {error ? (
        <ErrorState
          title={mode === 'semantic' ? 'Semantic search failed' : 'Search failed'}
          message={error.message}
          code={error.code}
          retryable={error.retryable}
          onRetry={() => run()}
        />
      ) : null}

      {result && result.index_status !== 'ok' ? (
        <div className="lg-notice lg-search-notice" role="status">
          <p>
            {mode === 'semantic' ? 'Semantic index unavailable' : 'Search index unavailable'} (
            {result.index_unavailable_reason ?? 'unknown'}). Original files are still viewable in
            Files; an explicit protected rebuild may be needed.
          </p>
          {mode === 'semantic' ? (
            <button type="button" className="lg-link-button" onClick={search.fallbackToKeyword}>
              Switch to Keyword
            </button>
          ) : null}
        </div>
      ) : null}

      {result && result.index_status === 'ok' && result.hits.length === 0 ? (
        <EmptyState
          title={mode === 'semantic' ? 'No semantic matches' : 'No matching material'}
          compact
        >
          {mode === 'semantic'
            ? 'Nothing in your authorized scope matched a vector. Audio can only match through a media vector; it has no transcript.'
            : 'Nothing in your authorized scope matched. Materials with no trusted body are not indexed.'}
        </EmptyState>
      ) : null}

      {result && result.hits.length > 0 ? (
        <ul className="lg-source-search__hits" aria-label="Search hits">
          {result.hits.map((hit) => (
            <HitRow
              key={`${hit.source_id}-${hit.source_version}-${hit.kind ?? 'lexical'}`}
              hit={hit}
              mode={mode}
              mediaDirectEmbedding={mediaDirectEmbedding}
              onOpen={onOpen}
            />
          ))}
        </ul>
      ) : null}

      {result && result.stale.length > 0 ? (
        <div className="lg-source-search__stale" role="status">
          <StatusBadge kind="warning">{result.stale.length} stale hit(s) refused</StatusBadge>
          <span className="lg-materials__hint">
            Their source version or hash changed, or the source was revoked; reopen from Files to
            re-verify.
          </span>
        </div>
      ) : null}
    </section>
  )
}

function SemanticAvailability({
  search,
  canRebuild,
  role,
}: {
  search: MaterialSearchController
  canRebuild: boolean
  role: string | null
}) {
  if (search.statusLoading) {
    return <p className="lg-materials__hint">Checking semantic index status…</p>
  }
  if (search.statusError) {
    return (
      <div className="lg-notice lg-search-notice" role="status">
        <p>Semantic index status unavailable ({search.statusError.code}).</p>
        <button type="button" className="lg-link-button" onClick={search.fallbackToKeyword}>
          Switch to Keyword
        </button>
      </div>
    )
  }
  const status = search.vectorStatus
  if (!status) return null

  const cacheReason = status.cache?.reason ?? null
  const needsRebuild =
    status.model_mismatch_rebuild_required === true ||
    status.cache?.compatible === false ||
    cacheReason === 'model_mismatch_rebuild_required' ||
    cacheReason === 'cache_version_mismatch_rebuild_required'

  if (!status.enabled) {
    return (
      <div className="lg-notice lg-search-notice" role="status">
        <p>
          Semantic search is unavailable: embedding is not configured
          {status.reason ? ` (${status.reason})` : ''}. Keyword search and original files still
          work.
        </p>
        <button type="button" className="lg-link-button" onClick={search.fallbackToKeyword}>
          Switch to Keyword
        </button>
      </div>
    )
  }

  if (needsRebuild) {
    return (
      <div className="lg-notice lg-search-notice" role="status">
        <p>
          The semantic cache does not match the configured model. An explicit protected rebuild is
          required before semantic results can be trusted. {rebuildGuidance(canRebuild, role)}
        </p>
        <button type="button" className="lg-link-button" onClick={search.fallbackToKeyword}>
          Switch to Keyword
        </button>
      </div>
    )
  }

  return (
    <p className="lg-materials__hint">
      Semantic model: <span className="lg-card__path">{status.backend?.model ?? 'configured'}</span>
      {status.cache?.documents != null ? ` · ${status.cache.documents} cached vector(s)` : ''}
    </p>
  )
}

function rebuildGuidance(canRebuild: boolean, role: string | null): string {
  if (canRebuild) return 'Open Settings to run the explicit vector rebuild.'
  if (role === 'admin' || role === 'owner') {
    return 'This session is not authorized for the protected rebuild; sign in with an admin session in Settings.'
  }
  return 'Ask an administrator to run the explicit vector rebuild in Settings.'
}

function HitRow({
  hit,
  mode,
  mediaDirectEmbedding,
  onOpen,
}: {
  hit: SearchHit
  mode: MaterialSearchMode
  mediaDirectEmbedding: boolean
  onOpen: (sourceId: string) => void
}) {
  const kind = hit.kind === 'text' || hit.kind === 'image' || hit.kind === 'audio' ? hit.kind : null
  return (
    <li className="lg-source-search__hit">
      <div className="lg-source-search__hit-head">
        <span className="lg-materials__name">{hit.title ?? hit.source_id}</span>
        <StatusBadge kind={hit.verified ? 'success' : 'warning'}>
          {hit.verified ? 'verified' : hit.reason ?? 'unverified'}
        </StatusBadge>
        <StatusBadge kind="neutral">v{hit.source_version}</StatusBadge>
        {mode === 'semantic' && kind ? (
          <StatusBadge kind="neutral">{kindLabel(kind)}</StatusBadge>
        ) : null}
      </div>
      <p className="lg-source-search__snippet">{hit.snippet}</p>
      {mode === 'semantic' && kind === 'audio' ? (
        <p className="lg-search-kind-note">
          Audio media vector · no transcript is implied. Keyword search may find the machine English
          transcript when one is ready; the media vector and transcript branches stay independent.
        </p>
      ) : null}
      {mode === 'semantic' && kind === 'image' ? (
        <p className="lg-search-kind-note">
          Image media vector · it does not imply OCR text was extracted.
        </p>
      ) : null}
      <div className="lg-source-search__hit-meta">
        <span className="lg-card__path" title={hit.source_id}>
          {hit.source_id}
        </span>
        {hit.content_hash ? (
          <span className="lg-card__path" title={hit.content_hash}>
            #{hit.content_hash.slice(0, 12)}
          </span>
        ) : null}
        <span className="lg-materials__flag">
          basis: {hit.basis}
          {kind ? ` · ${kind}` : ''}
        </span>
        {mediaDirectEmbedding && kind && kind !== 'text' ? (
          <span className="lg-materials__flag">media direct</span>
        ) : null}
        <button type="button" className="lg-link-button" onClick={() => onOpen(hit.source_id)}>
          Open in Files
        </button>
      </div>
    </li>
  )
}

function kindLabel(kind: 'text' | 'image' | 'audio'): string {
  if (kind === 'audio') return 'Audio'
  if (kind === 'image') return 'Image'
  return 'Text'
}
