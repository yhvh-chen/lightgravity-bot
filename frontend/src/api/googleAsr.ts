/**
 * Frozen Google-native ASR types for contract 1.22.0 candidate (LG-235).
 *
 * Types only: this file deliberately contains no network function and no
 * fallback client. LG-237 owns the actual Settings/upload UI and may extend the
 * existing `englishAsr.ts` client additively; LG-236/LG-238 own the backend.
 *
 * Contract: `probes/google-native-asr-20261018/lg235/CONTRACT.md` and
 * `docs/08-interface-contract.md` §23. The public contract version is not
 * bumped until the public backend runtime is implemented and integrated.
 */

import type { EnglishAsrSettingsView } from './englishAsr'

export type GoogleAsrProvider = 'google-native'
export type GoogleAsrRuntime = 'google-native'

export interface GoogleAsrLimits {
  /** Google inline audio has no product-imposed 30-second Reader cap. */
  max_audio_seconds: null
  max_audio_bytes: number
  /** Official total request-size limit, including base64 expansion. */
  max_request_bytes: number
  timeout_seconds: number
  max_concurrency: number
  [key: string]: unknown
}

/**
 * `GET /settings.english_asr` projection when `provider === 'google-native'`.
 * `available` means "configured and attemptable", never "credential verified";
 * per-file success comes only from the source receipt.
 */
export interface GoogleAsrSettingsView
  extends Omit<EnglishAsrSettingsView, 'models' | 'limits'> {
  provider: GoogleAsrProvider
  runtime: GoogleAsrRuntime
  model: string
  base_url: string
  credential_configured: boolean
  models: Record<string, unknown>
  limits: GoogleAsrLimits
}

/**
 * `PUT /settings/english_asr` Google input. `credential_ref` and
 * `credential_value` are write-only and must never be rendered from a GET view.
 * Omit both to retain the stored secret; the first enable needs a stored secret
 * or a supplied value/ref.
 */
export interface GoogleAsrUpdateInput {
  expected_revision: number
  enabled: boolean
  provider: GoogleAsrProvider
  runtime: GoogleAsrRuntime
  model?: string
  base_url?: string
  credential_ref?: string
  credential_value?: string
  timeout_seconds?: number
  max_audio_bytes?: number
}

export const GOOGLE_ASR_DEFAULT_MODEL = 'gemini-3.8-flash'
export const GOOGLE_ASR_DEFAULT_BASE_URL =
  'https://generativelanguage.googleapis.com/v1beta'
export const GOOGLE_ASR_MAX_REQUEST_BYTES = 20_000_000
export const GOOGLE_ASR_DEFAULT_MAX_AUDIO_BYTES = 10_000_000
export const GOOGLE_ASR_MAX_AUDIO_BYTES = 14_000_000
export const GOOGLE_ASR_DEFAULT_TIMEOUT_SECONDS = 180
export const GOOGLE_ASR_MIN_TIMEOUT_SECONDS = 30
export const GOOGLE_ASR_MAX_TIMEOUT_SECONDS = 600
