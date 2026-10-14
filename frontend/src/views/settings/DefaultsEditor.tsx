import { useState, type FormEvent } from 'react'

import type {
  ConnectionView,
  DefaultDescription,
  GlobalSettingsView,
  SettingsApi,
} from '../../api/settings'
import { ErrorState } from '../../components/ErrorState'
import { StatusBadge } from '../../components/StatusBadge'
import { toApiError } from './apiError'
import { isExecutableBackend } from './backends'

export interface DefaultsEditorProps {
  api: SettingsApi
  settings: GlobalSettingsView
  connections: ConnectionView[]
  onSaved: (settings: GlobalSettingsView) => void
  onReload: () => Promise<GlobalSettingsView | null>
}

function describeDefault(
  role: string,
  description: DefaultDescription | null,
): string {
  if (!description) return `No ${role} default configured.`
  if (!description.resolved) {
    return `${role} default points at "${description.ref ?? 'unknown'}", which does not resolve.`
  }
  const model = description.model ? ` · ${description.model}` : ''
  return `${role} default: ${description.id ?? description.ref ?? '?'} @ revision ${
    description.revision ?? '?'
  }${model}`
}

/**
 * Global default coordinator/worker connection refs (docs/07 §3; docs/08 §6.5).
 *
 * Defaults only affect new sessions/recruitment; active members keep the
 * connection revision pinned when they were recruited. The page states this so
 * a default change is never presented as a live hot-swap.
 */
export function DefaultsEditor({
  api,
  settings,
  connections,
  onSaved,
  onReload,
}: DefaultsEditorProps) {
  const [coordinator, setCoordinator] = useState(
    settings.default_coordinator_connection_ref ?? '',
  )
  const [worker, setWorker] = useState(
    settings.default_worker_connection_ref ?? '',
  )
  const [revision, setRevision] = useState(settings.revision)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<ReturnType<typeof toApiError> | null>(null)
  const [conflict, setConflict] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)

  const options = connections.filter(
    (connection) => connection.enabled && isExecutableBackend(connection.backend),
  )
  const knownRef = (ref: string) => options.some((option) => option.id === ref)

  async function handleSubmit(event: FormEvent): Promise<void> {
    event.preventDefault()
    setError(null)
    setConflict(false)
    setNotice(null)
    setPending(true)
    try {
      const updated = await api.updateSettings({
        expected_revision: revision,
        default_coordinator_connection_ref: coordinator || null,
        default_worker_connection_ref: worker || null,
      })
      setRevision(updated.revision)
      onSaved(updated)
      setNotice(`Defaults saved at revision ${updated.revision}.`)
    } catch (cause) {
      const err = toApiError(cause)
      if (err.code === 'revision_conflict') {
        try {
          const latest = await onReload()
          if (latest) setRevision(latest.revision)
        } catch {
          /* keep the conflict visible */
        }
        setConflict(true)
      } else {
        setError(err)
      }
    } finally {
      setPending(false)
    }
  }

  return (
    <section className="lg-section-card" aria-label="Default models">
      <h3 className="lg-section-card__title">Default models</h3>
      <p className="lg-field__hint">
        Defaults apply to new sessions and recruitment only. Members already
        recruited keep the connection revision they were pinned to; changing a
        default does not hot-swap them.
      </p>
      <p className="lg-field__static">
        <StatusBadge kind="accent">resolution</StatusBadge>{' '}
        {describeDefault('coordinator', settings.defaults.coordinator)}
      </p>
      <p className="lg-field__static">
        {describeDefault('worker', settings.defaults.worker)}
      </p>

      {error ? (
        <ErrorState
          title="Could not save defaults"
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
            Settings changed elsewhere. The latest revision ({revision}) is
            loaded; review and save again.
          </p>
        </div>
      ) : null}
      {notice ? (
        <p className="lg-notice" role="status">
          {notice}
        </p>
      ) : null}

      <form className="lg-defaults-form" onSubmit={handleSubmit}>
        <label className="lg-field">
          <span className="lg-field__label">Default coordinator connection</span>
          <select
            className="lg-field__input"
            value={coordinator}
            onChange={(event) => setCoordinator(event.target.value)}
          >
            <option value="">None</option>
            {coordinator && !knownRef(coordinator) ? (
              <option value={coordinator}>Unresolved: {coordinator}</option>
            ) : null}
            {options.map((connection) => (
              <option key={connection.id} value={connection.id}>
                {connection.title} ({connection.id})
              </option>
            ))}
          </select>
        </label>
        <label className="lg-field">
          <span className="lg-field__label">Default worker connection</span>
          <select
            className="lg-field__input"
            value={worker}
            onChange={(event) => setWorker(event.target.value)}
          >
            <option value="">None</option>
            {worker && !knownRef(worker) ? (
              <option value={worker}>Unresolved: {worker}</option>
            ) : null}
            {options.map((connection) => (
              <option key={connection.id} value={connection.id}>
                {connection.title} ({connection.id})
              </option>
            ))}
          </select>
        </label>
        <div className="lg-connection-form__actions">
          <button
            type="submit"
            className="lg-button lg-button--primary"
            disabled={pending}
          >
            {pending ? 'Saving…' : 'Save defaults'}
          </button>
        </div>
      </form>
    </section>
  )
}
