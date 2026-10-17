import { useEffect, useMemo, useState } from 'react'

import type { AvailableAgent } from '../../api/team'
import { EmptyState } from '../../components/EmptyState'
import { StatusBadge, type StatusKind } from '../../components/StatusBadge'
import { availabilityBadge } from '../resources/availability'

export interface AvailablePanelProps {
  agents: AvailableAgent[]
  selectedId: string | null
  onSelect: (id: string) => void
  pageSize?: number
}

interface RoleBadge {
  kind: StatusKind
  label: string
  title: string
}

/**
 * Genuine role state, not a live-health claim:
 * unsupported mapping and disabled/invalid are distinct from a template that
 * only lacks the current worker connection to become executable.
 */
export function roleBadge(agent: AvailableAgent): RoleBadge {
  if (
    agent.recruitable === undefined &&
    !agent.role_category &&
    !agent.agency_source
  ) {
    // Older backend without LG-120 metadata: keep the existing honest label.
    return availabilityBadge(agent.availability)
  }
  const firstReason = agent.availability.reasons[0] ?? ''
  if (agent.availability.state === 'disabled') {
    return { kind: 'neutral', label: 'disabled', title: firstReason || 'enabled=false' }
  }
  if (agent.availability.state === 'invalid') {
    return { kind: 'error', label: 'invalid', title: firstReason || 'Invalid configuration.' }
  }
  if (agent.recruitable === false) {
    const reason = agent.unsupported_reasons?.[0] ?? firstReason
    return {
      kind: 'warning',
      label: 'unsupported',
      title: reason || 'No executable scheduler capability mapping.',
    }
  }
  switch (agent.availability.state) {
    case 'missing_dependency':
      return {
        kind: 'warning',
        label: 'needs setup',
        title: firstReason || 'A referenced connection/resource is not available yet.',
      }
    case 'unsupported':
      return { kind: 'warning', label: 'unsupported', title: firstReason || 'Unsupported here.' }
    case 'unknown':
      return agent.executable || agent.recruitable
        ? {
            kind: 'success',
            label: 'executable',
            title: 'Configuration compiles; a live session was not started.',
          }
        : { kind: 'neutral', label: 'health unknown', title: firstReason }
    default:
      return {
        kind: 'neutral',
        label: agent.availability.state,
        title: firstReason || agent.availability.state,
      }
  }
}

function matches(agent: AvailableAgent, query: string): boolean {
  if (!query) return true
  return [
    agent.title,
    agent.id,
    agent.summary ?? '',
    agent.role_category ?? '',
    ...(agent.capabilities ?? []),
  ]
    .join(' ')
    .toLowerCase()
    .includes(query)
}

/**
 * Complete role library browser (LG-120, docs/13 §2).
 *
 * Search, category/capability filters and pagination only control this page;
 * they never change task_ref or start a worker.  A template card is not an
 * active member and does not consume execution capacity.
 */
export function AvailablePanel({
  agents,
  selectedId,
  onSelect,
  pageSize = 24,
}: AvailablePanelProps) {
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState('all')
  const [capability, setCapability] = useState('all')
  const [page, setPage] = useState(1)

  const categories = useMemo(
    () => Array.from(new Set(agents.map((agent) => agent.role_category || 'custom'))).sort(),
    [agents],
  )
  const capabilities = useMemo(
    () =>
      Array.from(new Set(agents.flatMap((agent) => agent.capabilities ?? []))).sort(),
    [agents],
  )
  const query = search.trim().toLowerCase()
  const filtered = useMemo(
    () =>
      agents.filter(
        (agent) =>
          matches(agent, query) &&
          (category === 'all' || (agent.role_category || 'custom') === category) &&
          (capability === 'all' || (agent.capabilities ?? []).includes(capability)),
      ),
    [agents, capability, category, query],
  )
  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize))
  const currentPage = Math.min(page, totalPages)
  const pageItems = filtered.slice((currentPage - 1) * pageSize, currentPage * pageSize)

  useEffect(() => {
    setPage(1)
  }, [query, category, capability])

  return (
    <div className="lg-team__available">
      <div className="lg-team__toolbar" role="search" aria-label="Filter available roles">
        <label className="lg-field lg-team__search">
          <span className="lg-field__label">Search roles</span>
          <input
            type="search"
            value={search}
            placeholder="Name, capability, or keyword"
            onChange={(event) => setSearch(event.target.value)}
          />
        </label>
        <label className="lg-field lg-team__filter">
          <span className="lg-field__label">Category</span>
          <select value={category} onChange={(event) => setCategory(event.target.value)}>
            <option value="all">All categories</option>
            {categories.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>
        <label className="lg-field lg-team__filter">
          <span className="lg-field__label">Capability</span>
          <select value={capability} onChange={(event) => setCapability(event.target.value)}>
            <option value="all">All capabilities</option>
            {capabilities.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>
        <p className="lg-field__hint lg-team__count" role="status">
          {filtered.length} of {agents.length} role templates
        </p>
      </div>

      {filtered.length === 0 ? (
        <EmptyState title="No roles match">
          <p>Clear the search or choose another category/capability.</p>
        </EmptyState>
      ) : (
        <>
          <ul className="lg-team__items lg-team__items--roles" aria-label="Available role templates">
            {pageItems.map((agent) => {
              const badge = roleBadge(agent)
              return (
                <li key={agent.id}>
                  <button
                    type="button"
                    className={`lg-card lg-card--interactive lg-role-card${
                      selectedId === agent.id ? ' lg-role-card--selected' : ''
                    }`}
                    aria-pressed={selectedId === agent.id}
                    onClick={() => onSelect(agent.id)}
                  >
                    <div className="lg-card__head">
                      <h3 className="lg-card__title">{agent.title}</h3>
                      <StatusBadge kind={badge.kind} title={badge.title}>
                        {badge.label}
                      </StatusBadge>
                    </div>
                    <p className="lg-role-card__summary">
                      {agent.summary || 'No upstream summary recorded.'}
                    </p>
                    <div className="lg-role-card__meta">
                      <span className="lg-card__path">{agent.role_category ?? 'custom'}</span>
                      {(agent.capabilities ?? []).map((item) => (
                        <span key={item} className="lg-role-card__capability">
                          {item}
                        </span>
                      ))}
                    </div>
                    <span className="lg-card__path">{agent.id}</span>
                  </button>
                </li>
              )
            })}
          </ul>
          <nav className="lg-team__pager" aria-label="Available role pages">
            <button
              type="button"
              className="lg-button"
              disabled={currentPage <= 1}
              onClick={() => setPage((value) => Math.max(1, value - 1))}
            >
              Previous
            </button>
            <span className="lg-field__hint" role="status">
              Page {currentPage} of {totalPages}
            </span>
            <button
              type="button"
              className="lg-button"
              disabled={currentPage >= totalPages}
              onClick={() => setPage((value) => Math.min(totalPages, value + 1))}
            >
              Next
            </button>
          </nav>
        </>
      )}
    </div>
  )
}
