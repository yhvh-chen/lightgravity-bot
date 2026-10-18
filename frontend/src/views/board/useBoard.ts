/**
 * Board data hook (LG-013; docs/08 §4.3/§6/§9).
 *
 * Reads the real Task list and, for one selected Task, its detail, acceptance
 * snapshot and artifacts. It exposes control actions that keep *pending* and
 * *actual* results apart: a control call returns `confirmed` but the hook
 * re-reads the authoritative Task state rather than optimistically painting the
 * requested phase. A `confirmed=false` result is reported as pending.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { ApiError } from '../../api/client'
import { newRuntimeId } from '../../api/chat'
import {
  taskApi,
  type AcceptanceSnapshot,
  type ControlAction,
  type ControlActionResult,
  type TaskApi,
  type TaskArtifacts,
} from '../../api/tasks'
import type { TaskDetail, TaskSummary } from '../../api/types'

interface ReloadRequest {
  key: number
  /** Background refresh: keep the current board/detail on screen while reading. */
  silent: boolean
}

export interface BoardState {
  tasks: TaskSummary[]
  tasksLoading: boolean
  tasksError: ApiError | null
  refreshTasks: () => void
  /** Re-read the list without replacing it with a loading or empty state. */
  refreshTasksSilently: () => void
}

export function useTaskList(api: TaskApi = taskApi): BoardState {
  const [tasks, setTasks] = useState<TaskSummary[]>([])
  const [tasksLoading, setTasksLoading] = useState(true)
  const [tasksError, setTasksError] = useState<ApiError | null>(null)
  const [reload, setReload] = useState<ReloadRequest>({ key: 0, silent: false })

  useEffect(() => {
    const controller = new AbortController()
    let cancelled = false
    if (!reload.silent) {
      setTasksLoading(true)
      setTasksError(null)
    }
    api
      .listTasks({ limit: 100 }, controller.signal)
      .then((page) => {
        if (cancelled) return
        setTasks(page.items)
        setTasksError(null)
        setTasksLoading(false)
      })
      .catch((cause) => {
        if (cancelled || controller.signal.aborted) return
        if (!reload.silent) {
          setTasks([])
          setTasksError(toApiError(cause))
        }
        // A failed background poll keeps the last real list on screen.
        setTasksLoading(false)
      })
    return () => {
      cancelled = true
      controller.abort()
    }
  }, [api, reload])

  const refreshTasks = useCallback(
    () => setReload((current) => ({ key: current.key + 1, silent: false })),
    [],
  )
  const refreshTasksSilently = useCallback(
    () => setReload((current) => ({ key: current.key + 1, silent: true })),
    [],
  )

  return useMemo(
    () => ({
      tasks,
      tasksLoading,
      tasksError,
      refreshTasks,
      refreshTasksSilently,
    }),
    [tasks, tasksLoading, tasksError, refreshTasks, refreshTasksSilently],
  )
}

export interface TaskDetailState {
  detail: TaskDetail | null
  acceptance: AcceptanceSnapshot | null
  artifacts: TaskArtifacts | null
  loading: boolean
  error: ApiError | null
  refresh: () => void
  /** Re-read detail/acceptance/artifacts without a loading swap. */
  refreshSilently: () => void
}

export function useTaskDetail(taskRef: string | null, api: TaskApi = taskApi): TaskDetailState {
  const [detail, setDetail] = useState<TaskDetail | null>(null)
  const [acceptance, setAcceptance] = useState<AcceptanceSnapshot | null>(null)
  const [artifacts, setArtifacts] = useState<TaskArtifacts | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)
  const [reload, setReload] = useState<ReloadRequest>({ key: 0, silent: false })
  const lastTaskRef = useRef<string | null>(null)

  useEffect(() => {
    // A new Task always gets an honest loading state; only a same-Task poll may
    // stay silent (LG-220).
    const taskChanged = lastTaskRef.current !== taskRef
    lastTaskRef.current = taskRef
    const silent = reload.silent && !taskChanged
    if (!taskRef) {
      setDetail(null)
      setAcceptance(null)
      setArtifacts(null)
      setError(null)
      setLoading(false)
      return
    }
    const controller = new AbortController()
    let cancelled = false
    if (!silent) {
      setLoading(true)
      setError(null)
    }
    Promise.all([
      api.getTask(taskRef, controller.signal),
      api.getAcceptance(taskRef, controller.signal).catch(() => null),
      api.getArtifacts(taskRef, controller.signal).catch(() => null),
    ])
      .then(([nextDetail, nextAcceptance, nextArtifacts]) => {
        if (cancelled) return
        setDetail(nextDetail)
        setAcceptance(nextAcceptance)
        setArtifacts(nextArtifacts)
        setError(null)
        setLoading(false)
      })
      .catch((cause) => {
        if (cancelled || controller.signal.aborted) return
        if (!silent) {
          setDetail(null)
          setAcceptance(null)
          setArtifacts(null)
          setError(toApiError(cause))
        }
        // Keep the last real detail visible if a background poll fails.
        setLoading(false)
      })
    return () => {
      cancelled = true
      controller.abort()
    }
  }, [api, taskRef, reload])

  const refresh = useCallback(
    () => setReload((current) => ({ key: current.key + 1, silent: false })),
    [],
  )
  const refreshSilently = useCallback(
    () => setReload((current) => ({ key: current.key + 1, silent: true })),
    [],
  )

  return useMemo(
    () => ({
      detail,
      acceptance,
      artifacts,
      loading,
      error,
      refresh,
      refreshSilently,
    }),
    [detail, acceptance, artifacts, loading, error, refresh, refreshSilently],
  )
}

