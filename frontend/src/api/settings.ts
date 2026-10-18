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
import type { EnglishAsrSettingsView } from './englishAsr'

export const PREFERRED_MODEL = 'deepseek-v4-flash'
export const DEFAULT_BASE_URL = 'https://api.deepseek.com/v1'
export const DEFAULT_EXECUTABLE_BACKEND = 'openai-compat'

/** SDK 0.1.22 `models.DEFAULT_MODEL` (LG-105 audit). */
export const GEMINI_DEFAULT_MODEL = 'gemini-3.8-flash'

/**
 * Optional provider auth selector (LG-104/LG-106). These values are stored as
 * non-secret Connection fields and map to the installed SDK's real auth paths:
 * API key, Application Default Credentials (ADC), the product's loopback
 * proxy key path, or no credential at all (local LiteRT).
 */
export type ConnectionAuthMode = 'api_key' | 'adc' | 'proxy_api_key' | 'none'

/** LiteRT on-device runtime backend (SDK field `backend`). */
export type LiteRtBackend = 'CPU' | 'GPU' | 'NPU'

/**
 * Capability declaration for a Connection (LG-104). These are deliberately
 * separate facts and must never be inferred from one another:
 *
 * * `configurable` — the backend accepts/saves the provider configuration;
 * * `testable` — Test Connection can run its real layers;
 * * `executable` — the product executor may use it (and it may be a default);
 * * `vendor_verified` — evidence of a real vendor call exists.
 *
 * `null`/absent means the backend has not declared that fact. The frontend
 * only falls back to preset metadata for the already-existing DeepSeek path.
 */
export interface ConnectionCapabilities {
  configurable?: boolean | null
  testable?: boolean | null
  executable?: boolean | null
  vendor_verified?: boolean | null
}

/* ------------------------------------------------------------------ wire types */

export interface CredentialStatus {
  ref: string | null
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
  /* LG-104 optional non-secret provider fields; absent on old connections. */
  auth_mode?: ConnectionAuthMode | null
  project?: string | null
  location?: string | null
  model_path?: string | null
  litert_backend?: LiteRtBackend | null
  /** Backend-declared capability facts; absent/null means not declared. */
  capabilities?: ConnectionCapabilities | null
  /**
   * LG-110: latest *persisted* safe test summary, when the backend exposes it.
   * Draft tests are never written here. A missing value means the backend has
   * not declared a persisted test result; the UI must not invent one.
   */
  last_test?: PersistedConnectionTestStatus | null
}

