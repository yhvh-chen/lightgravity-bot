/**
 * Chat material-intake hook (LG-038; docs/09 §2–§4, §6).
 *
 * Chat is the single regular material-intake entry. This hook owns the
 * client-side per-file lifecycle for one Chat scope:
 *
 * * upload / drag-drop / paste-link are all funnelled through `POST /sources`
 *   with a stable `request_id` so a retry is idempotent and cannot create a
 *   second source, Task, Run or team;
 * * global uploads go to the controlled inbox (`origin.kind=upload`,
 *   `scope.inbox_ref`) and never create a delivery Task;
 * * Task Chat uploads inherit the Task scope only when the Task ref is real;
 * * a pasted link is recorded with `origin.kind=link`, `fetched=false` and is
 *   never shown as extracted text — no background crawl is performed;
 * * per-file states (`received → processing → extracted/partial/failed`) are
 *   read back from the source receipt so a reconnect shows the same state.
 *
 * The backend reports missing OCR/vector capability honestly
 * (`capability_unavailable`, `index_unavailable`); this hook never upgrades
 * such a state to success and never turns an embedding into text.
 */

import { useCallback, useRef, useState } from 'react'

import { ApiError } from '../../api/client'
import { newIntakeRequestId, type SourceView, type SourcesApi } from '../../api/sources'

/** Display status for one file (docs/09 §6; NOT a Task phase). */
export type MaterialState =
  | 'received'
  | 'processing'
  | 'extracted'
  | 'attributed'
  | 'indexed'
  | 'archived'
  | 'partial'
  | 'failed'
  | 'unavailable'

export interface MaterialRecord {
  /** Local list key; the intake `request_id`. */
  requestId: string
  filename: string
  /** `upload` | `link` (kept separate: a link is never "text"). */
  originKind: 'upload' | 'link'
  /** For a link origin: the recorded URL (never fetched here). */
  externalRef: string | null
  /** Human-readable per-file state; backend receipt wins. */
  state: MaterialState
  /** True only when a trusted body actually exists (never for link_only). */
  hasText: boolean
  sourceId: string | null
  sourceVersion: number | null
  contentHash: string | null
  lexical: string | null
  vector: string | null
  jobId: string | null
  stage: string | null
  detail: string | null
  error: { code: string; message: string } | null
  /** Explicit "no delivery Task/Run was created" marker. */
  deliveryCreated: false
}

export interface UseChatMaterialsResult {
  materials: MaterialRecord[]
  /** True while at least one upload/link is in flight. */
  busy: boolean
  /** Drop all local receipts and ignore late in-flight results (scope switch). */
  reset: () => void
  uploadFiles: (files: File[], options?: { taskRef?: string | null }) => Promise<void>
  recordLink: (url: string, options?: { taskRef?: string | null }) => Promise<void>
  /** Re-read one source's state from the backend (reconnect / manual refresh). */
  refresh: (requestId: string) => Promise<void>
  dismiss: (requestId: string) => void
}

function toRecord(
  partial: Pick<MaterialRecord, 'requestId' | 'filename' | 'originKind' | 'externalRef'>,
): MaterialRecord {
  return {
    requestId: partial.requestId,
    filename: partial.filename,
    originKind: partial.originKind,
    externalRef: partial.externalRef,
    state: 'received',
    hasText: false,
    sourceId: null,
    sourceVersion: null,
    contentHash: null,
    lexical: null,
    vector: null,
    jobId: null,
    stage: null,
    detail: null,
    error: null,
    deliveryCreated: false,
  }
}

function stateFromSource(source: SourceView): { state: MaterialState; detail: string | null } {
  const status = source.status as MaterialState
  let detail: string | null = null
  if (source.origin.kind === 'link' && !source.origin.fetched) {
    detail = 'link recorded only — not fetched, not text'
  }
  if (source.index?.lexical === 'not_indexed') {
    detail = detail ?? 'not indexed — no trusted body yet'
  }
  if (source.index?.vector && source.index.vector !== 'disabled') {
    detail = detail ?? `vector: ${source.index.vector}`
  }
  return { state: status, detail }
}