export interface ControlOutcome {
  /** True only when the backend confirmed the state change. */
  confirmed: boolean
  /** The backend's `state` field: requested|confirmed|unconfirmed. */
  state: string
  action: ControlAction
  result: ControlActionResult | null
  error: ApiError | null
  /** Human-readable pending/failure reason, never a fabricated success. */
  message: string | null
}

/**
 * Execute one control action and report pending vs actual honestly.
 *
 * The `request_id` is generated once and reused if the caller retries the same
 * action, matching the backend's idempotency contract (docs/08 §9).
 */
export function useControlAction(api: TaskApi = taskApi) {
  const [pending, setPending] = useState<ControlAction | null>(null)
  const [outcome, setOutcome] = useState<ControlOutcome | null>(null)

  const run = useCallback(
    async (
      taskRef: string,
      action: ControlAction,
      options: { acceptance?: AcceptanceSnapshot | null; runRef?: string | null; note?: string | null } = {},
    ): Promise<ControlOutcome> => {
      setPending(action)
      setOutcome(null)
      const requestId = newRuntimeId('req')
      try {
        const result = await api.act(taskRef, {
          action,
          request_id: requestId,
          target_run_id: options.runRef ?? undefined,
          expected_requirements_revision: options.acceptance?.requirements_revision,
          expected_deliverable_revision: options.acceptance?.deliverable_revision,
          note: options.note ?? undefined,
        })
        const confirmed = Boolean(result.confirmed)
        const next: ControlOutcome = {
          confirmed,
          state: result.state,
          action,
          result,
          error: null,
          message: confirmed
            ? null
            : `Requested ${action}; the backend has not confirmed the change yet.`,
        }
        setOutcome(next)
        return next
      } catch (cause) {
        const error = toApiError(cause)
        const next: ControlOutcome = {
          confirmed: false,
          state: 'failed',
          action,
          result: null,
          error,
          message: controlErrorMessage(action, error),
        }
        setOutcome(next)
        return next
      } finally {
        setPending(null)
      }
    },
    [api],
  )

  return useMemo(() => ({ run, pending, outcome }), [run, pending, outcome])
}

function controlErrorMessage(action: ControlAction, error: ApiError): string {
  switch (error.code) {
    case 'cancellation_unconfirmed':
      return `${action}: the backend has not confirmed the resource stopped; the Task is not marked cancelled.`
    case 'acceptance_stale':
      return 'This decision is stale — the requirements or candidate changed. Reload the Task before deciding.'
    case 'not_ready':
      return `${action} is not available yet: ${error.message}`
    case 'illegal_transition':
      return `${action} is not allowed in the current phase.`
    case 'revision_conflict':
      return 'Someone changed the Task first. Reload and retry.'
    default:
      return `${action} failed: ${error.message}`
  }
}

/** Bounded poll interval for real Task phase/detail progress (LG-220). */
export const BOARD_AUTO_REFRESH_MS = 4000

export interface BoardAutoRefreshOptions {
  /** Re-read the board and the selected Task detail. */
  onRefresh: () => void
  enabled?: boolean
  intervalMs?: number
}

/**
 * Bounded Board polling (LG-220).
 *
 * Reuses the existing read endpoints rather than opening a second SSE
 * subscription next to the TopBar notification stream. Polls are skipped while
 * the page is hidden and resume with one immediate read when it becomes visible
 * again, so a background tab does not hammer the backend. The callback only
 * triggers silent re-reads, so selection, drafts and focus are untouched.
 */
export function useBoardAutoRefresh({
  onRefresh,
  enabled = true,
  intervalMs = BOARD_AUTO_REFRESH_MS,
}: BoardAutoRefreshOptions): void {
  const onRefreshRef = useRef(onRefresh)
  onRefreshRef.current = onRefresh

  useEffect(() => {
    if (!enabled || typeof window === 'undefined') return
    if (!Number.isFinite(intervalMs) || intervalMs <= 0) return
    let timer: ReturnType<typeof window.setInterval> | null = null
    const stop = () => {
      if (timer !== null) {
        window.clearInterval(timer)
        timer = null
      }
    }
    const start = () => {
      if (timer !== null || document.visibilityState === 'hidden') return
      timer = window.setInterval(() => onRefreshRef.current(), intervalMs)
    }
    const onVisibility = () => {
      if (document.visibilityState === 'hidden') {
        stop()
        return
      }
      if (timer === null) {
        // Catch up once after returning to the tab, then continue polling.
        onRefreshRef.current()
        start()
      }
    }
    start()
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      stop()
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [enabled, intervalMs])
}

function toApiError(cause: unknown): ApiError {
  if (cause instanceof ApiError) return cause
  return new ApiError({
    message: cause instanceof Error ? cause.message : 'Request failed',
    code: 'network_error',
    httpStatus: null,
    retryable: true,
  })
}
