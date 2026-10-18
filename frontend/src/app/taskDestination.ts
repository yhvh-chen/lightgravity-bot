/**
 * Explicit Task destination (LG-220).
 *
 * Notification and Chat entry points need to open one *existing* Task without
 * dropping its Run or resetting the single Bot Chat.  `selectTask` alone keeps
 * the current view and clears `run_ref`, so callers that must move views use
 * this helper instead:
 *
 * ```ts
 * dispatch(openTaskDestination({ taskRef, runRef, view: 'tasks' }))
 * ```
 *
 * The reducer applies the view/task/run/item atomically and preserves chat
 * visibility, channel and drafts. Business state is still re-read from the
 * backend; this helper only carries navigation identity.
 */
import type { ViewId } from './navigation'
import type { ShellAction } from './uiState'

export interface TaskDestination {
  /** Stable server Task id (`task_...`), never a display title or folder name. */
  taskRef: string
  /** Exact Run to return to; `null`/omitted opens the Task without a Run. */
  runRef?: string | null
  /** Destination view. Defaults to the Tasks workspace. */
  view?: ViewId
  /** Optional view-specific selection (for example a Settings connection). */
  itemRef?: string | null
}

/** Build the atomic shell action for an explicit Task destination. */
export function openTaskDestination(destination: TaskDestination): ShellAction {
  return {
    type: 'openTaskDestination',
    view: destination.view ?? 'tasks',
    taskRef: destination.taskRef,
    runRef: destination.runRef ?? null,
    itemRef: destination.itemRef ?? null,
  }
}
