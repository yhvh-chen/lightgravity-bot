import { useState, type FormEvent } from 'react'

import { ApiError } from '../../api/client'
import type {
  ConnectionAuthMode,
  ConnectionCreateInput,
  ConnectionTestResult,
  ConnectionUpdateInput,
  ConnectionView,
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
  onCancel?: () => void
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

/** Auto-generated stable id; editable only under Advanced. */
function generateConnectionId(presetId: ProviderPresetId): string {
  const base = presetId === 'legacy-openai' ? 'openai-compatible' : presetId
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
 * Minimal provider form (LG-104/LG-106; docs/07 §3, §6; design.md §5 Settings).
 *
 * Primary flow: Provider → required auth input → defaulted model → Save → Test.
 * Stable ids, backend/auth enums, credential references, endpoint overrides,
 * references and layer diagnostics live under Advanced/Details. The credential
 * value is write-only: it lives in component state, is sent once, then cleared.
 *
 * The provider dropdown is a preset over the existing Connection entity, not a
 * second provider database. Existing records are inferred from their fields and
 * are never migrated or rewritten on load. An empty key field keeps the stored
 * secret; switching provider never deletes it. Test only runs after an explicit
 * click on a saved, non-dirty revision.
 */
export function ConnectionEditor({
  api,
  mode,
  connection,
  onSaved,
  onReload,
  onCancel,
}: ConnectionEditorProps) {
  const creating = mode === 'create'
  const initialPresetId: ProviderPresetId = connection
    ? inferPresetId(connection)
    : 'deepseek'
  const initialPreset = presetById(initialPresetId)

  const [presetId, setPresetId] = useState<ProviderPresetId>(initialPresetId)
  const [id, setId] = useState(() =>
    connection?.id ?? generateConnectionId(initialPresetId),
  )
  const [title, setTitle] = useState(connection?.title ?? '')
  const [enabled, setEnabled] = useState(connection?.enabled ?? true)
  const [model, setModel] = useState(
    connection ? (connection.model ?? '') : (initialPreset.defaultModel ?? ''),
  )
  const [baseUrl, setBaseUrl] = useState(
    connection
      ? (connection.base_url ?? '')
      : (initialPreset.defaultBaseUrl ?? ''),
  )
  const [project, setProject] = useState(connection?.project ?? '')
  const [location, setLocation] = useState(connection?.location ?? '')
  const [modelPath, setModelPath] = useState(connection?.model_path ?? '')
  const [litertBackend, setLitertBackend] = useState<LiteRtBackend>(
    connection?.litert_backend ?? initialPreset.defaultLitertBackend ?? 'GPU',
  )
  const [credentialRef, setCredentialRef] = useState(
    connection?.credential_ref ?? '',
  )
  const [secret, setSecret] = useState('')
  const [revision, setRevision] = useState(connection?.revision ?? 0)
  const [pending, setPending] = useState<'save' | 'test' | 'credential' | null>(
    null,
  )
  const [error, setError] = useState<ApiError | null>(null)
  const [conflict, setConflict] = useState<ApiError | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [testResult, setTestResult] = useState<ConnectionTestResult | null>(null)

  const preset = presetById(presetId)
  const busy = pending !== null
  const declaredCapabilities = connection
    ? connectionCapabilities(connection, preset)
    : preset.fallbackCapabilities

  /**
   * Test only checks the persisted revision. Any unsaved edit (including a
   * typed key) must be saved first, so a test can never imply it validated the
   * draft form.
   */
  const dirty =
    !creating &&
    connection !== null &&
    (presetId !== inferPresetId(connection) ||
      backendForSave(preset) !== connection.backend ||
      title !== (connection.title ?? '') ||
      enabled !== connection.enabled ||
      model !== (connection.model ?? '') ||
      baseUrl !== (connection.base_url ?? '') ||
      project !== (connection.project ?? '') ||
      location !== (connection.location ?? '') ||
      modelPath !== (connection.model_path ?? '') ||
      (preset.id === 'litert' &&
        litertBackend !== (connection.litert_backend ?? 'GPU')) ||
      credentialRef !== (connection.credential_ref ?? '') ||
      secret.length > 0)

  const credentialStatus = connection?.credential ?? null
  const configured = credentialStatus?.configured ?? false
  const stale =
    testResult !== null &&
    connection !== null &&
    (testResult.connection_revision !== revision ||
      (testResult.credential_version ?? null) !==
        (credentialStatus?.version ?? null))

  function backendForSave(current: ProviderPreset): string {
    return current.backend ?? connection?.backend ?? ''
  }

  function applyPreset(nextId: ProviderPresetId): void {
    const next = presetById(nextId)
    setPresetId(nextId)
    if (creating) setId(generateConnectionId(nextId))
    setModel(
      next.defaultModel ??
        (next.id === 'legacy-openai' ? (connection?.model ?? '') : ''),
    )
    setBaseUrl(
      next.defaultBaseUrl ??
        (next.id === 'legacy-openai' ? (connection?.base_url ?? '') : ''),
    )
    setProject(next.requiresProject ? (connection?.project ?? '') : '')
    setLocation(next.requiresLocation ? (connection?.location ?? '') : '')
    setModelPath(next.requiresModelPath ? (connection?.model_path ?? '') : '')
    if (next.defaultLitertBackend) setLitertBackend(next.defaultLitertBackend)
    setError(null)
    setNotice(null)
  }

  function resolvedCredentialRef(): string {
    const typed = credentialRef.trim()
    if (typed) return typed
    if (connection?.credential_ref) return connection.credential_ref
    if (creating && preset.requiresApiKey) return autoCredentialRef(id.trim())
    return ''
  }

  /** Optional LG-104 fields; omitted for untouched old OpenAI-compatible records. */
  function providerFields(): Partial<ConnectionCreateInput> {
    const include =
      preset.backend !== 'openai-compat' ||
      (connection !== null && hasOptionalProviderFields(connection))
    if (!include) return {}
    const fields: Partial<ConnectionCreateInput> = {
      auth_mode: preset.authMode as ConnectionAuthMode,
    }
    if (preset.requiresProject) {
      fields.project = project.trim()
    } else {
      fields.project = null
    }
    if (preset.requiresLocation) {
      fields.location = location.trim()
    } else {
      fields.location = null
    }
    if (preset.requiresModelPath) {
      fields.model_path = modelPath.trim()
    } else {
      fields.model_path = null
    }
    fields.litert_backend = preset.id === 'litert' ? litertBackend : null
    return fields
  }

  function validateForm(): ApiError | null {
    if (!SLUG.test(id.trim())) {
      return validationError(
        'Connection id must be a slug: lowercase letters, digits and dashes, starting with a letter or digit.',
      )
    }
    if (creating && preset.requiresApiKey && !secret.trim()) {
      return validationError(
        `Enter an ${preset.label} API key. It is sent once and never shown again.`,
      )
    }
    if (preset.requiresProject && !project.trim()) {
      return validationError('Enter the Google Cloud project ID for Vertex ADC.')
    }
    if (preset.requiresLocation && !location.trim()) {
      return validationError('Enter the Google Cloud location (for example us-central1).')
    }
    if (preset.requiresModelPath && !modelPath.trim()) {
      return validationError('Enter the local .litertlm model file path.')
    }
    if (preset.requiresBaseUrl && !baseUrl.trim()) {
      return validationError('Enter the OpenAI-compatible base URL.')
    }
    if (secret && !resolvedCredentialRef()) {
      return validationError(
        'A credential reference is required to store an API key. Open Advanced to set one.',
      )
    }
    return null
  }

  function applySaved(saved: ConnectionView): void {
    setRevision(saved.revision)
    setTitle(saved.title)
    setEnabled(saved.enabled)
    setModel(saved.model ?? '')
    setBaseUrl(saved.base_url ?? '')
    setProject(saved.project ?? '')
    setLocation(saved.location ?? '')
    setModelPath(saved.model_path ?? '')
    if (saved.litert_backend) setLitertBackend(saved.litert_backend)
    setCredentialRef(saved.credential_ref ?? '')
    setPresetId((current) =>
      saved.auth_mode == null &&
      presetById(current).backend === saved.backend &&
      saved.backend === 'openai-compat'
        ? current
        : inferPresetId(saved),
    )
  }

  async function reloadAfterConflict(): Promise<void> {
    if (!connection) return
    try {
      const latest = await onReload(connection.id)
      if (latest) setRevision(latest.revision)
    } catch {
      /* The parent surfaces reload failures separately; keep the conflict visible. */
    }
  }

  async function handleFailure(cause: unknown): Promise<void> {
    const err = toApiError(cause)
    if (err.code === 'revision_conflict' && mode === 'edit') {
      await reloadAfterConflict()
      setConflict(err)
      return
    }
    setError(err)
  }

  async function handleSave(event: FormEvent): Promise<void> {
    event.preventDefault()
    setError(null)
    setConflict(null)
    setNotice(null)

    const validation = validateForm()
    if (validation) {
      setError(validation)
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
        setSecret('')
        applySaved(created)
        onSaved(created)
        setNotice(`Created "${created.id}" at revision ${created.revision}.`)
      } else if (connection) {
        const payload: ConnectionUpdateInput = {
          expected_revision: revision,
          title: title.trim() || connection.title,
          enabled,
          model: preset.requiresModelPath ? null : model.trim() || null,
          base_url: preset.requiresBaseUrl ? baseUrl.trim() || null : null,
          credential_action: secret ? 'set' : 'keep',
          ...providerFields(),
        }
        if (backendForSave(preset) !== connection.backend) {
          payload.backend = backendForSave(preset)
        }
        if (credentialRef.trim() !== (connection.credential_ref ?? '')) {
          payload.credential_ref = credentialRef.trim() || null
        }
        if (secret) payload.credential_value = secret
        if (!enabled && connection.references.default_roles.length > 0) {
          payload.clear_defaults = true
        }
        const updated = await api.updateConnection(connection.id, payload)
        setSecret('')
        applySaved(updated)
        onSaved(updated)
        setNotice(`Saved revision ${updated.revision}.`)
      }
    } catch (cause) {
      await handleFailure(cause)
    } finally {
      setPending(null)
    }
  }

  async function handleRemoveCredential(): Promise<void> {
    if (!connection) return
    setError(null)
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
      setSecret('')
      setCredentialRef('')
      setRevision(updated.revision)
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
      onSaved(updated)
      setNotice(message)
    } catch (cause) {
      await handleFailure(cause)
    } finally {
      setPending(null)
    }
  }

  async function handleTest(): Promise<void> {
    if (!connection || creating || dirty) return
    setError(null)
    setPending('test')
    try {
      // Explicit manual Test only. `allow_network` remains a request-level flag
      // for the pending backend capability/budget policy; this UI never runs a
      // test on mount, selection, default change or save.
      const result = await api.testConnection(connection.id, {
        expected_revision: revision,
        allow_network: true,
      })
      setTestResult(result)
    } catch (cause) {
      await handleFailure(cause)
    } finally {
      setPending(null)
    }
  }

  const testDisabledReason = creating
    ? 'Save the connection before testing it.'
    : dirty
      ? 'Save your changes first. Test only checks the saved connection revision.'
      : declaredCapabilities.testable === false
        ? 'The backend has not enabled Test for this provider in this build.'
        : null

  const credentialHint = (() => {
    if (preset.requiresApiKey) {
      if (configured) {
        return 'Configured. Leave empty to keep the stored key; switching provider does not delete it.'
      }
      return creating
        ? 'Required. Sent once, cleared after save, never shown again.'
        : 'Not configured. Test will honestly report a missing credential.'
    }
    if (preset.authMode === 'adc') {
      return 'No API key is entered. Authentication comes from Application Default Credentials on the backend host.'
    }
    return 'No credential is used for this local model.'
  })()

  return (
    <form className="lg-connection-form" onSubmit={handleSave}>
      <div className="lg-connection-form__head">
        <h3 className="lg-section-card__title">
          {creating ? 'New connection' : connection?.title ?? 'Connection'}
        </h3>
        {!creating && connection ? (
          <span className="lg-card__meta">
            <StatusBadge kind="neutral">{preset.label}</StatusBadge>
            <span>rev {revision}</span>
          </span>
        ) : null}
      </div>

      {error ? (
        <ErrorState
          title="Request failed"
          message={error.message}
          code={error.code}
          retryable={error.retryable}
          requestId={error.requestId}
        />
      ) : null}
      {conflict ? (
        <div className="lg-state lg-state--error" role="alert">
          <p className="lg-state__title">Revision conflict</p>
          <p className="lg-state__body">
            This connection changed elsewhere. The latest revision ({revision}) is
            loaded; review your edits and save again. ({conflict.code})
          </p>
        </div>
      ) : null}
      {notice ? (
        <p className="lg-notice" role="status">
          {notice}
        </p>
      ) : null}

      <section className="lg-section-card" aria-label="Provider">
        <h4 className="lg-section-card__title">Provider</h4>
        <label className="lg-field">
          <span className="lg-field__label">Provider</span>
          <select
            className="lg-field__input"
            value={presetId}
            onChange={(event) => applyPreset(event.target.value as ProviderPresetId)}
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

        {preset.requiresApiKey ? (
          <label className="lg-field">
            <span className="lg-field__label">API key (write-only)</span>
            <input
              className="lg-field__input"
              type="password"
              value={secret}
              onChange={(event) => setSecret(event.target.value)}
              placeholder={
                configured ? 'Leave empty to keep the existing key' : 'Paste API key'
              }
              autoComplete="new-password"
              spellCheck={false}
            />
            <span className="lg-field__hint">
              {credentialHint}
              {!creating && configured ? (
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
              onChange={(event) => setProject(event.target.value)}
              placeholder="my-gcp-project"
              autoComplete="off"
              spellCheck={false}
            />
            <span className="lg-field__hint">
              Vertex Standard reads credentials from ADC; no key is stored here.
            </span>
          </label>
        ) : null}

        {preset.requiresLocation ? (
          <label className="lg-field">
            <span className="lg-field__label">Location</span>
            <input
              className="lg-field__input"
              value={location}
              onChange={(event) => setLocation(event.target.value)}
              placeholder="us-central1"
              autoComplete="off"
              spellCheck={false}
            />
          </label>
        ) : null}

        {preset.requiresModelPath ? (
          <>
            <label className="lg-field">
              <span className="lg-field__label">Model file path</span>
              <input
                className="lg-field__input"
                value={modelPath}
                onChange={(event) => setModelPath(event.target.value)}
                placeholder="/models/gemma.litertlm"
                autoComplete="off"
                spellCheck={false}
              />
              <span className="lg-field__hint">
                A readable local .litertlm file. The litert-lm runtime package must
                also be installed on the backend host.
              </span>
            </label>
            <label className="lg-field">
              <span className="lg-field__label">LiteRT backend</span>
              <select
                className="lg-field__input"
                value={litertBackend}
                onChange={(event) =>
                  setLitertBackend(event.target.value as LiteRtBackend)
                }
              >
                {LITERT_BACKENDS.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
              <span className="lg-field__hint">
                CPU/GPU/NPU availability is a hardware prerequisite, not a test
                result.
              </span>
            </label>
          </>
        ) : (
          <label className="lg-field">
            <span className="lg-field__label">Model</span>
            <input
              className="lg-field__input"
              value={model}
              onChange={(event) => setModel(event.target.value)}
              placeholder={preset.defaultModel ?? ''}
              autoComplete="off"
            />
            <span className="lg-field__hint">
              {preset.id === 'deepseek'
                ? 'DeepSeek OpenAI-compatible default.'
                : 'SDK 0.1.22 default; edit only if this provider requires another model id.'}
            </span>
          </label>
        )}

        <div className="lg-connection-form__actions">
          <button
            type="submit"
            className="lg-button lg-button--primary"
            disabled={busy}
          >
            {pending === 'save'
              ? 'Saving…'
              : creating
                ? 'Save connection'
                : 'Save changes'}
          </button>
          {onCancel ? (
            <button
              type="button"
              className="lg-button"
              onClick={onCancel}
              disabled={busy}
            >
              Cancel
            </button>
          ) : null}
        </div>
      </section>

      <section className="lg-section-card" aria-label="Test connection">
        <h4 className="lg-section-card__title">Test connection</h4>
        <ConnectionTestPanel
          result={testResult}
          stale={stale}
          running={pending === 'test'}
          onRun={handleTest}
          disabledReason={testDisabledReason}
        />
        {dirty ? (
          <p className="lg-field__hint" role="status">
            Unsaved changes are not tested.
          </p>
        ) : null}
      </section>

      <details className="lg-disclosure" aria-label="Advanced connection settings">
        <summary className="lg-disclosure__summary">Advanced</summary>
        <div className="lg-disclosure__body">
          <label className="lg-field">
            <span className="lg-field__label">Connection ID</span>
            <input
              className="lg-field__input"
              value={id}
              onChange={(event) => setId(event.target.value)}
              readOnly={!creating}
              placeholder="gemini-api-a1b2c3"
              autoComplete="off"
              required
            />
            <span className="lg-field__hint">
              Stable id used by Team/resource references. Auto-generated; normally
              no change is needed.
            </span>
          </label>
          <label className="lg-field">
            <span className="lg-field__label">Title</span>
            <input
              className="lg-field__input"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder={preset.label}
              autoComplete="off"
            />
            <span className="lg-field__hint">
              Optional human label. Defaults to the provider name.
            </span>
          </label>
          <label className="lg-field lg-field--inline">
            <input
              type="checkbox"
              checked={enabled}
              onChange={(event) => setEnabled(event.target.checked)}
            />
            <span className="lg-field__label">Enabled</span>
          </label>
          {!enabled && connection?.references.default_roles.length ? (
            <p className="lg-notice">
              This connection is a default. Disabling it also clears that default
              reference.
            </p>
          ) : null}

          <p className="lg-field__static">
            Backend: <span className="lg-card__path">{backendForSave(preset)}</span>
          </p>
          <p className="lg-field__static">
            Auth mode: <span className="lg-card__path">{preset.authMode}</span>
          </p>
          <p className="lg-field__static">
            Capabilities:{' '}
            {declaredCapabilities.executable === true ? (
              <StatusBadge kind="success">task execution</StatusBadge>
            ) : (
              <StatusBadge kind="neutral">execution not declared</StatusBadge>
            )}{' '}
            {declaredCapabilities.vendor_verified === true ? (
              <StatusBadge kind="accent">vendor verification recorded</StatusBadge>
            ) : (
              <StatusBadge kind="neutral">vendor verification not declared</StatusBadge>
            )}
          </p>

          {preset.requiresApiKey || credentialRef || configured ? (
            <label className="lg-field">
              <span className="lg-field__label">Credential reference</span>
              <input
                className="lg-field__input"
                value={credentialRef}
                onChange={(event) => setCredentialRef(event.target.value)}
                placeholder="gemini-api-key"
                autoComplete="off"
              />
              <span className="lg-field__hint">
                Only the reference is saved on the connection; the value lives in
                the local secret store. Empty means keep the current secret.
              </span>
            </label>
          ) : null}

          {configured ? (
            <p className="lg-field__static" role="status">
              Credential: <StatusBadge kind="success">Configured</StatusBadge>{' '}
              <span className="lg-field__hint">
                source: {credentialSourceLabel(credentialStatus?.source ?? null)}
                {credentialStatus?.version
                  ? ` · version ${credentialStatus.version}`
                  : ''}
              </span>
            </p>
          ) : (
            <p className="lg-field__static" role="status">
              Credential: <StatusBadge kind="neutral">Not configured</StatusBadge>
            </p>
          )}

          {preset.requiresBaseUrl ? (
            <label className="lg-field">
              <span className="lg-field__label">Base URL</span>
              <input
                className="lg-field__input"
                value={baseUrl}
                onChange={(event) => setBaseUrl(event.target.value)}
                placeholder="https://api.deepseek.com/v1"
                autoComplete="off"
                spellCheck={false}
              />
              <span className="lg-field__hint">
                Endpoint override for an OpenAI-compatible server.
              </span>
            </label>
          ) : null}

          {!creating && connection ? (
            <div className="lg-field">
              <p className="lg-field__static">
                References: defaults{' '}
                {connection.references.default_roles.join(', ') || 'none'}; agents{' '}
                {connection.references.agent_refs.join(', ') || 'none'}.
              </p>
              <button
                type="button"
                className="lg-button"
                onClick={handleRemoveCredential}
                disabled={busy || (!connection.credential_ref && !configured)}
              >
                {pending === 'credential'
                  ? 'Removing…'
                  : 'Remove credential'}
              </button>
              <span className="lg-field__hint">
                Removing a credential is a separate explicit action. It is never
                done by changing provider or leaving the key field empty.
              </span>
            </div>
          ) : null}
        </div>
      </details>
    </form>
  )
}
