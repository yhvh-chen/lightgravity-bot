/**
 * Chat selected-material picker (LG-044; docs/10 §1, §3, §5, §8).
 *
 * A small control inside the Chat composer area that lets the user manually
 * select **already-ingested** materials as optional context. It reads the same
 * authorized `sources` list the Files surface reads (one source of truth) and
 * never invents a source, a version or a hash:
 *
 * * global and current-Task materials are both offered; the current Task scope
 *   stays visible on every row;
 * * failed / revoked / not-yet-ingested sources are **not selectable** (the
 *   server re-validates independently — docs/10 §5);
 * * at most 3 sources; the limit is shown and the 4th add is refused in the UI;
 * * the selection is controlled by the parent hook so switching Task clears it.
 *
 * Labels are English and reuse the existing Material surface styling
 * (design.md §1, §3).
 */

import { useCallback, useEffect, useState } from 'react'

import { ApiError } from '../../api/client'
import type { SourceView, SourcesApi } from '../../api/sources'
import { ErrorState } from '../../components/ErrorState'
import { StatusBadge } from '../../components/StatusBadge'
import { isSourceContextSelectable, sourceContextUnavailableReason } from './sourceContext'
import { MAX_SELECTED_SOURCES, type SelectedMaterial } from './useChatSelection'

export interface ChatSourcePickerProps {
  api: SourcesApi
  taskRef: string | null
  selection: SelectedMaterial[]
  atLimit: boolean
  onToggle: (source: SourceView, scope: 'global' | 'task') => void
  onRemove: (sourceId: string) => void
  onClear: () => void
  /** Disabled while a send is pending (docs/10 §8). */
  disabled?: boolean
}

