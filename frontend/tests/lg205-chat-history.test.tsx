import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { createHistoryApi, type ConversationHistoryPage, type HistoryApi } from '../src/api/history'
import { ChatHistory } from '../src/views/chat/ChatHistory'

const PAGE: ConversationHistoryPage = {
  items: [
    {
      kind: 'task',
      task_ref: 'task_new',
      title: 'Newest task',
      last_message_at: '2026-10-18T11:00:00.000Z',
      last_message_seq: 4,
    },
    {
      kind: 'general',
      task_ref: null,
      title: 'General',
      last_message_at: '2026-10-18T10:30:00.000Z',
      last_message_seq: 2,
    },
    {
      kind: 'task',
      task_ref: 'task_old',
      title: 'Older task',
      last_message_at: '2026-10-18T09:00:00.000Z',
      last_message_seq: 1,
    },
  ],
}

function historyApi(items: ConversationHistoryPage = PAGE): HistoryApi {
  return { listHistory: vi.fn(async () => items) }
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe('LG-205 Team conversation history', () => {
  it('reads the additive history endpoint from the real API helper', async () => {
    const response = {
      ok: true,
      status: 200,
      headers: { get: () => 'application/json' },
      json: async () => PAGE,
    } as unknown as Response
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(response)

    await expect(createHistoryApi().listHistory()).resolves.toEqual(PAGE)
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/conversations/history',
      expect.objectContaining({ credentials: 'include' }),
    )
  })

  it('stays hidden outside Team mode and never calls the history endpoint', () => {
    const api = historyApi()
    render(<ChatHistory isTeam={false} onSelectTask={vi.fn()} api={api} />)
    expect(screen.queryByRole('button', { name: 'Conversation history' })).toBeNull()
    expect(api.listHistory).not.toHaveBeenCalled()
  })

  it('stays hidden on the Personal channel of a team deployment', () => {
    const api = historyApi()
    render(<ChatHistory isTeam channel="personal" onSelectTask={vi.fn()} api={api} />)
    expect(screen.queryByRole('button', { name: 'Conversation history' })).toBeNull()
    expect(api.listHistory).not.toHaveBeenCalled()
  })

  it('opens an accessible list in backend recency order and switches to the exact Task', async () => {
    const onSelectTask = vi.fn()
    const api = historyApi()
    render(
      <ChatHistory
        isTeam
        activeTaskRef="task_new"
        onSelectTask={onSelectTask}
        api={api}
      />,
    )

    const trigger = screen.getByRole('button', { name: 'Conversation history' })
    expect(trigger).toHaveAttribute('title', 'Conversation history')
    expect(trigger).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(trigger)

    const dialog = await screen.findByRole('dialog', { name: 'Conversation history' })
    await waitFor(() => expect(dialog).toHaveFocus())
    const list = screen.getByRole('list', { name: 'Team conversation history' })
    const items = within(list).getAllByRole('button')
    expect(items.map((item) => item.textContent)).toEqual([
      expect.stringContaining('Newest task'),
      expect.stringContaining('General'),
      expect.stringContaining('Older task'),
    ])
    expect(items[0]).toHaveAttribute('aria-current', 'page')
    expect(items[1]).not.toHaveAttribute('aria-current')

    fireEvent.click(items[2])
    expect(onSelectTask).toHaveBeenCalledWith('task_old')
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('selects General with a null task_ref and supports keyboard focus/Escape return', async () => {
    const onSelectTask = vi.fn()
    render(<ChatHistory isTeam activeTaskRef="task_old" onSelectTask={onSelectTask} api={historyApi()} />)

    const trigger = screen.getByRole('button', { name: 'Conversation history' })
    fireEvent.click(trigger)
    const dialog = await screen.findByRole('dialog', { name: 'Conversation history' })
    const list = screen.getByRole('list', { name: 'Team conversation history' })
    const items = within(list).getAllByRole('button')

    await waitFor(() => expect(dialog).toHaveFocus())
    fireEvent.keyDown(dialog, { key: 'ArrowDown' })
    expect(items[0]).toHaveFocus()
    fireEvent.keyDown(items[0], { key: 'ArrowDown' })
    expect(items[1]).toHaveFocus()
    fireEvent.keyDown(items[1], { key: 'ArrowDown' })
    expect(items[2]).toHaveFocus()
    expect(items[2]).toHaveAttribute('aria-current', 'page')

    fireEvent.keyDown(items[2], { key: 'Escape' })
    await waitFor(() => expect(trigger).toHaveFocus())
    expect(screen.queryByRole('dialog')).toBeNull()

    fireEvent.click(trigger)
    const reopened = await screen.findByRole('dialog', { name: 'Conversation history' })
    const general = within(reopened).getByRole('button', { name: /General/ })
    fireEvent.click(general)
    expect(onSelectTask).toHaveBeenCalledWith(null)
  })

  it('aborts an in-flight read when the popover closes so late data cannot resurrect it', async () => {
    let signal: AbortSignal | undefined
    const pending = new Promise<ConversationHistoryPage>(() => undefined)
    const api: HistoryApi = {
      listHistory: vi.fn((next?: AbortSignal) => {
        signal = next
        return pending
      }),
    }
    render(<ChatHistory isTeam onSelectTask={vi.fn()} api={api} />)

    const trigger = screen.getByRole('button', { name: 'Conversation history' })
    fireEvent.click(trigger)
    await waitFor(() => expect(signal).toBeDefined())
    expect(signal?.aborted).toBe(false)

    fireEvent.click(trigger)
    expect(signal?.aborted).toBe(true)
    expect(screen.queryByRole('dialog')).toBeNull()
  })
})
