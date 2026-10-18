import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { TaskApi } from '../src/api/tasks'
import type { TaskDetail, TaskSummary } from '../src/api/types'
import { routeFromUrl } from '../src/app/uiState'
import { TaskDirectory } from '../src/views/files/TaskDirectory'

const task = {
  id: 'task_real',
  task_id: 'task_real',
  title: 'Review source',
  phase: 'awaiting_acceptance',
  archived: false,
} as TaskSummary

function taskApi(overrides: Partial<TaskApi> = {}): TaskApi {
  return {
    listTasks: vi.fn(async () => ({ items: [task], next_cursor: null })),
    getTask: vi.fn(async () => ({ ...task, run: null, members: [], subtasks: [] }) as TaskDetail),
    ...overrides,
  } as TaskApi
}

afterEach(() => cleanup())

describe('LG-202 legacy routes', () => {
  it('normalizes the retired Chat main view to Tasks while keeping task/run/item/channel', () => {
    expect(routeFromUrl('?view=chat&task=t1&run=r1&item=source:s1&channel=team')).toMatchObject({
      view: 'tasks',
      taskRef: 't1',
      runRef: 'r1',
      selectedItemRef: 'source:s1',
      chatChannel: 'team',
    })
  })

  it('normalizes legacy Files links and unknown/default routes to Tasks', () => {
    expect(routeFromUrl('?view=files&task=t1&run=r1')).toMatchObject({
      view: 'tasks',
      taskRef: 't1',
      runRef: 'r1',
    })
    expect(routeFromUrl('')).toMatchObject({ view: 'tasks' })
    expect(routeFromUrl('?view=unknown').view).toBe('tasks')
  })
})

describe('LG-202 Tasks directory', () => {
  it('pins General first and opens it without inventing a Task identity', async () => {
    const onOpen = vi.fn()
    render(<TaskDirectory api={taskApi()} onOpen={onOpen} />)
    await screen.findByRole('button', { name: /Review source/ })
    const general = screen.getByRole('button', { name: 'General' })
    expect(general).toHaveAttribute('aria-current', 'page')
    const buttons = screen.getAllByRole('button')
    const generalIndex = buttons.indexOf(general)
    const taskIndex = buttons.findIndex((button) => /Review source/.test(button.textContent ?? ''))
    expect(generalIndex).toBeGreaterThan(-1)
    expect(generalIndex).toBeLessThan(taskIndex)
    expect(screen.getByRole('button', { name: 'New task' })).toBeInTheDocument()
    fireEvent.click(general)
    expect(onOpen).toHaveBeenCalledWith(null)
  })

  it('keeps General selected when a Task verification resolves late', async () => {
    let resolveTask!: (task: TaskDetail) => void
    const getTask = vi.fn(
      () => new Promise<TaskDetail>((resolve) => { resolveTask = resolve }),
    )
    const onOpen = vi.fn()
    render(<TaskDirectory api={taskApi({ getTask })} onOpen={onOpen} />)
    fireEvent.click(await screen.findByRole('button', { name: /Review source/ }))
    fireEvent.click(screen.getByRole('button', { name: 'General' }))
    expect(onOpen).toHaveBeenCalledWith(null)
    await act(async () => {
      resolveTask({ ...task, run: null, members: [], subtasks: [] } as TaskDetail)
    })
    expect(onOpen).not.toHaveBeenCalledWith('task_real')
  })

  it('verifies the real Task and reports the selected Task', async () => {
    const onOpen = vi.fn()
    const api = taskApi()
    render(<TaskDirectory api={api} activeTaskRef="task_real" onOpen={onOpen} />)
    const taskButton = await screen.findByRole('button', { name: /Review source/ })
    expect(taskButton).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('button', { name: 'General' })).not.toHaveAttribute('aria-current')
    fireEvent.click(taskButton)
    await waitFor(() => expect(onOpen).toHaveBeenCalledWith('task_real'))
    expect(api.getTask).toHaveBeenCalledWith('task_real', expect.any(AbortSignal))
  })
})


it('refreshes a mounted directory for a Chat-created Task and includes a real selected Task beyond page one', async () => {
  const created = { ...task, id: 'task_created', task_id: 'task_created', title: 'Launch brief' }
  const api = taskApi({ getTask: vi.fn(async (id) => ({ ...created, id, task_id: id, run: null, members: [], subtasks: [] }) as TaskDetail) })
  const view = render(<TaskDirectory api={api} activeTaskRef={null} onOpen={() => {}} />)
  await screen.findByRole('button', { name: /Review source/ })
  view.rerender(<TaskDirectory api={api} activeTaskRef="task_created" onOpen={() => {}} />)
  expect(await screen.findByRole('button', { name: /Launch brief/ })).toHaveAttribute('aria-current', 'page')
  expect(api.listTasks).toHaveBeenCalledTimes(2)
  expect(api.getTask).toHaveBeenCalledWith('task_created', expect.any(AbortSignal))
})
