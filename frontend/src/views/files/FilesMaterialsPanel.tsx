/**
 * Files → Materials panel (LG-038; docs/09 §5, docs/05 Files).
 *
 * Files is the archive/inspection surface: preview, source traceability,
 * correction, reprocess and download. This panel reads the **same** `source`
 * state as Chat (via `SourcesApi`) so receipts never diverge, and it does not
 * invent a second intake path — a Files upload is explicitly redirected to
 * Chat (see `FilesLegacyUploadNotice`), while the LG-014 `POST /files/upload`
 * endpoint and its history are kept intact for authorization/download.
 *
 * Honesty/security rules enforced here:
 * * Markdown is rendered as text and HTML is never rendered/executed;
 * * `link_only` sources are labelled and never shown as an extracted body;
 * * a missing OCR/vector service shows its real status, never a fake body;
 * * correction sends `expected_revision` and reports `revision_conflict`
 *   instead of overwriting; reprocess is offered separately from the formal
 *   version so a correction is never clobbered;
 * * opening a source that is out of the current Task/authorized scope is
 *   refused by the backend and surfaced, not hidden.
 */

import { useCallback, useEffect, useState } from 'react'

import { ApiError } from '../../api/client'
import type { SourceContentView, SourceView, SourcesApi } from '../../api/sources'
import { EmptyState } from '../../components/EmptyState'
import { ErrorState } from '../../components/ErrorState'
import { MarkdownViewer } from '../../components/MarkdownViewer'
import { StatusBadge } from '../../components/StatusBadge'

export interface FilesMaterialsPanelProps {
  api: SourcesApi
  taskRef: string | null
  /** A source id to open immediately (deep link from Chat hits/attachments). */
  openSourceId?: string | null
}

type ItemStatus = 'loading' | 'ready' | 'error'

