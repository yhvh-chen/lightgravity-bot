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
   * Connection record to select on load (e.g. from Resources → Connections
   * "Edit in Settings").  Purely a UI locator; it does not change the entity.
   */
  connectionId?: string | null
  /** Current Task scope, kept only for display while Settings is open. */
  taskRef?: string | null
}

/**
 * Models & Providers (owner LG-026; docs/07, design.md §5 Settings).
 *
 * It reads and writes the same Connection entity that Resources → Connections
 * uses — there is no second provider/model list. Typed forms cover connection
 * fields, write-only credentials, layered tests and the global
 * coordinator/worker defaults.
 *
 * Mounted only for an administrator (or single-user mode).  A member never
 * reaches this panel, so the Connections/settings requests are never issued.
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
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [missingTarget, setMissingTarget] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)

  // LG-103 selection guards.  `selectedIdRef` lets a late save/reload observe
  // the *current* selection instead of the one captured when the request
  // started; `targetRef` is the external navigation target (Connection id from
  // a Team/Resources reference) and is cleared once the user picks manually.
  const selectedIdRef = useRef<string | null>(null)
  const targetRef = useRef<string | null>(connectionId ?? null)
  const lastConnectionIdRef = useRef<string | null>(connectionId ?? null)
  const creatingRef = useRef(false)

  const selectConnection = useCallback((id: string | null) => {
    selectedIdRef.current = id
    setSelectedId(id)
  }, [])

  const selectExisting = useCallback(
    (id: string) => {
      targetRef.current = null
      setMissingTarget(null)
      setCreating(false)
      creatingRef.current = false
      selectConnection(id)
    },
    [selectConnection],
  )

  const startCreating = useCallback(() => {
    targetRef.current = null
    setMissingTarget(null)
    setCreating(true)
    creatingRef.current = true
    selectConnection(null)
  }, [selectConnection])

  const cancelCreating = useCallback(() => {
    setCreating(false)
    creatingRef.current = false
    targetRef.current = null
    setMissingTarget(null)
    selectConnection(connections?.[0]?.id ?? null)
  }, [connections, selectConnection])

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
            selectConnection(target)
            setMissingTarget(null)
          } else {
            // Never silently select a different Connection when the requested
            // stable id is absent. Keep the explicit miss visible instead.
            selectConnection(null)
            setMissingTarget(target)
          }
          return
        }
        const previous = selectedIdRef.current
        selectConnection(
          previous && list.some((connection) => connection.id === previous)
            ? previous
            : (list[0]?.id ?? null),
        )
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
  }, [api, refreshKey, selectConnection])

  // A new external Connection target (e.g. navigating from Team while Settings
  // is already mounted) applies immediately, or waits for the first list load.
  useEffect(() => {
    const next = connectionId ?? null
    if (next === lastConnectionIdRef.current) return
    lastConnectionIdRef.current = next
    targetRef.current = next
    setMissingTarget(null)
    if (next === null || connections === null) return
    if (connections.some((connection) => connection.id === next)) {
      selectConnection(next)
    } else {
      selectConnection(null)
      setMissingTarget(next)
    }
  }, [connectionId, connections, selectConnection])

  const reload = useCallback(() => setRefreshKey((key) => key + 1), [])

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

  const handleSaved = useCallback(
    (updated: ConnectionView) => {
      const wasCreating = creatingRef.current
      creatingRef.current = false
      setCreating(false)
      setConnections((previous) =>
        previous
          ? previous.map((connection) =>
              connection.id === updated.id ? updated : connection,
            )
          : [updated],
      )
      // A response for an older Connection must not pull the editor back after
      // the user selected another id (cross-ID late-response guard).
      if (selectedIdRef.current === updated.id || (wasCreating && creatingRef.current === false && selectedIdRef.current === null)) {
        targetRef.current = null
        setMissingTarget(null)
        selectConnection(updated.id)
      }
      reload()
    },
    [reload, selectConnection],
  )

  const selected =
    connections?.find((connection) => connection.id === selectedId) ?? null

  return (
    <div className="lg-settings-view">
      <DetailHeader
        title="Settings"
        badges={<StatusBadge kind="accent">Models &amp; Providers</StatusBadge>}
      />

      <section className="lg-settings-view__intro" aria-label="Connections overview">
        <h3 className="lg-section-card__title">Connections</h3>
        <p className="lg-field__hint">
          Choose a provider, enter the authentication that provider actually
          needs, save, then test. A saved or tested connection is not the same as
          Task execution or vendor verification; those capabilities are shown
          only when the backend declares them.
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
          onRetry={reload}
        />
      ) : initialising && connections === null ? (
        <p className="lg-field__hint" role="status">
          Loading connections…
        </p>
      ) : connections && connections.length === 0 && !creating ? (
        <EmptyState title="No connections yet">
          <p>
            Create a DeepSeek (OpenAI-compatible) connection to let the bot
            execute tasks. Team and resource references open this same record.
          </p>
          <button
            type="button"
            className="lg-button lg-button--primary"
            onClick={startCreating}
          >
            New connection
          </button>
        </EmptyState>
      ) : (
        <div className="lg-settings">
          <section className="lg-settings__list" aria-label="Connection list">
            <div className="lg-settings__list-head">
              <span className="lg-field__label">
                {connections?.length ?? 0} connection
                {(connections?.length ?? 0) === 1 ? '' : 's'}
              </span>
              <button
                type="button"
                className="lg-button"
                onClick={startCreating}
              >
                New connection
              </button>
            </div>
            <ul className="lg-settings__items">
              {(connections ?? []).map((connection) => {
                const isSelected = !creating && connection.id === selectedId
                const preset = presetForConnection(connection)
                return (
                  <li key={connection.id}>
                    <button
                      type="button"
                      className={`lg-settings__item${isSelected ? ' is-selected' : ''}`}
                      aria-pressed={isSelected}
                      onClick={() => selectExisting(connection.id)}
                    >
                      <span className="lg-settings__item-title">
                        {connection.title}
                      </span>
                      <span className="lg-settings__item-badges">
                        <StatusBadge kind="neutral">{preset.label}</StatusBadge>
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
                      </span>
                      <span className="lg-card__path">{connection.id}</span>
                    </button>
                  </li>
                )
              })}
            </ul>
          </section>

          <section className="lg-settings__editor" aria-label="Connection details">
            {creating || selected ? (
              <ConnectionEditor
                key={creating ? 'create' : (selected?.id ?? 'create')}
                api={api}
                mode={creating ? 'create' : 'edit'}
                connection={creating ? null : selected}
                onSaved={handleSaved}
                onReload={reloadConnection}
                onCancel={creating ? cancelCreating : undefined}
              />
            ) : (
              <EmptyState title="No connection selected">
                <p>Select a connection on the left, or create a new one.</p>
              </EmptyState>
            )}
          </section>
        </div>
      )}

      {settings ? (
        <details className="lg-disclosure" aria-label="Advanced defaults">
          <summary className="lg-disclosure__summary">
            Advanced / Defaults
          </summary>
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
 *   the admin account list.  Admin areas stay hidden here *and* authorized on
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
