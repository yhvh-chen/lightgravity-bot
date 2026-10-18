/**
 * Grouped Recruited panel (LG-125; docs/13 §2–3, docs/08 §19.2/§19.5).
 *
 * Active/History, all-Task/Task filter and search are local page state.  They
 * never change the shell `task_ref` or the active chat.  Only the explicit
 * Open chat / View task actions change Task scope or navigation.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import type { ApiError } from '../../api/client'
import type {
  TeamGroup,
  TeamGroupMember,
  TeamGroupRun,
  TeamGroupSubtask,
} from '../../api/teamGroups'
import { EmptyState } from '../../components/EmptyState'
import { ErrorState } from '../../components/ErrorState'
import { StatusBadge } from '../../components/StatusBadge'
import {
  activeRun,
  assignedSubtasks,
  displayRun,
  formatWaitingReason,
  groupBucket,
  groupStatus,
  historyMembers,
  memberStatus,
  runHeading,
  shortTaskId,
  sortGroups,
  subtaskStatus,
} from './grouphelpers'

type RecruitedTab = 'active' | 'history'

interface SavedUi {
  tab: RecruitedTab
  taskFilter: string
  search: string
  expanded: string[]
  expandedMembers: string[]
  selected: string | null
}

const UI_KEY = 'lg125.team-groups-ui'

function readSavedUi(): SavedUi {
  const fallback: SavedUi = {
    tab: 'active',
    taskFilter: 'all',
    search: '',
    expanded: [],
    expandedMembers: [],
    selected: null,
  }
  try {
    if (typeof window === 'undefined' || !window.sessionStorage) return fallback
    const raw = window.sessionStorage.getItem(UI_KEY)
    if (!raw) return fallback
    const parsed = JSON.parse(raw) as Partial<SavedUi>
    return {
      tab: parsed.tab === 'history' ? 'history' : 'active',
      taskFilter: typeof parsed.taskFilter === 'string' ? parsed.taskFilter : 'all',
      search: typeof parsed.search === 'string' ? parsed.search : '',
      expanded: Array.isArray(parsed.expanded)
        ? parsed.expanded.filter((item): item is string => typeof item === 'string')
        : [],
      expandedMembers: Array.isArray(parsed.expandedMembers)
        ? parsed.expandedMembers.filter((item): item is string => typeof item === 'string')
        : [],
      selected: typeof parsed.selected === 'string' ? parsed.selected : null,
    }
  } catch {
    return fallback
  }
}

function saveUi(value: SavedUi): void {
  try {
    if (typeof window === 'undefined' || !window.sessionStorage) return
    window.sessionStorage.setItem(UI_KEY, JSON.stringify(value))
  } catch {
    /* UI preference only; loss does not affect backend facts. */
  }
}

function safeDomId(value: string): string {
  return value.replace(/[^a-zA-Z0-9_-]/g, '-')
}

function matchesSearch(group: TeamGroup, query: string): boolean {
  if (!query) return true
  const haystack = [
    group.task.title,
    group.task.id,
    group.task.status,
    group.task.phase,
    group.task.active_run ?? '',
    group.task.last_run ?? '',
    ...group.members.map((member) => `${member.role_ref ?? ''} ${member.id}`),
  ]
    .join(' ')
    .toLowerCase()
  return haystack.includes(query)
}

export interface RecruitedPanelProps {
  groups: TeamGroup[] | null
  nextCursor: string | null
  loading: boolean
  loadingMore: boolean
  error: ApiError | null
  stale: boolean
  lastUpdatedAt: Date | null
  currentTaskRef: string | null
  initialGroupId?: string | null
  onRetry: () => void
  onLoadMore: () => void
  onSelectGroup?: (taskId: string | null) => void
  onOpenChat: (taskId: string) => void
  onViewTask: (taskId: string) => void
  /** Keep a just-released group in Active briefly, then move it to History. */
  recentReleaseMs?: number
}

