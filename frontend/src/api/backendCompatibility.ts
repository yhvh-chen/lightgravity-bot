import { ApiError } from './client'
import { SCHEMA_NAMESPACE, type HealthResponse } from './types'

// This UI requires the shared-team authentication contract. Later additive
// 1.x releases are supported; execution/model readiness is a separate concern.
export const MINIMUM_BACKEND_CONTRACT = '1.13.0'
/** docs/08 §20 material intake v2 is additive from contract 1.19.0. */
export const MINIMUM_MATERIAL_INTAKE_CONTRACT = '1.19.0'

/** Health capability names frozen by docs/08 §20.2 (all default false). */
export const MATERIAL_INTAKE_V2_CAPABILITY = 'material_intake_v2'
export const SEMANTIC_SEARCH_CAPABILITY = 'semantic_search'
export const MEDIA_DIRECT_EMBEDDING_CAPABILITY = 'media_direct_embedding'

const REQUIRED_CAPABILITIES = [
  'store', 'coordinator', 'events_sse', 'settings', 'files', 'resources', 'global_chat',
] as const

/** Contract minor for a strict 1.x version, or null when unsupported/garbage. */
function contractMinor(health: HealthResponse | null | undefined): number | null {
  const version = /^(\d+)\.(\d+)\.(\d+)$/.exec(health?.contract_version ?? '')
  if (!version || Number(version[1]) !== 1) return null
  return Number(version[2])
}

function supportsAdditiveCapability(
  health: HealthResponse,
  minimumMinor: number,
  capability: string,
): boolean {
  const minor = contractMinor(health)
  return Boolean(
    minor !== null && minor >= minimumMinor && health.capabilities?.[capability] === true,
  )
}

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
  return supportsAdditiveCapability(health, 14, 'personal_chat')
}

/**
 * LG-062 account management is additive (contract >= 1.15) and team-only.
 * Older/single-user backends report the capability false and the UI must not
 * advertise an account surface that does not exist.
 */
export function supportsAccounts(health: HealthResponse): boolean {
  return supportsAdditiveCapability(health, 15, 'accounts')
}

/**
 * docs/08 §20.2 gate for the whole material-intake v2 UI: deferred intake,
 * receipt branches, message `source_refs`. A 1.18 backend (or a 1.19 backend
 * that has not really wired the worker) reports false; the UI must then keep
 * the existing 1.18 upload/search flow and never infer support from a 404.
 */
export function supportsMaterialIntakeV2(health: HealthResponse): boolean {
  return supportsAdditiveCapability(health, 19, MATERIAL_INTAKE_V2_CAPABILITY)
}

/**
 * Gate for the Keyword/Semantic search toggle. This does not mean embedding is
 * configured; callers still read `/vector/status.enabled` for real availability.
 */
export function supportsSemanticSearch(health: HealthResponse): boolean {
  return supportsAdditiveCapability(health, 19, SEMANTIC_SEARCH_CAPABILITY)
}

/**
 * Gate for the direct image/audio embedding path. The media badge must also
 * check that the source's own receipt reports an `image`/`audio` kind, so this
 * capability alone never claims a particular source was indexed.
 */
export function supportsMediaDirectEmbedding(health: HealthResponse): boolean {
  return supportsAdditiveCapability(health, 19, MEDIA_DIRECT_EMBEDDING_CAPABILITY)
}
