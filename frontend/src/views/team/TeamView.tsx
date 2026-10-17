import { useCallback, useEffect, useMemo, useState } from 'react'

import { ApiError } from '../../api/client'
import {
  createTeamApi,
  isFailed,
  isReleased,
  type AvailableAgent,
  type TeamApi,
  type TeamMember,
} from '../../api/team'
import type { ViewId } from '../../app/navigation'
import { useShell } from '../../app/ShellProvider'
import { useAuth } from '../../app/AuthProvider'
import { draftKey } from '../../app/uiState'
import { DetailHeader } from '../../components/DetailHeader'
import { EmptyState } from '../../components/EmptyState'
import { ErrorState } from '../../components/ErrorState'
import { MarkdownViewer } from '../../components/MarkdownViewer'
import { ResourceCard } from '../../components/ResourceCard'
import { StatusBadge } from '../../components/StatusBadge'
import { availabilityBadge } from '../resources/availability'
import { Diagnostics } from '../resources/Diagnostics'
import { rememberTeamReturn } from './returnState'
import './team.css'

type TeamTab = 'available' | 'recruited'

export interface TeamViewProps {
  /** Injectable for tests; defaults to the real `/team/*` endpoints. */
  api?: TeamApi
  taskRef?: string | null
  runRef?: string | null
  selectedItemRef?: string | null
  navigate?: (view: ViewId) => void
  selectItem?: (ref: string | null) => void
  openChatDraft?: (message: string) => void
}

interface Selection {
  tab: TeamTab
  id: string | null
}

function parseSelection(ref: string | null | undefined): Selection {
  if (!ref) return { tab: 'available', id: null }
  if (ref === 'team-recruited' || ref === 'team:recruited') {
    return { tab: 'recruited', id: null }
  }
  if (ref.startsWith('team:member:')) {
    return { tab: 'recruited', id: ref.slice('team:member:'.length) }
  }
  if (ref.startsWith('team:agent:')) {
    return { tab: 'available', id: ref.slice('team:agent:'.length) }
  }
  return { tab: 'available', id: null }
}

function itemRef(selection: Selection): string | null {
  if (!selection.id) return null
  return selection.tab === 'available' ? `team:agent:${selection.id}` : `team:member:${selection.id}`
}

function memberBadge(member: TeamMember): { kind: 'neutral' | 'accent' | 'success' | 'warning' | 'error'; label: string } {
  switch (member.state) {
    case 'running':
      return { kind: 'accent', label: 'running' }
    case 'ready':
      return { kind: 'success', label: 'ready' }
    case 'recruiting':
      return { kind: 'warning', label: 'recruiting' }
    case 'waiting_user':
      return { kind: 'warning', label: 'waiting_user' }
    case 'failed':
      return { kind: 'error', label: 'failed' }
    case 'released':
      return { kind: 'neutral', label: 'released' }
    default:
      return { kind: 'neutral', label: member.state ?? 'unknown' }
  }
}

/**
 * Team (owner LG-015; docs/05 §5, design.md §5 Team).
 *
 * Available reads agent templates and shows declared/parsed/compiled
 * availability; Recruited reads Member instances for the active Task/Run and
 * keeps released members as history (excluded from the current count).  Role
 * and member resource references navigate to Resources while remembering the
 * return position.  "Request for current task" only opens Task Chat with an
 * intent draft; it never creates an SDK worker or bypasses the recruiter.
 */
