/**
 * LG-203/204 focused tests (no browser, no backend).
 *
 * * New task is title-only and calls the real POST /tasks helper with an
 *   idempotency key; the objective defaults to the title, failures keep the
 *   input, Escape closes and focus returns to the trigger.
 * * The Tasks material rows are the context selector; their checkbox state is
 *   the same bounded selection rendered as chips above the Chat composer.
 * * Only the current Task's materials plus global materials are offered.
 * * A material without readable text is not selectable (LG-221 projection).
 */

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { ChatApi, ChatScope } from '../src/api/chat'
import type { SourceView, SourcesApi } from '../src/api/sources'
import type { TaskApi } from '../src/api/tasks'
import type { TaskDetail, TaskSummary } from '../src/api/types'
import { ShellProvider } from '../src/app/ShellProvider'
import { ChatBody } from '../src/views/chat/ChatBody'
import { ChatSelectionProvider } from '../src/views/chat/useChatSelection'
import { FilesMaterialsPanel } from '../src/views/files/FilesMaterialsPanel'
import { TaskDirectory } from '../src/views/files/TaskDirectory'

afterEach(cleanup)

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

function source(overrides: Partial<SourceView> = {}): SourceView {
  return {
    id: 'source_01J',
    source_id: 'source_01J',
    title: 'notes.md',
    title_origin: 'user',
    status: 'extracted',
    context_selectable: true,
    revision: 2,
    etag: 'rev-2',
    scope: { task_ref: null, project_ref: null, inbox_ref: 'inbox_1' },
    origin: { kind: 'upload', external_ref: null, fetched: false },
    content_hash: 'realhash000000000000000000000000000000000000000000000000000000000000',
    stat_revision: '12-1',
    source_version: 3,
    original: null,
    derivatives: [],
    formal: null,
    index: null,
    receipt_ref: null,
    created_at: null,
    updated_at: null,
    path: 'sources/source_01J/SOURCE.md',
    ...overrides,
  }
}

function sourcesApi(items: SourceView[]): SourcesApi {
  return {
    createSource: vi.fn(),
    listSources: vi.fn(async (filter?: { task_ref?: string | null }) => ({
      items:
        filter?.task_ref === undefined
          ? items
          : items.filter((item) => item.scope.task_ref === filter.task_ref),
      next_cursor: null,
    })),
    getSource: vi.fn(async () => items[0]),
    getReceipt: vi.fn(),
    getContent: vi.fn(),
    downloadSource: vi.fn(),
    editFormal: vi.fn(),
    sourceAction: vi.fn(),
    appendInboxMessage: vi.fn(),
    search: vi.fn(),
  } as unknown as SourcesApi
}

function chatApi(): ChatApi & { sent: Array<{ scope: ChatScope; body: Record<string, unknown> }> } {
  const sent: Array<{ scope: ChatScope; body: Record<string, unknown> }> = []
  return {
    sent,
    readMessages: vi.fn(async () => ({ items: [], next_cursor: null })),
    sendMessage: vi.fn(async (scope, body) => {
      sent.push({ scope, body: body as unknown as Record<string, unknown> })
      return { kind: 'recorded' }
    }),
    createTask: vi.fn(async () => ({ kind: 'create_task', task_id: 'task_new' })),
  } as unknown as ChatApi & { sent: typeof sent }
}

