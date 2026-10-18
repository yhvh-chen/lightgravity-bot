/**
 * LG-119 private Personal attachment client (docs/08 §19.3).
 *
 * These requests are server-identity scoped: the HttpOnly team session cookie
 * is the only owner input.  In single-user mode protected writes carry the
 * local runtime token, exactly like other protected writes.  No attachment
 * request ever contains a raw filesystem path or a client-supplied owner.
 *
 * A missing `private_attachments` health capability disables this surface with
 * a real explanation; the UI never probes the route as a 404 feature test.
 */

import { getRuntimeToken } from './auth'
import { apiRequest } from './client'
import { newRuntimeId } from './chat'
import type { HealthResponse, PrivateAttachmentRef } from './types'

export type PrivateAttachment = Required<
  Pick<PrivateAttachmentRef, 'attachment_id' | 'filename' | 'media_type' | 'size'>
> &
  PrivateAttachmentRef & {
    sha256: string
    status: 'stored' | 'attached'
    created_at: string
  }

export interface PrivateAttachmentContent {
  attachment_id: string
  filename: string
  media_type: string
  size: number
  encoding: 'utf-8' | 'base64'
  content: string
  revision: string
}

export interface AttachmentsRuntimeConfig {
  /** Local runtime token for single-user protected writes; null in team mode. */
  getApiToken?: () => string | null
}

export interface UploadPrivateAttachmentOptions {
  /** Reuse the same client id on retry so the upload is idempotent. */
  attachmentId?: string
  signal?: AbortSignal
}

export interface AttachmentsApi {
  upload(
    file: File,
    options?: UploadPrivateAttachmentOptions,
  ): Promise<PrivateAttachment>
  read(attachmentId: string, signal?: AbortSignal): Promise<PrivateAttachment>
  content(attachmentId: string, signal?: AbortSignal): Promise<PrivateAttachmentContent>
  remove(attachmentId: string, signal?: AbortSignal): Promise<void>
}

/** Create a fresh client idempotency key (`att_<ULID>`). */
export function newPrivateAttachmentId(): string {
  return newRuntimeId('att')
}

export function supportsPrivateAttachments(health: HealthResponse | null | undefined): boolean {
  return health?.capabilities?.private_attachments === true
}

function withQuery(
  path: string,
  params: Record<string, string | null | undefined>,
): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined && value !== '') search.set(key, value)
  }
  const query = search.toString()
  return query ? `${path}?${query}` : path
}

function protectedHeaders(
  runtime: AttachmentsRuntimeConfig,
  extra: Record<string, string> = {},
): Record<string, string> {
  const headers: Record<string, string> = { Accept: 'application/json', ...extra }
  const token = runtime.getApiToken?.() ?? null
  if (token) headers['X-LG-Token'] = token
  return headers
}

export function createAttachmentsApi(
  runtime: AttachmentsRuntimeConfig = { getApiToken: getRuntimeToken },
): AttachmentsApi {
  return {
    upload(file, options = {}) {
      const attachmentId = options.attachmentId ?? newPrivateAttachmentId()
      const path = withQuery('/attachments/private', {
        attachment_id: attachmentId,
        filename: file.name,
        media_type: file.type || 'application/octet-stream',
      })
      return apiRequest<{ attachment: PrivateAttachment }>(path, {
        method: 'POST',
        headers: protectedHeaders(runtime, {
          'Content-Type': file.type || 'application/octet-stream',
        }),
        body: file,
        signal: options.signal,
      }).then((result) => result.attachment)
    },

    read(attachmentId, signal) {
      return apiRequest<{ attachment: PrivateAttachment }>(
        `/attachments/private/${encodeURIComponent(attachmentId)}`,
        { headers: protectedHeaders(runtime), signal },
      ).then((result) => result.attachment)
    },

    content(attachmentId, signal) {
      return apiRequest<PrivateAttachmentContent>(
        `/attachments/private/${encodeURIComponent(attachmentId)}/content`,
        { headers: protectedHeaders(runtime), signal },
      )
    },

    remove(attachmentId, signal) {
      return apiRequest<null>(
        `/attachments/private/${encodeURIComponent(attachmentId)}`,
        { method: 'DELETE', headers: protectedHeaders(runtime), signal },
      ).then(() => undefined)
    },
  }
}

export const attachmentsApi: AttachmentsApi = createAttachmentsApi()
