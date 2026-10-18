/**
 * Files API client (LG-014, docs/08 §4.3).
 *
 * Owns the Files-specific wire types and calls the frozen endpoints:
 * ``GET /files``, ``GET /files/content``, the LG-014 ``POST /files/upload`` /
 * ``GET /files/download`` pair and ``GET /tasks/{id}/artifacts``.
 *
 * The runtime token is *injected*, never persisted or logged: readonly
 * browsing needs no token, while upload is a protected write and honestly
 * fails with ``unauthorized`` when no token is available.  The integration
 * owner passes a stable ``FilesRuntimeConfig`` (or a whole ``FilesApi``), so
 * this module does not touch the shared token helper or routing.
 */

import { ApiError, apiRequest } from './client'
import { API_PREFIX } from './types'

export interface FileEntry {
  /** Canonical evidence must use the Task artifact resolver, never /files. */
  evidence_ref?: string
  name: string
  path: string
  type: 'file' | 'directory'
  size: number | null
  modified_at: string
  symlink: boolean
  media_type: string | null
  /** Stat-based change token; ``null`` for directories. */
  revision: string | null
}

export interface FileListing {
  path: string
  items: FileEntry[]
  next_cursor: string | null
}

export interface FileContent {
  evidence_ref?: string
  read_only?: boolean
  path: string
  name: string
  size: number
  truncated: boolean
  media_type: string
  encoding: 'utf-8' | 'base64'
  revision: string | null
  content: string
}

export interface UploadResult {
  path: string
  name: string
  size: number
  revision: string | null
  created: boolean
}

export interface DownloadResult {
  blob: Blob
  filename: string
  mediaType: string
  revision: string | null
}

export interface ArtifactCategories {
  inputs: FileEntry[]
  candidates: FileEntry[]
  deliverables: FileEntry[]
  evidence: FileEntry[]
  other: FileEntry[]
}

export interface TaskArtifacts {
  task_id: string
  task_revision: number
  requirements_revision: number | null
  deliverable_revision: number | null
  candidate_ref: string | null
  evidence_refs: string[]
  check_records: unknown[]
  workspace_ref: string | null
  categories: ArtifactCategories
  note: string | null
}

export interface FilesRuntimeConfig {
  /** Local access token injected at runtime; never persisted or logged. */
  apiToken?: string | null
  /** Resolve the token lazily (e.g. from a runtime handshake). */
  getApiToken?: () => string | null
}

export interface FilesApi {
  listFiles(path: string, signal?: AbortSignal): Promise<FileListing>
  readContent(path: string, signal?: AbortSignal): Promise<FileContent>
  downloadFile(
    path: string,
    revision?: string | null,
    signal?: AbortSignal,
  ): Promise<DownloadResult>
  uploadFile(
    path: string,
    data: Blob,
    expectedRevision: string | null,
    signal?: AbortSignal,
  ): Promise<UploadResult>
  readTaskDefinition?(taskRef: string, signal?: AbortSignal): Promise<FileContent>
  readArtifact?(taskRef: string, evidenceRef: string, signal?: AbortSignal): Promise<FileContent>
  downloadArtifact?(taskRef: string, evidenceRef: string, revision?: string | null, signal?: AbortSignal): Promise<DownloadResult>
  taskArtifacts(taskRef: string, signal?: AbortSignal): Promise<TaskArtifacts>
}

const TOKEN_HEADER = 'X-LG-Token'

function runtimeToken(runtime: FilesRuntimeConfig | undefined): string | null {
  if (!runtime) return null
  const value = runtime.getApiToken ? runtime.getApiToken() : runtime.apiToken
  return typeof value === 'string' && value.length > 0 ? value : null
}

function authHeaders(runtime: FilesRuntimeConfig | undefined): Record<string, string> {
  const token = runtimeToken(runtime)
  return token ? { [TOKEN_HEADER]: token } : {}
}

function query(params: Record<string, string | null | undefined>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') search.set(key, value)
  }
  const text = search.toString()
  return text ? `?${text}` : ''
}

function parseFilename(header: string | null, fallbackPath: string): string {
  const fallback = fallbackPath.split('/').pop() || 'download'
  if (!header) return fallback
  const starred = /filename\*=UTF-8''([^;]+)/i.exec(header)
  if (starred) {
    try {
      return decodeURIComponent(starred[1])
    } catch {
      /* fall through to the plain form */
    }
  }
  const plain = /filename="([^"]+)"/i.exec(header)
  return plain ? plain[1] : fallback
}