export function TeamView(props: TeamViewProps = {}) {
  const shell = useShell()
  const { isTeam } = useAuth()
  const api = useMemo(() => props.api ?? createTeamApi(), [props.api])
  const taskRef = props.taskRef !== undefined ? props.taskRef : shell.state.taskRef
  const runRef = props.runRef !== undefined ? props.runRef : shell.state.runRef
  const selectedItemRef =
    props.selectedItemRef !== undefined ? props.selectedItemRef : shell.state.selectedItemRef

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
  const [members, setMembers] = useState<TeamMember[] | null>(null)
  const [showReleased, setShowReleased] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)
  const [loading, setLoading] = useState(true)
  const [notice, setNotice] = useState<string | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)

  // Follow external navigation (context rail or the Resources "Back to Team").
  useEffect(() => {
    setSelection(parseSelection(selectedItemRef))
  }, [selectedItemRef])

  useEffect(() => {
    let cancelled = false
    const controller = new AbortController()
    setError(null)
    Promise.all([
      api.listAvailable(controller.signal),
      api.listMembers(
        { taskRef: taskRef ?? undefined, runRef: runRef ?? undefined, includeReleased: true },
        controller.signal,
      ),
    ])
      .then(([loadedAgents, loadedMembers]) => {
        if (cancelled) return
        setAgents(loadedAgents)
        setMembers(loadedMembers)
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
  }, [api, taskRef, runRef, refreshKey])

  const select = useCallback(
    (next: Selection) => {
      setSelection(next)
      selectItem(itemRef(next))
    },
    [selectItem],
  )

  const goToResource = useCallback(
    (kind: string, id: string, from: Selection) => {
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
      navigate('chat')
    },
    [navigate, openChatDraft, taskRef],
  )

  const currentMembers = (members ?? []).filter((member) => !isReleased(member))
  const releasedMembers = (members ?? []).filter(isReleased)
  const failedMembers = currentMembers.filter(isFailed)
  const selectedAgent =
    selection.tab === 'available'
      ? (agents ?? []).find((agent) => agent.id === selection.id) ?? null
      : null
  const selectedMember =
    selection.tab === 'recruited'
      ? (members ?? []).find((member) => member.id === selection.id) ?? null
      : null

  return (
    <div className="lg-team-view">
      <DetailHeader
        title="Team"
        badges={
          <>
            <StatusBadge kind="accent">Available</StatusBadge>
            <StatusBadge kind="neutral">Recruited</StatusBadge>
          </>
        }
        meta={[
          { label: 'task', value: taskRef ?? 'global' },
          { label: 'run', value: runRef ?? 'active' },
          { label: 'current members', value: String(currentMembers.length) },
        ]}
      />

      <div className="lg-team-tabs" role="tablist" aria-label="Team sections">
        <button
          type="button"
          role="tab"
          aria-selected={selection.tab === 'available'}
          className={`lg-button${selection.tab === 'available' ? ' lg-button--primary' : ''}`}
          onClick={() => select({ tab: 'available', id: null })}
        >
          Available
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={selection.tab === 'recruited'}
          className={`lg-button${selection.tab === 'recruited' ? ' lg-button--primary' : ''}`}
          onClick={() => select({ tab: 'recruited', id: null })}
        >
          Recruited ({currentMembers.length})
        </button>
      </div>

      {notice ? (
        <p className="lg-notice" role="status">
          {notice}
        </p>
      ) : null}

      {error ? (
        <ErrorState
          title="Could not load Team"
          message={error.message}
          code={error.code}
          retryable={error.retryable}
          requestId={error.requestId}
          onRetry={() => setRefreshKey((key) => key + 1)}
        />
      ) : loading && agents === null && members === null ? (
        <p className="lg-field__hint" role="status">
          Loading team…
        </p>
      ) : selection.tab === 'available' ? (
        <div className="lg-team">
          <section className="lg-team__list" aria-label="Available role templates">
            {agents && agents.length === 0 ? (
              <EmptyState title="No role templates">
                <p>
                  No <span className="lg-card__path">resources/agents/*.md</span> templates were
                  found. Add a role template before recruiting.
                </p>
              </EmptyState>
            ) : (
              <ul className="lg-team__items">
                {(agents ?? []).map((agent) => {
                  const badge = availabilityBadge(agent.availability)
                  return (
                    <li key={agent.id}>
                      <ResourceCard
                        title={agent.title}
                        kind="agent"
                        path={agent.id}
                        availability={{ kind: badge.kind, label: badge.label }}
                        onOpen={() => select({ tab: 'available', id: agent.id })}
                      />
                    </li>
                  )
                })}
              </ul>
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
      ) : (
        <div className="lg-team">
          <section className="lg-team__list" aria-label="Recruited members">
            <div className="lg-team__list-head">
              <span className="lg-field__label">Current members: {currentMembers.length}</span>
              <label className="lg-field lg-field--inline">
                <input
                  type="checkbox"
                  checked={showReleased}
                  onChange={(event) => setShowReleased(event.target.checked)}
                />
                <span className="lg-field__label">Show released history ({releasedMembers.length})</span>
              </label>
            </div>
            {currentMembers.length === 0 ? (
              <EmptyState
                title={
                  releasedMembers.length > 0
                    ? 'Current team released'
                    : 'No members recruited yet'
                }
              >
                <p>
                  {releasedMembers.length > 0
                    ? 'The current team was released. Its configuration and results remain in the history below.'
                    : taskRef
                      ? 'No Member instances exist for this Task/Run yet. Request a role from Available to start recruitment.'
                      : 'Select a Task to see its current team.'}
                </p>
                {failedMembers.length > 0 ? (
                  <p>
                    <StatusBadge kind="error">recruitment failed</StatusBadge>{' '}
                    {failedMembers[0].fail_reason ?? 'see member detail'}
                  </p>
                ) : null}
              </EmptyState>
            ) : (
              <ul className="lg-team__items">
                {currentMembers.map((member) => (
                  <MemberCard key={member.id} member={member} onOpen={() => select({ tab: 'recruited', id: member.id })} />
                ))}
              </ul>
            )}
            {showReleased && releasedMembers.length > 0 ? (
              <>
                <h3 className="lg-section__title">Released history</h3>
                <ul className="lg-team__items">
                  {releasedMembers.map((member) => (
                    <MemberCard key={member.id} member={member} onOpen={() => select({ tab: 'recruited', id: member.id })} />
                  ))}
                </ul>
              </>
            ) : null}
          </section>
          <section className="lg-team__detail" aria-label="Member detail">
            {selectedMember ? (
              <MemberDetail member={selectedMember} onResource={goToResource} />
            ) : (
              <EmptyState title="Select a member">
                <p>Member state, assigned Subtasks, pinned configuration and results appear here.</p>
              </EmptyState>
            )}
          </section>
        </div>
      )}
    </div>
  )
}

function MemberCard({ member, onOpen }: { member: TeamMember; onOpen: () => void }) {
  const badge = memberBadge(member)
  return (
    <ResourceCard
      title={`${member.role_ref ?? member.title} · ${member.id}`}
      kind="member"
      path={member.run_ref ?? undefined}
      availability={badge}
      onOpen={onOpen}
    />
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
  const badge = availabilityBadge(agent.availability)
  const from: Selection = { tab: 'available', id: agent.id }
  return (
    <div>
      <DetailHeader
        title={agent.title}
        badges={<StatusBadge kind={badge.kind} title={badge.title}>{badge.label}</StatusBadge>}
        meta={[
          { label: 'kind', value: 'agent' },
          { label: 'id', value: agent.id },
          { label: 'revision', value: agent.revision === null ? '—' : String(agent.revision) },
          { label: 'template version', value: agent.template_version ?? '1' },
        ]}
        actions={
          <button type="button" className="lg-button lg-button--primary" onClick={onRequest}>
            Request for current task
          </button>
        }
      />
      {!canRequest ? (
        <p className="lg-notice" role="note">
          A Task scope is required to request this role; open Chat to state a global goal first.
        </p>
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
      <section className="lg-team__block" aria-label="Role instructions">
        <h4 className="lg-section__title">Role instructions</h4>
        <MarkdownViewer content={agent.body ?? ''} />
      </section>
    </div>
  )
}

function MemberDetail({
  member,
  onResource,
}: {
  member: TeamMember
  onResource: (kind: string, id: string, from: Selection) => void
}) {
  const badge = memberBadge(member)
  const from: Selection = { tab: 'recruited', id: member.id }
  const entries = [
    member.connection_ref ? { kind: 'connection', ref: member.connection_ref, label: 'connection_ref' } : null,
    ...member.skill_refs.map((ref) => ({ kind: 'skill', ref, label: 'skill_refs' })),
  ].filter((entry): entry is { kind: string; ref: string; label: string } => entry !== null)
  return (
    <div>
      <DetailHeader
        title={member.role_ref ?? member.title}
        badges={<StatusBadge kind={badge.kind}>{badge.label}</StatusBadge>}
        meta={[
          { label: 'member', value: member.id },
          { label: 'run', value: member.run_ref ?? '—' },
          { label: 'template version', value: member.template_version ?? '—' },
        ]}
      />
      {member.fail_reason ? (
        <p className="lg-state lg-state--error" role="alert">
          <span className="lg-state__title">Failure</span>
          {' '}
          {member.fail_reason}
        </p>
      ) : null}
      <section className="lg-team__block" aria-label="Assignment">
        <h4 className="lg-section__title">Assignment</h4>
        <dl className="lg-kv">
          <dt>assigned subtasks</dt>
          <dd>
            {member.assigned_subtask_refs.length > 0
              ? member.assigned_subtask_refs.join(', ')
              : 'none'}
          </dd>
          <dt>SDK session</dt>
          <dd>{member.session_ref ?? 'not recorded'}</dd>
        </dl>
      </section>
      <section className="lg-team__block" aria-label="Pinned configuration">
        <h4 className="lg-section__title">Pinned configuration</h4>
        <dl className="lg-kv">
          <dt>config version</dt>
          <dd className="lg-card__path">{member.config_hash ?? 'not recorded'}</dd>
          <dt>template version</dt>
          <dd>{member.template_version ?? '—'}</dd>
        </dl>
        <p className="lg-field__hint">
          The member is pinned to this resolved configuration; later template edits do not hot-swap
          a running member.
        </p>
      </section>
      <ReferenceList title="Resolved references" entries={entries} onResource={(kind, ref) => onResource(kind, ref, from)} />
      {member.availability.reasons.length > 0 ? (
        <section className="lg-team__block" aria-label="Availability">
          <h4 className="lg-section__title">Availability</h4>
          <ul className="lg-team__reasons">
            {member.availability.reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </section>
      ) : null}
      {(member.diagnostics?.length ?? 0) > 0 ? (
        <Diagnostics diagnostics={member.diagnostics ?? []} />
      ) : null}
      {member.body ? (
        <section className="lg-team__block" aria-label="Member notes">
          <h4 className="lg-section__title">Notes</h4>
          <MarkdownViewer content={member.body} />
        </section>
      ) : null}
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
