/**
 * Admin English transcription configuration (LG-161; docs/08 §21, design.md §5).
 *
 * The form is shown only when the existing protected `GET /settings` response
 * contains `english_asr`. It is **not** gated on `capabilities.english_asr` or
 * `english_asr.available`: the health flag means processing availability, not
 * permission to configure, so default-off/missing-runtime states must still be
 * configurable. An old backend omits the view and no new endpoint is probed.
 *
 * Boundaries:
 * * `model_dir`/`reader_dir` are write-only; the read view never returns them.
 *   Blank inputs are omitted (retain stored paths), never sent as `""`/`null`.
 * * No TTS, Reader, transcription, download, install, train or test-inference
 *   action exists here. Saving only persists/validates configuration.
 * * A saved settings response is never presented as transcription success.
 */

import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

import { ApiError } from '../../api/client'
import {
  englishAsrReasonLabel,
  type EnglishAsrApi,
  type EnglishAsrSettingsView,
  type EnglishAsrUpdateInput,
  type EnglishAsrUpdateResult,
} from '../../api/englishAsr'
import { ErrorState } from '../../components/ErrorState'
import { StatusBadge, type StatusKind } from '../../components/StatusBadge'
import { toApiError } from './apiError'

export interface EnglishAsrPanelProps {
  api: EnglishAsrApi
  /** Current `settings.english_asr` view; already present when opened. */
  view: EnglishAsrSettingsView
  onSaved: (result: EnglishAsrUpdateResult) => void
  onClose: () => void
  /** Re-read the existing protected `GET /settings` document (no new probe). */
  onReload?: () => Promise<EnglishAsrSettingsView | null>
}

function validationError(message: string): ApiError {
  return new ApiError({
    message,
    code: 'validation_failed',
    httpStatus: null,
    retryable: false,
  })
}

function focusableElements(root: HTMLElement | null): HTMLElement[] {
  if (!root) return []
  const selector =
    'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
  return Array.from(root.querySelectorAll<HTMLElement>(selector)).filter(
    (element) => element.getAttribute('aria-hidden') !== 'true',
  )
}

function isAbsoluteLocalPath(value: string): boolean {
  return value.startsWith('/') || /^[A-Za-z]:[\\/]/.test(value)
}

function integerField(
  raw: string,
  minimum: number,
  maximum: number,
  label: string,
): number | ApiError {
  if (!/^\d+$/.test(raw.trim())) {
    return validationError(`${label} must be a whole number.`)
  }
  const value = Number(raw.trim())
  if (value < minimum || value > maximum) {
    return validationError(`${label} must be between ${minimum} and ${maximum}.`)
  }
  return value
}

function mergeView(
  current: EnglishAsrSettingsView,
  next: EnglishAsrSettingsView,
): EnglishAsrSettingsView {
  return {
    ...current,
    ...next,
    models: { ...current.models, ...next.models },
    limits: { ...current.limits, ...next.limits },
  }
}

function limitValue(value: unknown, fallback: number): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function englishAsrAvailabilityKind(view: EnglishAsrSettingsView): StatusKind {
  if (view.available) return 'success'
  if (view.reason === 'disabled') return 'neutral'
  return 'warning'
}

/**
 * Compact shared status badges for the Settings summary and the editor.
 * `enabled` intentionally is not rendered as a success state: enabling the
 * setting is not proof that the in-process runtime is available.
 */
export function EnglishAsrStatusBadges({ view }: { view: EnglishAsrSettingsView }) {
  return (
    <div className="lg-english-asr-status" aria-label="English transcription status">
      <StatusBadge kind={view.enabled ? 'accent' : 'neutral'}>
        {view.enabled ? 'enabled' : 'disabled'}
      </StatusBadge>
      <StatusBadge kind={view.configured ? 'accent' : 'neutral'}>
        {view.configured ? 'configured' : 'not configured'}
      </StatusBadge>
      <StatusBadge kind={englishAsrAvailabilityKind(view)}>
        {view.available ? 'available' : 'unavailable'}
      </StatusBadge>
      <StatusBadge kind="neutral">English</StatusBadge>
      <StatusBadge kind={view.timestamps_supported ? 'accent' : 'neutral'}>
        {view.timestamps_supported ? 'word timestamps supported' : 'word timestamps not available'}
      </StatusBadge>
    </div>
  )
}

