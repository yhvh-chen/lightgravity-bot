import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { ChatApi, ChatSubmitResult } from '../src/api/chat'
import type { AuthMeResponse } from '../src/api/teamAuth'
import { AuthProvider } from '../src/app/AuthProvider'
import { ShellProvider } from '../src/app/ShellProvider'
import { ChatBody, configuredTeamBotMention } from '../src/views/chat/ChatBody'
import { HEALTH_FIXTURE, backendFetch } from './setup'

/**
 * LG-249 UI hint: Team Global/Task ordinary messages are recorded only, and a
 * bot turn requires the leading mention configured by the backend. The tests
 * use a non-default mention so a hardcoded `@bot` cannot pass, and verify the
 * single-user and private Personal channels keep their old composer.
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

const CONFIGURED_MENTION = '!lg'
const EXPECTED_HINT = `Start with ${CONFIGURED_MENTION} to ask the assistant or create a task.`

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: () => 'application/json' },
    json: async () => body,
  } as unknown as Response
}

/** Publish a real health response, optionally with the backend mention field. */
function installHealth(mention?: string): void {
  const health: Record<string, unknown> = { ...HEALTH_FIXTURE }
  if (mention !== undefined) health.team_bot_mention = mention
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url =
        typeof input === 'string'
          ? input
          : input instanceof URL
            ? input.href
            : input.url
      if (url.endsWith('/api/v1/health')) return jsonResponse(health)
      return backendFetch(input)
    }),
  )
}

function makeApi(result: ChatSubmitResult = { kind: 'answer', reply: 'ok' }): {
  api: ChatApi
  sent: Array<{ taskRef: string | null; content: string }>
} {
  const sent: Array<{ taskRef: string | null; content: string }> = []
  return {
    sent,
    api: {
      readMessages: vi.fn(async () => ({ items: [], next_cursor: null })),
      sendMessage: vi.fn(async (scope, body) => {
        sent.push({ taskRef: scope.taskRef, content: body.content })
        return result
      }),
      createTask: vi.fn(async () => ({ kind: 'create_task' })),
    },
  }
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

beforeEach(() => {
  window.sessionStorage.clear()
  window.history.replaceState(null, '', '/')
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('LG-249 configured Team mention hint', () => {
  it('uses the configured mention in both Global and Task placeholders, never @bot', async () => {
    installHealth(CONFIGURED_MENTION)
    renderChat(TEAM_PROBE, makeApi().api)

    const globalComposer = await screen.findByLabelText('Message for Global')
    await waitFor(() => expect(globalComposer).toHaveAttribute('placeholder', EXPECTED_HINT))
    expect(globalComposer.getAttribute('placeholder')).not.toContain('@bot')

    cleanup()
    window.history.replaceState(null, '', '/?view=chat&task=task_real_1')
    renderChat(TEAM_PROBE, makeApi().api)

    const taskComposer = await screen.findByLabelText('Message for task_real_1')
    await waitFor(() => expect(taskComposer).toHaveAttribute('placeholder', EXPECTED_HINT))
    expect(taskComposer.getAttribute('placeholder')).not.toContain('@bot')
  })

  it('keeps a plain Team message silent and explains the configured mention in the receipt', async () => {
    installHealth(CONFIGURED_MENTION)
    const { api, sent } = makeApi({ kind: 'recorded', reply: null })
    renderChat(TEAM_PROBE, api)

    const composer = await screen.findByLabelText('Message for Global')
    await waitFor(() => expect(composer).toHaveAttribute('placeholder', EXPECTED_HINT))
    fireEvent.change(composer, { target: { value: 'Ben plain feedback' } })
    fireEvent.keyDown(composer, { key: 'Enter' })

    const receipt = await screen.findByText(/Recorded for the team; no bot reply was started/)
    expect(receipt).toHaveTextContent(EXPECTED_HINT)
    expect(receipt).not.toHaveTextContent('@bot')
    // The hint is UI copy only: the ordinary message body is sent unchanged.
    expect(sent).toEqual([{ taskRef: null, content: 'Ben plain feedback' }])
  })

  it('leaves Personal and single-user composers unchanged', async () => {
    installHealth(CONFIGURED_MENTION)
    renderChat(TEAM_PROBE, makeApi().api)

    const teamComposer = await screen.findByLabelText('Message for Global')
    await waitFor(() => expect(teamComposer).toHaveAttribute('placeholder', EXPECTED_HINT))
    fireEvent.click(screen.getByRole('tab', { name: 'Personal' }))
    expect(await screen.findByLabelText('Message for Personal')).toHaveAttribute(
      'placeholder',
      'Message…',
    )

    cleanup()
    window.history.replaceState(null, '', '/')
    renderChat(SINGLE_PROBE, makeApi().api)

    const singleComposer = await screen.findByLabelText('Message for Global')
    expect(singleComposer).toHaveAttribute('placeholder', 'Message…')
    expect(screen.queryByText(/Start with/)).toBeNull()
  })

  it('does not invent a mention when the backend omits it', async () => {
    installHealth()
    const { api } = makeApi({ kind: 'recorded', reply: null })
    renderChat(TEAM_PROBE, api)

    const composer = await screen.findByLabelText('Message for Global')
    expect(composer).toHaveAttribute('placeholder', 'Message…')
    fireEvent.change(composer, { target: { value: 'plain team note' } })
    fireEvent.keyDown(composer, { key: 'Enter' })

    expect(await screen.findByText('Shared with the team.')).toBeInTheDocument()
    expect(screen.queryByText(/Start with/)).toBeNull()
    expect(screen.queryByText(/@bot/)).toBeNull()
  })
})

describe('LG-249 configured mention parsing', () => {
  it('accepts only a non-blank string and trims surrounding whitespace', () => {
    expect(configuredTeamBotMention('  !lg  ')).toBe('!lg')
    expect(configuredTeamBotMention('')).toBeNull()
    expect(configuredTeamBotMention('   ')).toBeNull()
    expect(configuredTeamBotMention(undefined)).toBeNull()
    expect(configuredTeamBotMention(null)).toBeNull()
    expect(configuredTeamBotMention(42)).toBeNull()
  })
})
