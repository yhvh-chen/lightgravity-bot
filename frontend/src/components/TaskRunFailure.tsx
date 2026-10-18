import { useCallback, useEffect, useState } from 'react'
import { taskApi, type TaskApi } from '../api/tasks'
import type { TaskDetail } from '../api/types'
import { useBoardAutoRefresh } from '../views/board/useBoard'

/** Current server facts in the Task conversation, never a fabricated message. */
export function TaskRunFailure({ taskRef, api = taskApi }: { taskRef: string; api?: TaskApi }) {
  const [detail, setDetail] = useState<TaskDetail | null>(null)
  const [reload, setReload] = useState(0)
  const refresh = useCallback(() => setReload((value) => value + 1), [])
  useBoardAutoRefresh({ onRefresh: refresh })
  useEffect(() => {
    const controller = new AbortController()
    api.getTask(taskRef, controller.signal).then((value) => {
      if (!controller.signal.aborted && value.task_id === taskRef) setDetail(value)
    }).catch(() => { /* Keep the last read fact; never invent a failure reason. */ })
    return () => controller.abort()
  }, [api, taskRef, reload])
  if (detail?.task_id !== taskRef || (detail.phase !== 'failed' && detail.run?.state !== 'failed')) return null
  return <p className="lg-notice lg-notice--error" role="status">
    {detail.run ? `Run ${detail.run.id} failed: ` : 'Task failed: '}
    {detail.run?.fail_reason || 'No failure reason was recorded.'}
  </p>
}
