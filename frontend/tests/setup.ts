import '@testing-library/jest-dom/vitest'

/**
 * Test setup (LG-011 extends the LG-002 skeleton).
 *
 * - jsdom has no matchMedia; default to the wide layout so the shell renders
 *   its in-flow columns. Tests that need compact/mobile call `setViewport`.
 * - The backend is not running under test, so `fetch` is stubbed with a real
 *   `HealthResponse` shape and a 404 error envelope for all other routes (which
 *   the views must render as real empty/error states, never faked data).
 */

export const HEALTH_FIXTURE = {
  status: 'ok',
  package_version: '0.1.0',
  contract_version: '1.0.0',
  schema_version: 'lightgravity.bot/v1',
  capabilities: {
    health: true,
    version: true,
    store: false,
    events_sse: false,
    sdk_adapter: false,
  },
}

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

globalThis.fetch = vi.fn(backendFetch) as unknown as typeof fetch

/** Reusable default backend stub; tests can reset to it after overriding. */
export function backendFetch(input: RequestInfo | URL): Promise<Response> {
  const url =
    typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
  if (url.endsWith('/api/v1/health')) {
    return Promise.resolve(jsonResponse(HEALTH_FIXTURE))
  }
  if (url.endsWith('/api/v1/version')) {
    return Promise.resolve(
      jsonResponse({
        contract_version: '1.0.0',
        schema_version: 'lightgravity.bot/v1',
        package_version: '0.1.0',
        python_version: '3.12.13',
        platform: 'linux-x86_64',
      }),
    )
  }
  return Promise.resolve(
    jsonResponse(
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
    ),
  )
}

function createMatchMedia(width: number): typeof window.matchMedia {
  return ((query: string) => {
    const max = /max-width:\s*(\d+)px/.exec(query)
    const matches = max ? width <= Number(max[1]) : false
    return {
      matches,
      media: query,
      onchange: null,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      addListener: () => undefined,
      removeListener: () => undefined,
      dispatchEvent: () => false,
    } as unknown as MediaQueryList
  }) as unknown as typeof window.matchMedia
}

/** Simulate a viewport width for the responsive shell. */
export function setViewport(width: number): void {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    configurable: true,
    value: createMatchMedia(width),
  })
}

// Default: desktop layout.
setViewport(1440)
