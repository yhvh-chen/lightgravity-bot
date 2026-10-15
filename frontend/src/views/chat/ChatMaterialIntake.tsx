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

import { useRef, useState, type ChangeEvent, type DragEvent } from 'react'

import { ErrorState } from '../../components/ErrorState'
import { Icon } from '../../components/icons'
import { StatusBadge } from '../../components/StatusBadge'
import type { MaterialRecord, MaterialState } from './useChatMaterials'

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
