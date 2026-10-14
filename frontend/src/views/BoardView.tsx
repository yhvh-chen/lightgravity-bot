import { PlaceholderView } from './PlaceholderView'

/**
 * Board view (owner: LG-013). LG-011 only mounts it; the Task/Run board and
 * phase/queue rendering belong to LG-013 per docs/08 §11.
 */
export function BoardView() {
  return (
    <PlaceholderView
      viewId="board"
      ownerTask="LG-013"
      title="Board"
      summary="Task cards, phase/queue state and Run/Subtask detail are not implemented in the shell."
      planned={[
        'Task list reading GET /api/v1/tasks',
        'phase/status badges with pending/failed reasons',
        'Run and Subtask expansion from the same task_ref',
      ]}
    />
  )
}
