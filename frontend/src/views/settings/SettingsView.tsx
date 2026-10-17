import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { useAuth } from '../../app/AuthProvider'
import {
  createSettingsApi,
  type ConnectionView,
  type GlobalSettingsView,
  type SettingsApi,
} from '../../api/settings'
import { DetailHeader } from '../../components/DetailHeader'
import { EmptyState } from '../../components/EmptyState'
import { ErrorState } from '../../components/ErrorState'
import { StatusBadge } from '../../components/StatusBadge'
import './settings.css'
import { toApiError } from './apiError'
import { presetForConnection } from './backends'
import { AccountsPanel } from './AccountsPanel'
import { ConnectionEditor } from './ConnectionEditor'
import { DefaultsEditor } from './DefaultsEditor'
import { MyAccountPanel } from './MyAccountPanel'

export interface SettingsViewProps {
  /** Optional runtime access token injected by the App/startup bootstrap. */
  token?: string | null
  /** Full API override for embedding/tests; defaults to the real endpoints. */
  api?: SettingsApi
  /**
   * Connection record to open for editing on load (e.g. from Resources/Team
   * "Edit in Settings"). Purely a UI locator; it does not change the entity.
   */
  connectionId?: string | null
  /** Current Task scope, kept only for display while Settings is open. */
  taskRef?: string | null
}

interface ModalState {
  key: number
  mode: 'create' | 'edit'
  connectionId: string | null
}

interface RowError {
  message: string
  code?: string
}

interface DeleteState {
  id: string
  busy: boolean
  error: RowError | null
}

function persistedTestStatus(connection: ConnectionView): {
  kind: 'neutral' | 'accent' | 'success' | 'warning' | 'error'
  label: string
} {
  const latest = connection.last_test
  if (!latest) return { kind: 'neutral', label: 'Not tested' }
  const revisionStale =
    latest.connection_revision !== null &&
    latest.connection_revision !== undefined &&
    latest.connection_revision !== connection.revision
  const credentialStale =
    Boolean(latest.credential_version) &&
    Boolean(connection.credential.version) &&
    latest.credential_version !== connection.credential.version
  const stale = revisionStale || credentialStale
  const kind =
    latest.overall === 'verified'
      ? 'success'
      : latest.overall === 'partial'
        ? 'warning'
        : latest.overall === 'failed'
          ? 'error'
          : 'neutral'
  return {
    kind: stale ? 'warning' : kind,
    label: `${latest.overall}${stale ? ' · stale' : ''} · ${latest.finished_at}`,
  }
}

/**
 * Models & Providers (LG-026 → LG-104/LG-110; docs/07, design.md §5).
 *
 * The landing page is the saved Connection list only. New/Edit open one
 * accessible modal; Test tests that unsaved draft and Save is a separate
 * create/update. The list's test status comes only from the backend's persisted
 * `last_test` summary — a draft result is never promoted to saved verification.
 */
