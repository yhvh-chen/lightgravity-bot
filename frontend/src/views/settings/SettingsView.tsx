import { useCallback, useEffect, useMemo, useState } from 'react'

import { getRuntimeToken } from '../../api/auth'
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
import { backendLabel, isExecutableBackend } from './backends'
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
  const { token, api: injectedApi, connectionId, taskRef } = props
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
  const [creating, setCreating] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)

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
        setSelectedId((previous) => {
          if (connectionId && list.some((connection) => connection.id === connectionId)) {
            return connectionId
          }
          return previous && list.some((connection) => connection.id === previous)
            ? previous
            : (list[0]?.id ?? null)
        })
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
  }, [api, refreshKey, connectionId])

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
      setCreating(false)
      setSelectedId(updated.id)
      setConnections((previous) =>
        previous
          ? previous.map((connection) =>
              connection.id === updated.id ? updated : connection,
            )
          : [updated],
      )
      reload()
    },
    [reload],
  )

  const selected =
    connections?.find((connection) => connection.id === selectedId) ?? null
  const tokenMissing =
    injectedApi === undefined &&
    (token === undefined ? getRuntimeToken() === null : !token)

  return (
    <div className="lg-settings-view">
      <DetailHeader
        title="Settings"
        badges={<StatusBadge kind="accent">Models &amp; Providers</StatusBadge>}
        meta={[
          { label: 'section', value: 'Models & Providers' },
          { label: 'task', value: taskRef ?? 'global' },
          { label: 'source', value: 'GET /api/v1/settings' },
        ]}
      />

      {tokenMissing ? (
        <p className="lg-notice" role="note">
          Local writes are protected. The first-startup token handshake (LG-020)
          is not implemented yet, so saving, testing or removing may return
          <span className="lg-card__path"> unauthorized</span> until a runtime
          token is injected. Reading the connection list still works.
        </p>
      ) : null}

      <section className="lg-settings-view__intro" aria-label="Connections overview">
        <h3 className="lg-section-card__title">Connections</h3>
        <p className="lg-field__hint">
          The same Connection entity as Resources → Connections. Only the verified
          OpenAI-compatible (DeepSeek) backend can be saved as executable; other
          backends are status-only.
        </p>
      </section>

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
            execute tasks. Resources → Connections reads the same record.
          </p>
          <button
            type="button"
            className="lg-button lg-button--primary"
            onClick={() => {
              setCreating(true)
              setSelectedId(null)
            }}
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
                onClick={() => {
                  setCreating(true)
                  setSelectedId(null)
                }}
              >
                New connection
              </button>
            </div>
            <ul className="lg-settings__items">
              {(connections ?? []).map((connection) => {
                const isSelected = !creating && connection.id === selectedId
                return (
                  <li key={connection.id}>
                    <button
                      type="button"
                      className={`lg-settings__item${isSelected ? ' is-selected' : ''}`}
                      aria-pressed={isSelected}
                      onClick={() => {
                        setCreating(false)
                        setSelectedId(connection.id)
                      }}
                    >
                      <span className="lg-settings__item-title">
                        {connection.title}
                      </span>
                      <span className="lg-settings__item-badges">
                        <StatusBadge
                          kind={
                            isExecutableBackend(connection.backend)
                              ? 'success'
                              : 'warning'
                          }
                        >
                          {isExecutableBackend(connection.backend)
                            ? backendLabel(connection.backend)
                            : `${connection.backend} · planned`}
                        </StatusBadge>
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
                        ) : (
                          <StatusBadge kind="warning">no credential</StatusBadge>
                        )}
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
                onCancel={
                  creating
                    ? () => {
                        setCreating(false)
                        setSelectedId(connections?.[0]?.id ?? null)
                      }
                    : undefined
                }
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
        <DefaultsEditor
          api={api}
          settings={settings}
          connections={connections ?? []}
          onSaved={(updated) => setSettings(updated)}
          onReload={reloadSettings}
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

  const [section, setSection] = useState<SettingsSectionId | null>(() =>
    sections.includes('models') && props.connectionId ? 'models' : (sections[0] ?? null),
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