export function RecruitedPanel({
  groups,
  nextCursor,
  loading,
  loadingMore,
  error,
  stale,
  lastUpdatedAt,
  currentTaskRef,
  initialGroupId = null,
  onRetry,
  onLoadMore,
  onSelectGroup,
  onOpenChat,
  onViewTask,
  recentReleaseMs = 12000,
}: RecruitedPanelProps) {
  const saved = useMemo(readSavedUi, [])
  const [tab, setTab] = useState<RecruitedTab>(saved.tab)
  const [taskFilter, setTaskFilter] = useState(saved.taskFilter)
  const [search, setSearch] = useState(saved.search)
  const [expanded, setExpanded] = useState<string[]>(saved.expanded)
  const [expandedMembers, setExpandedMembers] = useState<string[]>(saved.expandedMembers)
  const [selected, setSelected] = useState<string | null>(initialGroupId ?? saved.selected)
  const [recentIds, setRecentIds] = useState<string[]>([])
  const [liveMessage, setLiveMessage] = useState('')
  const historyTabRef = useRef<HTMLButtonElement>(null)
  const groupsRef = useRef<TeamGroup[] | null>(groups)
  const previousBuckets = useRef<Map<string, 'active' | 'history'> | null>(null)
  const timers = useRef<Map<string, number>>(new Map())
  const didInitialSelect = useRef(false)

  groupsRef.current = groups

  useEffect(() => {
    saveUi({ tab, taskFilter, search, expanded, expandedMembers, selected })
  }, [tab, taskFilter, search, expanded, expandedMembers, selected])

  useEffect(() => {
    if (initialGroupId) {
      setSelected(initialGroupId)
      setExpanded((current) =>
        current.includes(initialGroupId) ? current : [...current, initialGroupId],
      )
    }
  }, [initialGroupId])

  // Select the current Task's group once on first load, unless the user already
  // had a remembered group selection.
  useEffect(() => {
    if (!groups || didInitialSelect.current) return
    didInitialSelect.current = true
    if (initialGroupId || selected) return
    if (currentTaskRef && groups.some((group) => group.task.id === currentTaskRef)) {
      setSelected(currentTaskRef)
      setExpanded((current) =>
        current.includes(currentTaskRef) ? current : [...current, currentTaskRef],
      )
    }
  }, [currentTaskRef, groups, initialGroupId, selected])

  const removeRecent = useCallback((taskId: string) => {
    const active = document.activeElement as HTMLElement | null
    const row = active?.closest('[data-team-group]')
    const focusedInside = row?.getAttribute('data-team-group') === taskId
    const title = groupsRef.current?.find((group) => group.task.id === taskId)?.task.title
    if (focusedInside) {
      historyTabRef.current?.focus()
      setLiveMessage(
        `${title ?? taskId} moved to History. Focus moved to the History tab so it stays usable.`,
      )
    } else {
      setLiveMessage(`${title ?? taskId} moved to History.`)
    }
    setRecentIds((current) => current.filter((id) => id !== taskId))
  }, [])

  // Detect Active -> History transitions across polls.  Keep the group in
  // Active briefly with an explicit View history action before moving it.
  useEffect(() => {
    if (!groups) return
    const next = new Map<string, 'active' | 'history'>()
    for (const group of groups) next.set(group.task.id, groupBucket(group))
    const previous = previousBuckets.current
    if (previous) {
      for (const group of groups) {
        const before = previous.get(group.task.id)
        const after = next.get(group.task.id)
        if (before === 'active' && after === 'history' && !timers.current.has(group.task.id)) {
          setRecentIds((current) =>
            current.includes(group.task.id) ? current : [...current, group.task.id],
          )
          const timer = window.setTimeout(() => {
            timers.current.delete(group.task.id)
            removeRecent(group.task.id)
          }, recentReleaseMs)
          timers.current.set(group.task.id, timer)
        }
      }
    }
    previousBuckets.current = next
  }, [groups, recentReleaseMs, removeRecent])

  useEffect(() => {
    return () => {
      for (const timer of timers.current.values()) window.clearTimeout(timer)
      timers.current.clear()
    }
  }, [])

  const sorted = useMemo(() => sortGroups(groups ?? []), [groups])
  const taskIds = useMemo(() => new Set(sorted.map((group) => group.task.id)), [sorted])
  const effectiveFilter = taskFilter !== 'all' && taskIds.has(taskFilter) ? taskFilter : 'all'
  const query = search.trim().toLowerCase()
  const recentSet = useMemo(() => new Set(recentIds), [recentIds])
  const activeCount = sorted.filter((group) => groupBucket(group) === 'active').length
  const historyCount = sorted.length - activeCount

  const tabGroups = sorted.filter((group) => {
    const bucket = groupBucket(group)
    return tab === 'active'
      ? bucket === 'active' || recentSet.has(group.task.id)
      : bucket === 'history'
  })
  const hasFilters = effectiveFilter !== 'all' || query.length > 0
  const visible = tabGroups.filter((group) => {
    if (effectiveFilter !== 'all' && group.task.id !== effectiveFilter) return false
    return matchesSearch(group, query)
  })

  const toggleGroup = (taskId: string) => {
    setSelected(taskId)
    onSelectGroup?.(taskId)
    setExpanded((current) =>
      current.includes(taskId) ? current.filter((id) => id !== taskId) : [...current, taskId],
    )
  }

  const toggleMember = (memberId: string) => {
    setExpandedMembers((current) =>
      current.includes(memberId) ? current.filter((id) => id !== memberId) : [...current, memberId],
    )
  }

  const viewHistory = (taskId: string) => {
    setTab('history')
    setTaskFilter(taskId)
    setSearch('')
    setSelected(taskId)
    onSelectGroup?.(taskId)
    setExpanded((current) => (current.includes(taskId) ? current : [...current, taskId]))
  }

  // Explicit Open chat / View task is also the selected group on return.  Save
  // synchronously because the parent navigation can unmount this panel before
  // the preference effect runs.
  const prepareNavigation = (taskId: string) => {
    const nextExpanded = expanded.includes(taskId) ? expanded : [...expanded, taskId]
    setSelected(taskId)
    setExpanded(nextExpanded)
    onSelectGroup?.(taskId)
    saveUi({
      tab,
      taskFilter,
      search,
      expanded: nextExpanded,
      expandedMembers,
      selected: taskId,
    })
  }

  const openChatFor = (taskId: string) => {
    prepareNavigation(taskId)
    onOpenChat(taskId)
  }

  const viewTaskFor = (taskId: string) => {
    prepareNavigation(taskId)
    onViewTask(taskId)
  }

  const clearFilters = () => {
    setTaskFilter('all')
    setSearch('')
  }

  const filteredEmpty = hasFilters && tabGroups.length > 0 && visible.length === 0
  const loadingInitial = groups === null && (loading || error === null)
  const errorInitial = error !== null && groups === null

  return (
    <section className="lg-team-groups" aria-label="Recruited teams">
      <div className="lg-team-groups__toolbar">
        <div className="lg-team-groups__tabs" role="tablist" aria-label="Recruited team state">
          <button
            type="button"
            role="tab"
            aria-selected={tab === 'active'}
            className={`lg-button${tab === 'active' ? ' lg-button--primary' : ''}`}
            onClick={() => setTab('active')}
          >
            Active ({activeCount})
          </button>
          <button
            ref={historyTabRef}
            type="button"
            role="tab"
            aria-selected={tab === 'history'}
            className={`lg-button${tab === 'history' ? ' lg-button--primary' : ''}`}
            onClick={() => setTab('history')}
          >
            History ({historyCount})
          </button>
        </div>

        <div className="lg-team-groups__filters" role="search" aria-label="Filter recruited teams">
          <label className="lg-field lg-team-groups__filter">
            <span className="lg-field__label">Task filter</span>
            <select value={effectiveFilter} onChange={(event) => setTaskFilter(event.target.value)}>
              <option value="all">All tasks</option>
              {sorted.map((group) => (
                <option key={group.task.id} value={group.task.id}>
                  {group.task.title} · {shortTaskId(group.task.id)}
                </option>
              ))}
            </select>
          </label>
          <label className="lg-field lg-team-groups__search">
            <span className="lg-field__label">Search tasks</span>
            <input
              type="search"
              value={search}
              placeholder="Title, Task ID, role or member"
              onChange={(event) => setSearch(event.target.value)}
            />
          </label>
          {effectiveFilter !== 'all' || search ? (
            <button type="button" className="lg-button lg-team-groups__clear" onClick={clearFilters}>
              Clear filters
            </button>
          ) : null}
          <p className="lg-field__hint lg-team-groups__count" role="status">
            {visible.length} of {tabGroups.length} task groups
          </p>
        </div>
      </div>

      {stale && groups !== null ? (
        <p className="lg-team-groups__stale" role="status">
          <StatusBadge kind="warning">Disconnected</StatusBadge>{' '}
          Showing the last snapshot{lastUpdatedAt ? ` from ${lastUpdatedAt.toLocaleTimeString()}` : ''}.
          It is not marked completed by this page.{' '}
          <button type="button" className="lg-button" onClick={onRetry}>
            Retry
          </button>
        </p>
      ) : null}

      {loadingInitial ? (
        <p className="lg-field__hint" role="status">
          Loading team groups…
        </p>
      ) : errorInitial && error ? (
        <ErrorState
          title="Could not load team groups"
          message={error.message}
          code={error.code}
          retryable={error.retryable}
          requestId={error.requestId}
          onRetry={onRetry}
        />
      ) : tabGroups.length === 0 ? (
        <EmptyState title={tab === 'active' ? 'No active teams' : 'No released teams yet'}>
          <p>
            {tab === 'active'
              ? 'A Task appears here when it is queued, assembling or executing.'
              : 'A team appears here after worker and reviewer stop is confirmed and the Task slot is free.'}
          </p>
        </EmptyState>
      ) : filteredEmpty ? (
        <EmptyState title="No task groups match">
          <p>Clear the Task filter or search to see the other groups. This does not change the active chat.</p>
          <button type="button" className="lg-button" onClick={clearFilters}>
            Clear filters
          </button>
        </EmptyState>
      ) : (
        <ul className="lg-team-groups__list">
          {visible.map((group) => (
            <li key={group.task.id}>
              <GroupCard
                group={group}
                expanded={expanded.includes(group.task.id)}
                selected={selected === group.task.id}
                transitioned={recentSet.has(group.task.id) && groupBucket(group) === 'history'}
                currentTask={currentTaskRef === group.task.id}
                expandedMembers={expandedMembers}
                onToggle={() => toggleGroup(group.task.id)}
                onToggleMember={toggleMember}
                onViewHistory={() => viewHistory(group.task.id)}
                onOpenChat={() => openChatFor(group.task.id)}
                onViewTask={() => viewTaskFor(group.task.id)}
              />
            </li>
          ))}
        </ul>
      )}

      {nextCursor && groups !== null ? (
        <div className="lg-team-groups__more">
          <button type="button" className="lg-button" disabled={loadingMore} onClick={onLoadMore}>
            {loadingMore ? 'Loading more…' : 'Load more task groups'}
          </button>
        </div>
      ) : null}

      <p className="lg-visually-hidden" role="status" aria-live="polite">
        {liveMessage}
      </p>
    </section>
  )
}

