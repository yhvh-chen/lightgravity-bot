import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ChatApi, ChatMessage, ChatSubmitResult } from '../src/api/chat'
import type { AuthMeResponse } from '../src/api/teamAuth'
import { AuthProvider } from '../src/app/AuthProvider'
import { ShellProvider, useShell } from '../src/app/ShellProvider'
import { HEALTH_FIXTURE, backendFetch } from './setup'
import { ChatBody } from '../src/views/chat/ChatBody'

const single = async (): Promise<AuthMeResponse> => ({ mode: 'single', authenticated: true, username: null, role: 'admin' })
const member = (username: string) => async (): Promise<AuthMeResponse> => ({ mode: 'team', authenticated: true, username, role: 'member' })
function api(overrides: Partial<ChatApi> = {}): ChatApi {
  return {
    readMessages: vi.fn(async () => ({ items: [], next_cursor: null })),
    sendMessage: vi.fn(async () => ({ kind: 'answer', reply: 'ok' })),
    createTask: vi.fn(async () => ({ kind: 'create_task' })),
    ...overrides,
  }
}
function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (cause: Error) => void
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}
function Harness({ chatApi }: { chatApi: ChatApi }) {
  const { state, dispatch } = useShell()
  return <>
    <output aria-label="Route channel">{state.chatChannel ?? 'default'}</output>
    <button onClick={() => dispatch({ type: 'openTaskConversation', taskRef: 'task_actual' })}>Open actual task</button>
    <ChatBody variant="main" api={chatApi} />
  </>
}
function tree(probe: () => Promise<AuthMeResponse>, chatApi: ChatApi) {
  return <AuthProvider probe={probe}><ShellProvider><Harness chatApi={chatApi} /></ShellProvider></AuthProvider>
}
beforeEach(() => { sessionStorage.clear(); history.replaceState(null, '', '/') })
afterEach(() => { cleanup(); vi.mocked(fetch).mockImplementation(backendFetch as typeof fetch) })

