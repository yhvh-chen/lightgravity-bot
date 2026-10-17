/**
 * Chat source search (LG-038; docs/09 §5, §7, docs/08 §4.3 `GET /search`).
 *
 * Lets the user query materials from Chat. Every hit is already re-verified by
 * the backend against the file SoT, so this component:
 *
 * * shows the source id, version and content hash for each hit;
 * * lets the user open the hit in Files, where the same source state is read
 *   (one source of truth — Chat never renders a second copy of the body);
 * * surfaces stale/invalidated hits explicitly (`source_stale`/revoked) rather
 *   than hiding them;
 * * reports `index_unavailable` honestly instead of an empty success.
 */

import type { SearchHit, SourcesApi } from '../../api/sources'
import { EmptyState } from '../../components/EmptyState'
import { ErrorState } from '../../components/ErrorState'
import { StatusBadge } from '../../components/StatusBadge'
import { useMaterialSearch, type MaterialSearchController } from '../../components/useMaterialSearch'

export interface ChatSourceSearchProps {
  api: SourcesApi
  taskRef: string | null
  /** Open one source's authoritative view (Files) at this id. */
  onOpen: (sourceId: string) => void
  /** Lend the search state from the top bar instead of owning a second input. */
  controller?: MaterialSearchController
  /** Set false when the caller already renders the editable top-bar input. */
  showInput?: boolean
}

export function ChatSourceSearch({
  api,
  taskRef,
  onOpen,
  controller,
  showInput = true,
}: ChatSourceSearchProps) {
  const internal = useMaterialSearch(api, taskRef)
  const search = controller ?? internal
  const { draft, setDraft, result, loading, error, run } = search

  return (
    <section className="lg-source-search" aria-label="Material search">
      {showInput ? (
        <div className="lg-source-search__row">
          <input
            type="text"
            className="lg-input"
            placeholder="Search your materials (lexical)…"
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

      {loading ? <p className="lg-materials__hint">Searching…</p> : null}

      {error ? (
        <ErrorState
          title="Search failed"
          message={error.message}
          code={error.code}
          retryable={error.retryable}
          onRetry={() => run()}
        />
      ) : null}

      {result && result.index_status !== 'ok' ? (
        <p className="lg-notice" role="status">
          Search index unavailable ({result.index_unavailable_reason ?? 'unknown'}). Original
          files are still viewable in Files; rebuild may be needed.
        </p>
      ) : null}

      {result && result.index_status === 'ok' && result.hits.length === 0 ? (
        <EmptyState title="No matching material" compact>
          Nothing in your authorized scope matched. Materials with no trusted body are not
          indexed.
        </EmptyState>
      ) : null}

      {result && result.hits.length > 0 ? (
        <ul className="lg-source-search__hits" aria-label="Search hits">
          {result.hits.map((hit) => (
            <HitRow key={`${hit.source_id}-${hit.source_version}`} hit={hit} onOpen={onOpen} />
          ))}
        </ul>
      ) : null}

      {result && result.stale.length > 0 ? (
        <div className="lg-source-search__stale" role="status">
          <StatusBadge kind="warning">{result.stale.length} stale hit(s) refused</StatusBadge>
          <span className="lg-materials__hint">
            Their source version changed or was revoked; reopen from Files to re-verify.
          </span>
        </div>
      ) : null}
    </section>
  )
}

function HitRow({ hit, onOpen }: { hit: SearchHit; onOpen: (sourceId: string) => void }) {
  return (
    <li className="lg-source-search__hit">
      <div className="lg-source-search__hit-head">
        <span className="lg-materials__name">{hit.title ?? hit.source_id}</span>
        <StatusBadge kind={hit.verified ? 'success' : 'warning'}>
          {hit.verified ? 'verified' : hit.reason ?? 'unverified'}
        </StatusBadge>
        <StatusBadge kind="neutral">v{hit.source_version}</StatusBadge>
      </div>
      <p className="lg-source-search__snippet">{hit.snippet}</p>
      <div className="lg-source-search__hit-meta">
        <span className="lg-card__path" title={hit.source_id}>
          {hit.source_id}
        </span>
        {hit.content_hash ? (
          <span className="lg-card__path" title={hit.content_hash}>
            #{hit.content_hash.slice(0, 12)}
          </span>
        ) : null}
        <span className="lg-materials__flag">basis: {hit.basis}</span>
        <button type="button" className="lg-link-button" onClick={() => onOpen(hit.source_id)}>
          Open in Files
        </button>
      </div>
    </li>
  )
}
