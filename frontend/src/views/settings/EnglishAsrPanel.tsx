/**
 * Admin English transcription configuration (LG-161; docs/08 §21, §23; design.md §5).
 *
 * The form is shown only when the existing protected `GET /settings` response
 * contains `english_asr`. It is **not** gated on `capabilities.english_asr` or
 * `english_asr.available`: the health flag means processing availability, not
 * permission to configure, so default-off/missing-runtime states must still be
 * configurable. An old backend omits the view and no new endpoint is probed.
 *
 * Provider-aware (additive 1.22 candidate):
 * * Legacy blocks (no `provider` or `eg2-reader`) keep the local model/Reader
 *   paths and existing limits.
 * * Google native blocks use a model id, base URL, write-only API key and the
 *   official inline request limits. They never render or require Reader/model
 *   directories or the Reader 30-second boundary.
 *
 * Boundaries:
 * * Credentials are write-only: blank means retain; the typed value is cleared
 *   after save/close/provider switch and is never written to storage or the URL.
 * * No TTS, Reader, transcription, download, install, train or test-inference
 *   action exists here. Saving only persists/validates configuration and never
 *   proves that Google, its key or the model is reachable.
 * * A saved settings response is never presented as transcription success.
 */

import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

import { ApiError } from '../../api/client'
import {
  englishAsrProvider,
  englishAsrReasonLabel,
  type EnglishAsrApi,
  type EnglishAsrProvider,
  type EnglishAsrSettingsView,
  type EnglishAsrUpdateInput,
  type EnglishAsrUpdateResult,
} from '../../api/englishAsr'
import {
  GOOGLE_ASR_DEFAULT_BASE_URL,
  GOOGLE_ASR_DEFAULT_MAX_AUDIO_BYTES,
  GOOGLE_ASR_DEFAULT_MODEL,
  GOOGLE_ASR_DEFAULT_TIMEOUT_SECONDS,
  GOOGLE_ASR_MAX_AUDIO_BYTES,
  GOOGLE_ASR_MAX_REQUEST_BYTES,
  GOOGLE_ASR_MAX_TIMEOUT_SECONDS,
  GOOGLE_ASR_MIN_TIMEOUT_SECONDS,
} from '../../api/googleAsr'
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

const LEGACY_PROVIDER: EnglishAsrProvider = 'eg2-reader'
const GOOGLE_PROVIDER: EnglishAsrProvider = 'google-native'
const GOOGLE_MODEL_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/
const GOOGLE_BASE_PATH = '/v1beta'

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

/**
 * Client pre-check of the frozen Google base URL shape. The backend remains the
 * authority; this only keeps obvious typos from a pointless save round trip.
 */
