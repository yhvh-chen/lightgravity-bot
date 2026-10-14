/**
 * Settings/Connection API client (LG-026; docs/07, docs/08 §4.3).
 *
 * These wrappers call the real `/api/v1/settings*` routes that LG-025 exposes
 * and LG-012 mounts. There is exactly **one** Connection authority (the same
 * files Resources → Connections reads); this module never builds a second
 * provider/model list.
 *
 * Secret rule: credential *values* are only ever sent, never read back. The
 * wire only returns `credential.configured`/`source`/`version`; callers must
 * keep the typed value in transient form state and clear it after submit.
 *
 * The local access token is attached from the in-memory helper in `auth.ts`
 * and is required for the mutating routes. When it is missing the backend
 * default-denies with `unauthorized`; this module surfaces that real error
 * instead of pretending the write succeeded.
 */

import { getRuntimeToken } from './auth'
import { apiRequest } from './client'

export const PREFERRED_MODEL = 'deepseek-v4-flash'
export const DEFAULT_BASE_URL = 'https://api.deepseek.com/v1'
export const DEFAULT_EXECUTABLE_BACKEND = 'openai-compat'

/* ------------------------------------------------------------------ wire types */

export interface CredentialStatus {
  ref: string
  configured: boolean
  /** `secret_store` | `environment` | null */
  source: string | null
  version: string | null
}

export interface ConnectionReferences {
  connection_id: string
  default_roles: string[]
  agent_refs: string[]
}

/** Public Connection view — never contains a secret value. */
export interface ConnectionView {
  id: string
  title: string
  enabled: boolean
  revision: number
  content_hash: string
  backend: string
  model: string | null
  base_url: string | null
  credential_ref: string | null
  credential: CredentialStatus
  references: ConnectionReferences
}

/** `service._describe_default` output: a resolved connection or `{ref, resolved:false}`. */
export interface DefaultDescription {
  ref?: string
  resolved: boolean
  id?: string
  title?: string
  enabled?: boolean
  revision?: number
  content_hash?: string
  backend?: string
  model?: string | null
  base_url?: string | null
  credential_ref?: string | null
  credential?: CredentialStatus
  references?: ConnectionReferences
}

export interface GlobalSettingsView {
  revision: number
  exists: boolean
  content_hash: string
  default_coordinator_connection_ref: string | null
  default_worker_connection_ref: string | null
  defaults: {
    coordinator: DefaultDescription | null
    worker: DefaultDescription | null
  }
}

export interface TestLayer {
  name: string
  /** `passed` | `failed` | `skipped` | `declared` */
  status: string
  detail: string
  duration_ms: number | null
}

export interface ConnectionTestResult {
  test_id: string
  connection_id: string
  connection_revision: number
  credential_ref: string | null
  credential_version: string | null
  backend: string
  model: string | null
  base_url_host: string | null
  started_at: string
  finished_at: string
  layers: TestLayer[]
  /** `verified` | `partial` | `failed` | `not_run` */
  overall: string
  note: string
}

/* -------------------------------------------------------------- request inputs */

export interface ConnectionCreateInput {
  id: string
  title?: string | null
  backend?: string
  model?: string | null
  base_url?: string | null
  credential_ref?: string | null
  /** Write-only; never echoed back. */
  credential_value?: string | null
  enabled?: boolean
}

export type CredentialAction = 'keep' | 'set' | 'remove'

export interface ConnectionUpdateInput {
  expected_revision: number
  title?: string | null
  enabled?: boolean
  model?: string | null
  base_url?: string | null
  credential_ref?: string | null
  credential_action?: CredentialAction
  credential_value?: string | null
  clear_defaults?: boolean
}

export interface SettingsUpdateInput {
  expected_revision?: number
  default_coordinator_connection_ref?: string | null
  default_worker_connection_ref?: string | null
}

export interface ConnectionTestInput {
  expected_revision?: number
  allow_network?: boolean
  probe_tools?: boolean
  probe_structured?: boolean
}

/* ------------------------------------------------------------------ operations */