export function FilesMaterialsPanel({ api, taskRef, openSourceId }: FilesMaterialsPanelProps) {
  const [sources, setSources] = useState<SourceView[]>([])
  const [listStatus, setListStatus] = useState<ItemStatus>('loading')
  const [listError, setListError] = useState<ApiError | null>(null)
  const [selected, setSelected] = useState<SourceView | null>(null)
  const [content, setContent] = useState<SourceContentView | null>(null)
  const [contentError, setContentError] = useState<ApiError | null>(null)
  const [contentStatus, setContentStatus] = useState<ItemStatus>('loading')
  const [draft, setDraft] = useState<string>('')
  const [openError, setOpenError] = useState<ApiError | null>(null)
  const [status, setStatus] = useState<{ kind: 'success' | 'error' | 'neutral'; text: string } | null>(
    null,
  )
  const [refreshToken, setRefreshToken] = useState(0)

  // Load the authorized source list for the current scope.
  useEffect(() => {
    const controller = new AbortController()
    setListStatus('loading')
    setListError(null)
    api
      .listSources({ task_ref: taskRef ?? undefined, limit: 200 }, controller.signal)
      .then((page) => {
        setSources(page.items)
        setListStatus('ready')
      })
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return
        setListError(asApiError(cause))
        setListStatus('error')
      })
    return () => controller.abort()
  }, [api, taskRef, refreshToken])

  const openSource = useCallback(
    async (sourceId: string) => {
      setContentStatus('loading')
      setContentError(null)
      setOpenError(null)
      setContent(null)
      try {
        const source = await api.getSource(sourceId)
        setSelected(source)
        const view = await api.getContent(sourceId, 'auto').catch((cause: unknown) => {
          // "no trusted body yet" (404) is a real, honest state, not a failure
          // to hide; other errors propagate.
          const error = asApiError(cause)
          if (error.code === 'not_found') return null
          throw cause
        })
        setContent(view)
        setDraft(view?.content ?? '')
        setContentStatus('ready')
      } catch (cause) {
        const error = asApiError(cause)
        setContentError(error)
        setOpenError(error)
        setContentStatus('error')
      }
    },
    [api],
  )

  // Deep link from Chat (open a specific source).
  useEffect(() => {
    if (openSourceId) void openSource(openSourceId)
  }, [openSourceId, openSource])

  const saveFormal = useCallback(async () => {
    if (!selected || !content) return
    setStatus(null)
    try {
      const formalRevision =
        typeof selected.formal?.revision === 'number' ? selected.formal.revision : 0
      const result = await api.editFormal(selected.source_id, {
        content: draft,
        edited_by: 'user',
        expected_revision: formalRevision,
      })
      setStatus({
        kind: 'success',
        text: `Saved formal version (revision ${result.revision}). Machine derivative untouched.`,
      })
      setRefreshToken((value) => value + 1)
      await openSource(selected.source_id)
    } catch (cause) {
      const error = asApiError(cause)
      setStatus({
        kind: 'error',
        text:
          error.code === 'revision_conflict'
            ? `Conflict: the formal version changed (${error.message}). Reload before editing.`
            : `Correction failed: ${error.message}`,
      })
    }
  }, [api, content, draft, openSource, selected])

  const reprocess = useCallback(async () => {
    if (!selected) return
    setStatus(null)
    try {
      await api.sourceAction(selected.source_id, { action: 'reprocess' })
      setStatus({
        kind: 'success',
        text: 'Reprocess started into a new machine derivative (formal version preserved).',
      })
      setRefreshToken((value) => value + 1)
      await openSource(selected.source_id)
    } catch (cause) {
      const error = asApiError(cause)
      setStatus({
        kind: error.code === 'capability_unavailable' ? 'neutral' : 'error',
        text:
          error.code === 'capability_unavailable'
            ? 'OCR service is not configured/reachable; original preserved, no body produced.'
            : `Reprocess failed: ${error.message}`,
      })
    }
  }, [api, openSource, selected])

  const toggleArchive = useCallback(async () => {
    if (!selected) return
    setStatus(null)
    const next = !selected.archived
    try {
      await api.sourceAction(selected.source_id, {
        action: next ? 'archive' : 'unarchive',
        expected_revision: selected.revision,
      })
      setStatus({
        kind: 'success',
        text: next
          ? 'Archived. The source stays searchable and openable.'
          : 'Unarchived. The source is back in the default list.',
      })
      setRefreshToken((value) => value + 1)
      await openSource(selected.source_id)
    } catch (cause) {
      const error = asApiError(cause)
      setStatus({
        kind: 'error',
        text:
          error.code === 'revision_conflict'
            ? `Conflict: the source changed (${error.message}). Reload before archiving.`
            : `Archive change failed: ${error.message}`,
      })
    }
  }, [api, openSource, selected])

  const download = useCallback(
    async (kind: 'original' | 'formal' | 'machine') => {
      if (!selected) return
      setStatus(null)
      try {
        const result = await api.downloadSource(selected.source_id, kind)
        const url = URL.createObjectURL(result.blob)
        const anchor = document.createElement('a')
        anchor.href = url
        anchor.download = result.filename
        document.body.appendChild(anchor)
        anchor.click()
        anchor.remove()
        URL.revokeObjectURL(url)
        setStatus({ kind: 'success', text: `Downloaded ${result.filename} (${kind}).` })
      } catch (cause) {
        setStatus({ kind: 'error', text: `Download failed: ${asApiError(cause).message}` })
      }
    },
    [api, selected],
  )

  return (
    <section className="lg-files-materials" aria-label="Materials (sources)">
      <header className="lg-files-materials__header">
        <h2 className="lg-files__section-title">Materials</h2>
        <span className="lg-files__note">
          Same source as Chat. Archive, correct, reprocess and download here.
        </span>
        {status ? (
          <p
            className={`lg-files__status lg-files__status--${status.kind}`}
            role={status.kind === 'error' ? 'alert' : 'status'}
          >
            {status.text}
          </p>
        ) : null}
      </header>

      <div className="lg-files-materials__body">
        <div className="lg-files-materials__list-panel">
          {listError ? (
            <ErrorState
              title="Cannot list materials"
              message={listError.message}
              code={listError.code}
              retryable={listError.retryable}
              onRetry={() => setRefreshToken((value) => value + 1)}
            />
          ) : listStatus === 'loading' && sources.length === 0 ? (
            <EmptyState title="Loading materials…" compact />
          ) : sources.length === 0 ? (
            <EmptyState title="No materials in this scope" compact>
              Materials are added from Chat (upload, drag-drop or a recorded link).
            </EmptyState>
          ) : (
            <ul className="lg-files-materials__list">
              {sources.map((source) => (
                <li key={source.source_id}>
                  <button
                    type="button"
                    className={`lg-files__entry${
                      selected?.source_id === source.source_id ? ' is-selected' : ''
                    }`}
                    title={source.source_id}
                    onClick={() => void openSource(source.source_id)}
                  >
                    <span className="lg-files__entry-name">
                      {source.title ?? source.original?.path ?? source.source_id}
                    </span>
                    <span className="lg-files__entry-meta">
                      {source.status} · v{source.source_version}
                      {source.origin.kind === 'link' && !source.origin.fetched
                        ? ' · link_only'
                        : ''}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="lg-files-materials__detail-panel">
          {!selected ? (
            openError ? (
              <ErrorState
                title={openError.httpStatus === 403 ? 'Out of scope' : 'Cannot open material'}
                message={openError.message}
                code={openError.code}
                retryable={openError.retryable}
              />
            ) : (
              <EmptyState title="No material selected" compact>
                Select a material to preview its content, correct the formal version, reprocess or
                download.
              </EmptyState>
            )
          ) : (
            <>
              <div className="lg-files__preview-header">
                <span className="lg-files__preview-name" title={selected.source_id}>
                  {selected.title ?? selected.source_id}
                </span>
                <StatusBadge kind="neutral">{selected.status}</StatusBadge>
                <StatusBadge kind="neutral">rev {selected.revision}</StatusBadge>
                {selected.origin.kind === 'link' && !selected.origin.fetched ? (
                  <StatusBadge kind="warning">link_only — not text</StatusBadge>
                ) : null}
              </div>

              <dl className="lg-files-materials__facts">
                <div>
                  <dt>Source</dt>
                  <dd className="lg-card__path">{selected.source_id}</dd>
                </div>
                <div>
                  <dt>Version / hash</dt>
                  <dd className="lg-card__path">
                    v{selected.source_version}
                    {selected.content_hash ? ` · #${selected.content_hash.slice(0, 16)}` : ''}
                  </dd>
                </div>
                <div>
                  <dt>Index</dt>
                  <dd>
                    lexical: {selected.index?.lexical ?? 'n/a'}
                    {selected.index?.vector && selected.index.vector !== 'disabled'
                      ? ` · vector: ${selected.index.vector}`
                      : ' · vector: disabled'}
                  </dd>
                </div>
                <div>
                  <dt>Scope</dt>
                  <dd>{selected.scope.task_ref ?? selected.scope.inbox_ref ?? 'global'}</dd>
                </div>
              </dl>

              {contentStatus === 'error' && contentError ? (
                <ErrorState
                  title={
                    contentError.httpStatus === 403
                      ? 'Out of scope'
                      : 'Cannot read content'
                  }
                  message={contentError.message}
                  code={contentError.code}
                  retryable={contentError.retryable}
                  onRetry={() => void openSource(selected.source_id)}
                />
              ) : null}

              {contentStatus === 'ready' && !content ? (
                <EmptyState title="No trusted text yet" compact>
                  This material has no formal or machine body. If it is an image/PDF, OCR may be
                  unavailable or still processing; the original is preserved and downloadable.
                </EmptyState>
              ) : null}

              {content ? (
                <>
                  <p className="lg-files__note">
                    Showing <strong>{content.kind}</strong> content
                    {content.formal_present ? ' (human formal version present)' : ''}.
                    {content.kind === 'machine'
                      ? ' Editing below creates/updates the human formal version without touching the machine derivative.'
                      : ''}
                  </p>
                  <div className="lg-files__preview-body">
                    <MarkdownViewer content={content.content} />
                  </div>
                  <label className="lg-files-materials__editor">
                    <span className="lg-files__note">Correct formal version (Markdown)</span>
                    <textarea
                      className="lg-input lg-files-materials__textarea"
                      value={draft}
                      onChange={(event) => setDraft(event.target.value)}
                      aria-label="Formal version content"
                    />
                  </label>
                </>
              ) : null}

              <div className="lg-files-materials__actions">
                <button
                  type="button"
                  className="lg-button lg-button--primary"
                  onClick={() => void saveFormal()}
                  disabled={!content}
                >
                  Save correction
                </button>
                <button
                  type="button"
                  className="lg-button"
                  onClick={() => void toggleArchive()}
                >
                  {selected.archived ? 'Unarchive' : 'Archive'}
                </button>
                <button type="button" className="lg-button" onClick={() => void reprocess()}>
                  Reprocess (OCR)
                </button>
                <button
                  type="button"
                  className="lg-button"
                  onClick={() => void download('original')}
                >
                  Download original
                </button>
                <button
                  type="button"
                  className="lg-button"
                  onClick={() => void download('formal')}
                  disabled={!selected.formal?.path}
                >
                  Download formal
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </section>
  )
}

function asApiError(cause: unknown): ApiError {
  if (cause instanceof ApiError) return cause
  return new ApiError({
    message: cause instanceof Error ? cause.message : 'Unexpected error',
    code: 'internal_error',
    httpStatus: null,
    retryable: false,
  })
}
