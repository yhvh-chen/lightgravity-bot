import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { ChatApi, ChatMessage } from '../src/api/chat'
import type { AuthMeResponse } from '../src/api/teamAuth'
import { AuthProvider } from '../src/app/AuthProvider'
import { ShellProvider } from '../src/app/ShellProvider'
import { ChatBody } from '../src/views/chat/ChatBody'

/**
 * LG-054 frontend channel regressions.
 *
 * These exercise the Personal/Team tabs, channel-scoped drafts, Task=>Team
 * scope and late-response isolation with a stubbed chat API (no backend/model).
 * The two-user HTTP privacy guarantee is covered by the backend test
 * `tests/team/test_personal_conversation.py` and the Playwright two-context
 * browser test.
 */

const TEAM_PROBE = async (): Promise<AuthMeResponse> => ({
  mode: 'team',
  authenticated: true,
  username: 'alice',
  role: 'member',
})

const SINGLE_PROBE = async (): Promise<AuthMeResponse> => ({
  mode: 'single',
  authenticated: true,
  username: null,
  role: 'admin',
})

beforeEach(() => {
  window.sessionStorage.clear()
  window.history.replaceState(null, '', '/')
})

afterEach(cleanup)

interface ApiHarness {
  api: ChatApi
  reads: Array<{ taskRef: string | null; personal?: boolean }>
  sends: Array<{ taskRef: string | null; personal?: boolean }>
}

function makeApi(read?: ChatApi['readMessages']): ApiHarness {
  const reads: Array<{ taskRef: string | null; personal?: boolean }> = []
  const sends: Array<{ taskRef: string | null; personal?: boolean }> = []
  const api: ChatApi = {
    readMessages: vi.fn(async (scope, cursor, signal) => {
      reads.push(scope)
      if (read) return read(scope, cursor, signal)
      return { items: [], next_cursor: null }
    }),
    sendMessage: vi.fn(async (scope) => {
      sends.push(scope)
      return { kind: 'direct', reply: 'ok' }
    }),
    createTask: vi.fn(async () => ({ kind: 'create_task' })),
  }
  return { api, reads, sends }
}

function renderChat(probe: () => Promise<AuthMeResponse>, api: ChatApi) {
  return render(
    <AuthProvider probe={probe}>
      <ShellProvider>
        <ChatBody variant="main" api={api} />
      </ShellProvider>
    </AuthProvider>,
  )
}

describe('LG-054 Personal / Team channel tabs', () => {
  it('shows accessible tabs, defaults to Team in team mode and switches to a private Personal scope', async () => {
    const { api, reads } = makeApi()
    renderChat(TEAM_PROBE, api)

    const personalTab = await screen.findByRole('tab', { name: 'Personal' })
    const teamTab = screen.getByRole('tab', { name: 'Team' })
    expect(teamTab).toBeEnabled()
    await waitFor(() => expect(teamTab).toHaveAttribute('aria-selected', 'true'))

    fireEvent.click(personalTab)
    await waitFor(() => expect(personalTab).toHaveAttribute('aria-selected', 'true'))
    await waitFor(() =>
      expect(reads.some((scope) => scope.personal === true && scope.taskRef === null)).toBe(true),
    )
    // Personal hides shared-material tools. The old permanent footer hint is
    // gone; LG-119 provides a real private Upload file button (disabled here
    // because the test health fixture does not advertise private_attachments).
    expect(screen.queryByRole('button', { name: 'Add attachments and materials' })).toBeNull()
    expect(screen.queryByText(/Shared materials and task delivery are available in Team/)).toBeNull()
    const upload = screen.getByRole('button', { name: 'Upload file' })
    await waitFor(() => expect(upload).toBeDisabled())
    // The shared Team read never used the personal endpoint.
    expect(reads[0]).toMatchObject({ taskRef: null, personal: false })
  })

  it('keeps Personal and Team drafts isolated', async () => {
    const { api } = makeApi()
    renderChat(TEAM_PROBE, api)

    const teamComposer = await screen.findByLabelText('Message for Global')
    fireEvent.change(teamComposer, { target: { value: 'team draft' } })

    fireEvent.click(screen.getByRole('tab', { name: 'Personal' }))
    const personalComposer = await screen.findByLabelText('Message for Personal')
    expect(personalComposer).toHaveValue('')

    fireEvent.change(personalComposer, { target: { value: 'private draft' } })

    fireEvent.click(screen.getByRole('tab', { name: 'Team' }))
    const teamAgain = await screen.findByLabelText('Message for Global')
    expect(teamAgain).toHaveValue('team draft')

    fireEvent.click(screen.getByRole('tab', { name: 'Personal' }))
    expect(await screen.findByLabelText('Message for Personal')).toHaveValue('private draft')
  })

  it('opens a Task as a shared Team conversation with the exact task_ref', async () => {
    window.history.replaceState(null, '', '/?view=chat&task=task_real_1')
    const { api, reads } = makeApi()
    renderChat(TEAM_PROBE, api)

    await waitFor(() =>
      expect(reads.some((scope) => scope.taskRef === 'task_real_1' && !scope.personal)).toBe(true),
    )
    expect(await screen.findByLabelText('Message for task_real_1')).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Team' })).toHaveAttribute('aria-selected', 'true')

    // Switching to Personal safely leaves the Task scope (no task leak).
    fireEvent.click(screen.getByRole('tab', { name: 'Personal' }))
    expect(await screen.findByLabelText('Message for Personal')).toBeInTheDocument()
    await waitFor(() =>
      expect(window.location.search).not.toContain('task=task_real_1'),
    )
    expect(
      reads.some((scope) => scope.personal === true && scope.taskRef === null),
    ).toBe(true)
  })

  it('shows a disabled Team tab with a truthful note in single-user mode', async () => {
    const { api } = makeApi()
    renderChat(SINGLE_PROBE, api)

    const teamTab = await screen.findByRole('tab', { name: 'Team' })
    expect(teamTab).toBeDisabled()
    expect(teamTab).toHaveAttribute(
      'title',
      'Enable team mode on the backend to use the shared team conversation',
    )
    expect(
      screen.getByText(/Team mode is not enabled on this backend/),
    ).toBeInTheDocument()
    // Single-user mode shows the legacy Global label and no private-only copy.
    expect(screen.getByLabelText('Message for Global')).toBeInTheDocument()
  })

  it('never renders a late response from the channel that was left', async () => {
    let releaseTeam: (value: { items: ChatMessage[]; next_cursor: string | null }) => void = () => undefined
    const teamRead = new Promise<{ items: ChatMessage[]; next_cursor: string | null }>((resolve) => {
      releaseTeam = resolve
    })
    const personalMessage: ChatMessage = {
      message_id: 'msg_personal',
      role: 'assistant',
      content: 'private answer',
      attachments: [],
    }
    const { api } = makeApi((scope) => {
      if (scope.personal) {
        return Promise.resolve({ items: [personalMessage], next_cursor: null })
      }
      return teamRead
    })
    renderChat(TEAM_PROBE, api)

    // Leave the still-pending shared Team read for Personal.
    fireEvent.click(await screen.findByRole('tab', { name: 'Personal' }))
    expect(await screen.findByText('private answer')).toBeInTheDocument()

    releaseTeam({
      items: [{ message_id: 'msg_team', role: 'assistant', content: 'stale team answer', attachments: [] }],
      next_cursor: null,
    })
    // The aborted Team read must never paint into the Personal conversation.
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(screen.queryByText('stale team answer')).toBeNull()
    expect(screen.getByText('private answer')).toBeInTheDocument()
  })
})