/**
 * Real reason / availability sentence. Uses only the view fields; never turns
 * a missing runtime or absent capability into "enabled" or "verified".
 */
export function EnglishAsrStatusNote({ view }: { view: EnglishAsrSettingsView }) {
  if (view.available) {
    return (
      <p className="lg-field__hint" role="note">
        Processing availability is reported as available. Per-file success still comes from the
        source receipt; saving settings does not run transcription.
      </p>
    )
  }
  if (!view.enabled) {
    return (
      <p className="lg-field__hint" role="note">
        Disabled. Shared audio is still stored and its original/direct-media branches remain
        independent; no transcript is generated.
      </p>
    )
  }
  return (
    <p className="lg-notice" role="note">
      Enabled, but processing is currently unavailable: {englishAsrReasonLabel(view.reason)}. No
      transcription success is claimed.
    </p>
  )
}

export function EnglishAsrPanel({
  api,
  view,
  onSaved,
  onClose,
  onReload,
}: EnglishAsrPanelProps) {
  const [currentView, setCurrentView] = useState(view)
  const [enabled, setEnabled] = useState(view.enabled)
  const [modelDir, setModelDir] = useState('')
  const [readerDir, setReaderDir] = useState('')
  const [timeoutSeconds, setTimeoutSeconds] = useState(
    String(limitValue(view.limits.timeout_seconds, 180)),
  )
  const [maxAudioSeconds, setMaxAudioSeconds] = useState(
    String(limitValue(view.limits.max_audio_seconds, 30)),
  )
  const [maxAudioBytes, setMaxAudioBytes] = useState(
    String(limitValue(view.limits.max_audio_bytes, 10_000_000)),
  )
  const [pending, setPending] = useState<'save' | 'reload' | null>(null)
  const [saveError, setSaveError] = useState<ApiError | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [discardOpen, setDiscardOpen] = useState(false)

  const dialogRef = useRef<HTMLDivElement>(null)
  const overlayRef = useRef<HTMLDivElement>(null)
  const mountedRef = useRef(true)

  const dirty =
    enabled !== currentView.enabled ||
    Boolean(modelDir.trim()) ||
    Boolean(readerDir.trim()) ||
    timeoutSeconds !== String(limitValue(currentView.limits.timeout_seconds, 180)) ||
    maxAudioSeconds !== String(limitValue(currentView.limits.max_audio_seconds, 30)) ||
    maxAudioBytes !== String(limitValue(currentView.limits.max_audio_bytes, 10_000_000))

  const busy = pending !== null

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
    }
  }, [])

  useEffect(() => {
    const overlay = overlayRef.current
    if (!overlay) return
    const siblings = Array.from(document.body.children).filter(
      (element) => element !== overlay && !element.contains(overlay),
    )
    const previous = siblings.map((element) => ({
      element,
      inert: element.hasAttribute('inert'),
      ariaHidden: element.getAttribute('aria-hidden'),
    }))
    for (const entry of previous) {
      entry.element.setAttribute('inert', '')
      entry.element.setAttribute('aria-hidden', 'true')
    }
    const timer = window.setTimeout(() => {
      const first = focusableElements(dialogRef.current)[0]
      ;(first ?? dialogRef.current)?.focus()
    }, 0)
    return () => {
      window.clearTimeout(timer)
      for (const entry of previous) {
        if (!entry.inert) entry.element.removeAttribute('inert')
        if (entry.ariaHidden === null) {
          entry.element.removeAttribute('aria-hidden')
        } else {
          entry.element.setAttribute('aria-hidden', entry.ariaHidden)
        }
      }
    }
  }, [])

  function requestClose(): void {
    if (pending === 'save') return
    if (dirty) {
      setDiscardOpen(true)
      return
    }
    onClose()
  }

  function saveInput(): EnglishAsrUpdateInput | ApiError {
    const timeout = integerField(timeoutSeconds, 30, 180, 'Timeout seconds')
    if (timeout instanceof ApiError) return timeout
    const maxSeconds = integerField(maxAudioSeconds, 1, 30, 'Maximum audio seconds')
    if (maxSeconds instanceof ApiError) return maxSeconds
    const maxBytes = integerField(maxAudioBytes, 1, 10_000_000, 'Maximum audio bytes')
    if (maxBytes instanceof ApiError) return maxBytes

    const model = modelDir.trim()
    const reader = readerDir.trim()
    if (enabled && !currentView.configured && (!model || !reader)) {
      return validationError(
        'The first enable requires both absolute local asset directories: model assets and reader assets.',
      )
    }
    if (model && !isAbsoluteLocalPath(model)) {
      return validationError('The model assets directory must be an absolute local directory.')
    }
    if (reader && !isAbsoluteLocalPath(reader)) {
      return validationError('The reader assets directory must be an absolute local directory.')
    }

    const input: EnglishAsrUpdateInput = {
      expected_revision: currentView.revision,
      enabled,
      runtime: 'inprocess',
      device: 'cpu',
      timeout_seconds: timeout,
      max_audio_seconds: maxSeconds,
      max_audio_bytes: maxBytes,
    }
    // Blank paths are omitted so the backend retains the stored directories.
    if (model) input.model_dir = model
    if (reader) input.reader_dir = reader
    return input
  }

  async function handleSave(): Promise<void> {
    if (busy) return
    setSaveError(null)
    setNotice(null)
    const input = saveInput()
    if (input instanceof ApiError) {
      setSaveError(input)
      return
    }
    setPending('save')
    try {
      const result = await api.update(input)
      if (!mountedRef.current) return
      const nextView = mergeView(currentView, result.english_asr)
      setCurrentView(nextView)
      setEnabled(nextView.enabled)
      setTimeoutSeconds(String(limitValue(nextView.limits.timeout_seconds, 180)))
      setMaxAudioSeconds(String(limitValue(nextView.limits.max_audio_seconds, 30)))
      setMaxAudioBytes(String(limitValue(nextView.limits.max_audio_bytes, 10_000_000)))
      setModelDir('')
      setReaderDir('')
      setDiscardOpen(false)
      setNotice(
        `English transcription settings saved at revision ${result.english_asr.revision}. Saving does not run transcription or prove processing availability.`,
      )
      onSaved(result)
    } catch (cause) {
      if (!mountedRef.current) return
      setSaveError(toApiError(cause))
    } finally {
      if (mountedRef.current) setPending(null)
    }
  }

  async function handleReload(): Promise<void> {
    if (busy || !onReload) return
    setPending('reload')
    setNotice(null)
    try {
      const latest = await onReload()
      if (!mountedRef.current) return
      if (!latest) {
        setSaveError(
          validationError(
            'English transcription settings are no longer exposed by this backend. Close this form; no configuration is guessed.',
          ),
        )
        return
      }
      setCurrentView(latest)
      setEnabled(latest.enabled)
      setTimeoutSeconds(String(limitValue(latest.limits.timeout_seconds, 180)))
      setMaxAudioSeconds(String(limitValue(latest.limits.max_audio_seconds, 30)))
      setMaxAudioBytes(String(limitValue(latest.limits.max_audio_bytes, 10_000_000)))
      setModelDir('')
      setReaderDir('')
      setSaveError(null)
      setDiscardOpen(false)
      setNotice(`Loaded the current English transcription revision ${latest.revision}.`)
    } catch (cause) {
      if (!mountedRef.current) return
      setSaveError(toApiError(cause))
    } finally {
      if (mountedRef.current) setPending(null)
    }
  }

  const limits = currentView.limits
  const encoder = currentView.models.encoder ?? null
  const reader = currentView.models.reader ?? null

  return createPortal(
    <div
      ref={overlayRef}
      className="lg-modal-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) requestClose()
      }}
    >
      <div
        ref={dialogRef}
        className="lg-modal lg-english-asr-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="lg-english-asr-modal-title"
        tabIndex={-1}
        onKeyDown={(event) => {
          if (event.key === 'Escape') {
            event.preventDefault()
            if (pending === 'save') return
            if (discardOpen) {
              setDiscardOpen(false)
              return
            }
            requestClose()
            return
          }
          if (event.key !== 'Tab') return
          const nodes = focusableElements(dialogRef.current)
          if (nodes.length === 0) {
            event.preventDefault()
            dialogRef.current?.focus()
            return
          }
          const first = nodes[0]
          const last = nodes[nodes.length - 1]
          const active = document.activeElement
          if (
            event.shiftKey &&
            (active === first || !dialogRef.current?.contains(active))
          ) {
            event.preventDefault()
            last.focus()
          } else if (!event.shiftKey && active === last) {
            event.preventDefault()
            first.focus()
          }
        }}
      >
        <header className="lg-modal__header">
          <div>
            <h2 id="lg-english-asr-modal-title" className="lg-modal__title">
              English transcription
            </h2>
            <p className="lg-field__hint">
              Shared English audio only. Machine transcripts are provenance-labelled and never
              replace the human formal version. No TTS, download, install, training or test
              inference is performed here.
            </p>
          </div>
          <button
            type="button"
            className="lg-button lg-modal__close"
            aria-label="Close English transcription settings"
            onClick={requestClose}
            disabled={pending === 'save'}
          >
            ×
          </button>
        </header>

        <div className="lg-modal__body" aria-busy={busy}>
          {saveError ? (
            <ErrorState
              title="English transcription settings were not saved"
              message={saveError.message}
              code={saveError.code}
              retryable={saveError.retryable}
              requestId={saveError.requestId}
            />
          ) : null}
          {saveError?.code === 'revision_conflict' && onReload ? (
            <div className="lg-inline-confirm" role="alert">
              <p>
                Another write changed the canonical settings. The form kept your values; reload the
                current revision before saving again.
              </p>
              <button
                type="button"
                className="lg-button"
                onClick={() => void handleReload()}
                disabled={busy}
              >
                {pending === 'reload' ? 'Reloading…' : 'Reload latest settings'}
              </button>
            </div>
          ) : null}
          {notice ? (
            <p className="lg-notice" role="status">
              {notice}
            </p>
          ) : null}

          <EnglishAsrStatusBadges view={currentView} />
          <p className="lg-field__hint">
            Revision {currentView.revision} · runtime {currentView.runtime} · configured{' '}
            {currentView.configured ? 'yes' : 'no'} · available{' '}
            {currentView.available ? 'yes' : 'no'} · reason:{' '}
            {currentView.available ? 'none' : englishAsrReasonLabel(currentView.reason)}
          </p>
          <EnglishAsrStatusNote view={currentView} />

          <label className="lg-field lg-field--inline">
            <input
              type="checkbox"
              checked={enabled}
              onChange={(event) => {
                setEnabled(event.target.checked)
                setDiscardOpen(false)
              }}
              disabled={pending === 'save'}
            />
            <span className="lg-field__label">Enable English transcription</span>
          </label>
          <p className="lg-field__hint">
            You can save these settings while English transcription is disabled or unavailable.
            Saving does not start transcription.
          </p>

          <label className="lg-field">
            <span className="lg-field__label">Model assets directory (write-only)</span>
            <input
              className="lg-field__input"
              value={modelDir}
              onChange={(event) => {
                setModelDir(event.target.value)
                setDiscardOpen(false)
              }}
              placeholder={
                currentView.configured
                  ? 'Leave blank to keep the stored path'
                  : '/absolute/local/path/to/google__embeddinggemma-2'
              }
              autoComplete="off"
              spellCheck={false}
              disabled={pending === 'save'}
            />
          </label>
          <label className="lg-field">
            <span className="lg-field__label">Reader assets directory (write-only)</span>
            <input
              className="lg-field__input"
              value={readerDir}
              onChange={(event) => {
                setReaderDir(event.target.value)
                setDiscardOpen(false)
              }}
              placeholder={
                currentView.configured
                  ? 'Leave blank to keep the stored path'
                  : '/absolute/local/path/to/eg2-reader-v2'
              }
              autoComplete="off"
              spellCheck={false}
              disabled={pending === 'save'}
            />
          </label>
          <p className="lg-field__hint">
            Saved directory paths are hidden. Leave a field blank to keep its saved path.
            Enter both directories when enabling transcription for the first time.
          </p>

          <details className="lg-disclosure" aria-label="English transcription limits and runtime">
            <summary className="lg-disclosure__summary">Limits and runtime</summary>
            <div className="lg-disclosure__body">
              <label className="lg-field">
                <span className="lg-field__label">Request timeout (seconds, 30–180)</span>
                <input
                  className="lg-field__input"
                  type="number"
                  min="30"
                  max="180"
                  step="1"
                  value={timeoutSeconds}
                  onChange={(event) => setTimeoutSeconds(event.target.value)}
                  disabled={pending === 'save'}
                />
              </label>
              <label className="lg-field">
                <span className="lg-field__label">Maximum audio seconds (1–30)</span>
                <input
                  className="lg-field__input"
                  type="number"
                  min="1"
                  max="30"
                  step="1"
                  value={maxAudioSeconds}
                  onChange={(event) => setMaxAudioSeconds(event.target.value)}
                  disabled={pending === 'save'}
                />
              </label>
              <label className="lg-field">
                <span className="lg-field__label">Maximum audio bytes (1–10,000,000)</span>
                <input
                  className="lg-field__input"
                  type="number"
                  min="1"
                  max="10000000"
                  step="1"
                  value={maxAudioBytes}
                  onChange={(event) => setMaxAudioBytes(event.target.value)}
                  disabled={pending === 'save'}
                />
              </label>
              <p className="lg-field__hint">
                Runtime is fixed to in-process CPU and concurrency is fixed to{' '}
                {limitValue(limits.max_concurrency, 1)}. Thread count is not exposed by the read
                view, so this form omits it rather than overwriting the backend value.
              </p>
            </div>
          </details>

          <details className="lg-disclosure" aria-label="Pinned English transcription models">
            <summary className="lg-disclosure__summary">Pinned models and hashes</summary>
            <div className="lg-disclosure__body">
              <dl className="lg-connection-row__facts">
                <div>
                  <dt>Encoder</dt>
                  <dd className="lg-card__path">
                    {encoder ? `${encoder.id} @ ${encoder.revision}` : 'not reported'}
                  </dd>
                </div>
                {encoder?.sha256 ? (
                  <div>
                    <dt>Encoder SHA-256</dt>
                    <dd className="lg-card__path">{encoder.sha256}</dd>
                  </div>
                ) : null}
                {encoder?.license ? (
                  <div>
                    <dt>Encoder license</dt>
                    <dd>{encoder.license}</dd>
                  </div>
                ) : null}
                <div>
                  <dt>Reader</dt>
                  <dd className="lg-card__path">
                    {reader ? `${reader.id} @ ${reader.revision}` : 'not reported'}
                  </dd>
                </div>
                {reader?.sha256 ? (
                  <div>
                    <dt>Reader SHA-256</dt>
                    <dd className="lg-card__path">{reader.sha256}</dd>
                  </div>
                ) : null}
                {reader?.license ? (
                  <div>
                    <dt>Reader license</dt>
                    <dd>{reader.license}</dd>
                  </div>
                ) : null}
              </dl>
              <p className="lg-field__hint">
                Assets are admin-provisioned local files. The product never downloads, installs,
                trains or replaces them from this form.
              </p>
            </div>
          </details>

          {discardOpen ? (
            <div className="lg-inline-confirm" role="alert">
              <p>Discard the unsaved English transcription changes?</p>
              <div className="lg-modal__footer-right">
                <button
                  type="button"
                  className="lg-button"
                  onClick={() => setDiscardOpen(false)}
                >
                  Keep editing
                </button>
                <button
                  type="button"
                  className="lg-button lg-button--danger"
                  onClick={onClose}
                >
                  Discard changes
                </button>
              </div>
            </div>
          ) : null}
        </div>

        <footer className="lg-modal__footer">
          <div className="lg-modal__footer-left">
            <p className="lg-field__hint">
              Current limits: {limitValue(limits.max_audio_seconds, 30)} s audio ·{' '}
              {formatBytes(limitValue(limits.max_audio_bytes, 10_000_000))} ·{' '}
              {limitValue(limits.timeout_seconds, 180)} s timeout · concurrency{' '}
              {limitValue(limits.max_concurrency, 1)}
            </p>
          </div>
          <div className="lg-modal__footer-right">
            <button
              type="button"
              className="lg-button"
              onClick={requestClose}
              disabled={pending === 'save'}
            >
              Cancel
            </button>
            <button
              type="button"
              className="lg-button lg-button--primary"
              onClick={() => void handleSave()}
              disabled={busy}
            >
              {pending === 'save' ? 'Saving…' : 'Save English transcription settings'}
            </button>
          </div>
        </footer>
      </div>
    </div>,
    document.body,
  )
}

export default EnglishAsrPanel
