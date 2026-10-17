/**
 * Provider presets for the Settings connection form (LG-104/LG-106).
 *
 * A preset is **not** a new persisted provider database. It is a small mapping
 * onto the existing Connection fields (`backend` plus the optional LG-104
 * non-secret auth fields) that mirrors the real config classes in the installed
 * `google-antigravity==0.1.22` (LG-105 audit):
 *
 *   LocalAgentConfig        -> Gemini API / Vertex Express / Vertex Standard
 *   LocalOpenAIAgentConfig  -> DeepSeek via the product's loopback proxy
 *   LiteRTAgentConfig       -> on-device LiteRT model
 *
 * Old connections have no `auth_mode`; they are inferred from the fields they
 * already have and are never migrated or rewritten on load. A custom
 * OpenAI-compatible connection whose endpoint is not the DeepSeek preset stays
 * a legacy/custom connection instead of being relabelled as DeepSeek.
 *
 * Capability facts (`configurable`, `testable`, `executable`, `vendor_verified`)
 * stay separate. The frontend only has a fallback for the already-existing
 * DeepSeek execution path; every other value is either backend-declared via
 * `ConnectionView.capabilities` or honestly unknown. SDK support alone never
 * becomes an executable or vendor-verified claim.
 */

import {
  DEFAULT_BASE_URL,
  GEMINI_DEFAULT_MODEL,
  PREFERRED_MODEL,
  type ConnectionAuthMode,
  type ConnectionCapabilities,
  type ConnectionView,
  type LiteRtBackend,
} from '../../api/settings'

export type ProviderPresetId =
  | 'gemini-api'
  | 'vertex-express'
  | 'vertex-adc'
  | 'deepseek'
  | 'litert'
  | 'legacy-openai'
  | 'legacy-unknown'

export interface ProviderPreset {
  id: ProviderPresetId
  label: string
  /** Existing Connection backend id. `null` only for an unknown legacy backend. */
  backend: string | null
  authMode: ConnectionAuthMode
  sdkSupported: boolean
  requiresApiKey: boolean
  requiresProject: boolean
  requiresLocation: boolean
  requiresModelPath: boolean
  requiresBaseUrl: boolean
  /** Model sent to the SDK; `null` means the local model file is the model. */
  defaultModel: string | null
  defaultBaseUrl: string | null
  defaultLitertBackend: LiteRtBackend | null
  /** Shown in the primary form; must not claim runtime/vendor verification. */
  note: string
  /** Honest statement about prerequisites/current execution status. */
  runtimeNote: string
  /** Capability fallback when the backend has not declared `capabilities`. */
  fallbackCapabilities: ConnectionCapabilities
  /** Only offered for an existing connection that needs preserving as-is. */
  legacyOnly: boolean
}

const DEEPSEEK_HINT = 'https://api.deepseek.com/v1'

/**
 * The five presets offered for a new connection. The two `legacy-*` presets
 * below are inferred for existing records only.
 */
