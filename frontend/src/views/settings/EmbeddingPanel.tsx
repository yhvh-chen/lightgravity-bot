import { useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

import { getRuntimeToken } from '../../api/auth'
import { ApiError } from '../../api/client'
import { createSearchApi, type SearchApi } from '../../api/search'
import type {
  EmbeddingDraftTestInput,
  EmbeddingDraftTestResult,
  EmbeddingSettingsView,
  EmbeddingUpdateInput,
  EmbeddingUpdateResult,
  SettingsApi,
} from '../../api/settings'
import { ErrorState } from '../../components/ErrorState'
import { StatusBadge, type StatusKind } from '../../components/StatusBadge'
import { toApiError } from './apiError'

export interface EmbeddingPanelProps {
  api: SettingsApi
  /** Current read-only view loaded with GET /settings; not refetched on render. */
  embedding: EmbeddingSettingsView
  /** Current SETTINGS.md revision, used for optimistic save/conflict checks. */
  revision: number
  onSaved: (result: EmbeddingUpdateResult) => void
  onClose: () => void
  /** True only for the real protected writer (single-user operator/team admin). */
  canRebuild?: boolean
  /** Injectable vector client for tests/integration; real settings use the token. */
  searchApi?: SearchApi
}

function validationError(message: string): ApiError {
  return new ApiError({
    message,
    code: 'validation_failed',
    httpStatus: null,
    retryable: false,
  })
}

function validHttpUrl(raw: string): boolean {
  try {
    const parsed = new URL(raw)
    return (parsed.protocol === 'http:' || parsed.protocol === 'https:') && Boolean(parsed.host)
  } catch {
    return false
  }
}

function positiveNumber(raw: string): number | null {
  const value = Number(raw)
  return Number.isFinite(value) && value > 0 ? value : null
}

function overallKind(overall: string): StatusKind {
  if (overall === 'verified') return 'success'
  if (overall === 'partial') return 'warning'
  if (overall === 'failed') return 'error'
  return 'neutral'
}

function cacheKind(embedding: EmbeddingSettingsView): StatusKind {
  if (embedding.cache.compatible === true) return 'success'
  if (embedding.cache.compatible === false) return 'warning'
  return 'neutral'
}

function cacheLabel(embedding: EmbeddingSettingsView): string {
  if (embedding.cache.compatible === true) return 'cache compatible'
  if (embedding.cache.reason === 'model_mismatch_rebuild_required') {
    return 'cache rebuild required'
  }
  if (embedding.cache.reason === 'cache_version_mismatch_rebuild_required') {
    return 'cache format rebuild required'
  }
  if (embedding.cache.reason === 'cache_missing') return 'no vector cache yet'
  if (embedding.cache.reason === 'embedding_disabled') return 'vector path disabled'
  return embedding.cache.reason ?? 'cache status unavailable'
}

function focusableElements(root: HTMLElement | null): HTMLElement[] {
  if (!root) return []
  const selector =
    'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
  return Array.from(root.querySelectorAll<HTMLElement>(selector)).filter(
    (element) => element.getAttribute('aria-hidden') !== 'true',
  )
}

/**
 * Compact independent Embedding editor (LG-117; docs/08 §19.4, docs/13 §6).
 *
 * This is deliberately not a Connection and never appears in chat/default
 * selectors. Test is a non-persisting draft request made only when clicked and
 * always explicitly opts into one network call; edits discard the old result.
 * The credential input is transient and cleared on save/close.
 */
export function EmbeddingPanel({
  api,
  embedding,
  revision,
  onSaved,
  onClose,
  canRebuild = false,
  searchApi: injectedSearchApi,
}: EmbeddingPanelProps) {
  const vectorApi = useMemo(
    () => injectedSearchApi ?? createSearchApi({ getApiToken: getRuntimeToken }),
    [injectedSearchApi],
  )
  const [enabled, setEnabled] = useState(embedding.enabled)
  const [baseUrl, setBaseUrl] = useState(embedding.base_url ?? '')
  const [model, setModel] = useState(embedding.model ?? '')
  const [secret, setSecret] = useState('')
  const [removeCredential, setRemoveCredential] = useState(false)
  const [timeoutSeconds, setTimeoutSeconds] = useState(String(embedding.timeout_seconds))
  const [coldTimeoutSeconds, setColdTimeoutSeconds] = useState(
    String(embedding.cold_timeout_seconds),
  )
  const [pending, setPending] = useState<'save' | 'test' | null>(null)
  const [saveError, setSaveError] = useState<ApiError | null>(null)
  const [testError, setTestError] = useState<ApiError | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [testResult, setTestResult] = useState<EmbeddingDraftTestResult | null>(null)
  const [testDiscarded, setTestDiscarded] = useState(false)
  const [discardOpen, setDiscardOpen] = useState(false)
  const [rebuildPending, setRebuildPending] = useState(false)
  const [rebuildStatus, setRebuildStatus] = useState<{
    tone: 'success' | 'neutral' | 'error'
    text: string
  } | null>(null)

  const dialogRef = useRef<HTMLDivElement>(null)
  const overlayRef = useRef<HTMLDivElement>(null)
  const mountedRef = useRef(true)
  const draftVersionRef = useRef(0)
  const initialSnapshotRef = useRef(
    JSON.stringify({
      enabled: embedding.enabled,
      baseUrl: embedding.base_url ?? '',
      model: embedding.model ?? '',
      timeoutSeconds: String(embedding.timeout_seconds),
      coldTimeoutSeconds: String(embedding.cold_timeout_seconds),
      secretPresent: false,
      removeCredential: false,
    }),
  )

  const dirty =
    JSON.stringify({
      enabled,
      baseUrl,
      model,
      timeoutSeconds,
      coldTimeoutSeconds,
      secretPresent: secret.length > 0,
      removeCredential,
    }) !== initialSnapshotRef.current
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

  function invalidateTest(): void {
    draftVersionRef.current += 1
    setTestResult(null)
    setTestError(null)
    setTestDiscarded(false)
    setSaveError(null)
    setNotice(null)
    setDiscardOpen(false)
  }

  function change(setter: (value: string) => void, value: string): void {
    setter(value)
    invalidateTest()
  }

  function finishClose(): void {
    setSecret('')
    setRemoveCredential(false)
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

  async function handleRebuild(): Promise<void> {
    if (!canRebuild || rebuildPending) return
    setRebuildPending(true)
    setRebuildStatus(null)
    try {
      const result = await vectorApi.rebuildVector()
      const count = result.documents
      setRebuildStatus({
        tone: result.rebuilt ? 'success' : 'neutral',
        text: result.rebuilt
          ? `Vector index rebuilt from stored originals: ${count} document${count === 1 ? '' : 's'}.`
          : 'Vector rebuild finished without changing the index.',
      })
    } catch (cause: unknown) {
      setRebuildStatus({ tone: 'error', text: toApiError(cause).message })
    } finally {
      setRebuildPending(false)
    }
  }

  function timeoutValues(): { timeout: number; cold: number } | ApiError {
    const timeout = positiveNumber(timeoutSeconds)
    const cold = positiveNumber(coldTimeoutSeconds)
    if (timeout === null) {
      return validationError('Timeout must be a positive number of seconds.')
    }
    if (cold === null) {
      return validationError('Cold-load timeout must be a positive number of seconds.')
    }
    return { timeout, cold }
  }

  function saveInput(): EmbeddingUpdateInput | ApiError {
    if (enabled) {
      if (!baseUrl.trim()) return validationError('Enter the Embedding API base URL.')
      if (!validHttpUrl(baseUrl.trim())) {
        return validationError('Embedding API base URL must be an http(s) URL.')
      }
      if (!model.trim()) return validationError('Enter the actual Embedding model ID.')
    } else if (baseUrl.trim() && !validHttpUrl(baseUrl.trim())) {
      return validationError('Embedding API base URL must be an http(s) URL.')
    }
    const values = timeoutValues()
    if (values instanceof ApiError) return values
    const action = secret.trim()
      ? 'set'
      : removeCredential
        ? 'remove'
        : 'keep'
    return {
      expected_revision: revision,
      enabled,
      base_url: baseUrl.trim() || null,
      model: model.trim() || null,
      credential_action: action,
      ...(action === 'set' ? { credential_value: secret } : {}),
      timeout_seconds: values.timeout,
      cold_timeout_seconds: values.cold,
    }
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
      const result = await api.updateEmbedding(input)
      if (!mountedRef.current) return
      setSecret('')
      onSaved(result)
    } catch (cause) {
      if (!mountedRef.current) return
      setSaveError(toApiError(cause))
    } finally {
      if (mountedRef.current) setPending(null)
    }
  }

  function testBlockReason(): string | null {
    if (!baseUrl.trim()) return 'Enter the API base URL before testing.'
    if (!validHttpUrl(baseUrl.trim())) return 'The API base URL must be an http(s) URL.'
    if (!model.trim()) return 'Enter the actual model ID before testing.'
    const values = timeoutValues()
    if (values instanceof ApiError) return values.message
    return null
  }

  function testInput(): EmbeddingDraftTestInput {
    const values = timeoutValues()
    const timeout = values instanceof ApiError ? embedding.timeout_seconds : values.timeout
    const cold =
      values instanceof ApiError ? embedding.cold_timeout_seconds : values.cold
    const canReuseExisting = embedding.credential.configured && !removeCredential
    return {
      base_url: baseUrl.trim() || null,
      model: model.trim() || null,
      ...(secret.trim() ? { credential_value: secret } : {}),
      use_existing_credential: !secret.trim() && canReuseExisting,
      allow_network: true,
      timeout_seconds: timeout,
      cold_timeout_seconds: cold,
    }
  }

  async function handleTest(): Promise<void> {
    const blocked = testBlockReason()
    if (busy || blocked) return
    const requestVersion = draftVersionRef.current
    setTestError(null)
    setTestResult(null)
    setTestDiscarded(false)
    setNotice(null)
    setPending('test')
    try {
      const result = await api.testDraftEmbedding(testInput())
      if (!mountedRef.current) return
      if (draftVersionRef.current !== requestVersion) {
        setTestDiscarded(true)
        return
      }
      setTestResult(result)
    } catch (cause) {
      if (!mountedRef.current) return
      if (draftVersionRef.current !== requestVersion) {
        setTestDiscarded(true)
        return
      }
      setTestError(toApiError(cause))
    } finally {
      if (mountedRef.current) setPending(null)
    }
  }

  const initialCredential = embedding.credential.configured
    ? embedding.credential.source === 'environment'
      ? 'Environment credential configured (read-only)'
      : 'Saved credential configured'
    : 'No credential configured'
  const blockedReason = testBlockReason()

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
        className="lg-modal lg-embedding-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="lg-embedding-modal-title"
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
            <h2 id="lg-embedding-modal-title" className="lg-modal__title">
              Embedding
            </h2>
            <p className="lg-field__hint">
              Independent semantic retrieval only. This is not a chat, worker or
              reviewer default.
            </p>
          </div>
          <button
            type="button"
            className="lg-button lg-modal__close"
            aria-label="Close embedding settings"
            onClick={requestClose}
            disabled={pending === 'save'}
          >
            ×
          </button>
        </header>

        <div className="lg-modal__body" aria-busy={busy}>
          {saveError ? (
            <ErrorState
              title="Embedding settings were not saved"
              message={saveError.message}
              code={saveError.code}
              retryable={saveError.retryable}
              requestId={saveError.requestId}
            />
          ) : null}
          {testError ? (
            <ErrorState
              title="Embedding test failed"
              message={testError.message}
              code={testError.code}
              retryable={testError.retryable}
              requestId={testError.requestId}
            />
          ) : null}
          {notice ? (
            <p className="lg-notice" role="status">
              {notice}
            </p>
          ) : null}

          <div className="lg-embedding-status" aria-label="Embedding status">
            <StatusBadge kind={enabled ? 'success' : 'neutral'}>
              {enabled ? 'enabled' : 'disabled'}
            </StatusBadge>
            <StatusBadge kind="accent">source: {embedding.source}</StatusBadge>
            <StatusBadge kind={initialCredential.startsWith('No') ? 'warning' : 'success'}>
              {initialCredential}
            </StatusBadge>
            <StatusBadge kind={cacheKind(embedding)}>{cacheLabel(embedding)}</StatusBadge>
          </div>

          {canRebuild ? (
            <section className="lg-embedding-rebuild" aria-label="Vector index maintenance">
              <div className="lg-embedding-rebuild__actions">
                <button
                  type="button"
                  className="lg-button"
                  onClick={() => void handleRebuild()}
                  disabled={busy || rebuildPending}
                >
                  {rebuildPending ? 'Rebuilding…' : 'Rebuild vector index'}
                </button>
                <p className="lg-field__hint">
                  Rebuilds from stored originals. Search and saving settings never rebuild.
                </p>
              </div>
              {rebuildStatus ? (
                <p
                  className={`lg-notice${
                    rebuildStatus.tone === 'error' ? ' lg-notice--error' : ''
                  }`}
                  role="status"
                >
                  {rebuildStatus.text}
                </p>
              ) : null}
            </section>
          ) : null}

          <label className="lg-field lg-field--inline">
            <input
              type="checkbox"
              checked={enabled}
              onChange={(event) => {
                setEnabled(event.target.checked)
                invalidateTest()
              }}
              disabled={pending === 'save'}
            />
            <span className="lg-field__label">Enable semantic retrieval</span>
          </label>
          <p className="lg-field__hint">
            When disabled or unavailable, lexical search and original files remain
            available. Connectivity does not verify retrieval quality.
          </p>

          <label className="lg-field">
            <span className="lg-field__label">API base URL</span>
            <input
              className="lg-field__input"
              value={baseUrl}
              onChange={(event) => change(setBaseUrl, event.target.value)}
              placeholder="https://your-server.example/v1"
              autoComplete="off"
              spellCheck={false}
              disabled={pending === 'save'}
            />
          </label>
          <label className="lg-field">
            <span className="lg-field__label">Actual model ID</span>
            <input
              className="lg-field__input"
              value={model}
              onChange={(event) => change(setModel, event.target.value)}
              placeholder="embeddinggemma-2-Q8_0"
              autoComplete="off"
              spellCheck={false}
              disabled={pending === 'save'}
            />
          </label>

          <label className="lg-field">
            <span className="lg-field__label">
              {initialCredential.startsWith('Saved') ? 'Replace API key' : 'API key (optional)'}
            </span>
            <input
              className="lg-field__input"
              type="password"
              value={secret}
              onChange={(event) => {
                setSecret(event.target.value)
                if (event.target.value) setRemoveCredential(false)
                invalidateTest()
              }}
              placeholder={
                initialCredential.startsWith('Saved')
                  ? 'Leave empty to keep the saved key'
                  : 'Stored only after Save'
              }
              autoComplete="new-password"
              disabled={pending === 'save' || removeCredential}
            />
          </label>
          <p className="lg-field__hint">
            The key is write-only, never returned, and cleared after Save or close.
            Saving a key overrides environment fallback for this saved record.
          </p>
          {initialCredential.startsWith('Saved') ? (
            <div className="lg-embedding-credential-actions">
              <button
                type="button"
                className="lg-button"
                onClick={() => {
                  setRemoveCredential((value) => !value)
                  setSecret('')
                  invalidateTest()
                }}
                disabled={pending !== null}
              >
                {removeCredential ? 'Keep saved key' : 'Remove saved key'}
              </button>
              {removeCredential ? (
                <span className="lg-field__hint">
                  The saved key will be removed when you Save.
                </span>
              ) : null}
            </div>
          ) : null}

          <details className="lg-disclosure" aria-label="Advanced embedding timeouts">
            <summary className="lg-disclosure__summary">Advanced timeouts</summary>
            <div className="lg-disclosure__body">
              <label className="lg-field">
                <span className="lg-field__label">Request timeout (seconds)</span>
                <input
                  className="lg-field__input"
                  type="number"
                  min="0.1"
                  step="0.1"
                  value={timeoutSeconds}
                  onChange={(event) => change(setTimeoutSeconds, event.target.value)}
                  disabled={pending === 'save'}
                />
              </label>
              <label className="lg-field">
                <span className="lg-field__label">Cold-load timeout (seconds)</span>
                <input
                  className="lg-field__input"
                  type="number"
                  min="0.1"
                  step="0.1"
                  value={coldTimeoutSeconds}
                  onChange={(event) => change(setColdTimeoutSeconds, event.target.value)}
                  disabled={pending === 'save'}
                />
              </label>
            </div>
          </details>

          {blockedReason ? (
            <p className="lg-field__hint" role="note">
              {blockedReason}
            </p>
          ) : null}
          {testDiscarded ? (
            <p className="lg-notice" role="status">
              The draft changed while the test was running, so the late result was
              discarded. Run Test again for the current values.
            </p>
          ) : null}
          {testResult ? (
            <section className="lg-embedding-test" aria-live="polite" aria-label="Embedding test result">
              <div className="lg-test__overall">
                <StatusBadge kind={overallKind(testResult.overall)}>
                  {testResult.overall}
                </StatusBadge>
                <StatusBadge kind="neutral">draft · not saved</StatusBadge>
                {testResult.cache_impact === 'rebuild_required' ? (
                  <StatusBadge kind="warning">vector rebuild required</StatusBadge>
                ) : null}
              </div>
              <dl className="lg-test__meta">
                <div>
                  <dt>requested model</dt>
                  <dd>{testResult.requested_model ?? '—'}</dd>
                </div>
                <div>
                  <dt>reported model</dt>
                  <dd>{testResult.reported_model ?? 'not reported'}</dd>
                </div>
                <div>
                  <dt>dimension</dt>
                  <dd>{testResult.dim ?? '—'}</dd>
                </div>
                <div>
                  <dt>latency</dt>
                  <dd>
                    {testResult.latency_seconds === null
                      ? '—'
                      : `${Math.round(testResult.latency_seconds * 1000)} ms`}
                  </dd>
                </div>
                <div>
                  <dt>credential source</dt>
                  <dd>{testResult.credential_source}</dd>
                </div>
                <div>
                  <dt>finished</dt>
                  <dd>{testResult.finished_at}</dd>
                </div>
              </dl>
              {testResult.error ? (
                <p className="lg-inline-confirm" role="alert">
                  {testResult.error.message}
                </p>
              ) : null}
              <details className="lg-disclosure">
                <summary className="lg-disclosure__summary">Check details</summary>
                <div className="lg-disclosure__body">
                  <ul className="lg-test__layers">
                    {testResult.checks.map((check) => (
                      <li key={check.name} className="lg-test__layer">
                        <StatusBadge
                          kind={
                            check.status === 'passed'
                              ? 'success'
                              : check.status === 'failed'
                                ? 'error'
                                : 'neutral'
                          }
                        >
                          {check.status}
                        </StatusBadge>
                        <span className="lg-test__layer-name">{check.name}</span>
                        <span className="lg-card__path">{check.detail}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </details>
              <p className="lg-field__hint">
                A successful connectivity/dimension test does not verify retrieval
                quality. The result is not saved as a test status.
              </p>
            </section>
          ) : null}

          {discardOpen ? (
            <div className="lg-inline-confirm" role="alert">
              <p>Discard the unsaved Embedding changes and clear the typed key?</p>
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
            <button
              type="button"
              className="lg-button"
              onClick={handleTest}
              disabled={busy || blockedReason !== null}
            >
              {pending === 'test' ? 'Testing…' : 'Test'}
            </button>
            <p className="lg-field__hint">
              Test sends one minimal embeddings request only when clicked and is
              never saved.
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
              onClick={handleSave}
              disabled={busy}
            >
              {pending === 'save' ? 'Saving…' : 'Save embedding settings'}
            </button>
          </div>
        </footer>
      </div>
    </div>,
    document.body,
  )
}

export default EmbeddingPanel