describe('LG057 single-user preservation', () => {
  it('keeps Files-style task navigation and materials in Personal with Team disabled', async () => {
    const chatApi = api()
    render(tree(single, chatApi))
    fireEvent.click(await screen.findByRole('button', { name: 'Open actual task' }))
    expect(await screen.findByLabelText('Message for task_actual')).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Personal' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tab', { name: 'Team' })).toBeDisabled()
    expect(screen.getByLabelText('Route channel')).toHaveTextContent('personal')
    // LG-204: the shared selection lives in Tasks; Chat keeps only the direct
    // file picker and no workspace-relative path input/extras toggle.
    expect(screen.queryByLabelText('Attach file path')).toBeNull()
    expect(screen.queryByRole('button', { name: 'Add attachments and materials' })).toBeNull()
    expect(screen.getByRole('button', { name: 'Upload file' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: 'Personal' }))
    expect(screen.getByLabelText('Message for task_actual')).toBeInTheDocument()
    expect(screen.queryByText('Team conversation')).toBeNull()
  })
  it('creates a Task from legacy global chat without switching to a disabled Team channel', async () => {
    const chatApi = api({ sendMessage: vi.fn(async () => ({ kind: 'create_task', task_id: 'task_created', reply: 'created' })) })
    render(tree(single, chatApi))
    const composer = await screen.findByLabelText('Message for Global')
    fireEvent.change(composer, { target: { value: 'generate a file' } })
    fireEvent.keyDown(composer, { key: 'Enter' })
    expect(await screen.findByLabelText('Message for task_created')).toBeInTheDocument()
    expect(screen.getByLabelText('Route channel')).toHaveTextContent('personal')
    expect(screen.getByRole('button', { name: 'Upload file' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Add attachments and materials' })).toBeNull()
  })
})

describe('LG057 private UI isolation', () => {
  it('disables unsupported private chat without removing the compatible shared workspace', async () => {
    history.replaceState(null, '', '/?channel=personal')
    vi.mocked(fetch).mockImplementation((async (input: RequestInfo | URL) => {
      if (String(input).endsWith('/api/v1/health')) return new Response(JSON.stringify({ ...HEALTH_FIXTURE, contract_version: '1.13.0', capabilities: { ...HEALTH_FIXTURE.capabilities, personal_chat: false } }), { headers: { 'Content-Type': 'application/json' } })
      return backendFetch(input)
    }) as typeof fetch)
    const chatApi = api()
    render(tree(member('alice'), chatApi))
    const personal = await screen.findByRole('tab', { name: 'Personal' })
    expect(personal).toBeDisabled()
    expect(screen.getByRole('tab', { name: 'Team' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByText(/Personal is unavailable on this backend/)).toBeInTheDocument()
    expect(chatApi.readMessages).not.toHaveBeenCalledWith(expect.objectContaining({ personal: true }), expect.anything(), expect.anything())
  })
  it('ignores late identity discovery after switching to a different authenticated user', async () => {
    const old = deferred<AuthMeResponse>()
    const oldProbe = () => old.promise
    const chatApi = api()
    const { rerender } = render(tree(oldProbe, chatApi))
    rerender(tree(member('bob'), chatApi))
    fireEvent.click(await screen.findByRole('tab', { name: 'Personal' }))
    fireEvent.change(screen.getByLabelText('Message for Personal'), { target: { value: 'Bob draft' } })
    await act(async () => old.resolve({ mode: 'team', authenticated: true, username: 'alice', role: 'member' }))
    expect(screen.getByLabelText('Message for Personal')).toHaveValue('Bob draft')
    expect(sessionStorage.getItem('lg011.shell-prefs:team:bob')).toContain('Bob draft')
    expect(sessionStorage.getItem('lg011.shell-prefs:team:alice')).toBeNull()
  })
  it('uses a private picker in Personal and the shared intake in Team', async () => {
    render(tree(member('alice'), api()))
    fireEvent.click(await screen.findByRole('tab', { name: 'Personal' }))
    expect(await screen.findByLabelText('Message for Personal')).toBeInTheDocument()
    // LG-119: Personal has its own direct file picker; the shared path/material
    // controls stay out of this channel.
    expect(screen.queryByLabelText('Attach file path')).toBeNull()
    expect(screen.getByLabelText('Upload file for Personal')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: 'Team' }))
    expect(screen.getByRole('button', { name: 'Upload file' })).toBeInTheDocument()
    expect(screen.queryByLabelText('Attach file path')).toBeNull()
  })
  it('does not reuse another signed-in identity private draft or unowned legacy draft', async () => {
    sessionStorage.setItem('lg011.shell-prefs', JSON.stringify({ drafts: { 'chat:personal:global': 'unowned secret' } }))
    const chatApi = api()
    const alice = member('alice')
    const bob = member('bob')
    const { rerender } = render(tree(alice, chatApi))
    fireEvent.click(await screen.findByRole('tab', { name: 'Personal' }))
    const composer = await screen.findByLabelText('Message for Personal')
    expect(composer).toHaveValue('')
    fireEvent.change(composer, { target: { value: 'Alice private draft' } })
    await waitFor(() => expect(sessionStorage.getItem('lg011.shell-prefs:team:alice')).toContain('Alice private draft'))
    rerender(tree(bob, chatApi))
    expect(await screen.findByLabelText('Message for Personal')).toHaveValue('')
    fireEvent.change(screen.getByLabelText('Message for Personal'), { target: { value: 'Bob private draft' } })
    rerender(tree(alice, chatApi))
    await waitFor(() => expect(screen.getByLabelText('Message for Personal')).toHaveValue('Alice private draft'))
  })
  it('does not show the previous private history while the shared history is loading', async () => {
    const shared = deferred<{ items: ChatMessage[]; next_cursor: null }>()
    const chatApi = api({ readMessages: vi.fn((scope) => scope.personal ? Promise.resolve({ items: [{ message_id: 'private', role: 'assistant', content: 'private only', attachments: [] }], next_cursor: null }) : shared.promise) })
    render(tree(member('alice'), chatApi))
    fireEvent.click(await screen.findByRole('tab', { name: 'Personal' }))
    expect(await screen.findByText('private only')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: 'Team' }))
    expect(screen.queryByText('private only')).toBeNull()
    await act(async () => shared.resolve({ items: [], next_cursor: null }))
  })
  it('ignores a late successful shared delivery after leaving for Personal', async () => {
    const send = deferred<ChatSubmitResult>()
    render(tree(member('alice'), api({ sendMessage: vi.fn(() => send.promise) })))
    const composer = await screen.findByLabelText('Message for Global')
    fireEvent.change(composer, { target: { value: '@bot generate a file' } })
    fireEvent.keyDown(composer, { key: 'Enter' })
    fireEvent.click(screen.getByRole('tab', { name: 'Personal' }))
    fireEvent.change(screen.getByLabelText('Message for Personal'), { target: { value: 'private unsent draft' } })
    await act(async () => send.resolve({ kind: 'create_task', task_id: 'task_late', reply: 'done' }))
    expect(screen.getByLabelText('Message for Personal')).toHaveValue('private unsent draft')
    expect(screen.queryByText(/Created Task task_late/)).toBeNull()
    expect(window.location.search).not.toContain('task_late')
  })
  it('keeps late private send failures out of the shared Team conversation', async () => {
    const send = deferred<ChatSubmitResult>()
    render(tree(member('alice'), api({ sendMessage: vi.fn(() => send.promise) })))
    fireEvent.click(await screen.findByRole('tab', { name: 'Personal' }))
    const composer = await screen.findByLabelText('Message for Personal')
    fireEvent.change(composer, { target: { value: 'private request' } })
    fireEvent.keyDown(composer, { key: 'Enter' })
    fireEvent.click(screen.getByRole('tab', { name: 'Team' }))
    await act(async () => send.reject(new Error('private failure detail')))
    expect(screen.queryByText(/private failure detail/)).toBeNull()
    expect(screen.queryByText(/Not sent/)).toBeNull()
    expect(screen.getByLabelText('Message for Global')).toBeEnabled()
  })
})
