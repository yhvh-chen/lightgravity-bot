import { useEffect, useMemo, useState } from 'react'

import { createTaskApi, type TaskApi } from '../../api/tasks'
import type { TaskSummary } from '../../api/types'
import { useShell } from '../../app/ShellProvider'
import { ContextList, type ContextItem, type ContextSection } from '../../components/ContextList'
import type { ViewContextProps } from '../registry'
import { phaseBadge } from '../board/phase'

export interface TaskRailProps extends ViewContextProps {
  /** Injectable for tests; defaults to the real `/tasks` endpoint. */
  api?: TaskApi
}

/**
 * Shared data-driven Task history rail (LG-013).
 *
 * Reads the real Task list (no mock) and lets selecting one scope Chat/Board to
 * that `task_ref`. The backend is the fact source; when it is empty or
 * unavailable the rail says so instead of showing invented tasks.
 */
export function TaskRail({ selectedId, onSelect, api: injectedApi }: TaskRailProps) {
  const shell = useShell()
  const api = useMemo(() => injectedApi ?? createTaskApi(), [injectedApi])
  const [tasks, setTasks] = useState<TaskSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    const controller = new AbortController()
    setError(null)
    api
      .listTasks({ limit: 100 }, controller.signal)
      .then((page) => {
        if (cancelled) return
        setTasks(page.items)
      })
      .catch(() => {
        if (cancelled || controller.signal.aborted) return
        setTasks([])
        setError('Task list unavailable from the backend; showing no tasks (not faked).')
      })
    return () => {
      cancelled = true
      controller.abort()
    }
  }, [api])

  const sections: ContextSection[] = [
    {
      id: 'task-history',
      title: 'Tasks',
      items: (tasks ?? []).map<ContextItem>((task) => {
        const badge = phaseBadge(task.phase)
        return {
          id: task.id,
          label: task.title,
          meta: `phase: ${task.phase}`,
          status: { kind: badge.kind, label: badge.label },
          taskRef: task.id,
        }
      }),
      empty: error ?? 'No tasks yet. Describe a goal in Chat to create one.',
    },
  ]

  return (
    <ContextList
      sections={sections}
      selectedId={selectedId ?? shell.state.taskRef}
      onSelect={(item) => onSelect(item)}
      ariaLabel="Task scope"
      header={
        <button
          type="button"
          className="lg-button"
          onClick={() => shell.dispatch({ type: 'selectTask', taskRef: null })}
        >
          Global scope
        </button>
      }
    />
  )
}
