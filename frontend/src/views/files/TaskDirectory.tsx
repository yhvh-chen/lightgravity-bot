import { useEffect, useMemo, useRef, useState } from 'react'
import { createTaskApi, type TaskApi } from '../../api/tasks'
import type { TaskSummary } from '../../api/types'
import { ErrorState } from '../../components/ErrorState'
import { EmptyState } from '../../components/EmptyState'

export interface TaskDirectoryProps {
  /** `null` selects the fixed General entry (the global conversation). */
  onOpen: (taskRef: string | null) => void
  /** Active Task from the shell, used only for the selected state. */
  activeTaskRef?: string | null
  api?: TaskApi
}

/**
 * Logical task directories from the task store, never guessed from a file path.
 *
 * LG-202: General is pinned first and always present; it is the global
 * conversation with no Task scope. The real Task list follows. Selecting a
 * Task opens its workspace and binds the right Bot Chat to the same task_ref.
 */
export function TaskDirectory({ onOpen, activeTaskRef = null, api: injectedApi }: TaskDirectoryProps) {
  const api = useMemo(() => injectedApi ?? createTaskApi(), [injectedApi])
  const [tasks, setTasks] = useState<TaskSummary[] | null>(null)
  const [cursor, setCursor] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [opening, setOpening] = useState<string | null>(null)
  const [reload, setReload] = useState(0)
  const openRequest = useRef<AbortController | null>(null)
  const mounted = useRef(true)
  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false; openRequest.current?.abort() }
  }, [])
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError(null)
    api.listTasks({ limit: 100 }, controller.signal).then((page) => {
      if (controller.signal.aborted) return
      setTasks(page.items)
      setCursor(page.next_cursor)
    }).catch((cause: unknown) => {
      if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'Cannot load tasks')
    }).finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [api, reload])
  const loadMore = async () => {
    if (!cursor) return
    setLoading(true)
    try {
      const page = await api.listTasks({ limit: 100, cursor })
      if (!mounted.current) return
      setTasks((current) => [...(current ?? []), ...page.items])
      setCursor(page.next_cursor)
      setError(null)
    } catch (cause) {
      if (mounted.current) setError(cause instanceof Error ? cause.message : 'Cannot load tasks')
    } finally { if (mounted.current) setLoading(false) }
  }
  const open = async (taskRef: string) => {
    openRequest.current?.abort()
    const controller = new AbortController()
    openRequest.current = controller
    setOpening(taskRef)
    setError(null)
    try {
      const task = await api.getTask(taskRef, controller.signal)
      if (controller.signal.aborted || !mounted.current) return
      if (task.id !== taskRef) throw new Error('The task identity changed. Refresh the task directory.')
      onOpen(task.id)
    } catch (cause) {
      if (!controller.signal.aborted && mounted.current) setError(cause instanceof Error ? cause.message : 'Cannot open task')
    } finally { if (!controller.signal.aborted && mounted.current) setOpening(null) }
  }
  return (
    <section className="lg-task-directory" aria-label="Task directories">
      <div className="lg-task-directory__head">
        <h2 className="lg-files__section-title">Tasks</h2>
        <p className="lg-field__hint">
          General is the global conversation. Choose a task directory to open its workspace;
          workspace folders remain files.
        </p>
      </div>
      <button
        type="button"
        className="lg-button lg-task-directory__general"
        aria-current={activeTaskRef ? undefined : 'page'}
        title="Global conversation without a Task scope"
        onClick={() => onOpen(null)}
      >
        <span aria-hidden="true">▸</span> General
      </button>
      <div className="lg-task-directory__tasks">
        <h3 className="lg-task-directory__title">Task directories</h3>
        {error ? <ErrorState title="Task directory unavailable" message={error} retryable onRetry={() => setReload(reload + 1)} /> : null}
        {!tasks && loading ? <p role="status">Loading tasks…</p> : null}
        {tasks?.length === 0 ? <EmptyState title="No tasks yet" compact>Create a task by describing a goal in Chat.</EmptyState> : null}
        <ul className="lg-task-directory__list" aria-label="Task list">
          {tasks?.map((task) => <li key={task.id}><button
            type="button"
            className="lg-button"
            disabled={opening !== null}
            aria-current={activeTaskRef === task.id ? 'page' : undefined}
            onClick={() => void open(task.id)}
            title={task.id}
          >
            <span aria-hidden="true">▸</span> {task.title} / <small>{task.archived ? 'archived' : task.phase}</small>{opening === task.id ? ' · Opening…' : ''}
          </button></li>)}
        </ul>
        {cursor ? <button type="button" className="lg-button" disabled={loading} onClick={() => void loadMore()}>More tasks</button> : null}
      </div>
    </section>
  )
}