function ModelsPanel(props: SettingsViewProps = {}) {
  const { token, api: injectedApi, connectionId } = props
  const defaultApi = useMemo(() => {
    if (token === undefined) return createSettingsApi()
    const fixed = token
    return createSettingsApi(() => fixed ?? null)
  }, [token])
  const api = injectedApi ?? defaultApi

  const [connections, setConnections] = useState<ConnectionView[] | null>(null)
  const [settings, setSettings] = useState<GlobalSettingsView | null>(null)
  const [initialising, setInitialising] = useState(true)
  const [loadError, setLoadError] = useState<ReturnType<typeof toApiError> | null>(
    null,
  )
  const [missingTarget, setMissingTarget] = useState<string | null>(null)
  const [modal, setModal] = useState<ModalState | null>(null)
  const [deleteState, setDeleteState] = useState<DeleteState | null>(null)
  const [listNotice, setListNotice] = useState<string | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)

  // LG-103/LG-110 target + late-response guards. A deeplink target opens Edit
  // exactly once; closing the modal never changes the target and reopens it.
  const targetRef = useRef<string | null>(connectionId ?? null)
  const lastConnectionIdRef = useRef<string | null>(connectionId ?? null)
  const modalCounterRef = useRef(0)
  const modalTriggerRef = useRef<HTMLElement | null>(null)
  const focusAfterCloseRef = useRef<{
    element?: HTMLElement | null
    connectionId?: string | null
  } | null>(null)
  const rowRefs = useRef(new Map<string, HTMLLIElement>())
  const newButtonRef = useRef<HTMLButtonElement>(null)

  const openModal = useCallback(
    (
      mode: 'create' | 'edit',
      id: string | null,
      trigger?: HTMLElement | null,
      fromTarget = false,
    ) => {
      if (!fromTarget) {
        targetRef.current = null
        setMissingTarget(null)
      }
      modalTriggerRef.current = trigger ?? null
      setDeleteState(null)
      setListNotice(null)
      modalCounterRef.current += 1
      setModal({
        key: modalCounterRef.current,
        mode,
        connectionId: id,
      })
    },
    [],
  )

  useEffect(() => {
    let cancelled = false
    const controller = new AbortController()
    setLoadError(null)
    Promise.all([
      api.listConnections(controller.signal),
      api.getSettings(controller.signal),
    ])
      .then(([list, loadedSettings]) => {
        if (cancelled) return
        setConnections(list)
        setSettings(loadedSettings)
        const target = targetRef.current
        if (target) {
          if (list.some((connection) => connection.id === target)) {
            setMissingTarget(null)
            targetRef.current = null
            openModal('edit', target, null, true)
          } else {
            // Never silently select another Connection for an unknown stable id.
            setMissingTarget(target)
          }
          return
        }
        setMissingTarget(null)
      })
      .catch((cause: unknown) => {
        if (cancelled || controller.signal.aborted) return
        setLoadError(toApiError(cause))
      })
      .finally(() => {
        if (!cancelled) setInitialising(false)
      })
    return () => {
      cancelled = true
      controller.abort()
    }
  }, [api, refreshKey, openModal])

  // A new external target while Settings is already mounted opens the correct
  // Edit modal once. A missing target stays visible and selects nothing.
  useEffect(() => {
    const next = connectionId ?? null
    if (next === lastConnectionIdRef.current) return
    lastConnectionIdRef.current = next
    targetRef.current = next
    setListNotice(null)
    if (next === null) {
      setMissingTarget(null)
      return
    }
    if (connections === null) return
    if (connections.some((connection) => connection.id === next)) {
      setMissingTarget(null)
      targetRef.current = null
      openModal('edit', next, null, true)
    } else {
      setMissingTarget(next)
      setModal(null)
    }
  }, [connectionId, connections, openModal])

  // Focus the new/edited row after save, or return focus to the trigger after
  // Cancel/Escape. Runs after the modal is unmounted and the list is current.
  useEffect(() => {
    if (modal !== null) return
    const pending = focusAfterCloseRef.current
    if (!pending) return
    focusAfterCloseRef.current = null
    const timer = window.setTimeout(() => {
      const target = pending.connectionId
        ? rowRefs.current.get(pending.connectionId)
        : pending.element
      target?.focus()
    }, 0)
    return () => window.clearTimeout(timer)
  }, [modal])

  const reloadConnection = useCallback(
    async (id: string): Promise<ConnectionView | null> => {
      try {
        const [list, loadedSettings] = await Promise.all([
          api.listConnections(),
          api.getSettings(),
        ])
        setConnections(list)
        setSettings(loadedSettings)
        return list.find((connection) => connection.id === id) ?? null
      } catch {
        return null
      }
    },
    [api],
  )

  const reloadSettings = useCallback(async (): Promise<GlobalSettingsView | null> => {
    try {
      const loadedSettings = await api.getSettings()
      setSettings(loadedSettings)
      return loadedSettings
    } catch {
      return null
    }
  }, [api])

  const handleSaved = useCallback((saved: ConnectionView) => {
    setConnections((previous) => {
      if (!previous) return [saved]
      const exists = previous.some((connection) => connection.id === saved.id)
      return exists
        ? previous.map((connection) =>
            connection.id === saved.id ? saved : connection,
          )
        : [...previous, saved]
    })
    setMissingTarget(null)
    targetRef.current = null
    modalTriggerRef.current = null
    focusAfterCloseRef.current = { connectionId: saved.id }
    setModal(null)
    setDeleteState(null)
    setListNotice(`Saved "${saved.title}" at revision ${saved.revision}.`)
    // Refresh list-level persisted test status/references from the real backend.
    setRefreshKey((key) => key + 1)
  }, [])

  const handleConnectionUpdated = useCallback((updated: ConnectionView) => {
    setConnections((previous) =>
      previous
        ? previous.map((connection) =>
            connection.id === updated.id ? updated : connection,
          )
        : [updated],
    )
  }, [])

  const closeModal = useCallback(() => {
    const trigger = modalTriggerRef.current
    const editedId = modal?.connectionId ?? null
    modalTriggerRef.current = null
    focusAfterCloseRef.current = trigger
      ? { element: trigger }
      : editedId
        ? { connectionId: editedId }
        : { element: newButtonRef.current }
    setModal(null)
    setListNotice(null)
  }, [modal])

  const askDelete = useCallback((connection: ConnectionView) => {
    setListNotice(null)
    setDeleteState({ id: connection.id, busy: false, error: null })
  }, [])

  async function confirmDelete(connection: ConnectionView): Promise<void> {
    const references = [
      ...connection.references.default_roles.map((role) => `default ${role}`),
      ...connection.references.agent_refs.map((agent) => `agent ${agent}`),
    ]
    if (references.length > 0) {
      setDeleteState({
        id: connection.id,
        busy: false,
        error: {
          message: `This connection is still referenced by ${references.join(
            ', ',
          )}. Remove those references before deleting it; deletion was not attempted.`,
          code: 'referenced',
        },
      })
      return
    }
    setDeleteState({ id: connection.id, busy: true, error: null })
    try {
      await api.deleteConnection(connection.id, connection.revision)
      setConnections((previous) =>
        previous
          ? previous.filter((item) => item.id !== connection.id)
          : previous,
      )
      setDeleteState(null)
      setListNotice(`Deleted "${connection.title}".`)
      window.setTimeout(() => newButtonRef.current?.focus(), 0)
    } catch (cause) {
      const error = toApiError(cause)
      setDeleteState({
        id: connection.id,
        busy: false,
        error: { message: error.message, code: error.code },
      })
    }
  }

  const selected =
    connections?.find((connection) => connection.id === modal?.connectionId) ??
    null

  return (
    <div className="lg-settings-view">
      <DetailHeader
        title="Settings"
        badges={<StatusBadge kind="accent">Models &amp; Providers</StatusBadge>}
      />

      <section className="lg-settings-view__intro" aria-label="Connections overview">
        <h3 className="lg-section-card__title">Connections</h3>
        <p className="lg-field__hint">
          Manage saved connections here. New/Edit opens a compact dialog; Test
          sends the unsaved draft only when you click it, and Save is a separate
          backend write. Saving or testing never claims Task execution or vendor
          verification.
        </p>
      </section>

      {missingTarget ? (
        <ErrorState
          title="Connection not found"
          message={`Connection "${missingTarget}" does not exist in this workspace. No other connection was selected. Choose a connection from the list or create a new one.`}
          code="not_found"
        />
      ) : null}

      {loadError ? (
        <ErrorState
          title="Could not load Models & Providers"
          message={loadError.message}
          code={loadError.code}
          retryable={loadError.retryable}
          requestId={loadError.requestId}
          onRetry={() => setRefreshKey((key) => key + 1)}
        />
      ) : null}

      {listNotice ? (
        <p className="lg-notice" role="status">
          {listNotice}
        </p>
      ) : null}

      {initialising && connections === null ? (
        <p className="lg-field__hint" role="status">
          Loading connections…
        </p>
      ) : connections && connections.length === 0 ? (
        <EmptyState title="No connections yet">
          <p>
            Create a DeepSeek (OpenAI-compatible) connection to let the bot
            execute tasks, or configure another SDK provider for later testing.
            Team and resource references open this same record.
          </p>
          <button
            ref={newButtonRef}
            type="button"
            className="lg-button lg-button--primary"
            onClick={() => openModal('create', null)}
          >
            New connection
          </button>
        </EmptyState>
      ) : connections ? (
        <section className="lg-connection-list" aria-label="Connection list">
          <div className="lg-connection-list__head">
            <span className="lg-field__label">
              {connections.length} connection
              {connections.length === 1 ? '' : 's'}
            </span>
            <button
              ref={newButtonRef}
              type="button"
              className="lg-button lg-button--primary"
              onClick={() => openModal('create', null)}
            >
              New connection
            </button>
          </div>
          <ul className="lg-connection-list__items">
            {connections.map((connection) => {
              const preset = presetForConnection(connection)
              const status = persistedTestStatus(connection)
              const deleting = deleteState?.id === connection.id
              return (
                <li
                  key={connection.id}
                  ref={(element) => {
                    if (element) rowRefs.current.set(connection.id, element)
                    else rowRefs.current.delete(connection.id)
                  }}
                  className="lg-connection-row"
                  tabIndex={-1}
                  aria-labelledby={`connection-name-${connection.id}`}
                >
                  <div className="lg-connection-row__main">
                    <h4
                      id={`connection-name-${connection.id}`}
                      className="lg-connection-row__name"
                    >
                      {connection.title}
                    </h4>
                    <dl className="lg-connection-row__facts">
                      <div>
                        <dt>Provider</dt>
                        <dd>{preset.label}</dd>
                      </div>
                      <div>
                        <dt>Model</dt>
                        <dd>{connection.model ?? '—'}</dd>
                      </div>
                      <div>
                        <dt>Test</dt>
                        <dd>
                          <StatusBadge kind={status.kind}>{status.label}</StatusBadge>
                        </dd>
                      </div>
                    </dl>
                    <div className="lg-connection-row__badges">
                      {!connection.enabled ? (
                        <StatusBadge kind="neutral">disabled</StatusBadge>
                      ) : null}
                      {connection.references.default_roles.length > 0 ? (
                        <StatusBadge kind="accent">
                          default: {connection.references.default_roles.join(', ')}
                        </StatusBadge>
                      ) : null}
                      {connection.credential.configured ? (
                        <StatusBadge kind="success">credential configured</StatusBadge>
                      ) : preset.requiresApiKey ? (
                        <StatusBadge kind="warning">no credential</StatusBadge>
                      ) : null}
                    </div>
                  </div>
                  <div className="lg-connection-row__actions">
                    <button
                      type="button"
                      className="lg-button"
                      aria-label={`Edit ${connection.title}`}
                      onClick={(event) =>
                        openModal('edit', connection.id, event.currentTarget)
                      }
                    >
                      Edit
                    </button>
                    <button
                      type="button"
                      className="lg-button lg-button--danger"
                      aria-label={`Delete ${connection.title}`}
                      onClick={() => askDelete(connection)}
                      disabled={deleting && deleteState.busy}
                    >
                      Delete
                    </button>
                  </div>
                  {deleting ? (
                    <div className="lg-inline-confirm" role="alert">
                      {deleteState.error ? (
                        <p>
                          Could not delete: {deleteState.error.message}
                          {deleteState.error.code ? (
                            <>
                              {' '}
                              <span className="lg-card__path">
                                ({deleteState.error.code})
                              </span>
                            </>
                          ) : null}
                        </p>
                      ) : (
                        <p>
                          Delete &quot;{connection.title}&quot;? This removes the
                          saved connection and cannot be undone.
                        </p>
                      )}
                      <div className="lg-modal__footer-right">
                        <button
                          type="button"
                          className="lg-button"
                          onClick={() => setDeleteState(null)}
                          disabled={deleteState.busy}
                        >
                          Cancel
                        </button>
                        {deleteState.error ? null : (
                          <button
                            type="button"
                            className="lg-button lg-button--danger"
                            onClick={() => confirmDelete(connection)}
                            disabled={deleteState.busy}
                          >
                            {deleteState.busy ? 'Deleting…' : 'Delete connection'}
                          </button>
                        )}
                      </div>
                    </div>
                  ) : null}
                </li>
              )
            })}
          </ul>
        </section>
      ) : null}

      {settings ? (
        <details className="lg-disclosure" aria-label="Default models">
          <summary className="lg-disclosure__summary">Default models</summary>
          <div className="lg-disclosure__body">
            <DefaultsEditor
              api={api}
              settings={settings}
              connections={connections ?? []}
              onSaved={(updated) => setSettings(updated)}
              onReload={reloadSettings}
            />
          </div>
        </details>
      ) : null}

      {modal ? (
        <ConnectionEditor
          key={modal.key}
          api={api}
          mode={modal.mode}
          connection={modal.mode === 'edit' ? selected : null}
          onSaved={handleSaved}
          onReload={reloadConnection}
          onClose={closeModal}
          onConnectionUpdated={handleConnectionUpdated}
        />
      ) : null}
    </div>
  )
}

