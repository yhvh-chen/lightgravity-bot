/**
 * Backend registry metadata for the Settings form (LG-026; docs/07 §2).
 *
 * The registry *describes* the SDK backends; it does not add multi-provider
 * execution. Only `openai-compat` (DeepSeek) is verified and may be saved as
 * an executable connection. Gemini/Vertex are marked `planned`/unavailable and
 * cannot be selected as a default. This mirrors the backend's own
 * `validate_backend` rule instead of inventing a second capability list.
 */

export type BackendAvailability = 'verified' | 'planned'

export interface BackendInfo {
  id: string
  label: string
  availability: BackendAvailability
  /** Short, product-facing explanation shown in the type form. */
  note: string
}

export const BACKENDS: readonly BackendInfo[] = [
  {
    id: 'openai-compat',
    label: 'OpenAI-compatible (DeepSeek)',
    availability: 'verified',
    note: 'Verified first-version path. The loopback auth proxy injects the credential at run time; this connection file never stores the value.',
  },
  {
    id: 'gemini',
    label: 'Gemini Developer API',
    availability: 'planned',
    note: 'Not verified in this environment. It cannot be saved as an executable connection or used as a default.',
  },
  {
    id: 'vertex',
    label: 'Vertex AI',
    availability: 'planned',
    note: 'Not verified in this environment. It cannot be saved as an executable connection or used as a default.',
  },
]

export function backendInfo(id: string): BackendInfo | null {
  return BACKENDS.find((item) => item.id === id) ?? null
}

export function backendLabel(id: string): string {
  return backendInfo(id)?.label ?? id
}

/** Only the verified backend may execute or be a default. */
export function isExecutableBackend(id: string): boolean {
  return backendInfo(id)?.availability === 'verified'
}
