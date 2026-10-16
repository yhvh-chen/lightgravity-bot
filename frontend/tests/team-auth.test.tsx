import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { App } from '../src/App'

/**
 * LG-050 team auth: login gate, logout, single-mode pass-through and the
 * administrator-only Settings entry. Every test stubs `fetch`; no real backend
 * or model is used.
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

function emptyResponse(status = 204): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: () => null },
    json: async () => null,
  } as unknown as Response
}

function notFound(): Response {
  return jsonResponse(
    {
      error: {
        code: 'not_found',
        message: 'not implemented',
        details: {},
        retryable: false,
        request_id: null,
      },
    },
    404,
  )
}

function unauthorized(): Response {
  return jsonResponse(
    {
      error: {
        code: 'unauthorized',
        message: 'authentication required',
        details: {},
        retryable: false,
        request_id: null,
      },
    },
    401,
  )
}

function urlOf(input: RequestInfo | URL): string {
  return typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
}

interface StubState {
  authMe?: () => Response
  login?: (body: unknown) => Response
  logout?: () => Response
  globalMessages?: () => Response
  taskMessages?: () => Response
}

function installFetch(stub: StubState = {}) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = urlOf(input)
    if (url.endsWith('/api/v1/auth/me')) {
      return stub.authMe ? stub.authMe() : notFound()
    }
    if (url.endsWith('/api/v1/auth/login')) {
      const body = init?.body ? JSON.parse(String(init.body)) : {}
      return stub.login ? stub.login(body) : jsonResponse({ username: 'alice', role: 'member' })
    }
    if (url.endsWith('/api/v1/auth/logout')) {
      return stub.logout ? stub.logout() : emptyResponse()
    }
    if (url.includes('/conversations/global/messages')) {
      return stub.globalMessages ? stub.globalMessages() : jsonResponse({ items: [], next_cursor: null })
    }
    if (url.includes('/tasks') && url.includes('/messages')) {
      return stub.taskMessages ? stub.taskMessages() : jsonResponse({ items: [], next_cursor: null })
    }
    if (url.endsWith('/api/v1/health')) {
      return jsonResponse({ status: 'ok', package_version: '0.1.0', contract_version: '1.0.0', schema_version: 'lightgravity.bot/v1', capabilities: {} })
    }
    return notFound()
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
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

describe('LG-050 auth: login gate', () => {
  it('shows the login gate for an unauthenticated team session and enters the workspace after login', async () => {
    const fetchMock = installFetch({
      authMe: () =>
        jsonResponse({ mode: 'team', authenticated: false, username: null, role: null }),
      login: (body) =>
        (body as { username: string }).username === 'alice'
          ? jsonResponse({ username: 'alice', role: 'member' })
          : unauthorized(),
    })

    render(<App />)

    // Gate appears once the probe resolves.
    expect(await screen.findByRole('main', { name: 'Sign in' })).toBeInTheDocument()
    expect(screen.queryByRole('navigation', { name: 'Primary navigation' })).toBeNull()

    fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'alice' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'pw' } })
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    // Workspace + real identity appear; login request carried credentials.
    expect(await screen.findByRole('navigation', { name: 'Primary navigation' })).toBeInTheDocument()
    expect(await screen.findByText('alice')).toBeInTheDocument()
    const loginCall = fetchMock.mock.calls.find((call) => urlOf(call[0]).endsWith('/auth/login'))
    expect(loginCall?.[1]).toMatchObject({ credentials: 'include', method: 'POST' })
  })

  it('rejects bad credentials without leaving the gate and clears the password', async () => {
    installFetch({
      authMe: () =>
        jsonResponse({ mode: 'team', authenticated: false, username: null, role: null }),
      login: () => unauthorized(),
    })

    render(<App />)
    await screen.findByRole('main', { name: 'Sign in' })

    fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'alice' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'wrong' } })
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByText('Invalid username or password.')).toBeInTheDocument()
    expect(screen.getByLabelText('Password')).toHaveValue('')
    expect(screen.queryByRole('navigation', { name: 'Primary navigation' })).toBeNull()
  })

  it('keeps the existing single-user workspace with no gate', async () => {
    installFetch({
      authMe: () =>
        jsonResponse({ mode: 'single', authenticated: true, username: null, role: 'admin' }),
    })
    render(<App />)
    expect(await screen.findByRole('navigation', { name: 'Primary navigation' })).toBeInTheDocument()
    expect(screen.queryByRole('main', { name: 'Sign in' })).toBeNull()
    // No identity/sign-out chrome in single-user mode.
    expect(screen.queryByRole('button', { name: 'Sign out' })).toBeNull()
  })

  it('falls back to single-user behavior when the backend has no /auth/me', async () => {
    installFetch()
    render(<App />)
    expect(await screen.findByRole('navigation', { name: 'Primary navigation' })).toBeInTheDocument()
    expect(screen.queryByRole('main', { name: 'Sign in' })).toBeNull()
  })
})

describe('LG-050 auth: identity, logout and admin entry', () => {
  it('shows the authenticated identity and returns to the gate on sign out', async () => {
    installFetch({
      authMe: () =>
        jsonResponse({ mode: 'team', authenticated: true, username: 'root', role: 'admin' }),
      logout: () => emptyResponse(),
    })
    render(<App />)

    expect(await screen.findByText('root')).toBeInTheDocument()
    expect(screen.getByText('admin')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Sign out' }))

    expect(await screen.findByRole('main', { name: 'Sign in' })).toBeInTheDocument()
  })

  it('enables Settings for an admin and disables it for a member', async () => {
    installFetch({
      authMe: () =>
        jsonResponse({ mode: 'team', authenticated: true, username: 'root', role: 'admin' }),
    })
    render(<App />)
    const adminSettings = await screen.findByRole('button', { name: 'Settings' })
    expect(adminSettings).toBeEnabled()

    cleanup()
    installFetch({
      authMe: () =>
        jsonResponse({ mode: 'team', authenticated: true, username: 'bob', role: 'member' }),
    })
    render(<App />)
    const memberSettings = await screen.findByRole('button', { name: 'Settings' })
    await waitFor(() => expect(memberSettings).toBeDisabled())
    expect(memberSettings).toHaveAttribute('title', 'Administrator only')
  })

  it('returns to the login gate when a request reports an expired session (401)', async () => {
    installFetch({
      authMe: () =>
        jsonResponse({ mode: 'team', authenticated: true, username: 'bob', role: 'member' }),
      globalMessages: () => unauthorized(),
    })
    render(<App />)

    // The workspace briefly mounts, then the real 401 hands control to the gate.
    expect(await screen.findByRole('main', { name: 'Sign in' })).toBeInTheDocument()
  })
})