function GroupCard({
  group,
  expanded,
  selected,
  transitioned,
  currentTask,
  expandedMembers,
  onToggle,
  onToggleMember,
  onViewHistory,
  onOpenChat,
  onViewTask,
}: {
  group: TeamGroup
  expanded: boolean
  selected: boolean
  transitioned: boolean
  currentTask: boolean
  expandedMembers: string[]
  onToggle: () => void
  onToggleMember: (memberId: string) => void
  onViewHistory: () => void
  onOpenChat: () => void
  onViewTask: () => void
}) {
  const status = groupStatus(group)
  const run = displayRun(group)
  const current = activeRun(group)
  const bodyId = `team-group-body-${safeDomId(group.task.id)}`
  return (
    <article
      className={`lg-team-group${selected ? ' lg-team-group--selected' : ''}`}
      data-team-group={group.task.id}
      aria-labelledby={`team-group-title-${safeDomId(group.task.id)}`}
    >
      <div className="lg-team-group__header">
        <button
          type="button"
          className="lg-team-group__title"
          aria-expanded={expanded}
          aria-controls={bodyId}
          onClick={onToggle}
        >
          <span className="lg-team-group__chevron" aria-hidden="true">
            {expanded ? '▾' : '▸'}
          </span>
          <span id={`team-group-title-${safeDomId(group.task.id)}`} className="lg-team-group__name">
            {group.task.title}
          </span>
        </button>

        <div className="lg-team-group__badges">
          <StatusBadge kind={status.kind} title={status.detail ?? status.label}>
            {status.label}
          </StatusBadge>
          {currentTask ? <StatusBadge kind="accent">Current chat</StatusBadge> : null}
        </div>

        <div className="lg-team-group__actions">
          {transitioned ? (
            <button type="button" className="lg-button" onClick={onViewHistory}>
              View history
            </button>
          ) : null}
          <button
            type="button"
            className="lg-button"
            aria-label={`Open chat for ${group.task.title}`}
            onClick={onOpenChat}
          >
            Open chat
          </button>
          <button
            type="button"
            className="lg-button"
            aria-label={`View task ${group.task.title}`}
            onClick={onViewTask}
          >
            View task
          </button>
        </div>
      </div>

      {status.detail ? (
        <p className="lg-team-group__detail" role="note">
          {status.detail}
        </p>
      ) : null}

      {expanded ? (
        <div id={bodyId} className="lg-team-group__body">
          <GroupBody
            group={group}
            run={run}
            current={Boolean(current)}
            expandedMembers={expandedMembers}
            onToggleMember={onToggleMember}
          />
        </div>
      ) : null}
    </article>
  )
}

