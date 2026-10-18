import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError, apiRequest } from '../src/api/client'
import {
  emitSessionExpired,
  onSessionExpired,
  type SessionExpiredDetail,
} from '../src/api/session'
import { App } from '../src/App'
import { HEALTH_FIXTURE } from './setup'

/**
 * LG-219: centralized 401 handling.
 *
 * The request boundary emits one session-expiry signal; the auth gate decides
 * between the team login gate ("Session expired") and the single-user refresh
 * notice. Drafts stay in shell state/session preferences, so they survive the
 * gate. All fetches are stubbed; no backend, model or browser is used.
 */

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: {
      get: (name: string) =>
        name.toLowerCase() === 'content-type' ? 'application/json' : null,
    },
    json: async () => body,
  } as unknown as Response
}

function errorResponse(
  status: number,
  code: string,
  message: string,
  details: Record<string, unknown> = {},
): Response {
  return jsonResponse(
    {
      error: {
        code,
        message,
        details,
        retryable: false,
        request_id: null,
      },
    },
    status,
  )
}

function unauthorized(details: Record<string, unknown> = {}): Response {
  return errorResponse(401, 'unauthorized', 'authentication required', details)
}

function notFound(): Response {
  return errorResponse(404, 'not_found', 'not implemented')
}

function urlOf(input: RequestInfo | URL): string {
  return typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
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

describe('LG-219 apiRequest session-expiry signal', () => {
  let events: SessionExpiredDetail[] = []
  let unsubscribe: () => void = () => undefined

  beforeEach(() => {
    events = []
    unsubscribe = onSessionExpired((detail) => events.push(detail))
  })

  afterEach(() => {
    unsubscribe()
  })

  it('emits one signal for a business 401 and still rejects with the real ApiError', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => unauthorized()))

    await expect(apiRequest('/tasks')).rejects.toBeInstanceOf(ApiError)
    await expect(apiRequest('/tasks')).rejects.toMatchObject({
      code: 'unauthorized',
      httpStatus: 401,
    })

    expect(events).toHaveLength(2)
    expect(events[0]).toMatchObject({
      httpStatus: 401,
      code: 'unauthorized',
      path: '/tasks',
    })
  })

  it('does not treat a wrong login password as an expired session', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => unauthorized()))

    await expect(
      apiRequest('/auth/login', { method: 'POST', body: '{}' }),
    ).rejects.toMatchObject({ httpStatus: 401 })
    expect(events).toHaveLength(0)
  })

  it('does not treat a wrong current password as an expired session', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        unauthorized({ reason: 'invalid_current_password' }),
      ),
    )

    await expect(
      apiRequest('/account/password', { method: 'POST', body: '{}' }),
    ).rejects.toMatchObject({ httpStatus: 401 })
    expect(events).toHaveLength(0)
  })

  it('ignores non-401 failures', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => notFound()))

    await expect(apiRequest('/tasks/missing')).rejects.toMatchObject({
      httpStatus: 404,
    })
    expect(events).toHaveLength(0)
  })

  it('stops notifying after unsubscribe', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => unauthorized()))
    unsubscribe()

    await expect(apiRequest('/team/available')).rejects.toMatchObject({
      httpStatus: 401,
    })
    expect(events).toHaveLength(0)
  })
})

interface StubState {
  authMe?: () => Response
  login?: () => Response
  globalMessages?: (init?: RequestInit) => Response
}

function installFetch(stub: StubState = {}) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = urlOf(input)
    if (url.endsWith('/api/v1/auth/me')) {
      return stub.authMe ? stub.authMe() : notFound()
    }
    if (url.endsWith('/api/v1/auth/login')) {
      return stub.login ? stub.login() : jsonResponse({ username: 'alice', role: 'member' })
    }
    if (url.includes('/conversations/global/messages')) {
      return stub.globalMessages
        ? stub.globalMessages(init)
        : jsonResponse({ items: [], next_cursor: null })
    }
    if (url.endsWith('/api/v1/health')) {
      return jsonResponse(HEALTH_FIXTURE)
    }
    return notFound()
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('LG-219 auth gate integration', () => {
  it('team mode returns to the login gate with a notice and keeps the unsent draft', async () => {
    installFetch({
      authMe: () =>
        jsonResponse({ mode: 'team', authenticated: true, username: 'alice', role: 'member' }),
      login: () => jsonResponse({ username: 'alice', role: 'member' }),
      // Reads succeed; sending fails like a revoked/expired server session.
      globalMessages: (init) =>
        init?.method === 'POST'
          ? unauthorized()
          : jsonResponse({ items: [], next_cursor: null }),
    })

    render(<App />)

    const composer = await screen.findByLabelText('Message for Global')
    fireEvent.change(composer, { target: { value: 'unsent draft survives' } })
    expect(composer).toHaveValue('unsent draft survives')

    fireEvent.click(screen.getByRole('button', { name: 'Send message' }))

    // Centralized 401 → login gate with the honest explanation.
    expect(await screen.findByRole('main', { name: 'Sign in' })).toBeInTheDocument()
    expect(screen.getByText(/Session expired/)).toBeInTheDocument()
    expect(screen.getByText(/unsent draft is kept/)).toBeInTheDocument()

    // The draft is owned by shell state and mirrored to session preferences.
    await waitFor(() => {
      const prefs = window.sessionStorage.getItem('lg011.shell-prefs:team:alice')
      expect(prefs).toContain('unsent draft survives')
    })

    fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'alice' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'pw' } })
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    const restored = await screen.findByLabelText('Message for Global')
    expect(restored).toHaveValue('unsent draft survives')
  })

  it('single-user mode instructs a refresh instead of showing a login gate', async () => {
    installFetch({
      authMe: () =>
        jsonResponse({ mode: 'single', authenticated: true, username: null, role: 'admin' }),
    })

    render(<App />)
    await screen.findByLabelText('Message for Global')

    act(() => {
      emitSessionExpired({
        httpStatus: 401,
        code: 'unauthorized',
        path: '/settings/connections',
        details: {},
      })
    })

    expect(screen.getByRole('alert')).toHaveTextContent(/Session expired/)
    expect(screen.getByRole('alert')).toHaveTextContent(/Refresh the page/)
    expect(screen.getByRole('button', { name: 'Refresh page' })).toBeInTheDocument()
    expect(screen.queryByRole('main', { name: 'Sign in' })).toBeNull()
    // The workspace (and therefore drafts) stays mounted behind the notice.
    expect(
      screen.getByRole('navigation', { name: 'Primary navigation' }),
    ).toBeInTheDocument()
  })
})
