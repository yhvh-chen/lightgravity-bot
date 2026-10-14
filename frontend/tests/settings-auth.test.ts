import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

type AuthModule = typeof import('../src/api/auth')

async function loadAuth(): Promise<AuthModule> {
  vi.resetModules()
  return import('../src/api/auth')
}

beforeEach(() => {
  delete window.__LG_RUNTIME_TOKEN__
  window.localStorage.clear()
  window.sessionStorage.clear()
})

afterEach(() => {
  delete window.__LG_RUNTIME_TOKEN__
})

describe('LG-026 runtime token helper', () => {
  it('returns null by default and never touches browser storage', async () => {
    const auth = await loadAuth()
    expect(auth.getRuntimeToken()).toBeNull()
    expect(auth.hasRuntimeToken()).toBe(false)
    auth.setRuntimeToken('secret-token-value')
    expect(auth.getRuntimeToken()).toBe('secret-token-value')
    expect(auth.hasRuntimeToken()).toBe(true)
    expect(JSON.stringify(window.localStorage)).not.toContain('secret-token-value')
    expect(JSON.stringify(window.sessionStorage)).not.toContain('secret-token-value')
  })

  it('reads the non-persistent trusted-page bootstrap global', async () => {
    window.__LG_RUNTIME_TOKEN__ = 'boot-token'
    const auth = await loadAuth()
    expect(auth.getRuntimeToken()).toBe('boot-token')
  })

  it('lets an explicit clear override the bootstrap global', async () => {
    window.__LG_RUNTIME_TOKEN__ = 'boot-token'
    const auth = await loadAuth()
    auth.clearRuntimeToken()
    expect(auth.getRuntimeToken()).toBeNull()
  })

  it('builds request headers only when a token is present', async () => {
    const auth = await loadAuth()
    expect(auth.runtimeTokenHeaders(null, { Accept: 'application/json' })).toEqual({
      Accept: 'application/json',
    })
    expect(auth.runtimeTokenHeaders('abc')).toEqual({ 'X-LG-Token': 'abc' })
  })
})