function applySource(record: MaterialRecord, source: SourceView): MaterialRecord {
  const shaped = stateFromSource(source)
  const hasText = ['extracted', 'attributed', 'indexed'].includes(shaped.state)
  return {
    ...record,
    sourceId: source.source_id,
    sourceVersion: source.source_version,
    contentHash: source.content_hash,
    lexical: source.index?.lexical ?? null,
    vector: source.index?.vector ?? null,
    state: shaped.state,
    detail: shaped.detail,
    hasText,
    error: null,
  }
}

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onerror = () => reject(reader.error ?? new Error('Could not read file'))
    reader.onload = () => {
      const result = reader.result
      if (typeof result !== 'string') {
        reject(new Error('Unexpected file reader result'))
        return
      }
      const comma = result.indexOf(',')
      resolve(comma >= 0 ? result.slice(comma + 1) : result)
    }
    reader.readAsDataURL(file)
  })
}

function guessMediaType(filename: string): string | null {
  const lower = filename.toLowerCase()
  if (lower.endsWith('.md') || lower.endsWith('.markdown')) return 'text/markdown'
  if (lower.endsWith('.txt')) return 'text/plain'
  if (lower.endsWith('.json')) return 'application/json'
  if (lower.endsWith('.pdf')) return 'application/pdf'
  if (lower.endsWith('.png')) return 'image/png'
  if (lower.endsWith('.jpg') || lower.endsWith('.jpeg')) return 'image/jpeg'
  if (lower.endsWith('.webp')) return 'image/webp'
  return null
}

function isLikelyUrl(value: string): boolean {
  try {
    const parsed = new URL(value.trim())
    return parsed.protocol === 'http:' || parsed.protocol === 'https:'
  } catch {
    return false
  }
}

export { isLikelyUrl }

