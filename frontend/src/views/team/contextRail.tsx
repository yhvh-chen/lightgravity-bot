import { useEffect, useMemo, useState } from 'react'

import {
  createTeamApi,
  isReleased,
  type AvailableAgent,
  type TeamApi,
  type TeamMember,
} from '../../api/team'
import { useShell } from '../../app/ShellProvider'
import { ContextList, type ContextItem, type ContextSection } from '../../components/ContextList'
import type { StatusKind } from '../../components/StatusBadge'
import { availabilityBadge } from '../resources/availability'

export interface ContextRailProps {
  selectedId: string | null
  onSelect: (item: ContextItem) => void
  /** Injectable for tests; defaults to the real `/team/*` endpoints. */
  api?: TeamApi
}

function memberStatus(member: TeamMember): { kind: StatusKind; label: string } {
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
 * Data-driven Team secondary rail (docs/05 §5).
 *
 * Available = agent templates; Recruited = Member instances for the current
 * Task/Run with released members kept as history (never counted as current).
 * It reads the real `/team/*` endpoints, so no mock role/member list is shown.
 */
export function TeamContextRail({ selectedId, onSelect, api: injectedApi }: ContextRailProps) {
  const shell = useShell()
  const api = useMemo(() => injectedApi ?? createTeamApi(), [injectedApi])
  const taskRef = shell.state.taskRef
  const runRef = shell.state.runRef
  const [agents, setAgents] = useState<AvailableAgent[] | null>(null)
  const [members, setMembers] = useState<TeamMember[] | null>(null)
  const [error, setError] = useState<string | null>(null)

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
      .catch(() => {
        if (cancelled || controller.signal.aborted) return
        setAgents([])
        setMembers([])
        setError('Team is unavailable; showing no members (not faked).')
      })
    return () => {
      cancelled = true
      controller.abort()
    }
  }, [api, taskRef, runRef])

  const current = (members ?? []).filter((member) => !isReleased(member))
  const released = (members ?? []).filter(isReleased)

  const sections: ContextSection[] = [
    {
      id: 'team-available',
      title: 'Available',
      items: (agents ?? []).map((agent) => {
        const badge = availabilityBadge(agent.availability)
        return {
          id: `team:agent:${agent.id}`,
          label: agent.title,
          meta: agent.executable ? 'template · compiled' : 'template · declared only',
          status: { kind: badge.kind, label: badge.label },
        }
      }),
      empty:
        error ??
        (agents === null ? 'Loading role templates…' : 'No role templates loaded (LG-015).'),
    },
    {
      id: 'team-recruited',
      title: 'Recruited',
      items: [...current, ...released].map((member) => ({
        id: `team:member:${member.id}`,
        label: `${member.role_ref ?? member.title} · ${member.id}`,
        meta: isReleased(member)
          ? `released · ${member.run_ref ?? 'no run'}`
          : `${member.state ?? 'unknown'} · ${member.run_ref ?? 'no run'}`,
        status: memberStatus(member),
      })),
      empty:
        error ??
        (members === null
          ? 'Loading members…'
          : taskRef
            ? 'No members recruited for this Task.'
            : 'Select a Task to see its current team.'),
    },
  ]

  return (
    <ContextList
      sections={sections}
      selectedId={selectedId}
      onSelect={onSelect}
      ariaLabel="Team recruitment"
    />
  )
}