export function ChatSourcePicker({
  api,
  taskRef,
  selection,
  atLimit,
  onToggle,
  onRemove,
  onClear,
  disabled = false,
}: ChatSourcePickerProps) {
  const [open, setOpen] = useState(false)
  const [sources, setSources] = useState<SourceView[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)

  const load = useCallback(
    async (signal?: AbortSignal) => {
      setLoading(true)
      setError(null)
      try {
        // Authorized scope: current Task materials plus global materials. The
        // backend list filter is single-scope, so for a Task scope we also read
        // the unscoped list and keep only global rows (other Tasks' rows are
        // dropped — cross-Task selection is forbidden, docs/10 §5). The server
        // re-validates every selected ref independently.
        const taskPage = await api.listSources(
          { task_ref: taskRef ?? undefined, limit: 200 },
          signal,
        )
        let items = taskPage.items
        if (taskRef) {
          const globalPage = await api.listSources({ limit: 200 }, signal)
          const seen = new Set(items.map((item) => item.source_id))
          const globalOnly = globalPage.items.filter(
            (item) => item.scope.task_ref == null && !seen.has(item.source_id),
          )
          items = [...items, ...globalOnly]
        }
        setSources(items)
      } catch (cause) {
        if (signal?.aborted) return
        setSources([])
        setError(asApiError(cause))
      } finally {
        if (!signal?.aborted) setLoading(false)
      }
    },
    [api, taskRef],
  )

  // Re-read on open and whenever the scope changes; never cache across Tasks.
  useEffect(() => {
    if (!open) {
      setSources([])
      return
    }
    const controller = new AbortController()
    void load(controller.signal)
    return () => controller.abort()
  }, [open, load])

  const selectedIds = new Set(selection.map((item) => item.source_id))

  return (
    <section className="lg-source-picker" aria-label="Selected materials">
      <div className="lg-source-picker__row">
        <button
          type="button"
          className="lg-button"
          aria-expanded={open}
          onClick={() => setOpen((value) => !value)}
          disabled={disabled}
        >
          Select materials
          {selection.length > 0 ? ` (${selection.length}/${MAX_SELECTED_SOURCES})` : ''}
        </button>
        <span className="lg-source-picker__scope">scope: {taskRef ?? 'Global'}</span>
        {selection.length > 0 ? (
          <button type="button" className="lg-link-button" onClick={onClear} disabled={disabled}>
            Clear selection
          </button>
        ) : null}
      </div>

      {selection.length > 0 ? (
        <ul className="lg-source-picker__chips" aria-label="Selected source refs">
          {selection.map((item) => (
            <li key={item.source_id} className="lg-chip">
              <span className="lg-materials__name" title={item.title ?? item.source_id}>
                {item.title ?? item.source_id}
              </span>
              <span className="lg-card__path">
                {item.source_id}
                {typeof item.source_version === 'number' ? ` · v${item.source_version}` : ''}
              </span>
              {item.content_hash ? (
                <span className="lg-card__path" title={item.content_hash}>
                  #{item.content_hash.slice(0, 12)}
                </span>
              ) : null}
              <StatusBadge kind="neutral">{item.scope}</StatusBadge>
              <button
                type="button"
                className="lg-icon-button"
                aria-label={`Remove ${item.title ?? item.source_id}`}
                onClick={() => onRemove(item.source_id)}
                disabled={disabled}
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="lg-source-picker__hint">
          No materials selected. Default is none — the message is sent unchanged.
        </p>
      )}

      {atLimit ? (
        <p className="lg-notice" role="status">
          Limit reached: at most {MAX_SELECTED_SOURCES} sources.
        </p>
      ) : null}

      {open ? (
        <div className="lg-source-picker__panel">
          {loading ? <p className="lg-materials__hint">Loading materials…</p> : null}
          {error ? (
            <ErrorState
              title="Could not list materials"
              message={error.message}
              code={error.code}
              retryable={error.retryable}
              onRetry={() => void load()}
            />
          ) : null}
          {!loading && !error && sources.length === 0 ? (
            <p className="lg-materials__empty">
              No ingested materials in scope. Upload a file in Chat first.
            </p>
          ) : null}
          {sources.length > 0 ? (
            <ul className="lg-source-picker__list" aria-label="Available materials">
              {sources.map((source) => {
                const selectable = isSourceContextSelectable(source)
                const selected = selectedIds.has(source.source_id)
                const rowScope: 'global' | 'task' = source.scope.task_ref ? 'task' : 'global'
                return (
                  <li key={source.source_id} className="lg-source-picker__item">
                    <label className="lg-source-picker__label">
                      <input
                        type="checkbox"
                        checked={selected}
                        disabled={disabled || (!selectable && !selected) || (atLimit && !selected)}
                        aria-label={`Select ${source.title ?? source.source_id}`}
                        onChange={() => onToggle(source, rowScope)}
                      />
                      <span className="lg-materials__name" title={source.title ?? source.source_id}>
                        {source.title ?? source.source_id}
                      </span>
                    </label>
                    <span className="lg-materials__item-meta">
                      <StatusBadge kind="neutral">{rowScope}</StatusBadge>
                      <StatusBadge kind={badgeTone(source)}>{source.status}</StatusBadge>
                      <span className="lg-card__path">
                        {source.source_id} · v{source.source_version}
                      </span>
                    </span>
                    {!selectable ? (
                      <span className="lg-materials__hint">{sourceContextUnavailableReason(source)}</span>
                    ) : null}
                  </li>
                )
              })}
            </ul>
          ) : null}
        </div>
      ) : null}
    </section>
  )
}

function badgeTone(source: SourceView): 'neutral' | 'success' | 'warning' | 'error' {
  if (source.status === 'archived' || source.status === 'failed') return 'error'
  if (source.status === 'partial') return 'warning'
  if (isSourceContextSelectable(source)) return 'success'
  return 'neutral'
}

function asApiError(cause: unknown): ApiError {
  if (cause instanceof ApiError) return cause
  return new ApiError({
    message: cause instanceof Error ? cause.message : 'Could not list materials',
    code: 'internal_error',
    httpStatus: null,
    retryable: true,
  })
}
