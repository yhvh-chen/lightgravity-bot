import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent as ReactKeyboardEvent } from 'react'
import { createPortal } from 'react-dom'

import { ApiError } from '../../api/client'
import type {
  ConnectionAuthMode,
  ConnectionCreateInput,
  ConnectionTestResult,
  ConnectionUpdateInput,
  ConnectionView,
  DraftConnectionTestInput,
  LiteRtBackend,
  SettingsApi,
} from '../../api/settings'
import { ErrorState } from '../../components/ErrorState'
import { StatusBadge } from '../../components/StatusBadge'
import { toApiError } from './apiError'
import {
  PROVIDER_PRESETS,
  connectionCapabilities,
  inferPresetId,
  presetById,
  type ProviderPreset,
  type ProviderPresetId,
} from './backends'
import { ConnectionTestPanel } from './ConnectionTestPanel'

const SLUG = /^[a-z0-9][a-z0-9-]{0,63}$/
const LITERT_BACKENDS: readonly LiteRtBackend[] = ['CPU', 'GPU', 'NPU']

export interface ConnectionEditorProps {
  api: SettingsApi
  mode: 'create' | 'edit'
  /** Null in create mode. */
  connection: ConnectionView | null
  onSaved: (connection: ConnectionView) => void
  /** Refetch a connection after a revision conflict; returns the latest view. */
  onReload: (id: string) => Promise<ConnectionView | null>
  /** Close without saving (the modal handles dirty confirmation first). */
  onClose: () => void
  /** A separate explicit credential operation updated the saved record. */
  onConnectionUpdated?: (connection: ConnectionView) => void
}

function credentialSourceLabel(source: string | null): string {
  if (source === 'secret_store') return 'local secret store'
  if (source === 'environment') return 'environment (read-only)'
  return 'unknown source'
}

function randomSuffix(): string {
  const cryptoApi = globalThis.crypto
  if (cryptoApi && typeof cryptoApi.randomUUID === 'function') {
    return cryptoApi.randomUUID().replace(/-/g, '').slice(0, 6)
  }
  return Math.random().toString(36).slice(2, 8)
}

/** Auto-generated stable id; never a primary form field. */
function generateConnectionId(presetId: ProviderPresetId): string {
  const base =
    presetId === 'legacy-openai'
      ? 'openai-compatible'
      : presetId === 'legacy-unknown'
        ? 'connection'
        : presetId
  return `${base}-${randomSuffix()}`
}

function autoCredentialRef(id: string): string {
  const ref = `${id}-key`
  return ref.length <= 64 ? ref : ref.slice(0, 64).replace(/-+$/, '')
}

function hasOptionalProviderFields(connection: ConnectionView): boolean {
  return Boolean(
    connection.auth_mode ||
      connection.project ||
      connection.location ||
      connection.model_path ||
      connection.litert_backend,
  )
}

function validationError(message: string): ApiError {
  return new ApiError({
    message,
    code: 'validation_failed',
    httpStatus: null,
    retryable: false,
  })
}

/**
 * Normalize the endpoint identity used for credential reuse. The full origin +
 * path is compared (not the model), so a saved key is never silently sent to a
 * different provider/host/path. Invalid values still compare as opaque text so
 * a change is always detected.
 */
function normalizeEndpoint(value: string | null | undefined): string {
  const raw = (value ?? '').trim()
  if (!raw) return ''
  try {
    const url = new URL(raw)
    const path = url.pathname.replace(/\/+$/, '')
    return `${url.protocol}//${url.host}${path}${url.search}`.toLowerCase()
  } catch {
    return raw.replace(/\/+$/, '').toLowerCase()
  }
}

function credentialIdentity(
  backend: string | null,
  authMode: ConnectionAuthMode,
  baseUrl: string | null | undefined,
  project?: string | null,
): string {
  return [
    backend ?? '',
    authMode,
    normalizeEndpoint(baseUrl),
    authMode === 'adc' ? (project ?? '').trim() : '',
  ].join('|')
}

interface DraftSnapshotInput {
  presetId: ProviderPresetId
  title: string
  enabled: boolean
  model: string
  baseUrl: string
  project: string
  location: string
  modelPath: string
  litertBackend: LiteRtBackend
  secretPresent: boolean
}

function draftSnapshot(input: DraftSnapshotInput): string {
  return JSON.stringify({
    ...input,
    // Never put the secret value itself into a snapshot/string.
    secretPresent: input.secretPresent,
  })
}