function GroupBody({
  group,
  run,
  current,
  expandedMembers,
  onToggleMember,
}: {
  group: TeamGroup
  run: TeamGroupRun | null
  current: boolean
  expandedMembers: string[]
  onToggleMember: (memberId: string) => void
}) {
  const members = current ? historyMembers(group) : membersForHistory(group)
  const waiting = formatWaitingReason(run?.waiting_reason)
  return (
    <>
      {waiting ? <p className="lg-field__hint">Waiting: {waiting}</p> : null}
      {run?.fail_reason ? <p className="lg-field__hint">Failure: {run.fail_reason}</p> : null}
      {group.task.queue?.waiting_reason ? (
        <p className="lg-field__hint">
          Queue waiting: {formatWaitingReason(group.task.queue.waiting_reason)}
        </p>
      ) : null}
      <section className="lg-team-group__section" aria-label="Team members">
        <h4 className="lg-section__title">Members</h4>
        {members.length === 0 ? (
          <p className="lg-field__hint">
            {run ? 'No Member instances belong to this Run.' : 'No team members were created.'}
          </p>
        ) : (
          <ul className="lg-team-members">
            {members.map((member) => (
              <MemberRow
                key={member.id}
                group={group}
                member={member}
                expanded={expandedMembers.includes(member.id)}
                onToggle={() => onToggleMember(member.id)}
              />
            ))}
          </ul>
        )}
      </section>

      <details className="lg-team-group__section">
        <summary aria-label={`Details for ${group.task.title}`}>Details</summary>
        <section aria-label="Run facts">
          <h4 className="lg-section__title">Run</h4>
          <dl className="lg-kv">
            <dt>Task ID</dt>
            <dd><CopyableId label="Task ID" value={group.task.id} /></dd>
            {run ? (
              <>
                <dt>Run</dt>
                <dd>{runHeading(run, current)}</dd>
                <dt>Run ID</dt>
                <dd><CopyableId label="Run ID" value={run.id} /></dd>
                <dt>Attempt</dt>
                <dd>{run.attempt}</dd>
                <dt>Worker cleanup</dt>
                <dd>{run.cleanup?.status ?? 'not recorded'}</dd>
                <dt>Reviewer cleanup</dt>
                <dd>
                  {run.reviewer_cleanup
                    ? `${run.reviewer_cleanup.status ? `${run.reviewer_cleanup.status} · ` : ''}${
                        run.reviewer_cleanup.confirmed === true ? 'confirmed' : 'not confirmed'
                      }`
                    : 'No independent review session is recorded'}
                </dd>
              </>
            ) : null}
          </dl>
          {!run ? <p className="lg-field__hint">No Run is recorded for this Task yet.</p> : null}
        </section>
        {group.runs.length > 0 ? (
          <section className="lg-team-group__section" aria-label="Run history">
            <h4 className="lg-section__title">Runs</h4>
            <ul className="lg-team-runs">
              {[...group.runs]
                .sort((a, b) => a.attempt - b.attempt || a.id.localeCompare(b.id))
                .map((candidate) => (
                  <li key={candidate.id} className="lg-team-runs__item">
                    <span>
                      Run {candidate.attempt} · {candidate.state}
                      {candidate.id === run?.id ? ' · current view' : ''}
                    </span>
                    <CopyableId label={`Run ${candidate.attempt} ID`} value={candidate.id} />
                    <span className="lg-field__hint">
                      cleanup: {candidate.cleanup?.status ?? 'not recorded'}
                      {candidate.fail_reason ? ` · ${candidate.fail_reason}` : ''}
                    </span>
                  </li>
                ))}
            </ul>
          </section>
        ) : null}
      </details>
    </>
  )
}

