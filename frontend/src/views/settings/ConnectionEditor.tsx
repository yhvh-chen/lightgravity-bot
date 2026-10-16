import { useState, type FormEvent } from 'react'

import { ApiError } from '../../api/client'
import {
  DEFAULT_BASE_URL,
  DEFAULT_EXECUTABLE_BACKEND,
  PREFERRED_MODEL,
  type ConnectionTestResult,
  type ConnectionUpdateInput,
  type ConnectionView,
  type SettingsApi,
} from '../../api/settings'
import { ErrorState } from '../../components/ErrorState'
import { StatusBadge } from '../../components/StatusBadge'
import { toApiError } from './apiError'
import { BACKENDS, backendInfo, isExecutableBackend } from './backends'
import { ConnectionTestPanel } from './ConnectionTestPanel'

const SLUG = /^[a-z0-9][a-z0-9-]{0,63}$/

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

/**
 * Type-aware Connection form (docs/07 §3, §6; design.md §5 Settings).
 *
 * The form renders fields for the selected backend only. The credential value
 * is a write-only password field: it lives in component state, is submitted
 * once and then cleared, and is never echoed by the API or persisted in the
 * browser. Revision conflicts are surfaced explicitly with a reload.
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
  const [id, setId] = useState('')
  const [title, setTitle] = useState(connection?.title ?? '')
  const [backend, setBackend] = useState(
    connection?.backend ?? DEFAULT_EXECUTABLE_BACKEND,
  )
  const [enabled, setEnabled] = useState(connection?.enabled ?? true)
  const [model, setModel] = useState(connection?.model ?? PREFERRED_MODEL)
  const [baseUrl, setBaseUrl] = useState(connection?.base_url ?? DEFAULT_BASE_URL)
  const [credentialRef, setCredentialRef] = useState(connection?.credential_ref ?? '')
  const [secret, setSecret] = useState('')
  const [revision, setRevision] = useState(connection?.revision ?? 0)
  const [pending, setPending] = useState<'save' | 'test' | 'credential' | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [conflict, setConflict] = useState<ApiError | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [testResult, setTestResult] = useState<ConnectionTestResult | null>(null)

  const executable = isExecutableBackend(backend)
  const info = backendInfo(backend)
  const busy = pending !== null

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

    if (creating) {
      if (!SLUG.test(id.trim())) {
        setError(
          new ApiError({
            message:
              'Connection id must be a slug: lowercase letters, digits and dashes, starting with a letter or digit.',
            code: 'validation_failed',
            httpStatus: null,
            retryable: false,
          }),
        )
        return
      }
    }
    if (secret && !credentialRef.trim()) {
      setError(
        new ApiError({
          message:
            'A credential_ref is required to store an API key. Set a reference such as "deepseek-primary".',
          code: 'validation_failed',
          httpStatus: null,
          retryable: false,
        }),
      )
      return
    }

    setPending('save')
    try {
      if (creating) {
        const created = await api.createConnection({
          id: id.trim(),
          title: title.trim() || null,
          backend,
          model: executable ? model.trim() || null : null,
          base_url: executable ? baseUrl.trim() || null : null,
          credential_ref: credentialRef.trim() || null,
          credential_value: secret ? secret : undefined,
          enabled,
        })
        setSecret('')
        onSaved(created)
        setNotice(`Created "${created.id}" at revision ${created.revision}.`)
      } else if (connection) {
        const payload: ConnectionUpdateInput = {
          expected_revision: revision,
          title: title.trim() || null,
          enabled,
          credential_action: secret ? 'set' : 'keep',
        }
        if (executable) {
          payload.model = model.trim() || null
          payload.base_url = baseUrl.trim() || null
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
        setRevision(updated.revision)
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
    if (!connection) return
    setError(null)
    setPending('test')
    try {
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

  const credentialStatus = connection?.credential ?? null
  const configured = credentialStatus?.configured ?? false
  const configuredSource = credentialStatus?.source ?? null
  const stale =
    testResult !== null &&
    connection !== null &&
    (testResult.connection_revision !== revision ||
      (testResult.credential_version ?? null) !==
        (credentialStatus?.version ?? null))

  const testDisabledReason = !executable
    ? `Testing is unavailable for ${info?.label ?? backend}: it is not a verified executable backend.`
    : creating
      ? 'Save the connection before testing it.'
      : null

  return (
    <form className="lg-connection-form" onSubmit={handleSave}>
      <div className="lg-connection-form__head">
        <h3 className="lg-section-card__title">
          {creating ? 'New connection' : connection?.title ?? 'Connection'}
        </h3>
        {!creating && connection ? (
          <span className="lg-card__meta">
            <span className="lg-card__path">{connection.id}</span>
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

      <section className="lg-section-card" aria-label="Connection">
        <h4 className="lg-section-card__title">Connection</h4>
        {creating ? (
          <label className="lg-field">
            <span className="lg-field__label">Connection id</span>
            <input
              className="lg-field__input"
              value={id}
              onChange={(event) => setId(event.target.value)}
              placeholder="deepseek-primary"
              autoComplete="off"
              required
            />
            <span className="lg-field__hint">
              Stable slug used by Resources and Team references.
            </span>
          </label>
        ) : null}
        <label className="lg-field">
          <span className="lg-field__label">Title</span>
          <input
            className="lg-field__input"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="DeepSeek (primary)"
            autoComplete="off"
          />
        </label>
        <label className="lg-field">
          <span className="lg-field__label">Backend</span>
          {creating ? (
            <select
              className="lg-field__input"
              value={backend}
              onChange={(event) => setBackend(event.target.value)}
            >
              {BACKENDS.map((item) => (
                <option
                  key={item.id}
                  value={item.id}
                  disabled={item.availability !== 'verified'}
                >
                  {item.label}
                  {item.availability !== 'verified' ? ' — planned / unavailable' : ''}
                </option>
              ))}
            </select>
          ) : (
            <span className="lg-field__static">
              {info?.label ?? backend}{' '}
              <StatusBadge kind={executable ? 'success' : 'warning'}>
                {executable ? 'verified' : 'planned / unavailable'}
              </StatusBadge>
            </span>
          )}
        </label>
        {info ? <p className="lg-field__hint">{info.note}</p> : null}

        {executable ? (
          <>
            <label className="lg-field">
              <span className="lg-field__label">Model</span>
              <input
                className="lg-field__input"
                value={model}
                onChange={(event) => setModel(event.target.value)}
                placeholder={PREFERRED_MODEL}
                autoComplete="off"
              />
            </label>
            <label className="lg-field">
              <span className="lg-field__label">Base URL</span>
              <input
                className="lg-field__input"
                value={baseUrl}
                onChange={(event) => setBaseUrl(event.target.value)}
                placeholder={DEFAULT_BASE_URL}
                autoComplete="off"
                spellCheck={false}
              />
            </label>
          </>
        ) : (
          <p className="lg-field__hint">
            This backend is shown for status only and cannot be saved as an
            executable connection.
          </p>
        )}

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
      </section>

      {!creating && connection ? (
        <section className="lg-section-card" aria-label="References">
          <h4 className="lg-section-card__title">References</h4>
          {connection.references.default_roles.length > 0 ||
          connection.references.agent_refs.length > 0 ? (
            <p className="lg-field__static">
              Used by defaults:{' '}
              {connection.references.default_roles.join(', ') || 'none'}; agents:{' '}
              {connection.references.agent_refs.join(', ') || 'none'}.
            </p>
          ) : (
            <p className="lg-field__hint">
              Not referenced by a default or agent.
            </p>
          )}
        </section>
      ) : null}

      <section className="lg-section-card" aria-label="Credential">
        <h4 className="lg-section-card__title">Credential</h4>
        <label className="lg-field">
          <span className="lg-field__label">Credential reference</span>
          <input
            className="lg-field__input"
            value={credentialRef}
            onChange={(event) => setCredentialRef(event.target.value)}
            placeholder="deepseek-primary"
            autoComplete="off"
          />
          <span className="lg-field__hint">
            Only the reference is saved on the connection; the value lives in the
            local secret store.
          </span>
        </label>
        <p className="lg-field__static" role="status">
          Status:{' '}
          {configured ? (
            <StatusBadge kind="success">Configured</StatusBadge>
          ) : credentialRef.trim() ? (
            <StatusBadge kind="warning">Not configured</StatusBadge>
          ) : (
            <StatusBadge kind="neutral">No credential</StatusBadge>
          )}{' '}
          {configured ? (
            <span className="lg-field__hint">
              source: {credentialSourceLabel(configuredSource)}
              {credentialStatus?.version ? ` · version ${credentialStatus.version}` : ''}
            </span>
          ) : null}
        </p>
        <label className="lg-field">
          <span className="lg-field__label">New API key (write-only)</span>
          <input
            className="lg-field__input"
            type="password"
            value={secret}
            onChange={(event) => setSecret(event.target.value)}
            placeholder={configured ? 'Leave empty to keep the existing key' : 'Paste key'}
            autoComplete="new-password"
            spellCheck={false}
          />
          <span className="lg-field__hint">
            Sent once and cleared on save. It is never returned, shown again, or
            stored in the browser.
          </span>
        </label>
        <div className="lg-connection-form__actions">
          <button
            type="submit"
            className="lg-button lg-button--primary"
            disabled={busy || !executable}
          >
            {pending === 'save' ? 'Saving…' : creating ? 'Create connection' : 'Save changes'}
          </button>
          {!creating ? (
            <button
              type="button"
              className="lg-button"
              onClick={handleRemoveCredential}
              disabled={busy || (!connection?.credential_ref && !configured)}
            >
              {pending === 'credential' ? 'Removing…' : 'Remove credential'}
            </button>
          ) : null}
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
        {creating ? (
          <p className="lg-field__hint">
            Save the connection to enable the layered test.
          </p>
        ) : null}
        <ConnectionTestPanel
          result={testResult}
          stale={stale}
          running={pending === 'test'}
          onRun={handleTest}
          disabledReason={testDisabledReason}
        />
      </section>
    </form>
  )
}