export const PROVIDER_PRESETS: readonly ProviderPreset[] = [
  {
    id: 'gemini-api',
    label: 'Gemini API',
    backend: 'gemini',
    authMode: 'api_key',
    sdkSupported: true,
    requiresApiKey: true,
    requiresProject: false,
    requiresLocation: false,
    requiresModelPath: false,
    requiresBaseUrl: false,
    defaultModel: GEMINI_DEFAULT_MODEL,
    defaultBaseUrl: null,
    defaultLitertBackend: null,
    note: 'LocalAgentConfig on the Gemini Developer API. Uses an API key.',
    runtimeNote:
      'Saving and testing depend on backend support for this provider; Task execution and default selection are not enabled in this build.',
    fallbackCapabilities: {
      configurable: null,
      testable: null,
      executable: false,
      vendor_verified: false,
    },
    legacyOnly: false,
  },
  {
    id: 'vertex-express',
    label: 'Vertex AI — Express (API key)',
    backend: 'vertex',
    authMode: 'api_key',
    sdkSupported: true,
    requiresApiKey: true,
    requiresProject: false,
    requiresLocation: false,
    requiresModelPath: false,
    requiresBaseUrl: false,
    defaultModel: GEMINI_DEFAULT_MODEL,
    defaultBaseUrl: null,
    defaultLitertBackend: null,
    note: 'Vertex Express endpoint authenticated with an API key.',
    runtimeNote:
      'Project and location must stay empty for Express. Saving and testing depend on backend support; Task execution is not enabled in this build.',
    fallbackCapabilities: {
      configurable: null,
      testable: null,
      executable: false,
      vendor_verified: false,
    },
    legacyOnly: false,
  },
  {
    id: 'vertex-adc',
    label: 'Vertex AI — Project + ADC',
    backend: 'vertex',
    authMode: 'adc',
    sdkSupported: true,
    requiresApiKey: false,
    requiresProject: true,
    requiresLocation: true,
    requiresModelPath: false,
    requiresBaseUrl: false,
    defaultModel: GEMINI_DEFAULT_MODEL,
    defaultBaseUrl: null,
    defaultLitertBackend: null,
    note: 'Vertex endpoint using a project, a location and Application Default Credentials.',
    runtimeNote:
      'Requires ADC on the backend host (GOOGLE_APPLICATION_CREDENTIALS or gcloud auth application-default login). No API key is entered here, and Task execution is not enabled in this build.',
    fallbackCapabilities: {
      configurable: null,
      testable: null,
      executable: false,
      vendor_verified: false,
    },
    legacyOnly: false,
  },
  {
    id: 'deepseek',
    label: 'DeepSeek (OpenAI-compatible)',
    backend: 'openai-compat',
    authMode: 'proxy_api_key',
    sdkSupported: true,
    requiresApiKey: true,
    requiresProject: false,
    requiresLocation: false,
    requiresModelPath: false,
    requiresBaseUrl: true,
    defaultModel: PREFERRED_MODEL,
    defaultBaseUrl: DEFAULT_BASE_URL,
    defaultLitertBackend: null,
    note: 'Not an SDK-native vendor class: LocalOpenAIAgentConfig plus the product loopback proxy.',
    runtimeNote:
      'The existing executable path. The key is injected by the loopback proxy at run time and is never stored in the connection file.',
    fallbackCapabilities: {
      configurable: true,
      testable: true,
      executable: true,
      // Existing product evidence (LG-003/LG-006/LG-025). This UI package does
      // not make a new vendor request, and the badge is backend-overridable.
      vendor_verified: true,
    },
    legacyOnly: false,
  },
  {
    id: 'litert',
    label: 'LiteRT (local model)',
    backend: 'litert',
    authMode: 'none',
    sdkSupported: true,
    requiresApiKey: false,
    requiresProject: false,
    requiresLocation: false,
    requiresModelPath: true,
    requiresBaseUrl: false,
    defaultModel: null,
    defaultBaseUrl: null,
    defaultLitertBackend: 'GPU',
    note: 'On-device LiteRT-LM model. The model file is the model; no cloud key is used.',
    runtimeNote:
      'Requires the litert-lm runtime package, a readable .litertlm model file and CPU/GPU/NPU support. No network test or inference is claimed here.',
    fallbackCapabilities: {
      configurable: null,
      testable: null,
      executable: false,
      vendor_verified: false,
    },
    legacyOnly: false,
  },
]

/** Preset for an existing custom OpenAI-compatible connection. */
export const LEGACY_OPENAI_PRESET: ProviderPreset = {
  id: 'legacy-openai',
  label: 'Custom OpenAI-compatible (legacy)',
  backend: 'openai-compat',
  authMode: 'proxy_api_key',
  sdkSupported: true,
  requiresApiKey: true,
  requiresProject: false,
  requiresLocation: false,
  requiresModelPath: false,
  requiresBaseUrl: true,
  defaultModel: null,
  defaultBaseUrl: null,
  defaultLitertBackend: null,
  note: 'Existing custom endpoint/model, preserved without migration.',
  runtimeNote:
    'The existing loopback-proxy execution path remains available. This custom endpoint has no vendor-verification claim.',
  fallbackCapabilities: {
    configurable: true,
    testable: true,
    executable: true,
    vendor_verified: false,
  },
  legacyOnly: true,
}

