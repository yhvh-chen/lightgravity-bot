/**
 * Chat material-intake panel (LG-038; docs/05 §3, docs/09 §2–§6, design.md §5).
 *
 * Renders the single regular material entry inside Chat: upload, drag-drop and
 * paste-link, plus the per-file receipt list. It is deliberately a small,
 * prop-driven component so the Chat body mounts exactly one instance and the
 * same `SourcesApi`/hook result powers both the panel and (optionally) a test.
 *
 * Honesty rules enforced here:
 * * a link shows `link recorded only — not text` and never an extracted body;
 * * OCR/vector/service gaps show the real backend status, never a fake success;
 * * global uploads state plainly that no delivery Task was created.
 */

import { useEffect, useRef, useState, type ChangeEvent, type DragEvent } from 'react'

import type {
  SourceKeywordBranch,
  SourceReceipt,
  SourceReceiptEntry,
  SourceRef,
  SourceSemanticBranch,
  SourceTextBranch,
  SourcesApi,
} from '../../api/sources'
import { isSourceReceiptV2 } from '../../api/sources'

import { ErrorState } from '../../components/ErrorState'
import { Icon } from '../../components/icons'
import { StatusBadge } from '../../components/StatusBadge'
import type { ChatDraft, MaterialRecord, MaterialState } from './useChatMaterials'
import './intake.css'

export interface ChatMaterialIntakeProps {
  materials: MaterialRecord[]
  busy: boolean
  scopeLabel: string
  onUploadFiles: (files: File[]) => void
  onRecordLink: (url: string) => void
  onRefresh: (requestId: string) => void
  onDismiss: (requestId: string) => void
  /** Whether protected writes are allowed (token present). */
  canWrite?: boolean
  /** Non-blocking error for a rejected link, etc. */
  notice?: string | null
}

const STATE_TONE: Record<MaterialState, 'neutral' | 'success' | 'warning' | 'error'> = {
  received: 'neutral',
  processing: 'warning',
  extracted: 'success',
  attributed: 'success',
  indexed: 'success',
  archived: 'neutral',
  partial: 'warning',
  failed: 'error',
  unavailable: 'warning',
}

const STATE_LABEL: Record<MaterialState, string> = {
  received: 'received',
  processing: 'processing',
  extracted: 'success',
  attributed: 'success',
  indexed: 'indexed',
  archived: 'archived',
  partial: 'partial success',
  failed: 'failed',
  unavailable: 'service unavailable',
}