/** History uses the last Run; Active uses the active Run member list. */
function membersForHistory(group: TeamGroup): TeamGroupMember[] {
  return historyMembers(group)
}

function MemberRow({
  group,
  member,
  expanded,
  onToggle,
}: {
  group: TeamGroup
  member: TeamGroupMember
  expanded: boolean
  onToggle: () => void
}) {
  const status = memberStatus(group, member)
  const subtasks = assignedSubtasks(group, member)
  const bodyId = `team-member-body-${safeDomId(member.id)}`
  return (
    <li className="lg-team-member" data-team-member={member.id}>
      <div className="lg-team-member__header">
        <div className="lg-team-member__identity">
          <h5 className="lg-team-member__role">{member.role_ref ?? 'Team member'}</h5>
        </div>
        <StatusBadge kind={status.kind} title={status.detail ?? status.label}>
          {status.label}
        </StatusBadge>
        <button
          type="button"
          className="lg-button"
          aria-expanded={expanded}
          aria-controls={bodyId}
          aria-label={`${expanded ? 'Hide' : 'Show'} details for ${member.role_ref ?? 'team member'}`}
          onClick={onToggle}
        >
          Details
        </button>
      </div>
      <p className="lg-team-member__assignment">
        <span className="lg-field__label">Assignment:</span>{' '}
        {subtasks.length > 0
          ? subtasks.map((subtask) => {
              const subtaskState = subtaskStatus(group, subtask)
              return `${subtask.key ?? subtask.id} — ${subtaskState.label}`
            }).join(' · ')
          : 'No assigned Subtasks'}
      </p>
      {expanded ? (
        <div id={bodyId} className="lg-team-member__body">
          <dl className="lg-kv">
            <dt>member</dt>
            <dd><CopyableId label="Member ID" value={member.id} /></dd>
            <dt>run</dt>
            <dd><CopyableId label="Member Run ID" value={member.run_ref} /></dd>
            <dt>member state</dt>
            <dd>{member.state ?? 'unknown'}</dd>
            <dt>template version</dt>
            <dd>{member.template_version ?? 'not recorded'}</dd>
            <dt>connection</dt>
            <dd>{member.connection_ref ?? 'default worker connection'}</dd>
            <dt>skills</dt>
            <dd>
              {member.skill_refs && member.skill_refs.length > 0
                ? member.skill_refs.join(', ')
                : 'none'}
            </dd>
            <dt>config hash</dt>
            <dd className="lg-card__path">{member.config_hash ?? 'not recorded'}</dd>
            {member.fail_reason ? (
              <>
                <dt>failure</dt>
                <dd>{member.fail_reason}</dd>
              </>
            ) : null}
          </dl>
          {subtasks.length > 0 ? (
            <ul className="lg-team-subtasks">
              {subtasks.map((subtask) => (
                <SubtaskRow key={subtask.id} group={group} subtask={subtask} />
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </li>
  )
}

function SubtaskRow({ group, subtask }: { group: TeamGroup; subtask: TeamGroupSubtask }) {
  const status = subtaskStatus(group, subtask)
  return (
    <li className="lg-team-subtask" data-subtask={subtask.id}>
      <div className="lg-team-subtask__head">
        <span className="lg-team-subtask__name">{subtask.key ?? subtask.id}</span>
        <StatusBadge kind={status.kind} title={status.detail ?? status.label}>
          {status.label}
        </StatusBadge>
      </div>
      <span className="lg-card__path">{subtask.id}</span>
      <span className="lg-field__hint">
        capability: {subtask.capability ?? 'not recorded'}
        {subtask.waiting_reason
          ? ` · waiting: ${formatWaitingReason(subtask.waiting_reason)}`
          : ''}
        {(subtask.depends_on?.length ?? 0) > 0
          ? ` · depends on: ${subtask.depends_on?.join(', ')}`
          : ''}
        {(subtask.blocked_by?.length ?? 0) > 0
          ? ` · blocked by: ${subtask.blocked_by?.join(', ')}`
          : ''}
        {subtask.acceptance?.status ? ` · acceptance: ${subtask.acceptance.status}` : ''}
        {subtask.fail_reason ? ` · failure: ${subtask.fail_reason}` : ''}
      </span>
    </li>
  )
}

/** Read-only text remains keyboard-selectable when clipboard access is unavailable. */
function CopyableId({ label, value }: { label: string; value: string }) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [feedback, setFeedback] = useState('')
  async function copy() {
    try {
      await navigator.clipboard.writeText(value)
      setFeedback('Copied')
    } catch {
      inputRef.current?.focus()
      inputRef.current?.select()
      setFeedback('Select and copy the ID with your keyboard or text menu.')
    }
  }
  return (
    <span>
      <input
        ref={inputRef}
        className="lg-input lg-card__path"
        aria-label={label}
        value={value}
        readOnly
        onFocus={(event) => event.currentTarget.select()}
      />
      <button type="button" className="lg-button" aria-label={`Copy ${label}`} onClick={() => void copy()}>
        Copy
      </button>
      <span className="lg-field__hint" role="status">{feedback}</span>
    </span>
  )
}