/** Fallback for an old/unknown backend id: preserve, never pretend to know it. */
export const LEGACY_UNKNOWN_PRESET: ProviderPreset = {
  id: 'legacy-unknown',
  label: 'Existing connection (unrecognized provider)',
  backend: null,
  authMode: 'none',
  sdkSupported: false,
  requiresApiKey: false,
  requiresProject: false,
  requiresLocation: false,
  requiresModelPath: false,
  requiresBaseUrl: false,
  defaultModel: null,
  defaultBaseUrl: null,
  defaultLitertBackend: null,
  note: 'This record uses a backend this build does not recognize.',
  runtimeNote:
    'Preserved read-only for compatibility. Capabilities are unknown unless the backend declares them.',
  fallbackCapabilities: {
    configurable: null,
    testable: null,
    executable: false,
    vendor_verified: false,
  },
  legacyOnly: true,
}

const BY_ID = new Map<ProviderPresetId, ProviderPreset>(
  [...PROVIDER_PRESETS, LEGACY_OPENAI_PRESET, LEGACY_UNKNOWN_PRESET].map((preset) => [
    preset.id,
    preset,
  ]),
)

export function presetById(id: ProviderPresetId): ProviderPreset {
  return BY_ID.get(id) ?? LEGACY_UNKNOWN_PRESET
}

function normalizedBaseUrl(value: string | null | undefined): string {
  return (value ?? '').trim().replace(/\/+$/, '').toLowerCase()
}

/** True when an existing openai-compat record still matches the DeepSeek preset. */
export function matchesDeepSeek(baseUrl: string | null | undefined): boolean {
  const normalized = normalizedBaseUrl(baseUrl)
  return normalized === '' || normalized === normalizedBaseUrl(DEEPSEEK_HINT)
}

/**
 * Infer the provider preset for an existing record without changing it.
 * Explicit `auth_mode` wins; absent means "old connection", inferred from the
 * fields that are already present.
 */
export function inferPresetId(connection: ConnectionView): ProviderPresetId {
  const authMode = connection.auth_mode ?? null
  switch (connection.backend) {
    case 'gemini':
      return 'gemini-api'
    case 'vertex':
      if (authMode === 'api_key') return 'vertex-express'
      if (authMode === 'adc') return 'vertex-adc'
      if (connection.project || connection.location) return 'vertex-adc'
      // An old key-backed Vertex record without explicit auth_mode is Express;
      // anything else is the project/location (ADC) shape.
      if (connection.credential_ref) return 'vertex-express'
      return 'vertex-adc'
    case 'litert':
      return 'litert'
    case 'openai-compat':
      if (authMode && authMode !== 'proxy_api_key') return 'legacy-openai'
      return matchesDeepSeek(connection.base_url) ? 'deepseek' : 'legacy-openai'
    default:
      return 'legacy-unknown'
  }
}

export function presetForConnection(connection: ConnectionView): ProviderPreset {
  return presetById(inferPresetId(connection))
}

/** Backend-declared capability wins; the preset fallback fills only the gaps. */
export function connectionCapabilities(
  connection: ConnectionView,
  preset: ProviderPreset = presetForConnection(connection),
): ConnectionCapabilities {
  const declared = connection.capabilities ?? {}
  const fallback = preset.fallbackCapabilities
  const pick = (key: keyof ConnectionCapabilities): boolean | null => {
    const value = declared[key]
    if (value === true || value === false) return value
    const base = fallback[key]
    return base === true || base === false ? base : null
  }
  return {
    configurable: pick('configurable'),
    testable: pick('testable'),
    executable: pick('executable'),
    vendor_verified: pick('vendor_verified'),
  }
}

/** Defaults may only use a connection the product can actually execute. */
export function isDefaultEligible(connection: ConnectionView): boolean {
  return (
    connection.enabled &&
    connectionCapabilities(connection).executable === true
  )
}

export function providerLabelForConnection(connection: ConnectionView): string {
  return presetForConnection(connection).label
}

/** True for the only provider path the current product can execute. */
export function isExecutableBackend(id: string): boolean {
  return id === 'openai-compat'
}