export function ChatMaterialIntake({
  materials,
  busy,
  scopeLabel,
  onUploadFiles,
  onRecordLink,
  onRefresh,
  onDismiss,
  canWrite = true,
  notice,
}: ChatMaterialIntakeProps) {
  const [dragActive, setDragActive] = useState(false)
  const [linkDraft, setLinkDraft] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)

  const handleFiles = (list: FileList | null) => {
    if (!list || list.length === 0) return
    onUploadFiles(Array.from(list))
  }

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    setDragActive(false)
    handleFiles(event.dataTransfer?.files ?? null)
  }

  const handleLink = () => {
    const value = linkDraft.trim()
    if (!value) return
    onRecordLink(value)
    setLinkDraft('')
  }

  const onPick = (event: ChangeEvent<HTMLInputElement>) => {
    handleFiles(event.target.files)
    event.target.value = ''
  }

  return (
    <section className="lg-materials" aria-label="Materials">
      <div className="lg-materials__header">
        <span className="lg-materials__title">Materials</span>
        <span className="lg-materials__scope">scope: {scopeLabel}</span>
      </div>

      <div
        className={`lg-materials__drop${dragActive ? ' is-active' : ''}`}
        onDragOver={(event) => {
          event.preventDefault()
          setDragActive(true)
        }}
        onDragLeave={() => setDragActive(false)}
        onDrop={handleDrop}
      >
        <input
          ref={fileRef}
          type="file"
          multiple
          className="lg-visually-hidden"
          onChange={onPick}
          aria-label="Upload files to this conversation"
        />
        <button
          type="button"
          className="lg-button"
          onClick={() => fileRef.current?.click()}
          disabled={busy}
        >
          <Icon name="files" size={14} /> Upload / drop files
        </button>
        <span className="lg-materials__hint">
          Original is stored first; no delivery Task/Run is created.
        </span>
      </div>

      <div className="lg-materials__link">
        <input
          type="text"
          className="lg-input"
          placeholder="Paste a link to record (not fetched)…"
          aria-label="Record a link"
          value={linkDraft}
          onChange={(event) => setLinkDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault()
              handleLink()
            }
          }}
        />
        <button
          type="button"
          className="lg-button"
          onClick={handleLink}
          disabled={busy || !linkDraft.trim()}
        >
          Record link
        </button>
      </div>

      {notice ? (
        <p className="lg-notice lg-notice--error" role="alert">
          {notice}
        </p>
      ) : null}

      {!canWrite ? (
        <p className="lg-notice" role="status">
          Upload is a protected write; without a local access token the backend
          returns <code>unauthorized</code> and nothing is stored.
        </p>
      ) : null}

      {materials.length === 0 ? (
        <p className="lg-materials__empty">
          No materials yet. Upload a file or record a link; each gets its own receipt.
        </p>
      ) : (
        <ul className="lg-materials__list" aria-label="Per-file receipts">
          {materials.map((item) => (
            <li key={item.requestId} className="lg-materials__item">
              <div className="lg-materials__item-head">
                <Icon name={item.originKind === 'link' ? 'link' : 'files'} size={14} />
                <span className="lg-materials__name" title={item.externalRef ?? item.filename}>
                  {item.filename}
                </span>
                <StatusBadge kind={STATE_TONE[item.state]}>
                  {STATE_LABEL[item.state]}
                </StatusBadge>
                {item.originKind === 'link' ? (
                  <StatusBadge kind="warning">link_only</StatusBadge>
                ) : null}
              </div>
              <div className="lg-materials__item-meta">
                {item.sourceId ? (
                  <span className="lg-card__path" title={item.sourceId}>
                    {item.sourceId} · v{item.sourceVersion ?? '?'}
                  </span>
                ) : (
                  <span className="lg-card__path">no source yet</span>
                )}
                {item.contentHash ? (
                  <span className="lg-card__path" title={item.contentHash}>
                    #{item.contentHash.slice(0, 12)}
                  </span>
                ) : null}
                {item.lexical ? <span className="lg-materials__flag">lexical: {item.lexical}</span> : null}
                {item.vector && item.vector !== 'disabled' ? (
                  <span className="lg-materials__flag">vector: {item.vector}</span>
                ) : null}
                {item.stage ? <span className="lg-materials__flag">stage: {item.stage}</span> : null}
              </div>
              {item.detail ? <p className="lg-materials__detail">{item.detail}</p> : null}
              {item.error ? (
                <ErrorState
                  title="Intake failed"
                  message={item.error.message}
                  code={item.error.code}
                  retryable={item.error.code === 'capability_unavailable'}
                  onRetry={() => onRefresh(item.requestId)}
                />
              ) : null}
              <div className="lg-materials__item-actions">
                <button
                  type="button"
                  className="lg-link-button"
                  onClick={() => onRefresh(item.requestId)}
                  disabled={!item.sourceId}
                >
                  Refresh state
                </button>
                <button
                  type="button"
                  className="lg-link-button"
                  onClick={() => onDismiss(item.requestId)}
                  aria-label={`Dismiss ${item.filename}`}
                >
                  Dismiss
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

/* ------------------------------------------- send-time draft chips (LG-142) */

export interface ChatDraftChipsProps {
  drafts: ChatDraft[]
  onRemove: (draftId: string) => void
  disabled?: boolean
}

export function ChatDraftChips({ drafts, onRemove, disabled = false }: ChatDraftChipsProps) {
  if (drafts.length === 0) return null
  return (
    <ul className="lg-intake-drafts" aria-label="Draft files">
      {drafts.map((draft) => (
        <li key={draft.id} className="lg-intake-draft">
          <Icon name="files" size={14} />
          <span className="lg-intake-draft__name" title={draft.filename}>
            {draft.filename}
          </span>
          <span className="lg-intake-draft__meta">
            {draft.mediaType ?? 'unknown type'} · {formatBytes(draft.size)}
          </span>
          <span
            className={`lg-intake-draft__state lg-intake-draft__state--${draft.status}`}
            title={draft.error?.message ?? undefined}
          >
            {draftStatusLabel(draft)}
          </span>
          {draft.status === 'accepted' && draft.sourceId ? (
            <span className="lg-intake-draft__meta" title={draft.sourceId}>
              {draft.sourceId}
            </span>
          ) : null}
          <button
            type="button"
            className="lg-icon-button"
            aria-label={`Remove draft ${draft.filename}`}
            onClick={() => onRemove(draft.id)}
            disabled={disabled || draft.status === 'intaking'}
          >
            <Icon name="close" size={12} />
          </button>
        </li>
      ))}
    </ul>
  )
}

function draftStatusLabel(draft: ChatDraft): string {
  switch (draft.status) {
    case 'intaking':
      return 'Sending…'
    case 'accepted':
      return 'Stored'
    case 'failed':
      return 'Intake failed'
    default:
      return 'Draft — starts on Send'
  }
}

/* --------------------------------------- authoritative receipt cards (LG-142) */

export type BranchTone = 'neutral' | 'success' | 'warning' | 'error'
export type BranchKind = 'text' | 'keyword' | 'semantic'

export interface BranchView {
  label: string
  tone: BranchTone
  detail: string | null
}

/**
 * Project one authoritative receipt branch into a compact English label.
 * `unsupported` is never treated as success; `unavailable` is not failure when
 * the media simply has no text path. `machine`/`language`/`timestamps` are the
 * additive 1.20.0 English ASR fields and are shown only when present.
 */
export function describeBranch(
  kind: BranchKind,
  status: string,
  reason?: string | null,
  errorCode?: string | null,
  textBranch?: SourceTextBranch,
): BranchView {
  const detail = reason ?? errorCode ?? null
  if (kind === 'text') {
    switch (status) {
      case 'pending':
        return { label: 'Pending', tone: 'neutral', detail }
      case 'extracting':
        if (reason === 'asr_stop_unconfirmed') {
          return {
            label: 'Transcription stop unconfirmed',
            tone: 'warning',
            detail:
              'The in-process model may still be running; no terminal state, retry or cancellation success is claimed.',
          }
        }
        return { label: 'Extracting', tone: 'warning', detail }
      case 'ready':
        if (textBranch?.machine) {
          return {
            label: 'English transcript ready',
            tone: 'success',
            detail: transcriptDetail(textBranch),
          }
        }
        return {
          label: reason === 'partial_pages' ? 'Text ready (partial pages)' : 'Text ready',
          tone: reason === 'partial_pages' ? 'warning' : 'success',
          detail: null,
        }
      case 'unavailable':
        if (reason === 'asr_unavailable') {
          return {
            label: 'Transcription unavailable',
            tone: 'warning',
            detail: 'ASR is unavailable; no transcript was created.',
          }
        }
        if (reason === 'asr_disabled') {
          return {
            label: 'English transcription disabled',
            tone: 'warning',
            detail: 'English transcription is disabled; no transcript was created.',
          }
        }
        if (reason === 'asr_unsupported_language') {
          return {
            label: 'English transcription unsupported',
            tone: 'warning',
            detail: 'Only shared English audio is supported; no transcript was created.',
          }
        }
        if (reason === 'cancelled') {
          return {
            label: 'English transcription cancelled',
            tone: 'neutral',
            detail: 'The attempt was cancelled before a transcript was created.',
          }
        }
        return { label: 'Text unavailable', tone: 'warning', detail }
      case 'failed':
        return textFailure(reason, detail)
      default:
        return { label: `Unknown text state: ${status}`, tone: 'warning', detail }
    }
  }
  if (kind === 'keyword') {
    switch (status) {
      case 'pending':
        return { label: 'Pending', tone: 'neutral', detail }
      case 'indexing':
        return { label: 'Indexing', tone: 'warning', detail }
      case 'searchable':
        return { label: 'Searchable', tone: 'success', detail: null }
      case 'no_text':
        return { label: 'No text', tone: 'neutral', detail: reason ?? 'no trusted body' }
      case 'failed':
        return { label: 'Keyword failed', tone: 'error', detail }
      default:
        return { label: `Unknown keyword state: ${status}`, tone: 'warning', detail }
    }
  }
  switch (status) {
    case 'pending':
      return { label: 'Pending', tone: 'neutral', detail }
    case 'indexing':
      return { label: 'Indexing', tone: 'warning', detail }
    case 'searchable':
      return { label: 'Searchable', tone: 'success', detail: null }
    case 'disabled':
      return { label: 'Disabled', tone: 'neutral', detail: reason ?? 'embedding is not enabled' }
    case 'unsupported':
      return {
        label: 'Unsupported',
        tone: 'warning',
        detail: reason ?? 'no embeddable text/image/audio input',
      }
    case 'failed':
      return { label: 'Semantic failed', tone: 'error', detail }
    default:
      return { label: `Unknown semantic state: ${status}`, tone: 'warning', detail }
  }
}

function semanticDetail(branch: SourceSemanticBranch): string | null {
  const parts: string[] = []
  if (branch.kinds.length > 0) parts.push(`indexed: ${branch.kinds.join(', ')}`)
  if (branch.failed_kinds.length > 0) parts.push(`failed: ${branch.failed_kinds.join(', ')}`)
  if (branch.model) parts.push(branch.model)
  if (branch.reason) parts.push(branch.reason)
  if (branch.error_code && !branch.reason) parts.push(branch.error_code)
  return parts.length > 0 ? parts.join(' · ') : null
}

function textFailure(reason: string | null | undefined, detail: string | null): BranchView {
  switch (reason) {
    case 'asr_timeout':
      return { label: 'English transcription timed out', tone: 'error', detail }
    case 'asr_failed':
      return { label: 'English transcription failed', tone: 'error', detail }
    case 'audio_too_long':
      return { label: 'Transcription skipped: audio too long', tone: 'warning', detail }
    case 'audio_decode_failed':
      return { label: 'Audio decode failed', tone: 'error', detail }
    case 'model_incompatible':
      return { label: 'Transcription model incompatible', tone: 'error', detail }
    case 'resource_exhausted':
      return { label: 'Transcription resources exhausted', tone: 'error', detail }
    default:
      return { label: 'Text failed', tone: 'error', detail }
  }
}

/** Provenance/timestamp note for a ready machine English transcript. */
function transcriptDetail(branch: SourceTextBranch): string | null {
  const machine = branch.machine
  if (!machine) return null
  const parts: string[] = ['machine English transcript']
  if (machine.engine) parts.push(machine.engine)
  if (machine.model_version) parts.push(machine.model_version)
  if (machine.runtime) parts.push(machine.runtime)
  if (machine.content_variant) parts.push(machine.content_variant)
  if (branch.timestamps == null) {
    parts.push('word timestamps not available')
  } else if (branch.timestamps.length > 0) {
    parts.push('timestamp data reported; no seek controls')
  }
  return parts.join(' · ')
}

function branchDetail(
  view: BranchView,
  branch: SourceSemanticBranch | SourceTextBranch | SourceKeywordBranch,
): string | null {
  if ('kinds' in branch) return semanticDetail(branch)
  return view.detail
}

export interface MaterialBranchListProps {
  item: SourceReceiptEntry | null
}

/** Independent text / keyword / semantic rows; absent branches stay absent. */
export function MaterialBranchList({ item }: MaterialBranchListProps) {
  if (!item?.text && !item?.keyword && !item?.semantic) return null
  const rows: Array<{
    kind: BranchKind
    branch: SourceTextBranch | SourceKeywordBranch | SourceSemanticBranch
    label: string
  }> = []
  if (item.text) rows.push({ kind: 'text', branch: item.text, label: 'Text' })
  if (item.keyword) rows.push({ kind: 'keyword', branch: item.keyword, label: 'Keyword' })
  if (item.semantic) rows.push({ kind: 'semantic', branch: item.semantic, label: 'Semantic' })
  return (
    <dl className="lg-intake-branches" aria-label="Processing branches">
      {rows.map(({ kind, branch, label }) => {
        const view = describeBranch(
          kind,
          branch.status,
          branch.reason,
          branch.error_code,
          kind === 'text' ? (branch as SourceTextBranch) : undefined,
        )
        const detail = branchDetail(view, branch)
        return (
          <div className="lg-intake-branch" key={kind}>
            <dt>{label}</dt>
            <dd>
              <StatusBadge kind={view.tone}>{view.label}</StatusBadge>
              {detail ? <span className="lg-intake-branch__detail">{detail}</span> : null}
            </dd>
          </div>
        )
      })}
    </dl>
  )
}

export interface ChatMaterialReceiptsProps {
  refs: SourceRef[]
  api: SourcesApi
  onOpen: (sourceId: string) => void
  /** docs/08 §20.2 gate; false means this receipt UI must not render v2 claims. */
  materialIntakeV2: boolean
  /** Media badge additionally requires the media_direct_embedding capability. */
  mediaDirectEmbedding?: boolean
  /** Test seam; the production card uses bounded exponential backoff. */
  baseDelayMs?: number
  maxAttempts?: number
}

export function ChatMaterialReceipts({
  refs,
  api,
  onOpen,
  materialIntakeV2,
  mediaDirectEmbedding = false,
  baseDelayMs = 1000,
  maxAttempts = 12,
}: ChatMaterialReceiptsProps) {
  if (refs.length === 0) return null
  return (
    <section className="lg-intake-receipts" aria-label="Material receipts">
      <div className="lg-intake-receipts__header">
        <span className="lg-intake-receipts__title">Materials</span>
        <span className="lg-intake-receipts__hint">
          Receipts only — not model context. Select materials explicitly to include context.
        </span>
      </div>
      <ul className="lg-intake-receipts__list">
        {refs.map((ref) => (
          <li key={`${ref.source_id}-${ref.source_version}`}>
            <ChatMaterialReceiptCard
              sourceRef={ref}
              api={api}
              onOpen={onOpen}
              materialIntakeV2={materialIntakeV2}
              mediaDirectEmbedding={mediaDirectEmbedding}
              baseDelayMs={baseDelayMs}
              maxAttempts={maxAttempts}
            />
          </li>
        ))}
      </ul>
    </section>
  )
}

function ChatMaterialReceiptCard({
  sourceRef,
  api,
  onOpen,
  materialIntakeV2,
  mediaDirectEmbedding,
  baseDelayMs,
  maxAttempts,
}: {
  sourceRef: SourceRef
  api: SourcesApi
  onOpen: (sourceId: string) => void
  materialIntakeV2: boolean
  mediaDirectEmbedding: boolean
  baseDelayMs: number
  maxAttempts: number
}) {
  const [receipt, setReceipt] = useState<SourceReceipt | null>(null)
  const [filename, setFilename] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [stopped, setStopped] = useState(false)
  const [reloadToken, setReloadToken] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | null = null
    let attempts = 0

    const read = async () => {
      if (cancelled) return
      const [receiptResult, sourceResult] = await Promise.allSettled([
        api.getReceipt(sourceRef.source_id, controller.signal),
        api.getSource(sourceRef.source_id, controller.signal),
      ])
      if (cancelled || controller.signal.aborted) return
      setLoading(false)
      if (sourceResult.status === 'fulfilled') {
        setFilename(sourceResult.value.title ?? sourceResult.value.original?.path ?? null)
      }
      if (receiptResult.status === 'rejected') {
        const cause = receiptResult.reason
        const code =
          cause && typeof cause === 'object' && 'code' in cause
            ? String((cause as { code?: unknown }).code)
            : 'internal_error'
        setError(
          cause instanceof Error ? cause.message
            : code === 'not_found' ? 'Material no longer available' : 'Could not read receipt',
        )
        // A removed/revoked source is terminal; other errors stop rather than
        // hammering the backend. The user can explicitly refresh.
        setStopped(true)
        return
      }
      const next = receiptResult.value
      setReceipt(next)
      setError(null)
      const terminal = !materialIntakeV2 || !isSourceReceiptV2(next) || receiptIsTerminal(next)
      if (terminal) {
        setStopped(false)
        return
      }
      attempts += 1
      if (attempts >= maxAttempts) {
        setStopped(true)
        return
      }
      const delay = Math.min(baseDelayMs * 2 ** Math.min(attempts - 1, 4), 15000)
      timer = setTimeout(() => void read(), delay)
    }

    setLoading(true)
    setError(null)
    setStopped(false)
    void read()
    return () => {
      cancelled = true
      controller.abort()
      if (timer) clearTimeout(timer)
    }
  }, [
    api,
    sourceRef.source_id,
    sourceRef.source_version,
    materialIntakeV2,
    baseDelayMs,
    maxAttempts,
    reloadToken,
  ])

  const v2 = isSourceReceiptV2(receipt) ? receipt : null
  const item = receipt?.latest ?? receipt?.items?.[0] ?? null
  const partial = v2?.partial === true
  const semantic = item?.semantic
  const mediaKinds =
    mediaDirectEmbedding && semantic
      ? semantic.kinds.filter((kind) => kind === 'image' || kind === 'audio')
      : []

  return (
    <article className="lg-intake-receipt" aria-label={`Material receipt ${sourceRef.source_id}`}>
      <div className="lg-intake-receipt__head">
        <Icon name="files" size={14} />
        <span className="lg-intake-receipt__name" title={sourceRef.source_id}>
          {filename ?? receiptFilename(item) ?? sourceRef.source_id}
        </span>
        <StatusBadge kind="neutral">Stored</StatusBadge>
        <StatusBadge kind="neutral">v{sourceRef.source_version}</StatusBadge>
        {partial ? <StatusBadge kind="warning">Partial</StatusBadge> : null}
        {mediaKinds.length > 0 ? (
          <StatusBadge kind="success">media vector: {mediaKinds.join(', ')}</StatusBadge>
        ) : null}
      </div>

      {v2 ? (
        <MaterialBranchList item={item} />
      ) : (
        <p className="lg-intake-receipt__note">
          {loading
            ? 'Reading authoritative receipt…'
            : 'Receipt v2 branches are unavailable on this backend; no branch success is inferred.'}
        </p>
      )}

      {partial ? (
        <p className="lg-intake-receipt__note">
          Some processing steps did not succeed; successful branches remain available.
        </p>
      ) : null}
      {error ? (
        <p className="lg-intake-receipt__error" role="alert">
          Receipt unavailable: {error}
        </p>
      ) : null}
      {stopped && !error ? (
        <p className="lg-intake-receipt__note">
          Still processing. Automatic refresh stopped; reopen or refresh to check again.
        </p>
      ) : null}

      <div className="lg-intake-receipt__actions">
        <button type="button" className="lg-link-button" onClick={() => onOpen(sourceRef.source_id)}>
          View material
        </button>
        <button
          type="button"
          className="lg-link-button"
          onClick={() => setReloadToken((value) => value + 1)}
          disabled={loading}
        >
          Refresh
        </button>
        {item && typeof item.error_code === 'string' && item.error_code ? (
          <span className="lg-intake-receipt__note">error: {item.error_code}</span>
        ) : null}
      </div>
    </article>
  )
}

function receiptFilename(item: SourceReceiptEntry | null): string | null {
  const value = item?.filename
  return typeof value === 'string' && value ? value : null
}

/** Terminal only when every present branch has reached a non-progress state. */
export function receiptIsTerminal(receipt: SourceReceipt): boolean {
  if (!isSourceReceiptV2(receipt)) return true
  const items = receipt.items.length > 0 ? receipt.items : receipt.latest ? [receipt.latest] : []
  if (items.length === 0) return true
  const textTerminal = new Set(['ready', 'unavailable', 'failed'])
  const keywordTerminal = new Set(['searchable', 'no_text', 'failed'])
  const semanticTerminal = new Set([
    'searchable',
    'disabled',
    'unsupported',
    'failed',
  ])
  return items.every(
    (item) =>
      textTerminal.has(item.text.status) &&
      keywordTerminal.has(item.keyword.status) &&
      semanticTerminal.has(item.semantic.status),
  )
}

function formatBytes(size: number): string {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / (1024 * 1024)).toFixed(1)} MB`
}
