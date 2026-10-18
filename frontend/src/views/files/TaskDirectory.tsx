import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { chatApi, newRuntimeId, type ChatApi } from '../../api/chat'
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
  /** Injectable POST /tasks helper (tests); defaults to the existing Chat API helper. */
  createTask?: ChatApi['createTask']
}

function focusableElements(root: HTMLElement | null): HTMLElement[] {
  if (!root) return []
  const selector =
    'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
  return Array.from(root.querySelectorAll<HTMLElement>(selector)).filter(
    (element) => element.getAttribute('aria-hidden') !== 'true',
  )
}

/**
 * Logical task directories from the task store, never guessed from a file path.
 *
 * LG-202: General is pinned first and always present; it is the global
 * conversation with no Task scope. The real Task list follows. Selecting a
 * Task opens its workspace and binds the right Bot Chat to the same task_ref.
 */
export function TaskDirectory({ onOpen, activeTaskRef = null, api: injectedApi, createTask }: TaskDirectoryProps) {
  const api = useMemo(() => injectedApi ?? createTaskApi(), [injectedApi])
  const [tasks, setTasks] = useState<TaskSummary[] | null>(null)
  const [cursor, setCursor] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [opening, setOpening] = useState<string | null>(null)
  const [reload, setReload] = useState(0)
  const [createOpen, setCreateOpen] = useState(false)
  const [newTitle, setNewTitle] = useState('')
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)
  const openRequest = useRef<AbortController | null>(null)
  const createRequestId = useRef('')
  const createTrigger = useRef<HTMLButtonElement>(null)
  const createDialog = useRef<HTMLDivElement>(null)
  const createInput = useRef<HTMLInputElement>(null)
  const mounted = useRef(true)
  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false; openRequest.current?.abort() }
  }, [])
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError(null)
    api.listTasks({ limit: 100 }, controller.signal).then(async (page) => {
      if (controller.signal.aborted) return
      let items = page.items
      // Chat-created Tasks may be newer than this mounted list, or beyond its
      // first page. Fetch the selected real Task rather than inventing a row.
      if (activeTaskRef && !items.some((task) => task.id === activeTaskRef)) {
        const selected = await api.getTask(activeTaskRef, controller.signal)
        if (controller.signal.aborted) return
        if (selected.id !== activeTaskRef) throw new Error('The task identity changed. Refresh the task directory.')
        items = [...items, selected]
      }
      if (controller.signal.aborted) return
      setTasks(items)
      setCursor(page.next_cursor)
    }).catch((cause: unknown) => {
      if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'Cannot load tasks')
    }).finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [api, reload, activeTaskRef])
  const loadMore = async () => {
    if (!cursor) return
    setLoading(true)
    try {
      const page = await api.listTasks({ limit: 100, cursor })
      if (!mounted.current) return
      setTasks((current) => Array.from(new Map([...(current ?? []), ...page.items].map((task) => [task.id, task])).values()))
      setCursor(page.next_cursor)
      setError(null)
    } catch (cause) {
      if (mounted.current) setError(cause instanceof Error ? cause.message : 'Cannot load tasks')
    } finally { if (mounted.current) setLoading(false) }
  }
  const openGeneral = () => {
    // General must win over an in-flight Task verification: abort it so a late
    // response cannot select a Task after the user returned to Global.
    openRequest.current?.abort()
    openRequest.current = null
    setOpening(null)
    setError(null)
    onOpen(null)
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

  const openCreate = () => {
    createRequestId.current = newRuntimeId('request')
    setNewTitle('')
    setCreateError(null)
    setCreateOpen(true)
  }

  useEffect(() => {
    if (!createOpen) return
    createInput.current?.focus()
  }, [createOpen])

  const closeCreate = () => {
    if (creating) return
    setCreateOpen(false)
    setCreateError(null)
    createTrigger.current?.focus()
  }

  const submitCreate = async (event: FormEvent) => {
    event.preventDefault()
    const title = newTitle.trim()
    if (!title) {
      setCreateError('Enter a task title.')
      createInput.current?.focus()
      return
    }
    if (!createRequestId.current) createRequestId.current = newRuntimeId('request')
    setCreating(true)
    setCreateError(null)
    try {
      const result = await (createTask ?? chatApi.createTask)({
        request_id: createRequestId.current,
        title,
        objective: title,
      })
      const created = result.task_id ?? result.id ?? null
      if (!created) throw new Error('The server did not return the created Task id.')
      if (!mounted.current) return
      setCreateOpen(false)
      setNewTitle('')
      setReload((value) => value + 1)
      onOpen(created)
    } catch (cause) {
      if (!mounted.current) return
      setCreateError(cause instanceof Error ? cause.message : 'Cannot create task')
    } finally {
      if (mounted.current) setCreating(false)
    }
  }
  return (
    <section className="lg-task-directory" aria-label="Task directories">
      <div className="lg-task-directory__head">
        <div className="lg-task-directory__head-row">
          <h2 className="lg-files__section-title">Tasks</h2>
          <button
            ref={createTrigger}
            type="button"
            className="lg-button lg-button--primary"
            onClick={openCreate}
          >
            New task
          </button>
        </div>
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
        onClick={openGeneral}
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
      {createOpen ? (
        <div
          className="lg-modal-backdrop lg-new-task-backdrop"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) closeCreate()
          }}
        >
          <div
            ref={createDialog}
            className="lg-modal lg-new-task"
            role="dialog"
            aria-modal="true"
            aria-labelledby="lg-new-task-title"
            tabIndex={-1}
            onKeyDown={(event) => {
              if (event.key === 'Escape') {
                event.preventDefault()
                closeCreate()
                return
              }
              if (event.key !== 'Tab') return
              const nodes = focusableElements(createDialog.current)
              if (nodes.length === 0) {
                event.preventDefault()
                createDialog.current?.focus()
                return
              }
              const first = nodes[0]
              const last = nodes[nodes.length - 1]
              const active = document.activeElement
              if (event.shiftKey && (active === first || !createDialog.current?.contains(active))) {
                event.preventDefault()
                last.focus()
              } else if (!event.shiftKey && active === last) {
                event.preventDefault()
                first.focus()
              }
            }}
          >
            <form onSubmit={(event) => void submitCreate(event)}>
              <header className="lg-modal__header">
                <h2 id="lg-new-task-title" className="lg-modal__title">New task</h2>
                <button
                  type="button"
                  className="lg-button lg-modal__close"
                  aria-label="Close new task dialog"
                  onClick={closeCreate}
                  disabled={creating}
                >
                  ×
                </button>
              </header>
              <div className="lg-modal__body">
                <label className="lg-field">
                  <span className="lg-field__label">Task title</span>
                  <input
                    ref={createInput}
                    className="lg-input"
                    value={newTitle}
                    onChange={(event) => {
                      setNewTitle(event.target.value)
                      // A changed title is a new create request, never a replay
                      // of an earlier idempotency key.
                      createRequestId.current = newRuntimeId('request')
                      if (createError) setCreateError(null)
                    }}
                    disabled={creating}
                    autoComplete="off"
                  />
                </label>
                <p className="lg-field__hint">
                  The backend creates the real Task directory and default workspace; the title is
                  also the objective.
                </p>
                {createError ? (
                  <p className="lg-notice lg-notice--error" role="alert">
                    Create failed: {createError}
                  </p>
                ) : null}
              </div>
              <footer className="lg-modal__footer">
                <button type="button" className="lg-button" onClick={closeCreate} disabled={creating}>
                  Cancel
                </button>
                <button type="submit" className="lg-button lg-button--primary" disabled={creating}>
                  {creating ? 'Creating…' : 'Create task'}
                </button>
              </footer>
            </form>
          </div>
        </div>
      ) : null}
    </section>
  )
}