export interface SettingsApi {
  listConnections(signal?: AbortSignal): Promise<ConnectionView[]>
  getConnection(id: string, signal?: AbortSignal): Promise<ConnectionView>
  getSettings(signal?: AbortSignal): Promise<GlobalSettingsView>
  createConnection(
    input: ConnectionCreateInput,
    signal?: AbortSignal,
  ): Promise<ConnectionView>
  updateConnection(
    id: string,
    input: ConnectionUpdateInput,
    signal?: AbortSignal,
  ): Promise<ConnectionView>
  updateSettings(
    input: SettingsUpdateInput,
    signal?: AbortSignal,
  ): Promise<GlobalSettingsView>
  setCredential(
    ref: string,
    value: string,
    signal?: AbortSignal,
  ): Promise<CredentialStatus>
  keepCredential(ref: string, signal?: AbortSignal): Promise<CredentialStatus>
  removeCredential(ref: string, signal?: AbortSignal): Promise<CredentialStatus>
  testConnection(
    id: string,
    input: ConnectionTestInput,
    signal?: AbortSignal,
  ): Promise<ConnectionTestResult>
}

function headers(
  token: string | null,
  json: boolean,
): Record<string, string> {
  const result: Record<string, string> = { Accept: 'application/json' }
  if (json) result['Content-Type'] = 'application/json'
  if (token) result['X-LG-Token'] = token
  return result
}

function encodeRef(ref: string): string {
  return encodeURIComponent(ref)
}

/**
 * Build a {@link SettingsApi} bound to a token source. The default reads the
 * in-memory runtime token from `auth.ts` at call time so a late startup
 * injection is picked up without recreating the client.
 */
export function createSettingsApi(
  getToken: () => string | null = getRuntimeToken,
): SettingsApi {
  const token = () => getToken()

  return {
    async listConnections(signal) {
      const body = await apiRequest<{ items: ConnectionView[] }>(
        '/settings/connections',
        { headers: headers(token(), false), signal },
      )
      return body.items
    },

    getConnection(id, signal) {
      return apiRequest<ConnectionView>(
        `/settings/connections/${encodeURIComponent(id)}`,
        { headers: headers(token(), false), signal },
      )
    },

    getSettings(signal) {
      return apiRequest<GlobalSettingsView>('/settings', {
        headers: headers(token(), false),
        signal,
      })
    },

    createConnection(input, signal) {
      return apiRequest<ConnectionView>('/settings/connections', {
        method: 'POST',
        headers: headers(token(), true),
        body: JSON.stringify(input),
        signal,
      })
    },

    updateConnection(id, input, signal) {
      return apiRequest<ConnectionView>(
        `/settings/connections/${encodeURIComponent(id)}`,
        {
          method: 'PATCH',
          headers: headers(token(), true),
          body: JSON.stringify(input),
          signal,
        },
      )
    },

    updateSettings(input, signal) {
      return apiRequest<GlobalSettingsView>('/settings', {
        method: 'PATCH',
        headers: headers(token(), true),
        body: JSON.stringify(input),
        signal,
      })
    },

    setCredential(ref, value, signal) {
      return apiRequest<CredentialStatus>(
        `/settings/credentials/${encodeRef(ref)}`,
        {
          method: 'PUT',
          headers: headers(token(), true),
          body: JSON.stringify({ action: 'set', value }),
          signal,
        },
      )
    },

    keepCredential(ref, signal) {
      return apiRequest<CredentialStatus>(
        `/settings/credentials/${encodeRef(ref)}`,
        {
          method: 'PUT',
          headers: headers(token(), true),
          body: JSON.stringify({ action: 'keep', value: null }),
          signal,
        },
      )
    },

    removeCredential(ref, signal) {
      return apiRequest<CredentialStatus>(
        `/settings/credentials/${encodeRef(ref)}`,
        {
          method: 'DELETE',
          headers: headers(token(), false),
          signal,
        },
      )
    },

    testConnection(id, input, signal) {
      return apiRequest<ConnectionTestResult>(
        `/settings/connections/${encodeURIComponent(id)}/test`,
        {
          method: 'POST',
          headers: headers(token(), true),
          body: JSON.stringify(input),
          signal,
        },
      )
    },
  }
}
