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
import { isDefaultEligible } from './backends'

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
 * Global default coordinator/worker/reviewer connection refs (docs/07 §3; docs/08 §6.5).
 *
 * Coordinator/reviewer defaults are wired at server startup; new Runs freeze
 * the worker default. Active members retain their pinned revisions, so
 * a default change is never presented as a live hot-swap. The reviewer default
 * (LG-017) is a separate role so independent review does not reuse the
 * implementer's connection; leaving it None is an honest "no reviewer" state.
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
  const [reviewer, setReviewer] = useState(
    settings.default_reviewer_connection_ref ?? '',
  )
  const [revision, setRevision] = useState(settings.revision)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<ReturnType<typeof toApiError> | null>(null)
  const [conflict, setConflict] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)

  const options = connections.filter(isDefaultEligible)
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
        default_reviewer_connection_ref: reviewer || null,
      })
      setRevision(updated.revision)
      onSaved(updated)
      setNotice(updated.runtime_applied === true
        ? `Defaults saved at revision ${updated.revision}. Applied to new conversations and Runs.`
        : updated.runtime_message ?? `Defaults saved at revision ${updated.revision}. Restart the server to apply coordinator or reviewer changes.`)
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
        Coordinator and reviewer defaults apply to new conversations and Runs after saving.
        Worker
        defaults apply when a new Run freezes its connection. Existing Runs and
        recruited members keep their pinned connection revisions.
      </p>
      <p className="lg-field__static">
        <StatusBadge kind="accent">resolution</StatusBadge>{' '}
        {describeDefault('coordinator', settings.defaults.coordinator)}
      </p>
      <p className="lg-field__static">
        {describeDefault('worker', settings.defaults.worker)}
      </p>
      <p className="lg-field__static">
        <StatusBadge kind="accent">independent review</StatusBadge>{' '}
        {describeDefault('reviewer', settings.defaults.reviewer)}
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
        <label className="lg-field">
          <span className="lg-field__label">Default reviewer connection</span>
          <select
            className="lg-field__input"
            value={reviewer}
            onChange={(event) => setReviewer(event.target.value)}
          >
            <option value="">None</option>
            {reviewer && !knownRef(reviewer) ? (
              <option value={reviewer}>Unresolved: {reviewer}</option>
            ) : null}
            {options.map((connection) => (
              <option key={connection.id} value={connection.id}>
                {connection.title} ({connection.id})
              </option>
            ))}
          </select>
        </label>
        <p className="lg-field__hint">
          The independent reviewer runs on its own connection so its context is
          separate from the implementer. When left None there is no real
          reviewer, so a candidate reports an honest unavailable review and
          acceptance stays blocked; the worker connection is never silently
          reused for review.
        </p>
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