export function isValidGoogleBaseUrl(raw: string): boolean {
  let parsed: URL
  try {
    parsed = new URL(raw)
  } catch {
    return false
  }
  if (parsed.protocol !== 'https:') return false
  if (parsed.username || parsed.password) return false
  if (parsed.search || parsed.hash) return false
  if (parsed.hostname !== 'generativelanguage.googleapis.com') return false
  if (parsed.port && parsed.port !== '443') return false
  return parsed.pathname === GOOGLE_BASE_PATH || parsed.pathname === `${GOOGLE_BASE_PATH}/`
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

function nullableLimitValue(value: unknown, fallback: number): number | null {
  return value === null ? null : limitValue(value, fallback)
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function defaultModel(view: EnglishAsrSettingsView): string {
  return view.model ?? GOOGLE_ASR_DEFAULT_MODEL
}

function defaultBaseUrl(view: EnglishAsrSettingsView): string {
  return view.base_url ?? GOOGLE_ASR_DEFAULT_BASE_URL
}

export function englishAsrAvailabilityKind(view: EnglishAsrSettingsView): StatusKind {
  if (view.available) return 'success'
  if (view.reason === 'disabled') return 'neutral'
  return 'warning'
}

export function englishAsrProviderLabel(view: EnglishAsrSettingsView): string {
  return englishAsrProvider(view) === GOOGLE_PROVIDER
    ? 'Google native'
    : 'EG2 + Reader (legacy)'
}

/**
 * Compact shared status badges for the Settings summary and the editor.
 * `enabled` intentionally is not rendered as a success state: enabling the
 * setting is not proof that processing is available or that credentials work.
 */
export function EnglishAsrStatusBadges({ view }: { view: EnglishAsrSettingsView }) {
  const provider = englishAsrProvider(view)
  const google = provider === GOOGLE_PROVIDER
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
      <StatusBadge kind={google ? 'accent' : 'neutral'}>
        {google ? 'Google native' : 'EG2 + Reader (legacy)'}
      </StatusBadge>
      {google ? (
        <StatusBadge kind={view.credential_configured ? 'accent' : 'warning'}>
          {view.credential_configured ? 'API key configured' : 'API key not configured'}
        </StatusBadge>
      ) : null}
      <StatusBadge kind="neutral">English</StatusBadge>
      <StatusBadge kind={view.timestamps_supported ? 'accent' : 'neutral'}>
        {view.timestamps_supported ? 'word timestamps supported' : 'word timestamps not available'}
      </StatusBadge>
    </div>
  )
}

/**
 * Real reason / availability sentence. Uses only the view fields; never turns
 * a missing runtime, key or capability into "enabled" or "verified".
 */
export function EnglishAsrStatusNote({ view }: { view: EnglishAsrSettingsView }) {
  const google = englishAsrProvider(view) === GOOGLE_PROVIDER
  if (view.available) {
    return (
      <p className="lg-field__hint" role="note">
        {google
          ? 'Native Google transcription is configured and can be attempted, but the key, model and network are not verified. Per-file success comes only from the source receipt; saving settings does not run transcription.'
          : 'Processing availability is reported as available. Per-file success still comes from the source receipt; saving settings does not run transcription.'}
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
  const initialProvider = englishAsrProvider(view)
  const [currentView, setCurrentView] = useState(view)
  const [provider, setProvider] = useState<EnglishAsrProvider>(initialProvider)
  const [enabled, setEnabled] = useState(view.enabled)
  const [modelDir, setModelDir] = useState('')
  const [readerDir, setReaderDir] = useState('')
  const [model, setModel] = useState(defaultModel(view))
  const [baseUrl, setBaseUrl] = useState(defaultBaseUrl(view))
  const [apiKey, setApiKey] = useState('')
  const [timeoutSeconds, setTimeoutSeconds] = useState(
    String(limitValue(view.limits.timeout_seconds, 180)),
  )
  const [maxAudioSeconds, setMaxAudioSeconds] = useState(
    String(limitValue(view.limits.max_audio_seconds, 30)),
  )
  const [maxAudioBytes, setMaxAudioBytes] = useState(
    String(limitValue(view.limits.max_audio_bytes, GOOGLE_ASR_DEFAULT_MAX_AUDIO_BYTES)),
  )
  const [pending, setPending] = useState<'save' | 'reload' | null>(null)
  const [saveError, setSaveError] = useState<ApiError | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [discardOpen, setDiscardOpen] = useState(false)

  const dialogRef = useRef<HTMLDivElement>(null)
  const overlayRef = useRef<HTMLDivElement>(null)
  const mountedRef = useRef(true)
  /**
   * Any draft/provider change bumps this token. A late save/reload response
   * from an older token is ignored, so it can never repopulate a previous
   * provider's secret or overwrite the current provider fields.
   */
  const draftVersionRef = useRef(0)

  const google = provider === GOOGLE_PROVIDER
  const currentProvider = englishAsrProvider(currentView)
  const googleSecretConfigured =
    currentProvider === GOOGLE_PROVIDER && Boolean(currentView.credential_configured)
  const legacyConfigured =
    currentProvider === LEGACY_PROVIDER && Boolean(currentView.configured)

  const dirty =
    provider !== currentProvider ||
    enabled !== currentView.enabled ||
    (google
      ? model.trim() !== defaultModel(currentView).trim() ||
        baseUrl.trim() !== defaultBaseUrl(currentView).trim() ||
        Boolean(apiKey) ||
        timeoutSeconds !== String(limitValue(currentView.limits.timeout_seconds, 180)) ||
        maxAudioBytes !==
          String(limitValue(currentView.limits.max_audio_bytes, GOOGLE_ASR_DEFAULT_MAX_AUDIO_BYTES))
      : Boolean(modelDir.trim()) ||
        Boolean(readerDir.trim()) ||
        timeoutSeconds !== String(limitValue(currentView.limits.timeout_seconds, 180)) ||
        maxAudioSeconds !==
          String(limitValue(currentView.limits.max_audio_seconds, 30)) ||
        maxAudioBytes !==
          String(limitValue(currentView.limits.max_audio_bytes, 10_000_000)))

  const busy = pending !== null

  function touchDraft(): void {
    draftVersionRef.current += 1
    setDiscardOpen(false)
    setSaveError(null)
    setNotice(null)
  }

  function clearSecret(): void {
    setApiKey('')
  }

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

  function finishClose(): void {
    clearSecret()
    onClose()
  }

  function requestClose(): void {
    if (pending === 'save') return
    if (dirty) {
      setDiscardOpen(true)
      return
    }
    finishClose()
  }

  function applyView(nextView: EnglishAsrSettingsView): void {
    setCurrentView(nextView)
    setProvider(englishAsrProvider(nextView))
    setEnabled(nextView.enabled)
    setTimeoutSeconds(String(limitValue(nextView.limits.timeout_seconds, 180)))
    setMaxAudioSeconds(String(limitValue(nextView.limits.max_audio_seconds, 30)))
    setMaxAudioBytes(
      String(limitValue(nextView.limits.max_audio_bytes, GOOGLE_ASR_DEFAULT_MAX_AUDIO_BYTES)),
    )
    setModel(defaultModel(nextView))
    setBaseUrl(defaultBaseUrl(nextView))
    setModelDir('')
    setReaderDir('')
    setDiscardOpen(false)
  }

  function saveInput(): EnglishAsrUpdateInput | ApiError {
    if (google) {
      const timeout = integerField(
        timeoutSeconds,
        GOOGLE_ASR_MIN_TIMEOUT_SECONDS,
        GOOGLE_ASR_MAX_TIMEOUT_SECONDS,
        'Timeout seconds',
      )
      if (timeout instanceof ApiError) return timeout
      const maxBytes = integerField(
        maxAudioBytes,
        1,
        GOOGLE_ASR_MAX_AUDIO_BYTES,
        'Maximum audio bytes',
      )
      if (maxBytes instanceof ApiError) return maxBytes

      const modelValue = model.trim() || GOOGLE_ASR_DEFAULT_MODEL
      if (!GOOGLE_MODEL_PATTERN.test(modelValue)) {
        return validationError(
          'Model must start with a letter or digit and use only letters, digits, dot, underscore or hyphen.',
        )
      }
      const baseValue = baseUrl.trim() || GOOGLE_ASR_DEFAULT_BASE_URL
      if (!isValidGoogleBaseUrl(baseValue)) {
        return validationError(
          'Base URL must be the secure Google Generative Language API endpoint at https://generativelanguage.googleapis.com/v1beta.',
        )
      }
      const newSecret = apiKey.trim()
      if (enabled && !googleSecretConfigured && !newSecret) {
        return validationError(
          'Enter a Google API key before enabling native Google transcription for the first time.',
        )
      }

      const input: EnglishAsrUpdateInput = {
        expected_revision: currentView.revision,
        enabled,
        provider: GOOGLE_PROVIDER,
        runtime: 'google-native',
        model: modelValue,
        base_url: baseValue,
        timeout_seconds: timeout,
        max_audio_bytes: maxBytes,
      }
      // Blank means retain the stored secret; never send ""/null.
      if (newSecret) input.credential_value = newSecret
      return input
    }

    const timeout = integerField(timeoutSeconds, 30, 180, 'Timeout seconds')
    if (timeout instanceof ApiError) return timeout
    const maxSeconds = integerField(maxAudioSeconds, 1, 30, 'Maximum audio seconds')
    if (maxSeconds instanceof ApiError) return maxSeconds
    const maxBytes = integerField(maxAudioBytes, 1, 10_000_000, 'Maximum audio bytes')
    if (maxBytes instanceof ApiError) return maxBytes

    const nextModelDir = modelDir.trim()
    const nextReaderDir = readerDir.trim()
    if (enabled && !legacyConfigured && (!nextModelDir || !nextReaderDir)) {
      return validationError(
        'The first enable requires both absolute local asset directories: model assets and reader assets.',
      )
    }
    if (nextModelDir && !isAbsoluteLocalPath(nextModelDir)) {
      return validationError('The model assets directory must be an absolute local directory.')
    }
    if (nextReaderDir && !isAbsoluteLocalPath(nextReaderDir)) {
      return validationError('The reader assets directory must be an absolute local directory.')
    }

    const input: EnglishAsrUpdateInput = {
      expected_revision: currentView.revision,
      enabled,
      provider: LEGACY_PROVIDER,
      runtime: 'inprocess',
      device: 'cpu',
      timeout_seconds: timeout,
      max_audio_seconds: maxSeconds,
      max_audio_bytes: maxBytes,
    }
    // Blank paths are omitted so the backend retains the stored directories.
    if (nextModelDir) input.model_dir = nextModelDir
    if (nextReaderDir) input.reader_dir = nextReaderDir
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
    const requestVersion = draftVersionRef.current
    const requestProvider = provider
    setPending('save')
    try {
      const result = await api.update(input)
      if (!mountedRef.current) return
      clearSecret()
      if (draftVersionRef.current !== requestVersion || provider !== requestProvider) {
        // Never apply an old provider's response to the current draft.
        setNotice(
          'A late settings response was ignored because the form changed. Reload the current settings before saving again.',
        )
        return
      }
      const nextView = mergeView(currentView, result.english_asr)
      applyView(nextView)
      setNotice(
        `${englishAsrProviderLabel(nextView)} settings saved at revision ${
          result.english_asr.revision
        }. Saving does not run transcription or prove that the provider, key or model is reachable.`,
      )
      onSaved(result)
    } catch (cause) {
      if (!mountedRef.current) return
      // Keep the typed credential on failure so the admin can correct and retry.
      setSaveError(toApiError(cause))
    } finally {
      if (mountedRef.current) setPending(null)
    }
  }

  async function handleReload(): Promise<void> {
    if (busy || !onReload) return
    const requestVersion = draftVersionRef.current
    setPending('reload')
    setNotice(null)
    try {
      const latest = await onReload()
      if (!mountedRef.current) return
      clearSecret()
      if (!latest) {
        setSaveError(
          validationError(
            'English transcription settings are no longer exposed by this backend. Close this form; no configuration is guessed.',
          ),
        )
        return
      }
      if (draftVersionRef.current !== requestVersion) {
        setNotice(
          'A late settings reload was ignored because the form changed. The current draft was kept.',
        )
        return
      }
      applyView(latest)
      setSaveError(null)
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
  const maxRequestBytes = limitValue(limits.max_request_bytes, GOOGLE_ASR_MAX_REQUEST_BYTES)
  const safeAudioSeconds = nullableLimitValue(limits.max_audio_seconds, 30)

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
              replace the human formal version. Choose Google native or the legacy EG2 + Reader
              provider. No TTS, download, install, training or test inference is performed here.
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
            Revision {currentView.revision} · runtime {currentView.runtime} · provider{' '}
            {englishAsrProviderLabel(currentView)} · configured{' '}
            {currentView.configured ? 'yes' : 'no'} · available{' '}
            {currentView.available ? 'yes' : 'no'} · reason:{' '}
            {currentView.available ? 'none' : englishAsrReasonLabel(currentView.reason)}
          </p>
          <EnglishAsrStatusNote view={currentView} />

          <label className="lg-field">
            <span className="lg-field__label">Provider</span>
            <select
              className="lg-field__input"
              value={provider}
              onChange={(event) => {
                const next = event.target.value as EnglishAsrProvider
                setProvider(next)
                clearSecret()
                touchDraft()
              }}
            >
              <option value={GOOGLE_PROVIDER}>Google native audio</option>
              <option value={LEGACY_PROVIDER}>EG2 + Reader (legacy)</option>
            </select>
          </label>
          <p className="lg-field__hint">
            Google native calls the Gemini audio API directly. The legacy provider requires local
            model assets and keeps its original limits.
          </p>

          <label className="lg-field lg-field--inline">
            <input
              type="checkbox"
              checked={enabled}
              onChange={(event) => {
                setEnabled(event.target.checked)
                touchDraft()
              }}
              disabled={pending === 'save'}
            />
            <span className="lg-field__label">Enable English transcription</span>
          </label>
          <p className="lg-field__hint">
            You can save these settings while English transcription is disabled or unavailable.
            Saving does not start transcription.
          </p>

          {google ? (
            <>
              <label className="lg-field">
                <span className="lg-field__label">Model</span>
                <input
                  className="lg-field__input"
                  value={model}
                  onChange={(event) => {
                    setModel(event.target.value)
                    touchDraft()
                  }}
                  placeholder={GOOGLE_ASR_DEFAULT_MODEL}
                  autoComplete="off"
                  spellCheck={false}
                  disabled={pending === 'save'}
                />
              </label>
              <p className="lg-field__hint">
                Default {GOOGLE_ASR_DEFAULT_MODEL}. The form never probes or switches models
                automatically.
              </p>

              <label className="lg-field">
                <span className="lg-field__label">Base URL</span>
                <input
                  className="lg-field__input"
                  value={baseUrl}
                  onChange={(event) => {
                    setBaseUrl(event.target.value)
                    touchDraft()
                  }}
                  placeholder={GOOGLE_ASR_DEFAULT_BASE_URL}
                  autoComplete="off"
                  spellCheck={false}
                  disabled={pending === 'save'}
                />
              </label>
              <p className="lg-field__hint">
                Use the native Google Generative Language API endpoint, not an OpenAI-compatible
                path.
              </p>

              <label className="lg-field">
                <span className="lg-field__label">Google API key (write-only)</span>
                <input
                  className="lg-field__input"
                  type="password"
                  value={apiKey}
                  onChange={(event) => {
                    setApiKey(event.target.value)
                    touchDraft()
                  }}
                  placeholder={
                    googleSecretConfigured
                      ? 'Leave blank to keep the configured API key'
                      : 'Enter the Google API key'
                  }
                  autoComplete="new-password"
                  spellCheck={false}
                  disabled={pending === 'save'}
                />
              </label>
              <p className="lg-field__hint">
                {googleSecretConfigured
                  ? 'An API key is stored. It is never shown again; leave blank to keep it.'
                  : 'The key is sent only for this save and is cleared afterwards. It is not stored in the browser.'}
              </p>

              <details
                className="lg-disclosure"
                aria-label="Google transcription limits and runtime"
              >
                <summary className="lg-disclosure__summary">Limits and runtime</summary>
                <div className="lg-disclosure__body">
                  <label className="lg-field">
                    <span className="lg-field__label">
                      Request timeout (seconds, {GOOGLE_ASR_MIN_TIMEOUT_SECONDS}–
                      {GOOGLE_ASR_MAX_TIMEOUT_SECONDS})
                    </span>
                    <input
                      className="lg-field__input"
                      type="number"
                      min={GOOGLE_ASR_MIN_TIMEOUT_SECONDS}
                      max={GOOGLE_ASR_MAX_TIMEOUT_SECONDS}
                      step="1"
                      value={timeoutSeconds}
                      onChange={(event) => {
                        setTimeoutSeconds(event.target.value)
                        touchDraft()
                      }}
                      disabled={pending === 'save'}
                    />
                  </label>
                  <label className="lg-field">
                    <span className="lg-field__label">
                      Maximum audio bytes (1–{GOOGLE_ASR_MAX_AUDIO_BYTES.toLocaleString()})
                    </span>
                    <input
                      className="lg-field__input"
                      type="number"
                      min="1"
                      max={GOOGLE_ASR_MAX_AUDIO_BYTES}
                      step="1"
                      value={maxAudioBytes}
                      onChange={(event) => {
                        setMaxAudioBytes(event.target.value)
                        touchDraft()
                      }}
                      disabled={pending === 'save'}
                    />
                  </label>
                  <p className="lg-field__hint">
                    Google inline audio is not subject to the legacy short-audio cap. The total
                    request limit is {formatBytes(maxRequestBytes)} including audio encoding
                    overhead; it is fixed by the provider and read-only here. Runtime is fixed to
                    Google native with concurrency {limitValue(limits.max_concurrency, 1)}.
                  </p>
                </div>
              </details>

              <details className="lg-disclosure" aria-label="Google native model summary">
                <summary className="lg-disclosure__summary">Model and endpoint</summary>
                <div className="lg-disclosure__body">
                  <dl className="lg-connection-row__facts">
                    <div>
                      <dt>Provider</dt>
                      <dd>Google native</dd>
                    </div>
                    <div>
                      <dt>Configured model</dt>
                      <dd>{currentView.model ?? 'not reported'}</dd>
                    </div>
                    <div>
                      <dt>Endpoint host</dt>
                      <dd className="lg-card__path">
                        {currentView.base_url ?? GOOGLE_ASR_DEFAULT_BASE_URL}
                      </dd>
                    </div>
                    <div>
                      <dt>Credential</dt>
                      <dd>
                        {currentView.credential_configured
                          ? 'API key stored'
                          : 'no API key stored'}
                      </dd>
                    </div>
                  </dl>
                  <p className="lg-field__hint">
                    Managed model metadata and hashes are not reported for this provider. Saving
                    does not verify the key or model; a source receipt is the only per-file success
                    evidence.
                  </p>
                </div>
              </details>
            </>
          ) : (
            <>
              <label className="lg-field">
                <span className="lg-field__label">Model assets directory (write-only)</span>
                <input
                  className="lg-field__input"
                  value={modelDir}
                  onChange={(event) => {
                    setModelDir(event.target.value)
                    touchDraft()
                  }}
                  placeholder={
                    legacyConfigured
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
                    touchDraft()
                  }}
                  placeholder={
                    legacyConfigured
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

              <details
                className="lg-disclosure"
                aria-label="English transcription limits and runtime"
              >
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
                      onChange={(event) => {
                        setTimeoutSeconds(event.target.value)
                        touchDraft()
                      }}
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
                      onChange={(event) => {
                        setMaxAudioSeconds(event.target.value)
                        touchDraft()
                      }}
                      disabled={pending === 'save'}
                    />
                  </label>
                  <label className="lg-field">
                    <span className="lg-field__label">
                      Maximum audio bytes (1–10,000,000)
                    </span>
                    <input
                      className="lg-field__input"
                      type="number"
                      min="1"
                      max="10000000"
                      step="1"
                      value={maxAudioBytes}
                      onChange={(event) => {
                        setMaxAudioBytes(event.target.value)
                        touchDraft()
                      }}
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

              <details
                className="lg-disclosure"
                aria-label="Pinned English transcription models"
              >
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
            </>
          )}

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
                  onClick={finishClose}
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
              {google ? (
                <>
                  Current limits: {formatBytes(limitValue(limits.max_audio_bytes, GOOGLE_ASR_DEFAULT_MAX_AUDIO_BYTES))}{' '}
                  audio · {formatBytes(maxRequestBytes)} request ·{' '}
                  {limitValue(limits.timeout_seconds, GOOGLE_ASR_DEFAULT_TIMEOUT_SECONDS)} s timeout
                  · concurrency {limitValue(limits.max_concurrency, 1)}
                </>
              ) : (
                <>
                  Current limits: {safeAudioSeconds ?? '—'} s audio ·{' '}
                  {formatBytes(limitValue(limits.max_audio_bytes, 10_000_000))} ·{' '}
                  {limitValue(limits.timeout_seconds, 180)} s timeout · concurrency{' '}
                  {limitValue(limits.max_concurrency, 1)}
                </>
              )}
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
