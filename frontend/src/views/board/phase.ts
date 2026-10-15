import type { StatusKind } from '../../components/StatusBadge'
import type { TaskPhase } from '../../api/types'

export interface PhaseBadge {
  kind: StatusKind
  label: string
  /** Short reason shown with the badge (e.g. failed/paused), never color-only. */
  detail?: string
}

/**
 * Map a real Task phase to a badge (docs/08 §6.1, design.md §4).
 *
 * A cancelled/failed/paused Task is never shown as running. `failed` and
 * `recovery_required` are errors; `cancelling`/`pausing` are pending, not
 * terminal; only `executing`/`planning`/`recruiting`/`verifying`/`repairing`
 * read as active work.
 */
export function phaseBadge(phase: TaskPhase | string): PhaseBadge {
  switch (phase) {
    case 'intake':
      return { kind: 'neutral', label: 'intake' }
    case 'queued':
      return { kind: 'neutral', label: 'queued' }
    case 'waiting_dependencies':
      return { kind: 'warning', label: 'waiting deps', detail: 'blocked on an upstream Subtask' }
    case 'planning':
      return { kind: 'accent', label: 'planning' }
    case 'recruiting':
      return { kind: 'accent', label: 'recruiting' }
    case 'executing':
      return { kind: 'accent', label: 'executing' }
    case 'verifying':
      return { kind: 'accent', label: 'verifying' }
    case 'repairing':
      return { kind: 'accent', label: 'repairing' }
    case 'waiting_user':
      return { kind: 'warning', label: 'waiting user' }
    case 'pausing':
      return { kind: 'warning', label: 'pausing…', detail: 'stop not yet confirmed' }
    case 'paused':
      return { kind: 'warning', label: 'paused' }
    case 'cancelling':
      return { kind: 'warning', label: 'cancelling…', detail: 'stop not yet confirmed' }
    case 'awaiting_acceptance':
      return { kind: 'warning', label: 'awaiting acceptance' }
    case 'recovery_required':
      return { kind: 'error', label: 'recovery required' }
    case 'failed':
      return { kind: 'error', label: 'failed' }
    case 'cancelled':
      return { kind: 'neutral', label: 'cancelled' }
    case 'completed':
      return { kind: 'success', label: 'completed' }
    default:
      return { kind: 'neutral', label: String(phase) }
  }
}

/** Phases where the Task is doing real work (used for honest "active" counts). */
export function isActivePhase(phase: TaskPhase | string): boolean {
  return ['planning', 'recruiting', 'executing', 'verifying', 'repairing'].includes(phase)
}

/** Phases that are non-terminal but not actively working. */
export function isPendingPhase(phase: TaskPhase | string): boolean {
  return ['pausing', 'cancelling', 'queued', 'waiting_dependencies', 'waiting_user'].includes(phase)
}