export function useChatMaterials(api: SourcesApi): UseChatMaterialsResult {
  const [materials, setMaterials] = useState<MaterialRecord[]>([])
  const [busy, setBusy] = useState(false)
  // Stable per-attempt request ids so a retry is idempotent server-side.
  const pending = useRef<Map<string, string>>(new Map())
  // LG-119: a channel/Task switch drops local receipts and makes late upload
  // responses inert, so one conversation's material state cannot paint into
  // another channel or account.
  const generation = useRef(0)

  const patch = useCallback((requestId: string, updater: (r: MaterialRecord) => MaterialRecord) => {
    setMaterials((current) =>
      current.map((item) => (item.requestId === requestId ? updater(item) : item)),
    )
  }, [])

  const patchIfCurrent = useCallback(
    (requestGeneration: number, requestId: string, updater: (r: MaterialRecord) => MaterialRecord) => {
      if (requestGeneration !== generation.current) return
      patch(requestId, updater)
    },
    [patch],
  )

  const reset = useCallback(() => {
    generation.current += 1
    pending.current.clear()
    setMaterials([])
    setBusy(false)
  }, [])

  const refresh = useCallback(
    async (requestId: string) => {
      const requestGeneration = generation.current
      const record = materials.find((item) => item.requestId === requestId)
      if (!record?.sourceId) return
      try {
        const source = await api.getSource(record.sourceId)
        patchIfCurrent(requestGeneration, requestId, (item) => applySource(item, source))
      } catch (cause) {
        patchIfCurrent(requestGeneration, requestId, (item) => ({ ...item, error: asError(cause) }))
      }
    },
    [api, materials, patchIfCurrent],
  )

  const submit = useCallback(
    async (
      record: MaterialRecord,
      body: {
        filename: string
        path?: string
        content_base64?: string
        media_type?: string | null
        title?: string | null
        taskRef?: string | null
        externalRef?: string | null
      },
    ) => {
      const requestGeneration = generation.current
      try {
        const result = await api.createSource({
          request_id: record.requestId,
          filename: body.filename,
          path: body.path,
          content_base64: body.content_base64,
          media_type: body.media_type ?? guessMediaType(body.filename),
          title: body.title ?? null,
          title_origin: 'user',
          scope: body.taskRef ? { task_ref: body.taskRef } : {},
          origin: body.externalRef
            ? { kind: 'link', external_ref: body.externalRef, fetched: false }
            : { kind: 'upload', fetched: false },
        })
        patchIfCurrent(requestGeneration, record.requestId, (item) => {
          const applied = applySource(item, result.source)
          return {
            ...applied,
            jobId: result.job?.job_id ?? null,
            stage: result.job?.stage ?? null,
            // Dedup/existing source keeps its real state; new upload is `received`.
            detail:
              applied.detail ??
              (result.deduplicated ? 'already received (deduplicated)' : 'received — processing'),
          }
        })
      } catch (cause) {
        patchIfCurrent(requestGeneration, record.requestId, (item) => {
          const error = asError(cause)
          // Honest status for an unavailable capability; never a fake success.
          const state: MaterialState =
            error.code === 'capability_unavailable' ? 'unavailable' : 'failed'
          return { ...item, state, error }
        })
      }
    },
    [api, patchIfCurrent],
  )

  const uploadFiles = useCallback(
    async (files: File[], options: { taskRef?: string | null } = {}) => {
      if (files.length === 0) return
      const requestGeneration = generation.current
      const scopeKey = options.taskRef ?? 'global'
      setBusy(true)
      try {
        for (const file of files) {
          if (requestGeneration !== generation.current) return
          const key = `${scopeKey}:${file.name}`
          const requestId = pending.current.get(key) ?? newIntakeRequestId()
          pending.current.set(key, requestId)
          const record = toRecord({
            requestId,
            filename: file.name,
            originKind: 'upload',
            externalRef: null,
          })
          if (requestGeneration !== generation.current) return
          setMaterials((current) => [...current, record])
          patchIfCurrent(requestGeneration, requestId, (item) => ({ ...item, state: 'processing' }))
          try {
            const content_base64 = await fileToBase64(file)
            await submit(record, {
              filename: file.name,
              content_base64,
              media_type: file.type || guessMediaType(file.name),
              taskRef: options.taskRef ?? null,
            })
            pending.current.delete(key)
          } catch (cause) {
            patchIfCurrent(requestGeneration, requestId, (item) => ({ ...item, state: 'failed', error: asError(cause) }))
          }
          // Read back the real receipt so reconnect shows the same state.
          await refresh(requestId)
        }
      } finally {
        if (requestGeneration === generation.current) setBusy(false)
      }
    },
    [patchIfCurrent, refresh, submit],
  )

  const recordLink = useCallback(
    async (url: string, options: { taskRef?: string | null } = {}) => {
      const value = url.trim()
      if (!isLikelyUrl(value)) throw new Error('Not a valid http(s) link')
      const requestGeneration = generation.current
      const scopeKey = `${options.taskRef ?? 'global'}:link:${value}`
      const requestId = pending.current.get(scopeKey) ?? newIntakeRequestId()
      pending.current.set(scopeKey, requestId)
      const host = (() => {
        try {
          return new URL(value).host
        } catch {
          return value
        }
      })()
      const record = toRecord({
        requestId,
        filename: host,
        originKind: 'link',
        externalRef: value,
      })
      if (requestGeneration !== generation.current) return
      setMaterials((current) => [...current, record])
      setBusy(true)
      try {
        await submit(record, {
          filename: host,
          // A link is a zero-byte record: the backend receives an empty inline
          // body so no network fetch happens, and `fetched` stays false.
          content_base64: '',
          media_type: 'text/uri-list',
          title: value,
          taskRef: options.taskRef ?? null,
          externalRef: value,
        })
        pending.current.delete(scopeKey)
        await refresh(requestId)
      } finally {
        if (requestGeneration === generation.current) setBusy(false)
      }
    },
    [refresh, submit],
  )

  const dismiss = useCallback((requestId: string) => {
    setMaterials((current) => current.filter((item) => item.requestId !== requestId))
  }, [])

  return { materials, busy, reset, uploadFiles, recordLink, refresh, dismiss }
}

function asError(cause: unknown): { code: string; message: string } {
  if (cause instanceof ApiError) return { code: cause.code, message: cause.message }
  return {
    code: 'internal_error',
    message: cause instanceof Error ? cause.message : 'Unexpected error',
  }
}