describe('LG-203 New task dialog', () => {
  it('creates a title-only Task with request_id/objective and opens it', async () => {
    const onOpen = vi.fn()
    const createTask = vi.fn(async () => ({ kind: 'create_task', task_id: 'task_new' }))
    render(<TaskDirectory api={taskApi()} createTask={createTask} onOpen={onOpen} />)
    await screen.findByRole('button', { name: /Review source/ })

    fireEvent.click(screen.getByRole('button', { name: 'New task' }))
    const dialog = screen.getByRole('dialog', { name: 'New task' })
    expect(dialog).toBeInTheDocument()
    const input = screen.getByLabelText('Task title')
    await waitFor(() => expect(input).toHaveFocus())

    fireEvent.change(input, { target: { value: 'Build the demo' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create task' }))

    await waitFor(() => expect(onOpen).toHaveBeenCalledWith('task_new'))
    expect(createTask).toHaveBeenCalledWith(
      expect.objectContaining({
        request_id: expect.stringMatching(/^request_/),
        title: 'Build the demo',
        objective: 'Build the demo',
      }),
    )
    expect(screen.queryByRole('dialog', { name: 'New task' })).toBeNull()
  })

  it('keeps the title and shows an inline error when creation fails', async () => {
    const createTask = vi.fn(async () => {
      throw new Error('workspace denied')
    })
    render(<TaskDirectory api={taskApi()} createTask={createTask} onOpen={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: 'New task' }))
    fireEvent.change(screen.getByLabelText('Task title'), { target: { value: 'Keep me' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create task' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Create failed: workspace denied')
    expect(screen.getByLabelText('Task title')).toHaveValue('Keep me')
    expect(screen.getByRole('dialog', { name: 'New task' })).toBeInTheDocument()
  })

  it('closes on Escape and returns focus to the New task trigger', async () => {
    render(<TaskDirectory api={taskApi()} createTask={vi.fn()} onOpen={vi.fn()} />)
    const trigger = await screen.findByRole('button', { name: 'New task' })
    fireEvent.click(trigger)
    const input = screen.getByLabelText('Task title')
    await waitFor(() => expect(input).toHaveFocus())
    fireEvent.keyDown(input, { key: 'Escape' })
    expect(screen.queryByRole('dialog', { name: 'New task' })).toBeNull()
    expect(trigger).toHaveFocus()
  })
})

describe('LG-204 Tasks material selection', () => {
  function renderWorkspace(items: SourceView[], taskRef: string | null = null) {
    const api = chatApi()
    const sources = sourcesApi(items)
    render(
      <ShellProvider>
        <ChatSelectionProvider taskRef={taskRef}>
          <FilesMaterialsPanel api={sources} taskRef={taskRef} />
          <ChatBody variant="main" api={api} sourcesApi={sources} />
        </ChatSelectionProvider>
      </ShellProvider>,
    )
    return { api, sources }
  }

  it('shares the Tasks checkbox selection as composer chips and sends it', async () => {
    const { api } = renderWorkspace([source()])
    const checkbox = (await screen.findByLabelText('Use notes.md as context')) as HTMLInputElement
    fireEvent.click(checkbox)
    expect(checkbox.checked).toBe(true)

    expect(await screen.findByLabelText('Selected context materials')).toHaveTextContent('notes.md')
    // The chip can remove the same shared selection.
    fireEvent.click(screen.getByRole('button', { name: 'Remove context notes.md' }))
    expect(screen.queryByLabelText('Selected context materials')).toBeNull()
    expect((screen.getByLabelText('Use notes.md as context') as HTMLInputElement).checked).toBe(false)

    fireEvent.click(screen.getByLabelText('Use notes.md as context'))
    const composer = await screen.findByLabelText('Message for Global')
    fireEvent.change(composer, { target: { value: 'summarize' } })
    fireEvent.keyDown(composer, { key: 'Enter' })

    await waitFor(() => expect(api.sent).toHaveLength(1))
    expect(api.sent[0].body.selected_sources).toEqual([
      {
        source_id: 'source_01J',
        source_version: 3,
        content_hash: 'realhash000000000000000000000000000000000000000000000000000000000000',
      },
    ])
  })

  it('offers only current Task and global materials, never another Task', async () => {
    renderWorkspace(
      [
        source({ source_id: 'g', title: 'global.md' }),
        source({
          source_id: 't9',
          title: 'task9.md',
          scope: { task_ref: 'task_9', project_ref: null, inbox_ref: null },
        }),
        source({
          source_id: 'other',
          title: 'other-task.md',
          scope: { task_ref: 'task_other', project_ref: null, inbox_ref: null },
        }),
      ],
      'task_9',
    )
    await screen.findByLabelText('Use global.md as context')
    expect(screen.getByLabelText('Use task9.md as context')).toBeInTheDocument()
    expect(screen.queryByLabelText('Use other-task.md as context')).toBeNull()
  })

  it('does not offer a material whose only body is a media vector', async () => {
    renderWorkspace([
      source({ source_id: 'media', title: 'audio.wav', status: 'partial', context_selectable: false }),
    ])
    const checkbox = (await screen.findByLabelText('Use audio.wav as context')) as HTMLInputElement
    expect(checkbox.disabled).toBe(true)
    expect(screen.getByText('no readable text body — not selectable')).toBeInTheDocument()
  })

  it('enforces the shared 3-source limit across the Tasks entry', async () => {
    renderWorkspace([
      source({ source_id: 's1', title: 'one.md' }),
      source({ source_id: 's2', title: 'two.md' }),
      source({ source_id: 's3', title: 'three.md' }),
      source({ source_id: 's4', title: 'four.md' }),
    ])
    for (const name of ['one.md', 'two.md', 'three.md']) {
      fireEvent.click(await screen.findByLabelText(`Use ${name} as context`))
    }
    expect(await screen.findByText('3/3 selected in Tasks')).toBeInTheDocument()
    expect((screen.getByLabelText('Use four.md as context') as HTMLInputElement).disabled).toBe(true)
  })
})