function focusableElements(root: HTMLElement | null): HTMLElement[] {
  if (!root) return []
  const selector =
    'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
  return Array.from(root.querySelectorAll<HTMLElement>(selector)).filter(
    (element) =>
      element.getAttribute('aria-hidden') !== 'true' && !element.closest('[hidden]'),
  )
}

/**
 * Accessible New/Edit connection modal (LG-104/LG-110; MODAL-CONTRACT).
 *
 * Primary flow: Provider → Name → required auth/endpoint → Model. Test is a
 * draft request that never saves; Save is a separate create/update call with
 * `expected_revision`. Secrets are write-only component state, cleared on
 * close/save/provider switch, and never written to storage, URLs or logs.
 */
export function ConnectionEditor({
  api,
  mode,
  connection,
  onSaved,
  onReload,
  onClose,
  onConnectionUpdated,
}: ConnectionEditorProps) {
  const creating = mode === 'create'
  const initialPresetId: ProviderPresetId = connection
    ? inferPresetId(connection)
    : 'deepseek'
  const initialPreset = presetById(initialPresetId)
  const initialId = connection?.id ?? generateConnectionId(initialPresetId)
  const initialModel = connection
    ? (connection.model ?? '')
    : (initialPreset.defaultModel ?? '')
  const initialBaseUrl = connection
    ? (connection.base_url ?? '')
    : (initialPreset.defaultBaseUrl ?? '')

  const [presetId, setPresetId] = useState<ProviderPresetId>(initialPresetId)
  const [id, setId] = useState(initialId)
  const [title, setTitle] = useState(connection?.title ?? '')
  const [enabled, setEnabled] = useState(connection?.enabled ?? true)
  const [model, setModel] = useState(initialModel)
  const [baseUrl, setBaseUrl] = useState(initialBaseUrl)
  const [project, setProject] = useState(connection?.project ?? '')
  const [location, setLocation] = useState(connection?.location ?? '')
  const [modelPath, setModelPath] = useState(connection?.model_path ?? '')
  const [litertBackend, setLitertBackend] = useState<LiteRtBackend>(
    connection?.litert_backend ?? initialPreset.defaultLitertBackend ?? 'GPU',
  )
  const [credentialRef, setCredentialRef] = useState(
    connection?.credential_ref ?? '',
  )
  const [credentialStatus, setCredentialStatus] = useState(
    connection?.credential ?? null,
  )
  const [secret, setSecret] = useState('')
  const [revision, setRevision] = useState(connection?.revision ?? 0)
  const [pending, setPending] = useState<
    'save' | 'test' | 'credential' | null
  >(null)
  const [saveError, setSaveError] = useState<ApiError | null>(null)
  const [testError, setTestError] = useState<ApiError | null>(null)
  const [conflict, setConflict] = useState<ApiError | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [testResult, setTestResult] = useState<ConnectionTestResult | null>(null)
  const [testResultVersion, setTestResultVersion] = useState<number | null>(null)
  const [testDiscarded, setTestDiscarded] = useState(false)
  const [discardOpen, setDiscardOpen] = useState(false)
  const [removeCredentialConfirm, setRemoveCredentialConfirm] = useState(false)

  const dialogRef = useRef<HTMLDivElement>(null)
  const overlayRef = useRef<HTMLDivElement>(null)
  const mountedRef = useRef(true)
  const draftVersionRef = useRef(0)

  const preset = presetById(presetId)
  const saving = pending === 'save'
  const busy = pending !== null
  const declaredCapabilities = connection
    ? connectionCapabilities(connection, preset)
    : preset.fallbackCapabilities
  const configured = credentialStatus?.configured ?? false

  const initialSnapshotRef = useRef(
    draftSnapshot({
      presetId: initialPresetId,
      title: connection?.title ?? '',
      enabled: connection?.enabled ?? true,
      model: initialModel,
      baseUrl: initialBaseUrl,
      project: connection?.project ?? '',
      location: connection?.location ?? '',
      modelPath: connection?.model_path ?? '',
      litertBackend: connection?.litert_backend ?? initialPreset.defaultLitertBackend ?? 'GPU',
      secretPresent: false,
    }),
  )

  const currentSnapshot = draftSnapshot({
    presetId,
    title,
    enabled,
    model,
    baseUrl,
    project,
    location,
    modelPath,
    litertBackend,
    secretPresent: secret.length > 0,
  })
  const dirty = currentSnapshot !== initialSnapshotRef.current
  const stale =
    testResult !== null &&
    testResultVersion !== null &&
    testResultVersion !== draftVersionRef.current

  function noteDraftChange(): void {
    draftVersionRef.current += 1
    setDiscardOpen(false)
    setSaveError(null)
    setTestError(null)
    setTestDiscarded(false)
    setNotice(null)
  }

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
    }
  }, [])

  // Background inert + initial focus. Focus is returned by SettingsView after
  // close/save so it can target the new record instead of an unmounted trigger.
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

  function backendForSave(current: ProviderPreset): string {
    return current.backend ?? connection?.backend ?? ''
  }

  const draftIdentity = credentialIdentity(
    backendForSave(preset),
    preset.authMode,
    preset.requiresBaseUrl ? baseUrl : null,
    project,
  )
  const savedIdentity = connection
    ? credentialIdentity(
        connection.backend,
        connection.auth_mode ?? initialPreset.authMode,
        connection.base_url,
        connection.project,
      )
    : null
  const identityChanged = connection !== null && draftIdentity !== savedIdentity
  const requiresFreshKey =
    !creating && preset.requiresApiKey && identityChanged && configured

  function resolvedCredentialRef(): string {
    const typed = credentialRef.trim()
    if (typed) return typed
    if (creating && preset.requiresApiKey) return autoCredentialRef(id.trim())
    if (secret && preset.requiresApiKey) return autoCredentialRef(id.trim())
    return ''
  }

  function providerFields(): Partial<ConnectionCreateInput> {
    const include =
      preset.backend !== 'openai-compat' ||
      preset.id === 'custom-openai' ||
      (connection !== null && hasOptionalProviderFields(connection))
    if (!include) return {}
    return {
      auth_mode: preset.authMode,
      project: preset.requiresProject ? project.trim() : null,
      location: preset.requiresLocation ? location.trim() : null,
      model_path: preset.requiresModelPath ? modelPath.trim() : null,
      litert_backend: preset.id === 'litert' ? litertBackend : null,
    }
  }

  function applyPreset(nextId: ProviderPresetId): void {
    const next = presetById(nextId)
    setPresetId(nextId)
    if (creating) setId(generateConnectionId(nextId))
    setModel(
      next.defaultModel ??
        (next.id === 'legacy-openai' || next.id === 'custom-openai'
          ? (connection?.model ?? '')
          : ''),
    )
    setBaseUrl(
      next.defaultBaseUrl ??
        (next.requiresBaseUrl ? (connection?.base_url ?? '') : ''),
    )
    setProject(next.requiresProject ? (connection?.project ?? '') : '')
    setLocation(next.requiresLocation ? (connection?.location ?? '') : '')
    setModelPath(next.requiresModelPath ? (connection?.model_path ?? '') : '')
    if (next.defaultLitertBackend) setLitertBackend(next.defaultLitertBackend)
    // A key typed for one provider/host is never carried to another recipient.
    setSecret('')
    setTestResult(null)
    setTestResultVersion(null)
    setTestError(null)
    setSaveError(null)
    setConflict(null)
    setNotice(null)
    setRemoveCredentialConfirm(false)
    noteDraftChange()
  }

  function validateSave(): ApiError | null {
    if (!SLUG.test(id.trim())) {
      return validationError(
        'Connection id must be a slug: lowercase letters, digits and dashes, starting with a letter or digit.',
      )
    }
    if (preset.requiresBaseUrl && !baseUrl.trim()) {
      return validationError('Enter the OpenAI-compatible Base URL.')
    }
    if (preset.requiresProject && !project.trim()) {
      return validationError('Enter the Google Cloud project ID for Vertex ADC.')
    }
    if (preset.requiresLocation && !location.trim()) {
      return validationError(
        'Enter the Google Cloud location (for example us-central1).',
      )
    }
    if (preset.requiresModelPath && !modelPath.trim()) {
      return validationError('Enter the local .litertlm model file path.')
    }
    if (creating && preset.requiresApiKey && !secret.trim()) {
      return validationError(
        `Enter an ${preset.label} API key. It is sent once and never shown again.`,
      )
    }
    if (requiresFreshKey && !secret.trim()) {
      return validationError(
        'Provider, authentication or endpoint changed. Enter a new API key before saving; the saved key is never reused for a different provider or host.',
      )
    }
    if (secret && !resolvedCredentialRef()) {
      return validationError(
        'An internal credential reference could not be assigned. Reopen the form and try again.',
      )
    }
    return null
  }

  function testBlockReason(): string | null {
    if (!backendForSave(preset)) {
      return 'This provider record has no recognized backend, so it cannot be tested.'
    }
    if (preset.requiresBaseUrl && !baseUrl.trim()) {
      return 'Enter the Base URL before testing.'
    }
    if (preset.requiresProject && !project.trim()) {
      return 'Enter the Google Cloud project ID before testing.'
    }
    if (preset.requiresLocation && !location.trim()) {
      return 'Enter the Google Cloud location before testing.'
    }
    if (preset.requiresModelPath && !modelPath.trim()) {
      return 'Enter the local model file path before testing.'
    }
    if (creating && preset.requiresApiKey && !secret.trim()) {
      return 'Enter an API key before testing this provider.'
    }
    if (requiresFreshKey && !secret.trim()) {
      return 'Provider, authentication or endpoint changed. Enter a new API key before testing; the saved key is not sent to a different provider or host.'
    }
    if (declaredCapabilities.testable === false) {
      return 'The backend has not enabled Test for this provider in this build.'
    }
    return null
  }

  function draftTestInput(): DraftConnectionTestInput {
    return {
      connection: {
        backend: backendForSave(preset),
        model: preset.requiresModelPath ? null : model.trim() || null,
        base_url: preset.requiresBaseUrl ? baseUrl.trim() || null : null,
        auth_mode: preset.authMode,
        project: preset.requiresProject ? project.trim() || null : null,
        location: preset.requiresLocation ? location.trim() || null : null,
        model_path: preset.requiresModelPath ? modelPath.trim() || null : null,
        litert_backend: preset.id === 'litert' ? litertBackend : null,
      },
      ...(secret ? { credential_value: secret } : {}),
      ...(connection ? { existing_connection_id: connection.id } : {}),
      expected_revision: connection?.revision ?? 0,
      allow_network: true,
    }
  }

  async function reloadAfterConflict(): Promise<void> {
    if (!connection) return
    try {
      const latest = await onReload(connection.id)
      if (latest) setRevision(latest.revision)
    } catch {
      /* Keep the conflict visible; the parent surfaces reload failures. */
    }
  }

  async function handleFailure(cause: unknown, area: 'save' | 'test'): Promise<void> {
    const err = toApiError(cause)
    if (err.code === 'revision_conflict' && mode === 'edit') {
      await reloadAfterConflict()
      if (!mountedRef.current) return
      if (area === 'test') setTestError(err)
      else setConflict(err)
      return
    }
    if (!mountedRef.current) return
    if (area === 'test') setTestError(err)
    else setSaveError(err)
  }

  async function handleTest(): Promise<void> {
    const blocked = testBlockReason()
    if (pending !== null || blocked) return
    const requestVersion = draftVersionRef.current
    setSaveError(null)
    setTestError(null)
    setTestDiscarded(false)
    setConflict(null)
    setNotice(null)
    setTestResult(null)
    setTestResultVersion(null)
    setPending('test')
    try {
      const result = await api.testDraftConnection(draftTestInput())
      if (!mountedRef.current) return
      if (draftVersionRef.current !== requestVersion) {
        // The draft changed while the request was in flight. Never apply the
        // old result to the new draft.
        setTestDiscarded(true)
        return
      }
      setTestResult(result)
      setTestResultVersion(requestVersion)
    } catch (cause) {
      if (!mountedRef.current) return
      if (draftVersionRef.current !== requestVersion) {
        setTestDiscarded(true)
        return
      }
      await handleFailure(cause, 'test')
    } finally {
      if (mountedRef.current) setPending(null)
    }
  }

  async function handleSave(event: FormEvent): Promise<void> {
    event.preventDefault()
    if (pending !== null) return
    setSaveError(null)
    setTestError(null)
    setConflict(null)
    setNotice(null)

    const validation = validateSave()
    if (validation) {
      setSaveError(validation)
      return
    }

    setPending('save')
    try {
      if (creating) {
        const payload: ConnectionCreateInput = {
          id: id.trim(),
          title: title.trim() || preset.label,
          backend: backendForSave(preset),
          model: preset.requiresModelPath ? null : model.trim() || null,
          base_url: preset.requiresBaseUrl ? baseUrl.trim() || null : null,
          credential_ref: resolvedCredentialRef() || null,
          credential_value: secret ? secret : undefined,
          enabled,
          ...providerFields(),
        }
        const created = await api.createConnection(payload)
        if (!mountedRef.current) return
        setSecret('')
        onSaved(created)
      } else if (connection) {
        const payload: ConnectionUpdateInput = {
          expected_revision: revision,
          title: title.trim() || connection.title,
          enabled,
          model: preset.requiresModelPath ? null : model.trim() || null,
          base_url: preset.requiresBaseUrl ? baseUrl.trim() || null : null,
          // Never "keep" a saved credential across a changed provider/auth/
          // endpoint identity. A typed key sets the new value; otherwise the
          // old reference is cleared without sending the old secret anywhere.
          credential_action: secret ? 'set' : identityChanged ? 'remove' : 'keep',
          ...providerFields(),
        }
        if (backendForSave(preset) !== connection.backend) {
          payload.backend = backendForSave(preset)
        }
        const nextRef = resolvedCredentialRef()
        if (nextRef !== (connection.credential_ref ?? '')) {
          payload.credential_ref = nextRef || null
        }
        if (secret) payload.credential_value = secret
        if (!enabled && connection.references.default_roles.length > 0) {
          payload.clear_defaults = true
        }
        const updated = await api.updateConnection(connection.id, payload)
        if (!mountedRef.current) return
        setSecret('')
        onSaved(updated)
      }
    } catch (cause) {
      await handleFailure(cause, 'save')
    } finally {
      if (mountedRef.current) setPending(null)
    }
  }

  async function handleRemoveCredential(): Promise<void> {
    if (!connection || pending !== null) return
    setSaveError(null)
    setConflict(null)
    setNotice(null)
    setPending('credential')
    const previousRef = connection.credential_ref
    const previousSource = connection.credential.source
    try {
      const updated = await api.updateConnection(connection.id, {
        expected_revision: revision,
        credential_action: 'remove',
      })
      if (!mountedRef.current) return
      setSecret('')
      setCredentialRef('')
      setCredentialStatus(updated.credential)
      setRevision(updated.revision)
      setRemoveCredentialConfirm(false)
      let message = 'Credential reference removed from the connection.'
      if (previousRef && previousSource === 'secret_store') {
        try {
          await api.removeCredential(previousRef)
          message = 'Credential removed from the local secret store.'
        } catch (cause) {
          message = `Connection saved without a credential, but the stored secret could not be deleted: ${
            toApiError(cause).message
          }`
        }
      } else if (previousSource === 'environment') {
        message =
          'Connection no longer references a credential. Environment credentials are read-only and were not touched.'
      }
      if (!mountedRef.current) return
      setNotice(message)
      onConnectionUpdated?.(updated)
    } catch (cause) {
      await handleFailure(cause, 'save')
    } finally {
      if (mountedRef.current) setPending(null)
    }
  }

  function requestClose(): void {
    if (saving) return
    if (dirty) {
      setDiscardOpen(true)
      return
    }
    onClose()
  }

  function handleDialogKeyDown(event: ReactKeyboardEvent<HTMLDivElement>): void {
    if (event.key === 'Escape') {
      event.preventDefault()
      if (saving) return
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
    if (event.shiftKey && (active === first || !dialogRef.current?.contains(active))) {
      event.preventDefault()
      last.focus()
    } else if (!event.shiftKey && active === last) {
      event.preventDefault()
      first.focus()
    }
  }

  const credentialHint = (() => {
    if (!preset.requiresApiKey) {
      if (preset.authMode === 'adc') {
        return 'No API key is entered. Authentication comes from Application Default Credentials on the backend host; this form never runs gcloud.'
      }
      return 'No credential is used for this local model.'
    }
    if (creating) {
      return 'Required. Sent only with Save or an explicit Test, then cleared; never stored in the browser.'
    }
    if (identityChanged) {
      return configured
        ? 'Provider, authentication or endpoint changed. Enter a new key; the saved key is never reused for a different provider or host.'
        : 'Provider, authentication or endpoint changed. Enter a key for the new recipient; no saved key will be reused.'
    }
    if (configured) {
      return 'Configured. Leave empty to use the saved key for this same provider and endpoint.'
    }
    return 'No saved key. Enter one here or Test will report the missing credential honestly.'
  })()

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
        className="lg-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="lg-connection-modal-title"
        tabIndex={-1}
        onKeyDown={handleDialogKeyDown}
      >
        <form className="lg-modal__form" onSubmit={handleSave} aria-busy={busy}>
          <header className="lg-modal__header">
            <div>
              <h2 id="lg-connection-modal-title" className="lg-modal__title">
                {creating ? 'New connection' : `Edit ${connection?.title ?? 'connection'}`}
              </h2>
              <p className="lg-field__hint">
                {creating
                  ? 'Configure and optionally test an unsaved draft.'
                  : `${preset.label} · draft revision ${revision}`}
              </p>
            </div>
            <button
              type="button"
              className="lg-button lg-modal__close"
              aria-label="Close connection dialog"
              onClick={requestClose}
              disabled={saving}
            >
              ×
            </button>
          </header>

          <div className="lg-modal__body">
            {saveError ? (
              <ErrorState
                title="Request failed"
                message={saveError.message}
                code={saveError.code}
                retryable={saveError.retryable}
                requestId={saveError.requestId}
              />
            ) : null}
            {conflict ? (
              <div className="lg-state lg-state--error" role="alert">
                <p className="lg-state__title">Revision conflict</p>
                <p className="lg-state__body">
                  This connection changed elsewhere. The latest revision ({revision})
                  is loaded; review your edits and save again. ({conflict.code})
                </p>
              </div>
            ) : null}
            {notice ? (
              <p className="lg-notice" role="status">
                {notice}
              </p>
            ) : null}

            <section className="lg-modal__section" aria-label="Connection fields">
              <label className="lg-field">
                <span className="lg-field__label">Provider</span>
                <select
                  className="lg-field__input"
                  value={presetId}
                  onChange={(event) =>
                    applyPreset(event.target.value as ProviderPresetId)
                  }
                  disabled={saving}
                >
                  {PROVIDER_PRESETS.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.label}
                    </option>
                  ))}
                  {preset.legacyOnly ? (
                    <option value={preset.id}>{preset.label}</option>
                  ) : null}
                </select>
              </label>
              <p className="lg-field__hint">
                {preset.note} {preset.runtimeNote}
              </p>
              {identityChanged ? (
                <p className="lg-notice" role="status">
                  The provider, authentication or endpoint changed. The old saved
                  credential is never reused for the new recipient; enter a new key
                  for API-key providers, otherwise saving clears the old reference.
                </p>
              ) : null}

              <label className="lg-field">
                <span className="lg-field__label">Name</span>
                <input
                  className="lg-field__input"
                  value={title}
                  onChange={(event) => {
                    setTitle(event.target.value)
                    noteDraftChange()
                  }}
                  placeholder={preset.label}
                  autoComplete="off"
                  disabled={saving}
                />
                <span className="lg-field__hint">
                  Optional human label. The internal id is generated automatically.
                </span>
              </label>

              {preset.requiresApiKey ? (
                <label className="lg-field">
                  <span className="lg-field__label">API key (write-only)</span>
                  <input
                    className="lg-field__input"
                    type="password"
                    value={secret}
                    onChange={(event) => {
                      setSecret(event.target.value)
                      noteDraftChange()
                    }}
                    placeholder={
                      configured && !identityChanged
                        ? 'Leave empty to use the saved key'
                        : 'Paste API key'
                    }
                    autoComplete="new-password"
                    spellCheck={false}
                    disabled={saving}
                  />
                  <span className="lg-field__hint">
                    {credentialHint}
                    {configured && !identityChanged ? (
                      <>
                        {' '}
                        Status: <StatusBadge kind="success">Configured</StatusBadge>
                      </>
                    ) : null}
                  </span>
                </label>
              ) : null}

              {preset.requiresProject ? (
                <label className="lg-field">
                  <span className="lg-field__label">Project ID</span>
                  <input
                    className="lg-field__input"
                    value={project}
                    onChange={(event) => {
                      setProject(event.target.value)
                      noteDraftChange()
                    }}
                    placeholder="my-gcp-project"
                    autoComplete="off"
                    spellCheck={false}
                    disabled={saving}
                  />
                  <span className="lg-field__hint">
                    Vertex ADC uses Application Default Credentials on the backend
                    host; no key is stored here.
                  </span>
                </label>
              ) : null}

              {preset.requiresLocation ? (
                <label className="lg-field">
                  <span className="lg-field__label">Location</span>
                  <input
                    className="lg-field__input"
                    value={location}
                    onChange={(event) => {
                      setLocation(event.target.value)
                      noteDraftChange()
                    }}
                    placeholder="us-central1"
                    autoComplete="off"
                    spellCheck={false}
                    disabled={saving}
                  />
                </label>
              ) : null}

              {preset.requiresBaseUrl ? (
                <label className="lg-field">
                  <span className="lg-field__label">Base URL</span>
                  <input
                    className="lg-field__input"
                    value={baseUrl}
                    onChange={(event) => {
                      setBaseUrl(event.target.value)
                      noteDraftChange()
                    }}
                    placeholder="https://your-server.example/v1"
                    autoComplete="off"
                    spellCheck={false}
                    disabled={saving}
                    required
                  />
                  <span className="lg-field__hint">
                    Required OpenAI-compatible endpoint. This build only permits the
                    existing DeepSeek upstream for live testing/execution; other
                    hosts are blocked honestly before a network request.
                  </span>
                </label>
              ) : null}

              {preset.requiresModelPath ? (
                <>
                  <label className="lg-field">
                    <span className="lg-field__label">Model file path</span>
                    <input
                      className="lg-field__input"
                      value={modelPath}
                      onChange={(event) => {
                        setModelPath(event.target.value)
                        noteDraftChange()
                      }}
                      placeholder="/models/gemma.litertlm"
                      autoComplete="off"
                      spellCheck={false}
                      disabled={saving}
                    />
                    <span className="lg-field__hint">
                      A readable local .litertlm file. The litert-lm runtime package
                      must be installed on the backend host.
                    </span>
                  </label>
                  <label className="lg-field">
                    <span className="lg-field__label">LiteRT backend</span>
                    <select
                      className="lg-field__input"
                      value={litertBackend}
                      onChange={(event) => {
                        setLitertBackend(event.target.value as LiteRtBackend)
                        noteDraftChange()
                      }}
                      disabled={saving}
                    >
                      {LITERT_BACKENDS.map((item) => (
                        <option key={item} value={item}>
                          {item}
                        </option>
                      ))}
                    </select>
                    <span className="lg-field__hint">
                      CPU/GPU/NPU availability is a hardware prerequisite, not a test
                      result. Test only checks configuration and paths.
                    </span>
                  </label>
                </>
              ) : (
                <label className="lg-field">
                  <span className="lg-field__label">Model</span>
                  <input
                    className="lg-field__input"
                    value={model}
                    onChange={(event) => {
                      setModel(event.target.value)
                      noteDraftChange()
                    }}
                    placeholder={
                      preset.defaultModel ??
                      (preset.id === 'custom-openai'
                        ? 'Model id required by your server'
                        : '')
                    }
                    autoComplete="off"
                    spellCheck={false}
                    disabled={saving}
                  />
                  <span className="lg-field__hint">
                    {preset.id === 'deepseek'
                      ? 'DeepSeek OpenAI-compatible default from the existing executable path.'
                      : 'Sent to the provider as-is. Saving never claims execution or vendor verification.'}
                  </span>
                </label>
              )}
            </section>

            {testError ? (
              <ErrorState
                title="Draft test failed"
                message={testError.message}
                code={testError.code}
                retryable={testError.retryable}
                requestId={testError.requestId}
              />
            ) : null}
            {testDiscarded ? (
              <p className="lg-notice" role="status">
                The draft changed while Test was running, so that late result was
                discarded. The current values are unchanged; run Test again if
                needed.
              </p>
            ) : null}
            <section className="lg-modal__section" aria-label="Draft test result">
              <ConnectionTestPanel
                result={testResult}
                stale={stale}
                running={pending === 'test'}
                draft
              />
            </section>

            <details className="lg-disclosure" aria-label="Advanced connection settings">
              <summary className="lg-disclosure__summary">Advanced</summary>
              <div className="lg-disclosure__body">
                <label className="lg-field">
                  <span className="lg-field__label">Connection ID</span>
                  <input
                    className="lg-field__input"
                    value={id}
                    readOnly
                    aria-readonly="true"
                    autoComplete="off"
                  />
                  <span className="lg-field__hint">
                    Stable id used by Team/resource references. Generated
                    automatically and not editable here.
                  </span>
                </label>
                <label className="lg-field lg-field--inline">
                  <input
                    type="checkbox"
                    checked={enabled}
                    onChange={(event) => {
                      setEnabled(event.target.checked)
                      noteDraftChange()
                    }}
                    disabled={saving}
                  />
                  <span className="lg-field__label">Enabled</span>
                </label>
                {!enabled && connection?.references.default_roles.length ? (
                  <p className="lg-notice">
                    This connection is a default. Disabling it also clears that
                    default reference.
                  </p>
                ) : null}

                <p className="lg-field__static">
                  Backend:{' '}
                  <span className="lg-card__path">{backendForSave(preset)}</span>
                </p>
                <p className="lg-field__static">
                  Auth mode: <span className="lg-card__path">{preset.authMode}</span>
                </p>
                <p className="lg-field__static">
                  Capabilities:{' '}
                  {declaredCapabilities.executable === true ? (
                    <StatusBadge kind="success">task execution available</StatusBadge>
                  ) : (
                    <StatusBadge kind="neutral">execution not enabled</StatusBadge>
                  )}{' '}
                  {declaredCapabilities.vendor_verified === true ? (
                    <StatusBadge kind="accent">vendor verification recorded</StatusBadge>
                  ) : (
                    <StatusBadge kind="neutral">
                      vendor verification not declared
                    </StatusBadge>
                  )}
                </p>

                {preset.requiresApiKey || credentialRef || configured ? (
                  <p className="lg-field__static">
                    Credential reference:{' '}
                    <span className="lg-card__path">
                      {credentialRef || resolvedCredentialRef() || 'assigned on save'}
                    </span>
                  </p>
                ) : null}
                <p className="lg-field__static" role="status">
                  Credential:{' '}
                  {configured ? (
                    <StatusBadge kind="success">Configured</StatusBadge>
                  ) : (
                    <StatusBadge kind="neutral">Not configured</StatusBadge>
                  )}{' '}
                  {configured ? (
                    <span className="lg-field__hint">
                      source: {credentialSourceLabel(credentialStatus?.source ?? null)}
                      {credentialStatus?.version
                        ? ` · version ${credentialStatus.version}`
                        : ''}
                    </span>
                  ) : null}
                </p>

                {!creating && connection ? (
                  <div className="lg-field">
                    <p className="lg-field__static">
                      References: defaults{' '}
                      {connection.references.default_roles.join(', ') || 'none'};
                      agents {connection.references.agent_refs.join(', ') || 'none'}.
                    </p>
                    {removeCredentialConfirm ? (
                      <div className="lg-inline-confirm" role="alert">
                        <p>
                          Remove the saved credential from this connection? This is
                          separate from Save and cannot be undone.
                        </p>
                        <div className="lg-modal__footer-right">
                          <button
                            type="button"
                            className="lg-button"
                            onClick={() => setRemoveCredentialConfirm(false)}
                            disabled={busy}
                          >
                            Keep credential
                          </button>
                          <button
                            type="button"
                            className="lg-button lg-button--danger"
                            onClick={handleRemoveCredential}
                            disabled={busy}
                          >
                            {pending === 'credential' ? 'Removing…' : 'Remove credential'}
                          </button>
                        </div>
                      </div>
                    ) : (
                      <button
                        type="button"
                        className="lg-button"
                        onClick={() => setRemoveCredentialConfirm(true)}
                        disabled={busy || (!connection.credential_ref && !configured)}
                      >
                        Remove saved credential…
                      </button>
                    )}
                    <span className="lg-field__hint">
                      Changing provider or leaving the key field empty never removes
                      the saved credential by itself.
                    </span>
                  </div>
                ) : null}
              </div>
            </details>
          </div>

          {discardOpen ? (
            <div className="lg-modal__confirm" role="alert">
              <p>Discard this unsaved draft and close? Your typed key will be lost.</p>
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
                  onClick={() => {
                    setSecret('')
                    onClose()
                  }}
                >
                  Discard and close
                </button>
              </div>
            </div>
          ) : null}

          <footer className="lg-modal__footer">
            <div className="lg-modal__footer-left">
              <button
                type="button"
                className="lg-button"
                onClick={handleTest}
                disabled={busy || blockedReason !== null}
                aria-busy={pending === 'test'}
              >
                {pending === 'test' ? 'Testing…' : 'Test connection'}
              </button>
              {blockedReason ? (
                <p className="lg-field__hint" role="status">
                  {blockedReason}
                </p>
              ) : null}
            </div>
            <div className="lg-modal__footer-right">
              <button
                type="button"
                className="lg-button"
                onClick={requestClose}
                disabled={saving}
              >
                Cancel
              </button>
              <button
                type="submit"
                className="lg-button lg-button--primary"
                disabled={busy}
              >
                {saving
                  ? 'Saving…'
                  : creating
                    ? 'Save connection'
                    : 'Save changes'}
              </button>
            </div>
          </footer>
        </form>
      </div>
    </div>,
    document.body,
  )
}
