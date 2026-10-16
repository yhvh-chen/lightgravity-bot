import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../src/api/client'
import type { TaskApi } from '../src/api/tasks'
import type { TaskDetail, TaskSummary } from '../src/api/types'
import type { SearchResult, SourcesApi } from '../src/api/sources'
import { ShellProvider, useShell } from '../src/app/ShellProvider'
import { ChatSourceSearch } from '../src/views/chat/ChatSourceSearch'
import { TaskDirectory } from '../src/views/files/TaskDirectory'
import { FilesView } from '../src/views/files/FilesView'
import { backendFetch } from './setup'

afterEach(() => { cleanup(); vi.mocked(fetch).mockImplementation(backendFetch as typeof fetch) })
beforeEach(() => { sessionStorage.clear(); history.replaceState(null, '', '/') })
const task = { id: 'task_real', task_id: 'task_real', title: 'Review source', phase: 'awaiting_acceptance', archived: false } as TaskSummary
function taskApi(overrides: Partial<TaskApi> = {}): TaskApi {
  return {
    listTasks: vi.fn(async () => ({ items: [task], next_cursor: null })),
    getTask: vi.fn(async () => ({ ...task, run: null, members: [], subtasks: [] }) as TaskDetail),
    ...overrides,
  } as TaskApi
}
function deferred<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>((r) => { resolve = r }); return { promise, resolve } }
function result(title: string, taskRef: string | null): SearchResult {
  return {
    query: 'spec', kind: [], index_status: 'ok', stale: [], skipped: [],
    authorized_scope: { task_ref: taskRef, project_ref: null, inbox_ref: null, include_global: true },
    hits: [{ source_id: `id_${title}`, source_version: 1, content_hash: 'hash', title, snippet: 'text', basis: 'formal', scope: { task_ref: taskRef, project_ref: null, inbox_ref: null }, locators: [], verified: true, stale: false, reason: null }],
  }
}

describe('Files task identity', () => {
  it('verifies the authoritative task before opening its conversation', async () => {
    const onOpen = vi.fn()
    const api = taskApi()
    render(<TaskDirectory api={api} onOpen={onOpen} />)
    fireEvent.click(await screen.findByRole('button', { name: /Review source/ }))
    await waitFor(() => expect(onOpen).toHaveBeenCalledWith('task_real'))
    expect(api.getTask).toHaveBeenCalledWith('task_real', expect.any(AbortSignal))
  })
  it('keeps a removed task as a recoverable error rather than opening a guessed ID', async () => {
    const onOpen = vi.fn()
    const api = taskApi({ getTask: vi.fn(async () => { throw new ApiError({ code: 'not_found', message: 'Task was removed', httpStatus: 404, retryable: false }) }) })
    render(<TaskDirectory api={api} onOpen={onOpen} />)
    fireEvent.click(await screen.findByRole('button', { name: /Review source/ }))
    expect(await screen.findByText('Task was removed')).toBeInTheDocument()
    expect(onOpen).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
  })
  it('refuses a mismatching task identity in a detail response', async () => {
    const onOpen = vi.fn()
    render(<TaskDirectory api={taskApi({ getTask: vi.fn(async () => ({ ...task, id: 'task_other' }) as TaskDetail) })} onOpen={onOpen} />)
    fireEvent.click(await screen.findByRole('button', { name: /Review source/ }))
    expect(await screen.findByText(/task identity changed/)).toBeInTheDocument()
    expect(onOpen).not.toHaveBeenCalled()
  })
  it('does not infer a Task from an ordinary workspace folder with a task-like name', async () => {
    function Route() { const { state } = useShell(); return <><output aria-label="Current task">{state.taskRef ?? 'none'}</output><FilesView /></> }
    vi.mocked(fetch).mockImplementation((async (input: RequestInfo | URL) => {
      const path = String(input)
      const body = path.endsWith('/tasks?limit=100') ? { items: [], next_cursor: null }
        : path.includes('/files') ? { path: '', items: path.includes('path=') ? [] : [{ name: 'task_fake', path: 'task_fake', type: 'directory', size: null, modified_at: '', symlink: false, media_type: null, revision: null }], next_cursor: null } : null
      if (body) return { ok: true, status: 200, headers: { get: () => 'application/json' }, json: async () => body } as unknown as Response
      return backendFetch(input)
    }) as typeof fetch)
    render(<ShellProvider><Route /></ShellProvider>)
    fireEvent.click(await screen.findByRole('button', { name: /task_fake/ }))
    expect(screen.getByLabelText('Current task')).toHaveTextContent('none')
    await waitFor(() => expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).includes('/files?path=task_fake'))).toBe(true))
  })
})

describe('Search scope races', () => {
  it('aborts a prior search on task switch and ignores a late response even when the transport does not abort', async () => {
    const old = deferred<SearchResult>()
    const current = deferred<SearchResult>()
    const search = vi.fn().mockReturnValueOnce(old.promise).mockReturnValueOnce(current.promise)
    const api = { search } as unknown as SourcesApi
    const { rerender } = render(<ChatSourceSearch api={api} taskRef="task_old" onOpen={vi.fn()} />)
    fireEvent.change(screen.getByLabelText('Search materials'), { target: { value: 'spec' } })
    fireEvent.click(screen.getByRole('button', { name: 'Search' }))
    const oldSignal = search.mock.calls[0][1] as AbortSignal
    rerender(<ChatSourceSearch api={api} taskRef="task_current" onOpen={vi.fn()} />)
    expect(oldSignal.aborted).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: 'Search' }))
    expect(search.mock.calls[1][0]).toMatchObject({ task_ref: 'task_current', include_global: true })
    await act(async () => current.resolve(result('current material', 'task_current')))
    expect(await screen.findByText('current material')).toBeInTheDocument()
    await act(async () => old.resolve(result('old material', 'task_old')))
    expect(screen.queryByText('old material')).toBeNull()
    expect(screen.getByText('current material')).toBeInTheDocument()
  })
  it('drops visible results when changing from task material to shared material', async () => {
    const api = { search: vi.fn(async () => result('old hit', 'task_old')) } as unknown as SourcesApi
    const { rerender } = render(<ChatSourceSearch api={api} taskRef="task_old" onOpen={vi.fn()} />)
    fireEvent.change(screen.getByLabelText('Search materials'), { target: { value: 'spec' } })
    fireEvent.click(screen.getByRole('button', { name: 'Search' }))
    expect(await screen.findByText('old hit')).toBeInTheDocument()
    rerender(<ChatSourceSearch api={api} taskRef={null} onOpen={vi.fn()} />)
    expect(screen.queryByText('old hit')).toBeNull()
  })
})