/** Safe, non-secret summary of a persisted connection test. */
export interface PersistedConnectionTestStatus {
  test_id?: string
  /** `verified` | `partial` | `failed` | `not_run` (or backend value). */
  overall: string
  finished_at: string
  connection_revision?: number | null
  credential_version?: string | null
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

/* ------------------------------------------------ LG-117 Embedding purpose */

export interface EmbeddingCacheView {
  compatible: boolean | null
  reason: string | null
  vector_model: string | null
}

/**
 * Independent Embedding usage view (docs/08 §19.4). It is never a chat,
 * coordinator, worker or reviewer default. Credential values are never present.
 */
export interface EmbeddingSettingsView {
  enabled: boolean
  base_url: string | null
  model: string | null
  timeout_seconds: number
  cold_timeout_seconds: number
  source: 'settings' | 'environment' | 'none' | string
  credential: CredentialStatus
  cache: EmbeddingCacheView
}

export interface EmbeddingUpdateInput {
  expected_revision: number
  enabled: boolean
  base_url: string | null
  model: string | null
  credential_action: CredentialAction
  /** Write-only; only sent for `credential_action: 'set'`. */
  credential_value?: string | null
  timeout_seconds?: number
  cold_timeout_seconds?: number
}

export interface EmbeddingUpdateResult extends EmbeddingSettingsView {
  revision: number
  content_hash: string
}

export interface EmbeddingDraftTestInput {
  base_url: string | null
  model: string | null
  credential_value?: string
  use_existing_credential: boolean
  /** The frontend Test button is the explicit network opt-in. */
  allow_network: boolean
  timeout_seconds?: number
  cold_timeout_seconds?: number
}

export interface EmbeddingDraftCheck {
  name: string
  status: 'passed' | 'failed' | 'skipped' | string
  detail: string
}

/** POST /settings/embedding/test-draft; never saved and never a retrieval claim. */
export interface EmbeddingDraftTestResult {
  draft: true
  overall: 'verified' | 'partial' | 'failed' | 'not_run' | string
  requested_model: string | null
  reported_model: string | null
  dim: number | null
  latency_seconds: number | null
  finished_at: string
  credential_source: 'secret_store' | 'environment' | 'none' | string
  checks: EmbeddingDraftCheck[]
  error: { code?: string; message: string } | null
  cache_impact: 'none' | 'rebuild_required' | string
}

export interface GlobalSettingsView {
  runtime_applied?: boolean
  runtime_message?: string
  revision: number
  exists: boolean
  content_hash: string
  default_coordinator_connection_ref: string | null
  default_worker_connection_ref: string | null
  /**
   * LG-017 additive: the independent reviewer's own default connection/credential
   * (a separate role from the implementer). `null` means no real reviewer is
   * configured, so the runtime reports an honest `unavailable` instead of
   * reviewing with the implementer's connection (docs/08 §6.5).
   */
  default_reviewer_connection_ref: string | null
  defaults: {
    coordinator: DefaultDescription | null
    worker: DefaultDescription | null
    reviewer: DefaultDescription | null
  }
  /**
   * LG-117 additive view. Optional so an older backend (or an older test fake)
   * is shown as unavailable rather than guessed from a 404.
   */
  embedding?: EmbeddingSettingsView | null
  /**
   * LG-161 additive 1.20.0 view. Its presence is the configuration seam: an
   * old backend omits it and the UI hides the English ASR form without calling
   * a new endpoint. Its presence does **not** mean processing is available.
   */
  english_asr?: EnglishAsrSettingsView | null
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
  /* LG-104 optional non-secret provider fields (additive; backend owner binds). */
  auth_mode?: ConnectionAuthMode
  project?: string | null
  location?: string | null
  model_path?: string | null
  litert_backend?: LiteRtBackend | null
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
  /* LG-104 optional non-secret provider fields (additive; backend owner binds). */
  backend?: string
  auth_mode?: ConnectionAuthMode
  project?: string | null
  location?: string | null
  model_path?: string | null
  litert_backend?: LiteRtBackend | null
}

export interface SettingsUpdateInput {
  expected_revision?: number
  default_coordinator_connection_ref?: string | null
  default_worker_connection_ref?: string | null
  /** LG-017 additive: set/clear the independent reviewer default (null clears). */
  default_reviewer_connection_ref?: string | null
}

export interface ConnectionTestInput {
  expected_revision?: number
  allow_network?: boolean
  probe_tools?: boolean
  probe_structured?: boolean
}

/** Draft connection fields accepted by the LG-104/LG-109 draft-test envelope. */
export interface ConnectionDraftTestConnection {
  backend: string
  model: string | null
  base_url: string | null
  auth_mode: ConnectionAuthMode | null
  project: string | null
  location: string | null
  model_path: string | null
  litert_backend: LiteRtBackend | null
}

/**
 * `POST /settings/connections/test-draft` (contract 1.17, additive MINOR).
 *
 * The connection is an unsaved draft. `credential_value` is write-only and only
 * present when the user typed a new/replacement key; the client never chooses a
 * saved `credential_ref`. For an edit, the backend may resolve the existing
 * credential only through `existing_connection_id` + `expected_revision`, after
 * validating the same backend/auth/endpoint identity.
 */
export interface DraftConnectionTestInput {
  connection: ConnectionDraftTestConnection
  credential_value?: string
  existing_connection_id?: string
  expected_revision: number
  allow_network: boolean
}

/** Existing safe TestResult plus draft markers; no saved revision is implied. */
export interface DraftConnectionTestResult extends ConnectionTestResult {
  draft: true
  connection_ref?: string | null
  revision?: number | null
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
  testDraftConnection(
    input: DraftConnectionTestInput,
    signal?: AbortSignal,
  ): Promise<DraftConnectionTestResult>
  /** LG-117: save the independent Embedding settings (separate from defaults). */
  updateEmbedding(
    input: EmbeddingUpdateInput,
    signal?: AbortSignal,
  ): Promise<EmbeddingUpdateResult>
  /** LG-117: draft Embedding test; never persists and only networks on request. */
  testDraftEmbedding(
    input: EmbeddingDraftTestInput,
    signal?: AbortSignal,
  ): Promise<EmbeddingDraftTestResult>
  /** Delete a saved Connection; the server must reject referenced/default rows. */
  deleteConnection(
    id: string,
    expectedRevision?: number,
    signal?: AbortSignal,
  ): Promise<void>
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

    testDraftConnection(input, signal) {
      return apiRequest<DraftConnectionTestResult>(
        '/settings/connections/test-draft',
        {
          method: 'POST',
          headers: headers(token(), true),
          body: JSON.stringify(input),
          signal,
        },
      )
    },

    updateEmbedding(input, signal) {
      return apiRequest<EmbeddingUpdateResult>('/settings/embedding', {
        method: 'PUT',
        headers: headers(token(), true),
        body: JSON.stringify(input),
        signal,
      })
    },

    testDraftEmbedding(input, signal) {
      return apiRequest<EmbeddingDraftTestResult>('/settings/embedding/test-draft', {
        method: 'POST',
        headers: headers(token(), true),
        body: JSON.stringify(input),
        signal,
      })
    },

    async deleteConnection(id, expectedRevision, signal) {
      const body =
        expectedRevision === undefined
          ? undefined
          : JSON.stringify({ expected_revision: expectedRevision })
      await apiRequest<unknown>(
        `/settings/connections/${encodeURIComponent(id)}`,
        {
          method: 'DELETE',
          headers: headers(token(), body !== undefined),
          body,
          signal,
        },
      )
    },
  }
}
