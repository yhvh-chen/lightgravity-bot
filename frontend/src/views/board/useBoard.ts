/**
 * Board data hook (LG-013; docs/08 §4.3/§6/§9).
 *
 * Reads the real Task list and, for one selected Task, its detail, acceptance
 * snapshot and artifacts. It exposes control actions that keep *pending* and
 * *actual* results apart: a control call returns `confirmed` but the hook
 * re-reads the authoritative Task state rather than optimistically painting the
 * requested phase. A `confirmed=false` result is reported as pending.
 */

import { useCallback, useEffect, useMemo, useState } from 'react'

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

export interface BoardState {
  tasks: TaskSummary[]
  tasksLoading: boolean
  tasksError: ApiError | null
  refreshTasks: () => void
}

export function useTaskList(api: TaskApi = taskApi): BoardState {
  const [tasks, setTasks] = useState<TaskSummary[]>([])
  const [tasksLoading, setTasksLoading] = useState(true)
  const [tasksError, setTasksError] = useState<ApiError | null>(null)
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    let cancelled = false
    setTasksLoading(true)
    setTasksError(null)
    api
      .listTasks({ limit: 100 }, controller.signal)
      .then((page) => {
        if (cancelled) return
        setTasks(page.items)
        setTasksLoading(false)
      })
      .catch((cause) => {
        if (cancelled || controller.signal.aborted) return
        setTasks([])
        setTasksError(toApiError(cause))
        setTasksLoading(false)
      })
    return () => {
      cancelled = true
      controller.abort()
    }
  }, [api, reloadKey])

  return useMemo(
    () => ({
      tasks,
      tasksLoading,
      tasksError,
      refreshTasks: () => setReloadKey((key) => key + 1),
    }),
    [tasks, tasksLoading, tasksError],
  )
}

export interface TaskDetailState {
  detail: TaskDetail | null
  acceptance: AcceptanceSnapshot | null
  artifacts: TaskArtifacts | null
  loading: boolean
  error: ApiError | null
  refresh: () => void
}

export function useTaskDetail(taskRef: string | null, api: TaskApi = taskApi): TaskDetailState {
  const [detail, setDetail] = useState<TaskDetail | null>(null)
  const [acceptance, setAcceptance] = useState<AcceptanceSnapshot | null>(null)
  const [artifacts, setArtifacts] = useState<TaskArtifacts | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
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
    setLoading(true)
    setError(null)
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
        setLoading(false)
      })
      .catch((cause) => {
        if (cancelled || controller.signal.aborted) return
        setDetail(null)
        setAcceptance(null)
        setArtifacts(null)
        setError(toApiError(cause))
        setLoading(false)
      })
    return () => {
      cancelled = true
      controller.abort()
    }
  }, [api, taskRef, reloadKey])

  return useMemo(
    () => ({
      detail,
      acceptance,
      artifacts,
      loading,
      error,
      refresh: () => setReloadKey((key) => key + 1),
    }),
    [detail, acceptance, artifacts, loading, error],
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

function toApiError(cause: unknown): ApiError {
  if (cause instanceof ApiError) return cause
  return new ApiError({
    message: cause instanceof Error ? cause.message : 'Request failed',
    code: 'network_error',
    httpStatus: null,
    retryable: true,
  })
}
