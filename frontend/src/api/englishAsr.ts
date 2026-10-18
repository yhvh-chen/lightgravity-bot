/**
 * English ASR (shared English audio machine transcription) client — LG-161.
 *
 * Contract: docs/08 §21 (1.20.0, additive MINOR).
 *
 * Read path uses the **existing** protected `GET /settings` document. This
 * module deliberately provides no read/probe method: an old backend that does
 * not expose `settings.english_asr` must not be probed through a new endpoint.
 *
 * Write path is `PUT /settings/english_asr`. The caller must send the
 * `english_asr.revision` returned by the settings view (never the global
 * settings revision) and only the fields it really changes:
 *
 * * `model_dir` / `reader_dir` are write-only. Blank/whitespace means the field
 *   is **omitted** (retain the stored path); it is never sent as `null`/`""`.
 * * No credential or transcript content is sent or persisted by the client.
 * * The local asset paths are admin configuration only; the read view never
 *   returns them, so they are never rendered after a reload.
 */

import { getRuntimeToken } from './auth'
import { apiRequest } from './client'

/** Frozen reason enum from docs/08 §21.3; unknown values stay displayable. */
export type EnglishAsrReason =
  | 'disabled'
  | 'model_missing'
  | 'model_hash_mismatch'
  | 'runtime_unavailable'
  | 'invalid_config'
  | 'resource_unavailable'

export interface EnglishAsrModelRef {
  id: string
  revision: string
  sha256: string
  license: string
}

export interface EnglishAsrModels {
  encoder?: EnglishAsrModelRef | null
  reader?: EnglishAsrModelRef | null
  [key: string]: unknown
}

export interface EnglishAsrLimits {
  max_audio_seconds: number
  max_audio_bytes: number
  timeout_seconds: number
  max_concurrency: number
  [key: string]: unknown
}

/**
 * `GET /settings.english_asr` view. This is a **configuration** view, not a
 * processing capability: `available=false`/`reason=disabled` does not mean the
 * admin cannot configure or enable it while the view is exposed.
 */
export interface EnglishAsrSettingsView {
  revision: number
  content_hash: string
  enabled: boolean
  runtime: string
  configured: boolean
  available: boolean
  reason: string | null
  language: string | null
  timestamps_supported: boolean
  models: EnglishAsrModels
  limits: EnglishAsrLimits
  [key: string]: unknown
}

/**
 * `PUT /settings/english_asr` input.
 *
 * Only include `model_dir`/`reader_dir` when the admin typed a new value. The
 * client intentionally does not expose `threads`/`device` as edit fields:
 * `device` is fixed to `cpu` in 1.20 and the GET view does not report the
 * configured thread count, so the UI must not silently overwrite it.
 */
export interface EnglishAsrUpdateInput {
  expected_revision: number
  enabled: boolean
  runtime: 'inprocess'
  device: 'cpu'
  timeout_seconds: number
  max_audio_seconds: number
  max_audio_bytes: number
  model_dir?: string
  reader_dir?: string
}

export interface EnglishAsrUpdateResult {
  revision: number
  content_hash: string
  english_asr: EnglishAsrSettingsView
}

export interface EnglishAsrApi {
  /**
   * Save admin configuration with optimistic revision checking. Saving only
   * validates the supplied paths/hashes and persists settings; it never runs
   * transcription and never proves processing availability.
   */
  update(input: EnglishAsrUpdateInput, signal?: AbortSignal): Promise<EnglishAsrUpdateResult>
}

function headers(token: string | null): Record<string, string> {
  const result: Record<string, string> = {
    Accept: 'application/json',
    'Content-Type': 'application/json',
  }
  if (token) result['X-LG-Token'] = token
  return result
}

/** Human-readable reason for the real `reason` enum; unknown stays raw. */
export function englishAsrReasonLabel(reason: string | null): string {
  switch (reason) {
    case 'disabled':
      return 'Disabled by configuration'
    case 'model_missing':
      return 'Model files missing at the configured asset directories'
    case 'model_hash_mismatch':
      return 'Model files do not match the pinned SHA-256'
    case 'runtime_unavailable':
      return 'In-process runtime unavailable'
    case 'invalid_config':
      return 'Invalid configuration'
    case 'resource_unavailable':
      return 'Resources unavailable (for example memory)'
    case null:
    case '':
      return 'No reason reported'
    default:
      return reason
  }
}

/** Build a client bound to the in-memory runtime token (or an injected one). */
export function createEnglishAsrApi(
  getToken: () => string | null = getRuntimeToken,
): EnglishAsrApi {
  const token = () => getToken()

  return {
    update(input, signal) {
      return apiRequest<EnglishAsrUpdateResult>('/settings/english_asr', {
        method: 'PUT',
        headers: headers(token()),
        body: JSON.stringify(input),
        signal,
      })
    },
  }
}
