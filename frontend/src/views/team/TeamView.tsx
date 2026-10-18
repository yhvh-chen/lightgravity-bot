import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { ApiError } from '../../api/client'
import {
  createTeamApi,
  type AvailableAgent,
  type TeamApi,
} from '../../api/team'
import {
  createTeamGroupsApi,
  fetchTeamGroupsCapability,
  type TeamGroup,
  type TeamGroupsApi,
} from '../../api/teamGroups'
import type { ViewId } from '../../app/navigation'
import { useShell } from '../../app/ShellProvider'
import { useAuth } from '../../app/AuthProvider'
import { draftKey, settingsConnectionRef } from '../../app/uiState'
import { DetailHeader } from '../../components/DetailHeader'
import { EmptyState } from '../../components/EmptyState'
import { ErrorState } from '../../components/ErrorState'
import { MarkdownViewer } from '../../components/MarkdownViewer'
import { StatusBadge } from '../../components/StatusBadge'
import { Diagnostics } from '../resources/Diagnostics'
import { AvailablePanel, roleBadge } from './AvailablePanel'
import { groupBucket } from './grouphelpers'
import { RecruitedPanel } from './RecruitedPanel'
import { rememberTeamReturn } from './returnState'
import './team.css'

type TeamTab = 'available' | 'recruited'

export interface TeamViewProps {
  /** Injectable for tests; defaults to the real `/team/*` endpoints. */
  api?: TeamApi
  /** Injectable grouped-teams client; defaults to `GET /team/groups`. */
  groupsApi?: TeamGroupsApi
  /** Test/integration override for the additive `team_groups` capability. */
  teamGroupsCapability?: boolean
  /** Poll interval for the grouped read model; 0 disables polling. */
  pollIntervalMs?: number
  taskRef?: string | null
  runRef?: string | null
  selectedItemRef?: string | null
  navigate?: (view: ViewId) => void
  selectItem?: (ref: string | null) => void
  openChatDraft?: (message: string) => void
  /** Explicit grouped-team navigation hooks (tests/integration). */
  onOpenTaskChat?: (taskRef: string) => void
  onViewTask?: (taskRef: string) => void
}

interface Selection {
  tab: TeamTab
  id: string | null
  groupId: string | null
}

function parseSelection(ref: string | null | undefined): Selection {
  if (!ref) return { tab: 'recruited', id: null, groupId: null }
  if (ref === 'team-available' || ref === 'team:available') {
    return { tab: 'available', id: null, groupId: null }
  }
  if (ref === 'team-recruited' || ref === 'team:recruited') {
    return { tab: 'recruited', id: null, groupId: null }
  }
  if (ref.startsWith('team:group:')) {
    return { tab: 'recruited', id: null, groupId: ref.slice('team:group:'.length) }
  }
  if (ref.startsWith('team:member:')) {
    return { tab: 'recruited', id: ref.slice('team:member:'.length), groupId: null }
  }
  if (ref.startsWith('team:agent:')) {
    return { tab: 'available', id: ref.slice('team:agent:'.length), groupId: null }
  }
  return { tab: 'recruited', id: null, groupId: null }
}

function itemRef(selection: Selection): string | null {
  if (selection.groupId) return `team:group:${selection.groupId}`
  if (!selection.id) return null
  return selection.tab === 'available' ? `team:agent:${selection.id}` : `team:member:${selection.id}`
}

function mergeGroupPage(
  previous: TeamGroup[] | null,
  page: { items: TeamGroup[]; next_cursor: string | null },
): TeamGroup[] {
  if (page.next_cursor === null) return page.items
  const byId = new Map(page.items.map((group) => [group.task.id, group]))
  const merged = [...page.items]
  for (const group of previous ?? []) {
    if (!byId.has(group.task.id)) merged.push(group)
  }
  return merged
}

/**
 * Team (LG-015 Available + LG-125 grouped Recruited; docs/05 §5, docs/13 §2).
 *
 * Available keeps the complete role library browser. Recruited consumes the
 * additive read-only `GET /team/groups` projection, grouped by Task, with
 * Active/History derived from R2 stop/cleanup facts. Browsing/filtering never
 * changes the active Task chat; only explicit Open chat / View task do.
 */
