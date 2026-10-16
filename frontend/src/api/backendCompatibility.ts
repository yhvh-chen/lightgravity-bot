import { ApiError } from './client'
import { SCHEMA_NAMESPACE, type HealthResponse } from './types'

// This UI requires the shared-team authentication contract. Later additive
// 1.x releases are supported; execution/model readiness is a separate concern.
export const MINIMUM_BACKEND_CONTRACT = '1.13.0'
const REQUIRED_CAPABILITIES = [
  'store', 'coordinator', 'events_sse', 'settings', 'files', 'resources', 'global_chat',
] as const

export function backendIncompatible(reason: string): ApiError {
  return new ApiError({
    code: 'backend_incompatible',
    message: `Backend is incompatible: ${reason}. Update or restart the backend serving this page.`,
    httpStatus: null,
    retryable: true,
  })
}

/** Validate workspace APIs, without requiring a configured generation model. */
export function assertBackendCompatible(health: HealthResponse): void {
  const version = /^(\d+)\.(\d+)\.(\d+)$/.exec(health?.contract_version ?? '')
  if (!version || Number(version[1]) !== 1 || Number(version[2]) < 13) {
    throw backendIncompatible(`requires contract >= ${MINIMUM_BACKEND_CONTRACT} and < 2.0.0 (received ${health?.contract_version ?? 'unknown'})`)
  }
  if (health.schema_version !== SCHEMA_NAMESPACE) {
    throw backendIncompatible('unsupported workspace schema')
  }
  const missing = REQUIRED_CAPABILITIES.filter((name) => health.capabilities?.[name] !== true)
  if (missing.length) {
    throw backendIncompatible(`missing workspace capabilities: ${missing.join(', ')}`)
  }
  if (health.status !== 'ok') {
    throw new ApiError({ code: 'not_ready', message: 'Backend is not ready. Retry after startup finishes.', httpStatus: null, retryable: true })
  }
}

/** Personal is additive; a compatible shared workspace may lack this endpoint. */
export function supportsPersonalChat(health: HealthResponse): boolean {
  const version = /^(\d+)\.(\d+)\.(\d+)$/.exec(health?.contract_version ?? '')
  return Boolean(version && Number(version[1]) === 1 && Number(version[2]) >= 14 && health.capabilities?.personal_chat === true)
}
