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

import { useCallback, useEffect, useRef, useState } from 'react'

import { ApiError } from '../../api/client'
import type { EnglishAsrModelRef } from '../../api/englishAsr'
import {
  isSourceReceiptV2,
  type JobView,
  type SourceContentView,
  type SourceReceipt,
  type SourceReceiptEntry,
  type SourceTextBranch,
  type SourceTextMachineProvenance,
  type SourceView,
  type SourcesApi,
} from '../../api/sources'
import { EmptyState } from '../../components/EmptyState'
import { ErrorState } from '../../components/ErrorState'
import { MarkdownViewer } from '../../components/MarkdownViewer'
import { StatusBadge } from '../../components/StatusBadge'
import { isSourceContextSelectable, sourceContextUnavailableReason } from '../chat/sourceContext'
import { useSharedChatSelection } from '../chat/useChatSelection'
import {
  MaterialBranchList,
  receiptIsTerminal,
} from '../chat/ChatMaterialIntake'

export interface FilesMaterialsPanelProps {
  api: SourcesApi
  taskRef: string | null
  /** A source id to open immediately (deep link from Chat hits/attachments). */
  openSourceId?: string | null
  /** docs/08 §20.2 gate; false keeps legacy 1.18 behavior only. */
  materialIntakeV2?: boolean
  /** Media badge path; actual kinds still come from the source receipt. */
  mediaDirectEmbedding?: boolean
}

type ItemStatus = 'loading' | 'ready' | 'error'