export function TeamView(props: TeamViewProps = {}) {
  const shell = useShell()
  const { isTeam } = useAuth()
  const api = useMemo(() => props.api ?? createTeamApi(), [props.api])
  const groupsApi = useMemo(
    () => props.groupsApi ?? createTeamGroupsApi(),
    [props.groupsApi],
  )
  const taskRef = props.taskRef !== undefined ? props.taskRef : shell.state.taskRef
  const runRef = props.runRef !== undefined ? props.runRef : shell.state.runRef
  const selectedItemRef =
    props.selectedItemRef !== undefined ? props.selectedItemRef : shell.state.selectedItemRef
  const pollIntervalMs = props.pollIntervalMs ?? 10000

  const navigate =
    props.navigate ?? ((view: ViewId) => shell.dispatch({ type: 'setView', view }))
  const selectItem =
    props.selectItem ??
    ((ref: string | null) => shell.dispatch({ type: 'selectItem', itemRef: ref }))
  const openChatDraft =
    props.openChatDraft ??
    ((message: string) => {
      // LG-054: a Team-triggered intent belongs to the shared Team channel, so
      // switch there and write the draft under the matching channel key.
      if (isTeam) shell.dispatch({ type: 'setChatChannel', channel: 'team' })
      const key = draftKey(taskRef ?? null, isTeam ? 'team' : null)
      const existing = shell.state.drafts[key] ?? ''
      const value = existing ? `${existing}\n${message}` : message
      shell.dispatch({ type: 'setDraft', key, value })
    })

  const [selection, setSelection] = useState<Selection>(() => parseSelection(selectedItemRef))
  const [agents, setAgents] = useState<AvailableAgent[] | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [loading, setLoading] = useState(true)
  const [notice, setNotice] = useState<string | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)

  const [groups, setGroups] = useState<TeamGroup[] | null>(null)
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  const [groupsLoading, setGroupsLoading] = useState(false)
  const [groupsLoadingMore, setGroupsLoadingMore] = useState(false)
  const [groupsError, setGroupsError] = useState<ApiError | null>(null)
  const [groupsStale, setGroupsStale] = useState(false)
  const [groupsLastUpdated, setGroupsLastUpdated] = useState<Date | null>(null)
  const [groupsRefreshKey, setGroupsRefreshKey] = useState(0)
  const [capabilityRetryKey, setCapabilityRetryKey] = useState(0)
  const [capabilityError, setCapabilityError] = useState<ApiError | null>(null)
  const [groupsCapability, setGroupsCapability] = useState<boolean | null>(() => {
    if (props.teamGroupsCapability !== undefined) return props.teamGroupsCapability
    return props.groupsApi ? true : null
  })
  const groupsRef = useRef<TeamGroup[] | null>(null)

  // Follow external navigation (context rail or the Resources "Back to Team").
  useEffect(() => {
    setSelection(parseSelection(selectedItemRef))
  }, [selectedItemRef])

  // Available remains independent of the grouped-teams capability.
  useEffect(() => {
    let cancelled = false
    const controller = new AbortController()
    setError(null)
    setLoading(true)
    api
      .listAvailable(controller.signal)
      .then((loadedAgents) => {
        if (cancelled) return
        setAgents(loadedAgents)
      })
      .catch((cause: unknown) => {
        if (cancelled || controller.signal.aborted) return
        setError(toApiError(cause))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
      controller.abort()
    }
  }, [api, refreshKey])

  // Missing capability is honest unavailability: never probe the route for 404.
  useEffect(() => {
    if (props.teamGroupsCapability !== undefined) {
      setGroupsCapability(props.teamGroupsCapability)
      setCapabilityError(null)
      return
    }
    if (props.groupsApi) {
      setGroupsCapability(true)
      setCapabilityError(null)
      return
    }
    let cancelled = false
    const controller = new AbortController()
    setGroupsCapability(null)
    setCapabilityError(null)
    fetchTeamGroupsCapability(controller.signal)
      .then((supported) => {
        if (!cancelled) setGroupsCapability(supported)
      })
      .catch((cause: unknown) => {
        if (cancelled || controller.signal.aborted) return
        setCapabilityError(toApiError(cause))
      })
    return () => {
      cancelled = true
      controller.abort()
    }
  }, [capabilityRetryKey, props.groupsApi, props.teamGroupsCapability])

  useEffect(() => {
    if (selection.tab !== 'recruited' || groupsCapability !== true) return
    let cancelled = false
    const controller = new AbortController()
    const load = async (initial: boolean) => {
      if (initial && groupsRef.current === null) setGroupsLoading(true)
      try {
        const page = await groupsApi.listGroups({ view: 'all', limit: 200 }, controller.signal)
        if (cancelled) return
        setGroups((previous) => {
          const next = mergeGroupPage(previous, page)
          groupsRef.current = next
          return next
        })
        setNextCursor(page.next_cursor)
        setGroupsError(null)
        setGroupsStale(false)
        setGroupsLastUpdated(new Date())
      } catch (cause: unknown) {
        if (cancelled || controller.signal.aborted) return
        setGroupsError(toApiError(cause))
        if (groupsRef.current !== null) setGroupsStale(true)
      } finally {
        if (!cancelled) setGroupsLoading(false)
      }
    }
    void load(true)
    const timer =
      pollIntervalMs > 0
        ? window.setInterval(() => {
            void load(false)
          }, pollIntervalMs)
        : null
    return () => {
      cancelled = true
      controller.abort()
      if (timer !== null) window.clearInterval(timer)
    }
  }, [groupsApi, groupsCapability, groupsRefreshKey, pollIntervalMs, selection.tab])

  const select = useCallback(
    (next: Selection) => {
      setSelection(next)
      selectItem(itemRef(next))
    },
    [selectItem],
  )

  const selectGroup = useCallback(
    (taskId: string | null) => {
      setSelection({ tab: 'recruited', id: null, groupId: taskId })
      selectItem(taskId ? `team:group:${taskId}` : null)
    },
    [selectItem],
  )

  const loadMoreGroups = useCallback(async () => {
    if (!nextCursor || groupsLoadingMore) return
    setGroupsLoadingMore(true)
    try {
      const page = await groupsApi.listGroups({ view: 'all', limit: 200, cursor: nextCursor })
      setGroups((previous) => {
        const items = [...(previous ?? [])]
        const seen = new Set(items.map((group) => group.task.id))
        for (const group of page.items) {
          if (!seen.has(group.task.id)) {
            seen.add(group.task.id)
            items.push(group)
          }
        }
        groupsRef.current = items
        return items
      })
      setNextCursor(page.next_cursor)
      setGroupsError(null)
      setGroupsStale(false)
      setGroupsLastUpdated(new Date())
    } catch (cause: unknown) {
      setGroupsError(toApiError(cause))
      if (groupsRef.current !== null) setGroupsStale(true)
    } finally {
      setGroupsLoadingMore(false)
    }
  }, [groupsApi, groupsLoadingMore, nextCursor])

  const openTaskChat = useCallback(
    (groupTaskRef: string) => {
      if (props.onOpenTaskChat) {
        props.onOpenTaskChat(groupTaskRef)
        return
      }
      // Explicit action: change task_ref and open the matching Task chat.
      shell.dispatch({ type: 'openTaskConversation', taskRef: groupTaskRef })
    },
    [props.onOpenTaskChat, shell],
  )

  const viewTask = useCallback(
    (groupTaskRef: string) => {
      if (props.onViewTask) {
        props.onViewTask(groupTaskRef)
        return
      }
      // Explicit action: select the real Board Task and navigate there.
      shell.dispatch({ type: 'selectTask', taskRef: groupTaskRef })
      navigate('board')
    },
    [navigate, props.onViewTask, shell],
  )

  const goToResource = useCallback(
    (kind: string, id: string, from: Selection) => {
      if (kind === 'connection') {
        // LG-103: Connection management lives only in Settings. Carry the
        // stable Connection id so the matching record is selected; Task/Run
        // and the browser return position are preserved by the shell.
        selectItem(settingsConnectionRef(id))
        navigate('settings')
        return
      }
      rememberTeamReturn(itemRef(from) ?? (from.tab === 'recruited' ? 'team:recruited' : 'team:available'))
      selectItem(`resources:${kind}:${id}`)
      navigate('resources')
    },
    [navigate, selectItem],
  )

  const requestRole = useCallback(
    (agent: AvailableAgent) => {
      if (!taskRef) {
        setNotice(
          'Select a Task before requesting a role. A global goal must be stated in Chat first.',
        )
        return
      }
      openChatDraft(
        `Request: consider recruiting role "${agent.title}" (${agent.id}) for this Task. ` +
          'This is an intent only; the coordinator still validates and decides the team.',
      )
      navigate('tasks')
    },
    [navigate, openChatDraft, taskRef],
  )

  const activeGroupCount =
    groups === null ? null : groups.filter((group) => groupBucket(group) === 'active').length
  const selectedAgent =
    selection.tab === 'available'
      ? (agents ?? []).find((agent) => agent.id === selection.id) ?? null
      : null

  return (
    <div className="lg-team-view">
      <DetailHeader
        title="Team"
        meta={[
          { label: 'task', value: taskRef ?? 'global' },
          { label: 'run', value: runRef ?? 'active' },
        ]}
      />

      <div className="lg-team-tabs" role="tablist" aria-label="Team sections">
        <button
          type="button"
          role="tab"
          aria-selected={selection.tab === 'available'}
          className={`lg-button${selection.tab === 'available' ? ' lg-button--primary' : ''}`}
          onClick={() => select({ tab: 'available', id: null, groupId: null })}
        >
          Available
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={selection.tab === 'recruited'}
          className={`lg-button${selection.tab === 'recruited' ? ' lg-button--primary' : ''}`}
          onClick={() => select({ tab: 'recruited', id: null, groupId: null })}
        >
          Recruited{activeGroupCount === null ? '' : ` (${activeGroupCount})`}
        </button>
      </div>

      {notice ? (
        <p className="lg-notice" role="status">
          {notice}
        </p>
      ) : null}

      {selection.tab === 'available' ? (
        error ? (
          <ErrorState
            title="Could not load Team"
            message={error.message}
            code={error.code}
            retryable={error.retryable}
            requestId={error.requestId}
            onRetry={() => setRefreshKey((key) => key + 1)}
          />
        ) : loading && agents === null ? (
          <p className="lg-field__hint" role="status">
            Loading role templates…
          </p>
        ) : (
          <div className="lg-team lg-team--available">
            <section
              className="lg-team__list lg-team__list--available"
              aria-label="Available role templates"
            >
              {agents && agents.length === 0 ? (
                <EmptyState title="No role templates">
                  <p>
                    No <span className="lg-card__path">resources/agents/*.md</span> templates were
                    found. Add a role template before recruiting.
                  </p>
                </EmptyState>
              ) : (
                <AvailablePanel
                  agents={agents ?? []}
                  selectedId={selection.id}
                  onSelect={(id) => select({ tab: 'available', id, groupId: null })}
                />
              )}
            </section>
            <section className="lg-team__detail" aria-label="Role template detail">
              {selectedAgent ? (
                <AgentDetail
                  agent={selectedAgent}
                  onResource={goToResource}
                  onRequest={() => requestRole(selectedAgent)}
                  canRequest={Boolean(taskRef)}
                />
              ) : (
                <EmptyState title="Select a role template">
                  <p>Role details, declared references and availability appear here.</p>
                </EmptyState>
              )}
            </section>
          </div>
        )
      ) : capabilityError ? (
        <ErrorState
          title="Could not confirm grouped teams"
          message={capabilityError.message}
          code={capabilityError.code}
          retryable={capabilityError.retryable}
          requestId={capabilityError.requestId}
          onRetry={() => setCapabilityRetryKey((key) => key + 1)}
        />
      ) : groupsCapability === null ? (
        <p className="lg-field__hint" role="status">
          Checking grouped-teams capability…
        </p>
      ) : groupsCapability === false ? (
        <EmptyState title="Grouped teams unavailable">
          <p>
            This backend does not advertise the additive{' '}
            <span className="lg-card__path">team_groups</span> capability. No team-groups request
            was sent.
          </p>
        </EmptyState>
      ) : (
        <RecruitedPanel
          groups={groups}
          nextCursor={nextCursor}
          loading={groupsLoading}
          loadingMore={groupsLoadingMore}
          error={groupsError}
          stale={groupsStale}
          lastUpdatedAt={groupsLastUpdated}
          currentTaskRef={taskRef}
          initialGroupId={selection.groupId}
          onRetry={() => setGroupsRefreshKey((key) => key + 1)}
          onLoadMore={() => {
            void loadMoreGroups()
          }}
          onSelectGroup={selectGroup}
          onOpenChat={openTaskChat}
          onViewTask={viewTask}
        />
      )}
    </div>
  )
}

function AgentDetail({
  agent,
  onResource,
  onRequest,
  canRequest,
}: {
  agent: AvailableAgent
  onResource: (kind: string, id: string, from: Selection) => void
  onRequest: () => void
  canRequest: boolean
}) {
  const badge = roleBadge(agent)
  const from: Selection = { tab: 'available', id: agent.id, groupId: null }
  const source = agent.agency_source
  const capabilities = agent.capabilities ?? []
  const blocked = agent.recruitable === false || !agent.enabled
  return (
    <div>
      <DetailHeader
        title={agent.title}
        badges={<StatusBadge kind={badge.kind} title={badge.title}>{badge.label}</StatusBadge>}
        meta={[
          { label: 'kind', value: 'agent' },
          { label: 'category', value: agent.role_category ?? 'custom' },
          { label: 'id', value: agent.id },
          { label: 'revision', value: agent.revision === null ? '—' : String(agent.revision) },
          { label: 'template version', value: agent.template_version ?? '1' },
        ]}
        actions={
          <button
            type="button"
            className="lg-button lg-button--primary"
            onClick={onRequest}
            disabled={blocked}
            title={
              blocked
                ? agent.unsupported_reasons?.[0] ?? 'This role is not recruitable in this version.'
                : undefined
            }
          >
            Request for current task
          </button>
        }
      />
      {agent.summary ? <p className="lg-team__role-summary">{agent.summary}</p> : null}
      {!canRequest ? (
        <p className="lg-notice" role="note">
          A Task scope is required to request this role; open Chat to state a global goal first.
        </p>
      ) : null}
      {agent.recruitable === false ? (
        <p className="lg-notice" role="note">
          <strong>Unsupported:</strong>{' '}
          {agent.unsupported_reasons?.join('; ') ||
            'no executable scheduler capability mapping is declared'}
        </p>
      ) : null}
      {capabilities.length > 0 ? (
        <section className="lg-team__block" aria-label="Role capabilities">
          <h4 className="lg-section__title">Capabilities</h4>
          <div className="lg-team__capabilities">
            {capabilities.map((capability) => (
              <StatusBadge key={capability} kind="accent">
                {capability}
              </StatusBadge>
            ))}
          </div>
          {(agent.capability_notes ?? []).length > 0 ? (
            <ul className="lg-team__reasons">
              {(agent.capability_notes ?? []).map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          ) : null}
        </section>
      ) : null}
      <ReferenceList
        title="Declared references"
        entries={[
          agent.connection_ref ? { kind: 'connection', ref: agent.connection_ref, label: 'connection_ref' } : null,
          agent.conversation_ref
            ? { kind: 'conversation', ref: agent.conversation_ref, label: 'conversation_ref' }
            : null,
          ...agent.skill_refs.map((ref) => ({ kind: 'skill', ref, label: 'skills.refs' })),
          ...(agent.tool_refs ?? []).map((ref) => ({ kind: 'tool', ref, label: 'tool_refs' })),
          ...(agent.hook_refs ?? []).map((ref) => ({ kind: 'hook', ref, label: 'hook_refs' })),
          ...(agent.mcp_refs ?? []).map((ref) => ({ kind: 'mcp', ref, label: 'mcp_refs' })),
          ...(agent.trigger_refs ?? []).map((ref) => ({ kind: 'trigger', ref, label: 'trigger_refs' })),
        ].filter((entry): entry is { kind: string; ref: string; label: string } => entry !== null)}
        onResource={(kind, ref) => onResource(kind, ref, from)}
      />
      {agent.availability.reasons.length > 0 ? (
        <section className="lg-team__block" aria-label="Availability">
          <h4 className="lg-section__title">Availability</h4>
          <ul className="lg-team__reasons">
            {agent.availability.reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
          <p className="lg-field__hint">
            Template changes only affect future recruitment; an active Member keeps its pinned
            configuration version.
          </p>
        </section>
      ) : null}
      {(agent.diagnostics?.length ?? 0) > 0 ? (
        <Diagnostics diagnostics={agent.diagnostics ?? []} />
      ) : null}
      {source ? (
        <section className="lg-team__block" aria-label="Source and license">
          <h4 className="lg-section__title">Source &amp; license</h4>
          <dl className="lg-kv">
            <dt>repository</dt>
            <dd className="lg-card__path">{source.repository ?? 'agency-agents'}</dd>
            <dt>commit</dt>
            <dd className="lg-card__path" title={source.commit}>
              {source.commit.slice(0, 12)}
            </dd>
            <dt>upstream path</dt>
            <dd className="lg-card__path">{source.path}</dd>
            <dt>git blob</dt>
            <dd className="lg-card__path" title={source.blob_sha}>
              {source.blob_sha.slice(0, 12)}
            </dd>
            <dt>source sha256</dt>
            <dd className="lg-card__path" title={source.sha256}>
              {source.sha256.slice(0, 12)}
            </dd>
            <dt>license</dt>
            <dd>
              {source.license}
              {source.copyright ? ` · ${source.copyright}` : ''}
            </dd>
            <dt>seed version</dt>
            <dd>{agent.seed?.version ?? '—'}</dd>
          </dl>
          {agent.seed?.update_available ? (
            <p className="lg-notice" role="note">
              A newer built-in version is available. Your edited role body is preserved; the
              update only applies to a future recruitment after you explicitly accept it.
            </p>
          ) : null}
        </section>
      ) : null}
      <section className="lg-team__block" aria-label="Role instructions">
        <h4 className="lg-section__title">Role instructions</h4>
        <p className="lg-field__hint">
          Imported guidance only. It grants no tools, network, credentials, budget, or execution
          permission.
        </p>
        <MarkdownViewer content={agent.body ?? ''} />
      </section>
    </div>
  )
}

function ReferenceList({
  title,
  entries,
  onResource,
}: {
  title: string
  entries: ReadonlyArray<{ kind: string; ref: string; label: string }>
  onResource: (kind: string, ref: string) => void
}) {
  return (
    <section className="lg-team__block" aria-label={title}>
      <h4 className="lg-section__title">{title}</h4>
      {entries.length === 0 ? (
        <p className="lg-field__hint">No references declared.</p>
      ) : (
        <ul className="lg-refs">
          {entries.map((entry) => (
            <li key={`${entry.label}:${entry.kind}:${entry.ref}`}>
              <button
                type="button"
                className="lg-refs__link"
                onClick={() => onResource(entry.kind, entry.ref)}
              >
                <span className="lg-card__path">
                  {entry.kind}:{entry.ref}
                </span>
                <span className="lg-refs__field">{entry.label}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

function toApiError(cause: unknown): ApiError {
  if (cause instanceof ApiError) return cause
  return new ApiError({
    message: cause instanceof Error ? cause.message : 'Request failed',
    code: 'network_error',
    httpStatus: null,
    retryable: true,
  })
}
