import { act, cleanup, fireEvent, render, renderHook, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { ChatApi, ChatMessage, ChatSubmitResult } from '../src/api/chat'
import type { AuthMeResponse } from '../src/api/teamAuth'
import { AuthProvider } from '../src/app/AuthProvider'
import { ShellProvider } from '../src/app/ShellProvider'
import { ChatBody } from '../src/views/chat/ChatBody'
import { useChat, type ChatSendOutcome } from '../src/views/chat/useChat'

const { dispatched } = vi.hoisted(() => ({ dispatched: vi.fn() }))
vi.mock('../src/app/ShellProvider', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../src/app/ShellProvider')>()
  return {
    ...actual,
    useShell: () => {
      const shell = actual.useShell()
      return {
        ...shell,
        dispatch: (action: Parameters<typeof shell.dispatch>[0]) => {
          dispatched(action)
          shell.dispatch(action)
        },
      }
    },
  }
})

const TASK = 'task_01ARZ3NDEKTSV4RRFFQ69G5FAV'
const REPLY = `Task ${TASK} is executing; no additional Run was created.`
const team = async (): Promise<AuthMeResponse> => ({ mode: 'team', authenticated: true, username: 'bob', role: 'member' })
const single = async (): Promise<AuthMeResponse> => ({ mode: 'single', authenticated: true, username: null, role: 'admin' })

function makeApi(outcome: ChatSubmitResult) {
  let persisted: ChatMessage[] = []
  const api: ChatApi = {
    readMessages: vi.fn(async () => ({ items: persisted, next_cursor: null })),
    sendMessage: vi.fn(async (_scope, body) => {
      // Simulate a response which is persisted in the originating conversation;
      // the hook must reload history rather than inventing a local reply bubble.
      persisted = [{ message_id: `assistant:${body.message_id}`, role: 'assistant', content: outcome.reply ?? '', attachments: [] }]
      return outcome
    }),
    createTask: vi.fn(async () => ({ kind: 'create_task' })),
  }
  return api
}

function renderChat(api: ChatApi, probe = team) {
  return render(<AuthProvider probe={probe}><ShellProvider><ChatBody variant="main" api={api} /></ShellProvider></AuthProvider>)
}

async function submit(label: string, content: string) {
  const composer = await screen.findByLabelText(label)
  await act(async () => {
    fireEvent.change(composer, { target: { value: content } })
    fireEvent.keyDown(composer, { key: 'Enter' })
  })
}

beforeEach(() => {
  sessionStorage.clear()
  history.replaceState(null, '', '/')
  dispatched.mockClear()
})
afterEach(cleanup)

describe('LG071 response target versus newly created Task', () => {
  it.each(['query', 'control', 'clarify', 'retry', 'decision', 'answer'])('%s retains target metadata without claiming creation', async (kind) => {
    const api = makeApi({ kind, task_id: TASK, reply: REPLY, data: { creates_task: false } })
    const { result } = renderHook(() => useChat({ taskRef: null }, api))
    let outcome!: ChatSendOutcome
    await act(async () => { outcome = await result.current.send('@bot status') })
    expect(outcome.taskRef).toBe(TASK)
    expect(outcome.createdTaskRef).toBeNull()
    expect(outcome.kind).toBe(kind)
    await waitFor(() => expect(result.current.messages[0]?.content).toBe(REPLY))
  })

  it('preserves nested legacy task references without turning a query into creation', async () => {
    const api = makeApi({ kind: 'query', data: { task_id: TASK }, reply: REPLY })
    const { result } = renderHook(() => useChat({ taskRef: null }, api))
    await act(async () => {
      const outcome = await result.current.send('@bot status')
      expect(outcome.taskRef).toBe(TASK)
      expect(outcome.createdTaskRef).toBeNull()
    })
  })

  it.each([['Team', team], ['single-user Personal', single]] as const)('keeps %s query reply visible in its original global conversation', async (_label, probe) => {
    const api = makeApi({ kind: 'query', task_id: TASK, reply: REPLY, data: { creates_task: false, creates_run: false } })
    renderChat(api, probe)
    await submit('Message for Global', `@bot 查询 ${TASK} 状态，不创建任务`)
    expect(await screen.findByText(REPLY)).toBeInTheDocument()
    expect(screen.getByLabelText('Message for Global')).toHaveValue('')
    expect(screen.queryByText(/Created Task/)).toBeNull()
    expect(dispatched).not.toHaveBeenCalledWith(expect.objectContaining({ type: 'selectTask' }))
    expect(api.readMessages).not.toHaveBeenCalledWith(expect.objectContaining({ taskRef: TASK }), expect.anything(), expect.anything())
    expect(new URLSearchParams(location.search).get('task')).toBeNull()
    expect(screen.getByRole('tab', { name: probe === team ? 'Team' : 'Personal' })).toHaveAttribute('aria-selected', 'true')
  })

  it.each(['control', 'clarify', 'retry', 'decision'])('%s with an existing Task ID does not announce or navigate to a new Task', async (kind) => {
    const api = makeApi({ kind, task_id: TASK, reply: 'Existing Task response' })
    renderChat(api)
    await submit('Message for Global', '@bot request')
    expect(await screen.findByText('Existing Task response')).toBeInTheDocument()
    expect(screen.queryByText(/Created Task/)).toBeNull()
    expect(dispatched).not.toHaveBeenCalledWith(expect.objectContaining({ type: 'selectTask' }))
  })

  it.each([['Team', team], ['single-user Personal', single]] as const)('keeps the original creation notice and navigation for %s delivery', async (_label, probe) => {
    history.replaceState(null, '', '?view=team')
    const api = makeApi({ kind: 'create_task', task_id: TASK, reply: 'Created delivery', data: { creates_task: true } })
    renderChat(api, probe)
    await submit('Message for Global', '@bot create a page')
    expect(await screen.findByText(`Created Task ${TASK}. Opening its workspace.`)).toBeInTheDocument()
    expect(await screen.findByLabelText(`Message for ${TASK}`)).toBeInTheDocument()
    expect(dispatched).toHaveBeenCalledWith({ type: 'openTaskDestination', view: 'tasks', taskRef: TASK, runRef: null, itemRef: null })
    expect(new URLSearchParams(location.search).get('view')).toBe('tasks')
    expect(new URLSearchParams(location.search).get('task')).toBe(TASK)
    expect(screen.getByRole('tab', { name: probe === team ? 'Team' : 'Personal' })).toHaveAttribute('aria-selected', 'true')
  })

  it('keeps team-mode private Personal chat private on a switch-to-Team response', async () => {
    const api = makeApi({ kind: 'switch_to_team', reply: 'Please switch to Team.' })
    renderChat(api)
    fireEvent.click(await screen.findByRole('tab', { name: 'Personal' }))
    dispatched.mockClear()
    await submit('Message for Personal', `查询 ${TASK} 状态`)
    expect(await screen.findByText('Please switch to Team.')).toBeInTheDocument()
    expect(api.sendMessage).toHaveBeenCalledWith({ taskRef: null, personal: true }, expect.anything())
    expect(screen.getByRole('tab', { name: 'Personal' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.queryByText(/Created Task/)).toBeNull()
    expect(dispatched).not.toHaveBeenCalledWith(expect.objectContaining({ type: 'selectTask' }))
  })
})