export function FilesMaterialsPanel({
  api,
  taskRef,
  openSourceId,
  materialIntakeV2 = false,
  mediaDirectEmbedding = false,
}: FilesMaterialsPanelProps) {
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
  const [receipt, setReceipt] = useState<SourceReceipt | null>(null)
  const [receiptError, setReceiptError] = useState<ApiError | null>(null)
  const [job, setJob] = useState<JobView | null>(null)
  const [controlPending, setControlPending] = useState(false)
  const [originalUrl, setOriginalUrl] = useState<string | null>(null)
  const [originalError, setOriginalError] = useState<string | null>(null)
  const originalUrlRef = useRef<string | null>(null)
  const [machineContent, setMachineContent] = useState<SourceContentView | null>(null)
  const [machineStatus, setMachineStatus] = useState<
    'idle' | 'loading' | 'ready' | 'unavailable' | 'error'
  >('idle')
  const [machineError, setMachineError] = useState<ApiError | null>(null)

  // LG-204: the workspace material rows are the context selector. The same
  // bounded selection (version/hash/limit) appears as chips above the Chat
  // composer; the provider in AppShell makes both surfaces share one state.
  const selection = useSharedChatSelection(taskRef)
  const selectedIds = new Set(selection.selection.map((item) => item.source_id))

  const receiptItem = receipt?.latest ?? receipt?.items[0] ?? null
  const receiptText: SourceTextBranch | null = receiptItem?.text ?? null
  const transcriptDerivative = selected ? findTranscriptDerivative(selected) : null
  const machineEvidence = Boolean(
    selected &&
      ((selected.language === 'en' && selected.text_status === 'ready') ||
        (receiptText?.status === 'ready' &&
          receiptText?.language === 'en' &&
          Boolean(receiptText?.machine))),
  )

  // Load the authorized source list for the current scope. Only the current
  // Task and global materials are offered; another Task's materials are never
  // cross-selected (docs/10 §5).
  useEffect(() => {
    const controller = new AbortController()
    setListStatus('loading')
    setListError(null)
    const load = async () => {
      const taskPage = await api.listSources(
        { task_ref: taskRef ?? undefined, limit: 200 },
        controller.signal,
      )
      let items = taskPage.items
      if (taskRef) {
        const globalPage = await api.listSources({ limit: 200 }, controller.signal)
        const seen = new Set(items.map((item) => item.source_id))
        items = [
          ...items,
          ...globalPage.items.filter(
            (item) => item.scope.task_ref == null && !seen.has(item.source_id),
          ),
        ]
      } else {
        items = items.filter((item) => item.scope.task_ref == null)
      }
      return items
    }
    load()
      .then((items) => {
        if (controller.signal.aborted) return
        setSources(items)
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

  // Authoritative receipt projection. Poll with bounded exponential backoff
  // while any branch is still progressing; always stop on terminal and clean
  // the timer/abort on unmount, scope change or selection change.
  useEffect(() => {
    if (!selected || !materialIntakeV2) {
      setReceipt(null)
      setReceiptError(null)
      setJob(null)
      return
    }
    const controller = new AbortController()
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | null = null
    let attempts = 0
    const sourceId = selected.source_id

    const read = async () => {
      if (cancelled) return
      try {
        const next = await api.getReceipt(sourceId, controller.signal)
        if (cancelled || controller.signal.aborted) return
        setReceipt(next)
        setReceiptError(null)
        const jobId = intakeJobId(next)
        let observedJob: JobView | null = null
        if (jobId && api.getIntakeJob) {
          observedJob = await api.getIntakeJob(jobId, controller.signal).catch(() => null)
          if (!cancelled && !controller.signal.aborted) setJob(observedJob)
        } else {
          setJob(null)
        }
        const jobRunning = jobId ? jobViewIsRunning(observedJob) : false
        if (receiptIsTerminal(next) && !jobRunning) return
        attempts += 1
        if (attempts >= 12) return
        const delay = Math.min(1000 * 2 ** Math.min(attempts - 1, 4), 15000)
        timer = setTimeout(() => void read(), delay)
      } catch (cause) {
        if (cancelled || controller.signal.aborted) return
        setReceiptError(asApiError(cause))
      }
    }

    void read()
    return () => {
      cancelled = true
      controller.abort()
      if (timer) clearTimeout(timer)
    }
  }, [api, selected, materialIntakeV2, refreshToken])

  // Machine English transcript read path: the existing authorized content JSON
  // endpoint with `kind=machine`. It is fetched only when the source/receipt
  // proves a ready English machine transcript and the preview currently shows
  // the formal (formal-first) body. Failure never hides the original/formal.
  useEffect(() => {
    const controller = new AbortController()
    let cancelled = false
    setMachineContent(null)
    setMachineError(null)
    const sourceId = selected?.source_id
    if (!sourceId || !machineEvidence) {
      setMachineStatus('idle')
      return () => controller.abort()
    }
    if (content && content.kind === 'machine') {
      setMachineContent(content)
      setMachineStatus('ready')
      return () => controller.abort()
    }
    if (contentStatus !== 'ready' || content?.kind !== 'formal') {
      setMachineStatus('idle')
      return () => controller.abort()
    }
    setMachineStatus('loading')
    api
      .getContent(sourceId, 'machine', controller.signal)
      .then((view) => {
        if (cancelled || controller.signal.aborted) return
        setMachineContent(view)
        setMachineStatus('ready')
      })
      .catch((cause: unknown) => {
        if (cancelled || controller.signal.aborted) return
        const error = asApiError(cause)
        setMachineError(error)
        setMachineStatus(error.code === 'not_found' ? 'unavailable' : 'error')
      })
    return () => {
      cancelled = true
      controller.abort()
    }
  }, [
    api,
    selected?.source_id,
    selected?.source_version,
    machineEvidence,
    content,
    contentStatus,
  ])

  // Authorized original preview for image/audio (or an honest download-only
  // state). Data comes from the protected download endpoint, never a local path.
  useEffect(() => {
    if (originalUrlRef.current) {
      URL.revokeObjectURL(originalUrlRef.current)
      originalUrlRef.current = null
    }
    setOriginalUrl(null)
    setOriginalError(null)
    if (!selected) return
    const media = originalMediaType(selected)
    if (!media.startsWith('image/') && !media.startsWith('audio/')) return
    const controller = new AbortController()
    let cancelled = false
    const sourceId = selected.source_id
    api
      .downloadSource(sourceId, 'original', controller.signal)
      .then((result) => {
        if (cancelled) return
        const url = URL.createObjectURL(result.blob)
        originalUrlRef.current = url
        setOriginalUrl(url)
      })
      .catch((cause: unknown) => {
        if (cancelled || controller.signal.aborted) return
        setOriginalError(asApiError(cause).message)
      })
    return () => {
      cancelled = true
      controller.abort()
    }
  }, [api, selected])

  useEffect(() => {
    return () => {
      if (originalUrlRef.current) URL.revokeObjectURL(originalUrlRef.current)
      originalUrlRef.current = null
    }
  }, [])

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
      const result = await api.sourceAction(selected.source_id, {
        action: 'reprocess',
        expected_revision: selected.revision,
      })
      // A successful HTTP request may contain a failed/partial extraction.
      // Only the extraction's terminal success earns a success notice.
      const outcome = typeof result.status === 'string' ? result.status : 'unknown'
      const reason = typeof result.reason === 'string' && result.reason ? ` ${result.reason}` : ''
      setStatus({
        kind: outcome === 'succeeded' ? 'success' : outcome === 'failed' ? 'error' : 'neutral',
        text:
          (outcome === 'succeeded'
            ? 'Reprocess completed;'
            : outcome === 'failed'
              ? `Reprocess failed:${reason || ' extraction failed'};`
              : outcome === 'partial'
                ? `Reprocess partially completed;${reason}`
                : `Reprocess status: ${outcome};${reason}`) +
          ' original and formal version preserved.',
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

  const refreshControlState = useCallback(async () => {
    setRefreshToken((value) => value + 1)
    if (selected) await openSource(selected.source_id)
  }, [openSource, selected])

  const cancelIntake = useCallback(async () => {
    if (!selected || !api.intakeJobAction) return
    const jobId = receipt ? intakeJobId(receipt) : null
    if (!jobId) {
      setStatus({ kind: 'error', text: 'No intake job id is available to cancel.' })
      return
    }
    setControlPending(true)
    setStatus(null)
    try {
      const result = await api.intakeJobAction(jobId, { action: 'cancel', confirmed: false })
      if (result.status === 'cancelled' && result.confirmed) {
        setStatus({ kind: 'success', text: 'Intake cancelled after confirmed stop.' })
      } else {
        setStatus({
          kind: 'neutral',
          text: 'Cancellation requested; the job has NOT stopped yet. Status stays unchanged until stop is confirmed.',
        })
      }
      await refreshControlState()
    } catch (cause) {
      const error = asApiError(cause)
      setStatus({
        kind: error.code === 'cancellation_unconfirmed' ? 'neutral' : 'error',
        text:
          error.code === 'cancellation_unconfirmed'
            ? 'Cancellation requested; the job is still running. Stop is not confirmed yet.'
            : `Cancel failed: ${error.message}`,
      })
    } finally {
      setControlPending(false)
    }
  }, [api, receipt, refreshControlState, selected])

  const retryIntake = useCallback(async () => {
    if (!selected || !api.intakeJobAction) return
    const jobId = receipt ? intakeJobId(receipt) : null
    if (!jobId) {
      setStatus({ kind: 'error', text: 'No intake job id is available to retry.' })
      return
    }
    setControlPending(true)
    setStatus(null)
    try {
      const result = await api.intakeJobAction(jobId, { action: 'retry' })
      setStatus({
        kind: 'success',
        text: `Retry accepted; job status is ${result.status}. Formal version is untouched.`,
      })
      await refreshControlState()
    } catch (cause) {
      const error = asApiError(cause)
      setStatus({ kind: 'error', text: `Retry failed: ${error.message}` })
    } finally {
      setControlPending(false)
    }
  }, [api, receipt, refreshControlState, selected])

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
      <div className="lg-files-materials__header">
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
      </div>

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
              {sources.map((source) => {
                const selectable = isSourceContextSelectable(source)
                const isSelected = selectedIds.has(source.source_id)
                const rowScope: 'global' | 'task' = source.scope.task_ref ? 'task' : 'global'
                return (
                <li key={source.source_id}>
                  <button
                    type="button"
                    className={`lg-files__entry${
                      isSelected ? ' is-selected' : ''
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
                  <div className="lg-files-materials__context">
                    <label>
                      <input
                        type="checkbox"
                        checked={isSelected}
                        disabled={
                          (!selectable && !isSelected) || (selection.atLimit && !isSelected)
                        }
                        aria-label={`Use ${source.title ?? source.source_id} as context`}
                        onChange={() => selection.toggle(source, rowScope)}
                      />
                      Use as context
                    </label>
                    <StatusBadge kind="neutral">{rowScope}</StatusBadge>
                    {!selectable ? (
                      <span className="lg-files-materials__context-note">
                        {sourceContextUnavailableReason(source)}
                      </span>
                    ) : null}
                  </div>
                </li>
                )
              })}
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
                <div>
                  <dt>Intake</dt>
                  <dd>
                    {selected.intake_mode ?? 'sync'}
                    {mediaDirectEmbedding && receipt && isSourceReceiptV2(receipt)
                      ? mediaKindLabel(receipt)
                      : ''}
                  </dd>
                </div>
              </dl>

              {materialIntakeV2 ? (
                <section className="lg-files-materials__receipt" aria-label="Intake receipt">
                  <div className="lg-files-materials__receipt-head">
                    <span className="lg-files__section-title">Processing receipt</span>
                    {receipt && isSourceReceiptV2(receipt) && receipt.partial ? (
                      <StatusBadge kind="warning">Partial</StatusBadge>
                    ) : null}
                    {job ? (
                      <>
                        <StatusBadge kind={jobTone(job.status)}>
                          job: {job.status}
                        </StatusBadge>
                        <span className="lg-files__note">
                          stage {job.stage} · attempt {job.attempt ?? 'unknown'}
                          {job.waiting_reason ? ` · waiting: ${job.waiting_reason}` : ''}
                        </span>
                      </>
                    ) : null}
                  </div>
                  {receipt && isSourceReceiptV2(receipt) ? (
                    <MaterialBranchList item={receipt.latest ?? receipt.items[0] ?? null} />
                  ) : receiptError ? (
                    <p className="lg-files__status lg-files__status--error" role="alert">
                      Receipt unavailable: {receiptError.message}
                    </p>
                  ) : (
                    <p className="lg-files__note">
                      Reading receipt v2… no branch success is inferred while it is unavailable.
                    </p>
                  )}
                  {receipt && isSourceReceiptV2(receipt) && receipt.partial ? (
                    <p className="lg-files__note">
                      Some processing steps did not succeed; successful branches remain usable.
                    </p>
                  ) : null}
                  {job?.fail_reason ? (
                    <p className="lg-files__note">Job failure: {job.fail_reason}</p>
                  ) : null}
                </section>
              ) : (
                <p className="lg-files__note">
                  This backend does not advertise material_intake_v2; branch receipts stay hidden
                  instead of being inferred from a legacy status. Reprocess and download remain
                  available.
                </p>
              )}

              {originalPreviewAllowed(selected) ? (
                <div className="lg-files-materials__original" aria-label="Original preview">
                  <span className="lg-files__note">Original (authorized)</span>
                  {originalError ? (
                    <p className="lg-files__note">
                      Original preview unavailable ({originalError}); download it instead.
                    </p>
                  ) : originalMediaType(selected).startsWith('audio/') ? (
                    originalUrl ? (
                      <audio className="lg-files-materials__audio" controls src={originalUrl}>
                        Your browser does not support audio playback.
                      </audio>
                    ) : (
                      <span className="lg-files__note">Loading original audio…</span>
                    )
                  ) : originalUrl ? (
                    <img
                      className="lg-files__image"
                      src={originalUrl}
                      alt={selected.title ?? 'Original material'}
                    />
                  ) : (
                    <span className="lg-files__note">Loading original image…</span>
                  )}
                  <span className="lg-files__note">
                    Original preview is not OCR text and never implies a transcript.
                  </span>
                </div>
              ) : null}

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
                  {content.kind === 'machine' && machineEvidence ? (
                    <MachineTranscriptMeta
                      source={selected}
                      branch={receiptText}
                      derivative={transcriptDerivative}
                    />
                  ) : null}
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

              {content?.kind === 'formal' && machineEvidence ? (
                <section
                  className="lg-files-materials__transcript"
                  aria-label="Machine English transcript"
                >
                  <div className="lg-files__preview-header">
                    <span className="lg-files__section-title">Machine English transcript</span>
                    <StatusBadge kind="accent">English</StatusBadge>
                    <StatusBadge kind="neutral">machine · not formal</StatusBadge>
                    <StatusBadge kind="neutral">
                      {receiptText?.timestamps == null
                        ? 'word timestamps not available'
                        : 'timestamp data reported · no seek controls'}
                    </StatusBadge>
                  </div>
                  <p className="lg-files__note">
                    This is machine output read from the existing machine content endpoint. The
                    human formal version above remains authoritative and is never overwritten by
                    this transcript.
                  </p>
                  {machineStatus === 'loading' || machineStatus === 'idle' ? (
                    <p className="lg-files__note" role="status">
                      Reading the machine English transcript…
                    </p>
                  ) : null}
                  {machineStatus === 'ready' && machineContent ? (
                    <div className="lg-files__preview-body">
                      <MarkdownViewer content={machineContent.content} />
                    </div>
                  ) : null}
                  {machineStatus === 'unavailable' ? (
                    <p className="lg-files__note" role="note">
                      The machine transcript is not readable right now
                      {machineError?.details?.reason
                        ? ` (${String(machineError.details.reason)})`
                        : ''}
                      . The formal version and original audio are unaffected.
                    </p>
                  ) : null}
                  {machineStatus === 'error' && machineError ? (
                    <ErrorState
                      title="Machine transcript unavailable"
                      message={machineError.message}
                      code={machineError.code}
                      retryable={machineError.retryable}
                    />
                  ) : null}
                  <MachineTranscriptMeta
                    source={selected}
                    branch={receiptText}
                    derivative={transcriptDerivative}
                  />
                </section>
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
                {materialIntakeV2 && receipt && intakeJobId(receipt) ? (
                  <>
                    {job && jobViewIsRunning(job) ? (
                      <button
                        type="button"
                        className="lg-button"
                        onClick={() => void cancelIntake()}
                        disabled={controlPending || Boolean(job.cancel?.requested)}
                      >
                        {controlPending || job.cancel?.requested
                          ? 'Cancellation requested…'
                          : 'Cancel intake'}
                      </button>
                    ) : null}
                    {job && (job.status === 'failed' || job.status === 'partial') ? (
                      <button
                        type="button"
                        className="lg-button"
                        onClick={() => void retryIntake()}
                        disabled={controlPending}
                      >
                        Retry intake
                      </button>
                    ) : null}
                  </>
                ) : null}
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

function intakeJobId(receipt: SourceReceipt): string | null {
  const candidates: Array<SourceReceiptEntry | null> = [
    receipt.latest,
    ...receipt.items,
  ]
  for (const candidate of candidates) {
    if (!candidate) continue
    for (const key of ['job_id', 'job_ref']) {
      const value = candidate[key]
      if (typeof value === 'string' && value) return value
    }
  }
  const direct = (receipt as unknown as Record<string, unknown>).job_id
  return typeof direct === 'string' && direct ? direct : null
}

const RUNNING_JOB_STATES = new Set(['queued', 'running', 'cancelling', 'pending'])

function jobViewIsRunning(job: JobView | null): boolean {
  return Boolean(job && RUNNING_JOB_STATES.has(job.status))
}

function jobTone(status: string): 'neutral' | 'success' | 'warning' | 'error' {
  if (status === 'succeeded' || status === 'completed') return 'success'
  if (status === 'partial' || status === 'queued' || status === 'running') return 'warning'
  if (status === 'failed') return 'error'
  return 'neutral'
}

function originalMediaType(source: SourceView): string {
  const declared = source.original?.media_type
  const original = typeof declared === 'string' ? declared.toLowerCase() : ''
  if (original.startsWith('image/') || original.startsWith('audio/')) return original
  const name = (source.original?.path ?? source.title ?? source.source_id).toLowerCase()
  const extension = name.includes('.') ? name.slice(name.lastIndexOf('.') + 1) : ''
  if (['png', 'jpg', 'jpeg', 'webp', 'gif', 'bmp'].includes(extension)) {
    return extension === 'jpg' ? 'image/jpeg' : `image/${extension}`
  }
  if (['mp3', 'wav', 'ogg', 'm4a', 'aac', 'flac', 'webm'].includes(extension)) {
    return 'audio/unknown'
  }
  return original
}

function originalPreviewAllowed(source: SourceView): boolean {
  const media = originalMediaType(source)
  return media.startsWith('image/') || media.startsWith('audio/')
}

function mediaKindLabel(receipt: SourceReceipt): string {
  if (!isSourceReceiptV2(receipt)) return ''
  const item = receipt.latest ?? receipt.items[0] ?? null
  const kinds = item?.semantic.kinds.filter((kind) => kind === 'image' || kind === 'audio') ?? []
  return kinds.length > 0 ? ` · media vector: ${kinds.join(', ')}` : ''
}

function findTranscriptDerivative(source: SourceView): Record<string, unknown> | null {
  for (const entry of source.derivatives) {
    if (entry && typeof entry === 'object' && (entry as { kind?: unknown }).kind === 'transcript') {
      return entry as Record<string, unknown>
    }
  }
  return null
}

function stringField(record: Record<string, unknown> | null, key: string): string | null {
  const value = record?.[key]
  return typeof value === 'string' && value ? value : null
}

function transcriptTimestampStatus(branch: SourceTextBranch | null): string {
  if (!branch?.machine) return 'not reported'
  if (branch.timestamps == null) {
    return 'not available; no seek markers are fabricated'
  }
  if (branch.timestamps.length === 0) {
    return 'no timestamps reported; no seek markers'
  }
  return 'timestamp data reported; this version provides no seek controls'
}

function ModelPin({
  label,
  model,
}: {
  label: string
  model: EnglishAsrModelRef | null | undefined
}) {
  if (!model) return null
  return (
    <div>
      <dt>{label}</dt>
      <dd className="lg-card__path">
        {model.id} @ {model.revision}
        {model.sha256 ? ` · sha256 ${model.sha256}` : ''}
        {model.license ? ` · ${model.license}` : ''}
      </dd>
    </div>
  )
}

function MachineTranscriptMeta({
  source,
  branch,
  derivative,
}: {
  source: SourceView
  branch: SourceTextBranch | null
  derivative: Record<string, unknown> | null
}) {
  const machine: SourceTextMachineProvenance | null = branch?.machine ?? null
  const modelVersion = machine?.model_version ?? stringField(derivative, 'model_version')
  const transcriptHash = stringField(derivative, 'content_hash')
  const timestamp = transcriptTimestampStatus(branch)
  return (
    <>
      <p className="lg-files__note">
        Machine English transcript · engine {machine?.engine ?? 'not reported'} · model{' '}
        {modelVersion ?? 'not reported'} · runtime {machine?.runtime ?? 'not reported'} ·{' '}
        {timestamp}.
      </p>
      <details className="lg-disclosure" aria-label="Machine transcript provenance">
        <summary className="lg-disclosure__summary">
          Transcript provenance, hashes and word timing
        </summary>
        <div className="lg-disclosure__body">
          <dl className="lg-files-materials__facts">
            <div>
              <dt>Language</dt>
              <dd>{branch?.language ?? source.language ?? 'en'}</dd>
            </div>
            <div>
              <dt>Source version</dt>
              <dd>v{source.source_version}</dd>
            </div>
            <div>
              <dt>Source hash</dt>
              <dd className="lg-card__path">{source.content_hash ?? 'not reported'}</dd>
            </div>
            <div>
              <dt>Transcript hash</dt>
              <dd className="lg-card__path">{transcriptHash ?? 'not reported'}</dd>
            </div>
            <div>
              <dt>Model version</dt>
              <dd>{modelVersion ?? 'not reported'}</dd>
            </div>
            <div>
              <dt>Content variant</dt>
              <dd>{machine?.content_variant ?? 'machine'}</dd>
            </div>
            <div>
              <dt>Generated</dt>
              <dd>{machine?.generated_at ?? 'not reported'}</dd>
            </div>
            <div>
              <dt>Word timing</dt>
              <dd>{timestamp}</dd>
            </div>
            <ModelPin label="Encoder" model={machine?.encoder} />
            <ModelPin label="Reader" model={machine?.reader} />
          </dl>
          <p className="lg-field__hint">
            The transcript is machine-derived and is not a human formal version. Only verified
            decoder output can provide timestamps; this view never fabricates seek markers.
          </p>
        </div>
      </details>
    </>
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
