/**
 * Resources API client (LG-015; docs/05 §6.1, docs/08 §4.3).
 *
 * Reads go through the real `/api/v1/resources*` endpoints that LG-012 mounts
 * and LG-015's ``ResourceService`` now backs.  Diagnostics keep declared,
 * parsed, dependency and runtime availability separate; the client must never
 * turn a missing/unknown state into a success.
 *
 * Mutating calls send the in-memory runtime token and the caller's
 * ``expected_revision``.  When the token is missing the backend default-denies
 * with ``unauthorized``; this module surfaces that real error.
 *
 * Connections are read-only here: the detail view only navigates to Settings,
 * which owns the same Connection entity.  No second model list is built.
 */

import { getRuntimeToken, runtimeTokenHeaders } from './auth'
import { apiRequest } from './client'

export type ResourceKind =
  | 'agent'
  | 'connection'
  | 'conversation'
  | 'hook'
  | 'mcp'
  | 'tool'
  | 'trigger'
  | 'skill'

export type AvailabilityState =
  | 'unknown'
  | 'disabled'
  | 'unsupported'
  | 'missing_dependency'
  | 'invalid'
  | 'available'

export interface ResourceAvailability {
  state: AvailabilityState | string
  reasons: string[]
}

export interface ResourceDiagnostic {
  code: string
  message: string
  level?: string
  location?: string
  detail?: Record<string, unknown>
}

export interface ResourceReference {
  field?: string | null
  kind: string
  ref: string
  state: string
  source?: string | null
  configured?: boolean
}

export interface InboundReference {
  from_kind: string
  from_id: string
  field: string
}

export interface ResourceSummary {
  id: string
  kind: ResourceKind
  title: string
  enabled: boolean
  revision: number | null
  etag: string | null
  availability: ResourceAvailability
  diagnostics?: ResourceDiagnostic[]
}

export interface ResourceDetail extends ResourceSummary {
  entity: Record<string, unknown>
  body: string
  declared: { enabled: boolean }
  parsed: { valid: boolean }
  diagnostics: ResourceDiagnostic[]
  references: ResourceReference[]
  inbound_refs: InboundReference[]
  availability: ResourceAvailability
}

export interface ResourceUpdateInput {
  expected_revision: number
  patch: Record<string, unknown>
  body?: string | null
}

export interface ResourceList {
  items: ResourceSummary[]
  next_cursor: string | null
}

export interface ResourcesApi {
  listResources(kind: ResourceKind, signal?: AbortSignal): Promise<ResourceList>
  getResource(
    kind: ResourceKind,
    id: string,
    signal?: AbortSignal,
  ): Promise<ResourceDetail>
  updateResource(
    kind: ResourceKind,
    id: string,
    input: ResourceUpdateInput,
    signal?: AbortSignal,
  ): Promise<ResourceDetail>
}

export interface ResourceCategory {
  /** Context-rail item id used by the shell. */
  id: string
  /** Store kind behind the category. */
  kind: ResourceKind
  label: string
  blurb: string
}

/** Frozen Resources categories, in docs/05 §6.1 order. */
export const RESOURCE_CATEGORIES: readonly ResourceCategory[] = [
  {
    id: 'connections',
    kind: 'connection',
    label: 'Connections',
    blurb: 'Registered adapter, model and credential reference. Edited in Settings.',
  },
  {
    id: 'session-profiles',
    kind: 'conversation',
    label: 'Session Profiles',
    blurb: 'Conversation configuration templates — not live conversations.',
  },
  { id: 'hooks', kind: 'hook', label: 'Hooks', blurb: 'Registered lifecycle handlers.' },
  { id: 'mcp', kind: 'mcp', label: 'MCP', blurb: 'stdio/HTTP server descriptions.' },
  {
    id: 'tools',
    kind: 'tool',
    label: 'Tools',
    blurb: 'Builtin and registered callables; MCP tools stay owned by their service.',
  },
  { id: 'triggers', kind: 'trigger', label: 'Triggers', blurb: 'Event/time rule descriptions.' },
  { id: 'skills', kind: 'skill', label: 'Skills', blurb: 'Work methods and referenced files.' },
]

const RESOURCE_KINDS: readonly ResourceKind[] = [
  'agent',
  'connection',
  'conversation',
  'hook',
  'mcp',
  'tool',
  'trigger',
  'skill',
]

export function isResourceKind(value: string): value is ResourceKind {
  return (RESOURCE_KINDS as readonly string[]).includes(value)
}

export function categoryById(id: string | null): ResourceCategory | null {
  if (!id) return null
  return RESOURCE_CATEGORIES.find((category) => category.id === id) ?? null
}

export function categoryByKind(kind: ResourceKind): ResourceCategory | null {
  return RESOURCE_CATEGORIES.find((category) => category.kind === kind) ?? null
}

export function createResourcesApi(
  getToken: () => string | null = getRuntimeToken,
): ResourcesApi {
  const headers = (json: boolean) =>
    runtimeTokenHeaders(getToken(), json ? { 'Content-Type': 'application/json' } : undefined)

  return {
    async listResources(kind, signal) {
      return apiRequest<ResourceList>(`/resources/${kind}`, {
        headers: headers(false),
        signal,
      })
    },
    getResource(kind, id, signal) {
      return apiRequest<ResourceDetail>(
        `/resources/${kind}/${encodeURIComponent(id)}`,
        { headers: headers(false), signal },
      )
    },
    updateResource(kind, id, input, signal) {
      return apiRequest<ResourceDetail>(
        `/resources/${kind}/${encodeURIComponent(id)}`,
        {
          method: 'PATCH',
          headers: headers(true),
          body: JSON.stringify(input),
          signal,
        },
      )
    },
  }
}
