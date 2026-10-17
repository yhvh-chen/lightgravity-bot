import { HEALTH_FIXTURE } from './setup'
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
      return jsonResponse(HEALTH_FIXTURE)
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

  it('keeps an unsupported backend without /auth/me behind the error gate', async () => {
    installFetch()
    render(<App />)
    expect(await screen.findByText(/authentication discovery \/auth\/me is missing/)).toBeInTheDocument()
    expect(screen.queryByRole('navigation', { name: 'Primary navigation' })).toBeNull()
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

  it('enables Settings for both roles; members reach only My Account', async () => {
    installFetch({
      authMe: () =>
        jsonResponse({ mode: 'team', authenticated: true, username: 'root', role: 'admin' }),
    })
    render(<App />)
    const adminSettings = await screen.findByRole('button', { name: 'Settings' })
    expect(adminSettings).toBeEnabled()
    fireEvent.click(adminSettings)
    expect(await screen.findByRole('tab', { name: 'Models & Providers' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Accounts' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'My Account' })).toBeInTheDocument()

    cleanup()
    installFetch({
      authMe: () =>
        jsonResponse({ mode: 'team', authenticated: true, username: 'bob', role: 'member' }),
    })
    render(<App />)
    const memberSettings = await screen.findByRole('button', { name: 'Settings' })
    await waitFor(() => expect(memberSettings).toBeEnabled())
    fireEvent.click(memberSettings)
    expect(await screen.findByRole('heading', { name: 'My Account' })).toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: 'Models & Providers' })).toBeNull()
    expect(screen.queryByRole('tab', { name: 'Accounts' })).toBeNull()
    // The member settings never issued a Models/Connections or admin-list call.
    const accountListCalls = vi
      .mocked(fetch)
      .mock.calls.filter((call) => urlOf(call[0]).endsWith('/api/v1/accounts'))
    expect(accountListCalls).toHaveLength(0)
    const settingsCalls = vi
      .mocked(fetch)
      .mock.calls.filter((call) => urlOf(call[0]).includes('/api/v1/settings'))
    expect(settingsCalls).toHaveLength(0)
  })

  it('shows My Account plus an honest admin-only notice for an explicit member connection target', async () => {
    window.history.replaceState(
      null,
      '',
      '/?view=settings&item=settings:connection:deepseek&task=task_real',
    )
    const fetchMock = installFetch({
      authMe: () =>
        jsonResponse({ mode: 'team', authenticated: true, username: 'bob', role: 'member' }),
    })
    render(<App />)

    expect(
      await screen.findByText(/configuration is managed by\s+administrators/),
    ).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'My Account' })).toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: 'Models & Providers' })).toBeNull()
    expect(screen.queryByRole('tab', { name: 'Accounts' })).toBeNull()
    expect(window.location.search).toContain('view=settings')
    expect(window.location.search).toContain('task=task_real')
    expect(window.location.search).toContain('item=settings%3Aconnection%3Adeepseek')
    const settingsCalls = fetchMock.mock.calls.filter((call) =>
      urlOf(call[0]).includes('/api/v1/settings'),
    )
    expect(settingsCalls).toHaveLength(0)
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

describe('LG-050 auth: probe states are explicit (no optimistic single fallback)', () => {
  it('shows Loading while the probe is pending and does not mount the workspace', async () => {
    let release: (response: Response) => void = () => undefined
    const pending = new Promise<Response>((resolve) => {
      release = resolve
    })
    installFetch({ authMe: () => pending as unknown as Response })
    render(<App />)

    expect(
      screen.getByRole('status', { name: 'Checking authentication' }),
    ).toBeInTheDocument()
    expect(screen.queryByRole('navigation', { name: 'Primary navigation' })).toBeNull()
    expect(screen.queryByRole('main', { name: 'Sign in' })).toBeNull()

    release(
      jsonResponse({ mode: 'team', authenticated: false, username: null, role: null }),
    )
    expect(await screen.findByRole('main', { name: 'Sign in' })).toBeInTheDocument()
  })

  it('surfaces a retryable network error instead of falling back to single-user', async () => {
    let mode: 'fail' | 'team' = 'fail'
    installFetch({
      authMe: () => {
        if (mode === 'fail') throw new Error('Connection refused')
        return jsonResponse({ mode: 'team', authenticated: false, username: null, role: null })
      },
    })
    render(<App />)

    expect(await screen.findByText('Cannot reach the server')).toBeInTheDocument()
    // It never silently shows the single-user workspace.
    expect(screen.queryByRole('navigation', { name: 'Primary navigation' })).toBeNull()

    mode = 'team'
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findByRole('main', { name: 'Sign in' })).toBeInTheDocument()
  })

  it('treats an unknown auth mode as an error, not single-user', async () => {
    installFetch({
      authMe: () =>
        jsonResponse({ mode: 'weird', authenticated: true, username: null, role: null }),
    })
    render(<App />)

    expect(await screen.findByText('Cannot reach the server')).toBeInTheDocument()
    expect(screen.queryByRole('navigation', { name: 'Primary navigation' })).toBeNull()
  })
})
