import type { ResourceAvailability } from '../../api/resources'
import type { StatusKind } from '../../components/StatusBadge'

export interface AvailabilityBadge {
  kind: StatusKind
  label: string
  title: string
}

/**
 * Map the backend availability state to a visible badge.  "Unknown" is a
 * warning, never a green success: declared + parsed is not a live health check
 * (docs/05 §6.1, design.md §5).
 */
const MAP: Record<string, AvailabilityBadge> = {
  unknown: {
    kind: 'warning',
    label: 'health unknown',
    title: 'Declared and parsed; no live check was run.',
  },
  disabled: {
    kind: 'neutral',
    label: 'disabled',
    title: 'Declared enabled=false; it will not be used.',
  },
  unsupported: {
    kind: 'warning',
    label: 'unsupported',
    title: 'Not attachable/registered in this version.',
  },
  missing_dependency: {
    kind: 'error',
    label: 'missing dependency',
    title: 'A referenced resource does not resolve.',
  },
  invalid: {
    kind: 'error',
    label: 'invalid',
    title: 'Frontmatter failed validation.',
  },
  available: {
    kind: 'success',
    label: 'available',
    title: 'A live check succeeded.',
  },
}

export function availabilityBadge(
  availability?: ResourceAvailability | null,
): AvailabilityBadge {
  const state = availability?.state ?? 'unknown'
  const base =
    MAP[state] ?? {
      kind: 'neutral' as StatusKind,
      label: state,
      title: state,
    }
  const reason = availability?.reasons?.[0]
  return reason ? { ...base, title: `${base.title} ${reason}` } : base
}