/** Settings subareas (LG-062): admin config plus a personal account section. */
export type SettingsSectionId = 'models' | 'accounts' | 'account'

const SECTION_LABELS: Record<SettingsSectionId, string> = {
  models: 'Models & Providers',
  accounts: 'Accounts',
  account: 'My Account',
}

/**
 * Settings shell (LG-026 + LG-062 additive sections).
 *
 * * single-user mode: only Models & Providers (unchanged 1.14 behaviour);
 * * team admin: Models & Providers, Accounts and My Account;
 * * team member: My Account only, which never fetches Models/Connections or
 *   the admin account list. Admin areas stay hidden here *and* authorized on
 *   the server (403), never merely disabled in the UI.
 */
export function SettingsView(props: SettingsViewProps = {}) {
  const { isTeam, isAdmin, accountsAvailable } = useAuth()
  const sections = useMemo<SettingsSectionId[]>(() => {
    if (!isTeam) return ['models']
    const result: SettingsSectionId[] = []
    if (isAdmin) result.push('models')
    if (isAdmin && accountsAvailable) result.push('accounts')
    if (accountsAvailable) result.push('account')
    return result
  }, [isTeam, isAdmin, accountsAvailable])

  const requestedConnectionId = props.connectionId ?? null
  const [section, setSection] = useState<SettingsSectionId | null>(() =>
    sections.includes('models') && requestedConnectionId ? 'models' : (sections[0] ?? null),
  )
  const sectionKey = sections.join(',')
  const current = section && sections.includes(section) ? section : (sections[0] ?? null)

  useEffect(() => {
    if (section === null || !sections.includes(section)) {
      setSection(sections[0] ?? null)
    }
  }, [section, sectionKey, sections])

  if (current === null) {
    // Team member on a pre-1.15 backend: there is no account surface to call.
    // Explain honestly instead of showing the admin Models panel or an empty
    // page; the server would 404/403 anyway.
    return (
      <div className="lg-settings-view">
        <DetailHeader
          title="Settings"
          badges={<StatusBadge kind="warning">Unavailable</StatusBadge>}
        />
        <p className="lg-notice" role="note">
          Account management is not available on this backend version. Ask an
          administrator to update the backend to enable the My Account section.
        </p>
      </div>
    )
  }

  return (
    <div className="lg-settings-view">
      {requestedConnectionId && !sections.includes('models') ? (
        <p className="lg-notice" role="note">
          Connection &quot;{requestedConnectionId}&quot; configuration is managed by
          administrators. No model or credential configuration was loaded. You can
          manage your own account below.
        </p>
      ) : null}

      {sections.length > 1 ? (
        <div role="tablist" aria-label="Settings sections" className="lg-settings-tabs">
          {sections.map((id) => (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={current === id}
              className={`lg-settings-tabs__tab${current === id ? ' is-selected' : ''}`}
              onClick={() => setSection(id)}
            >
              {SECTION_LABELS[id]}
            </button>
          ))}
        </div>
      ) : null}

      {current === 'models' ? <ModelsPanel {...props} /> : null}
      {current === 'accounts' && isAdmin && accountsAvailable ? <AccountsPanel /> : null}
      {current === 'account' && accountsAvailable ? <MyAccountPanel /> : null}
    </div>
  )
}

export default SettingsView