function isErrorEnvelope(
  value: unknown,
): value is { error: { code: string; message: string; retryable?: boolean; details?: Record<string, unknown>; request_id?: string | null } } {
  if (!value || typeof value !== 'object') return false
  const candidate = value as { error?: unknown }
  return Boolean(candidate.error && typeof candidate.error === 'object')
}

async function toApiError(response: Response): Promise<ApiError> {
  const contentType = response.headers.get('content-type') ?? ''
  const payload: unknown = contentType.includes('application/json')
    ? await response.json().catch(() => null)
    : null
  if (isErrorEnvelope(payload)) {
    return new ApiError({
      message: payload.error.message,
      code: payload.error.code,
      httpStatus: response.status,
      retryable: payload.error.retryable ?? false,
      details: payload.error.details,
      requestId: payload.error.request_id,
    })
  }
  return new ApiError({
    message: `Request failed with status ${response.status}`,
    code: 'internal_error',
    httpStatus: response.status,
    retryable: response.status >= 500,
  })
}

async function downloadResponse(endpoint: string, path: string, runtime: FilesRuntimeConfig, signal?: AbortSignal): Promise<DownloadResult> {
  const response = await fetch(
    `${API_PREFIX}${endpoint}`,
    {
      // Same-origin session cookie for team mode (LG-050 §7).
      credentials: 'include',
      headers: { Accept: '*/*', ...authHeaders(runtime) },
      signal,
    },
  ).catch((cause: unknown) => {
    throw new ApiError({
      message: cause instanceof Error ? cause.message : 'Network request failed',
      code: 'network_error',
      httpStatus: null,
      retryable: true,
    })
  })
  if (!response.ok) throw await toApiError(response)
  return {
    blob: await response.blob(),
    filename: parseFilename(response.headers.get('content-disposition'), path),
    mediaType: response.headers.get('content-type') ?? 'application/octet-stream',
    revision: response.headers.get('x-lg-revision') || null,
  }
}

export function createFilesApi(runtime: FilesRuntimeConfig = {}): FilesApi {
  return {
    listFiles(path, signal) {
      return apiRequest<FileListing>(`/files${query({ path })}`, { signal })
    },
    readContent(path, signal) {
      return apiRequest<FileContent>(`/files/content${query({ path })}`, { signal })
    },
    async downloadFile(path, revision, signal) {
      return downloadResponse(`/files/download${query({ path, revision })}`, path, runtime, signal)
    },
    uploadFile(path, data, expectedRevision, signal) {
      return apiRequest<UploadResult>(
        `/files/upload${query({ path, expected_revision: expectedRevision })}`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/octet-stream',
            ...authHeaders(runtime),
          },
          body: data,
          signal,
        },
      )
    },
    readTaskDefinition(taskRef, signal) {
      return apiRequest<FileContent>(`/tasks/${encodeURIComponent(taskRef)}/definition/content`, { signal })
    },
    async readArtifact(taskRef, evidenceRef, signal) {
      const content = await apiRequest<Omit<FileContent, 'path'>>(
        `/tasks/${encodeURIComponent(taskRef)}/artifacts/content${query({ evidence_ref: evidenceRef })}`,
        { signal },
      )
      return { ...content, path: evidenceRef }
    },
    downloadArtifact(taskRef, evidenceRef, revision, signal) {
      return downloadResponse(
        `/tasks/${encodeURIComponent(taskRef)}/artifacts/download${query({ evidence_ref: evidenceRef, revision })}`,
        evidenceRef, runtime, signal,
      )
    },
    taskArtifacts(taskRef, signal) {
      return apiRequest<TaskArtifacts>(
        `/tasks/${encodeURIComponent(taskRef)}/artifacts`,
        { signal },
      )
    },
  }
}

/** Default (unauthenticated) client: readonly browsing works, uploads fail honestly. */
export const filesApi = createFilesApi()

export function listFiles(path: string, signal?: AbortSignal): Promise<FileListing> {
  return filesApi.listFiles(path, signal)
}

export function readContent(path: string, signal?: AbortSignal): Promise<FileContent> {
  return filesApi.readContent(path, signal)
}

export function taskArtifacts(
  taskRef: string,
  signal?: AbortSignal,
): Promise<TaskArtifacts> {
  return filesApi.taskArtifacts(taskRef, signal)
}
