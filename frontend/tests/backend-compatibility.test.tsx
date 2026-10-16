import { cleanup, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { assertBackendCompatible, supportsPersonalChat } from '../src/api/backendCompatibility'
import { useBackendStatus } from '../src/api/useBackendStatus'
import { HEALTH_FIXTURE } from './setup'

afterEach(() => { cleanup(); vi.restoreAllMocks() })

describe('backend workspace compatibility', () => {
  it('rejects the live metadata-only 1.0 skeleton', () => {
    expect(() => assertBackendCompatible({ ...HEALTH_FIXTURE, contract_version: '1.0.0', capabilities: { health: true, version: true } })).toThrow(/requires contract/)
  })

  it.each(['1.13.1', '1.14.0'])('accepts additive contract %s with no generation model', (contract_version) => {
    expect(() => assertBackendCompatible({ ...HEALTH_FIXTURE, contract_version, capabilities: { ...HEALTH_FIXTURE.capabilities, sdk_adapter: false } })).not.toThrow()
  })

  it.each(['2.0.0', '1.13.0-preview', 'garbage'])('rejects unsupported contract %s', (contract_version) => {
    expect(() => assertBackendCompatible({ ...HEALTH_FIXTURE, contract_version })).toThrow(/requires contract/)
  })

  it('rejects missing core APIs even if the version claims compatibility', () => {
    expect(() => assertBackendCompatible({ ...HEALTH_FIXTURE, capabilities: { ...HEALTH_FIXTURE.capabilities, files: false } })).toThrow(/missing workspace capabilities: files/)
  })

  it('rejects a different schema and a backend that is not ready', () => {
    expect(() => assertBackendCompatible({ ...HEALTH_FIXTURE, schema_version: 'other/v1' })).toThrow(/schema/)
    expect(() => assertBackendCompatible({ ...HEALTH_FIXTURE, status: 'starting' })).toThrow(/not ready/)
  })

  it('reports a metadata-only health 200 as incompatible, not connected', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ ...HEALTH_FIXTURE, contract_version: '1.0.0' }), { headers: { 'Content-Type': 'application/json' } }))
    const { result } = renderHook(() => useBackendStatus())
    await waitFor(() => expect(result.current.state).toBe('unavailable'))
    expect(result.current.error?.code).toBe('backend_incompatible')
  })

  it('keeps network failure distinct from backend incompatibility', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('Connection refused'))
    const { result } = renderHook(() => useBackendStatus())
    await waitFor(() => expect(result.current.state).toBe('unavailable'))
    expect(result.current.error?.code).toBe('network_error')
  })

  it('connects when workspace APIs are ready without an SDK/model', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify(HEALTH_FIXTURE), { headers: { 'Content-Type': 'application/json' } }))
    const { result } = renderHook(() => useBackendStatus())
    await waitFor(() => expect(result.current.state).toBe('connected'))
    expect(result.current.health?.capabilities.sdk_adapter).toBe(false)
  })
})


describe('Personal capability compatibility', () => {
  it.each(['1.13.0', '1.13.9', '2.0.0'])('does not advertise private chat on unsupported contract %s', (contract_version) => {
    expect(supportsPersonalChat({ ...HEALTH_FIXTURE, contract_version })).toBe(false)
  })
  it.each(['1.14.0', '1.14.1', '1.15.0'])('accepts additive Personal contract %s with explicit capability', (contract_version) => {
    expect(supportsPersonalChat({ ...HEALTH_FIXTURE, contract_version })).toBe(true)
  })
  it('does not infer Personal from version alone, while keeping the shared workspace compatible', () => {
    const capabilities = { ...HEALTH_FIXTURE.capabilities }
    delete (capabilities as Partial<typeof capabilities>).personal_chat
    const health = { ...HEALTH_FIXTURE, capabilities }
    expect(() => assertBackendCompatible(health)).not.toThrow()
    expect(supportsPersonalChat(health)).toBe(false)
    expect(supportsPersonalChat({ ...health, capabilities: { ...capabilities, personal_chat: false } })).toBe(false)
  })
})
