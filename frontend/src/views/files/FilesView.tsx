/**
 * Files view (owner: LG-014, design.md §5 Files).
 *
 * Read-only workspace browsing plus the LG-014 write path:
 *
 * * file tree over the authorized workspace root (``GET /files``);
 * * Markdown/code/image preview with no script execution
 *   (``GET /files/content``); HTML is never rendered, only offered for
 *   download, and unsafe/binary types show an honest unsupported state;
 * * task association of inputs / candidates / deliverables / run evidence
 *   from ``GET /tasks/{id}/artifacts`` while the Task scope stays visible;
 * * download and upload against the LG-014 endpoints.  Upload requires the
 *   injected runtime token; without it the backend returns ``unauthorized``
 *   and the view reports that instead of faking a write.
 *
 * ``FilesView`` is shell-aware (it reads the active ``task_ref``/``run_ref``
 * from the LG-011 shell when props are omitted).  ``FilesPanel`` is the pure
 * component the integration owner can mount with explicit props or a factory.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { getRuntimeToken } from '../../api/auth'
import { ApiError } from '../../api/client'
import {
  createSourcesApi,
  type SourcesApi,
  type SourcesRuntimeConfig,
} from '../../api/sources'
import {
  createFilesApi,
  type FileContent,
  type FileEntry,
  type FileListing,
  type FilesApi,
  type FilesRuntimeConfig,
  type TaskArtifacts,
} from '../../api/files'
import { EmptyState } from '../../components/EmptyState'
import { ErrorState } from '../../components/ErrorState'
import { MarkdownViewer } from '../../components/MarkdownViewer'
import { StatusBadge } from '../../components/StatusBadge'
import { useShell } from '../../app/ShellProvider'
import { FilesMaterialsPanel } from './FilesMaterialsPanel'
import './files.css'

const SAFE_IMAGE_TYPES = new Set([
  'image/png',
  'image/jpeg',
  'image/gif',
  'image/webp',
  'image/bmp',
])

const ARTIFACT_SECTIONS: ReadonlyArray<{
  key: keyof TaskArtifacts['categories']
  label: string
  hint: string
}> = [
  { key: 'inputs', label: 'Inputs', hint: 'materials supplied to the task' },
  { key: 'candidates', label: 'Candidates', hint: 'produced candidates awaiting acceptance' },
  { key: 'deliverables', label: 'Deliverables', hint: 'accepted delivery' },
  { key: 'evidence', label: 'Run evidence', hint: 'per-run artifacts and logs' },
  { key: 'other', label: 'Other files', hint: 'not classified by path convention' },
]

type PreviewKind = 'markdown' | 'text' | 'image' | 'html-disabled' | 'unsupported'

interface StatusMessage {
  kind: 'success' | 'error' | 'neutral'
  text: string
}

export interface FilesViewProps {
  /** Active Task scope; omit to inherit the LG-011 shell ``task_ref``. */
  taskRef?: string | null
  /** Active Run scope; omit to inherit the LG-011 shell ``run_ref``. */
  runRef?: string | null
  runtime?: FilesRuntimeConfig
  /** Injected client (tests / integration); overrides ``runtime``. */
  api?: FilesApi
  /** Injected sources client for the Materials surface (LG-038). */
  sourcesApi?: SourcesApi
  /** Runtime token source for the sources Materials surface (LG-038). */
  sourcesRuntime?: SourcesRuntimeConfig
  /** Lets the integration owner persist a Task chosen inside the view. */
  onSelectTaskRef?: (taskRef: string | null) => void
}

export interface FilesPanelProps {
  taskRef: string | null
  runRef: string | null
  api: FilesApi
  sourcesApi?: SourcesApi
  /** Selected item ref; `source:<id>` opens that material (LG-038 deep link). */
  selectedItemRef?: string | null
  onSelectTaskRef?: (taskRef: string | null) => void
}

/** Parse a `source:<id>` selection ref (LG-038). */
export function parseSourceRef(ref: string | null | undefined): string | null {
  if (!ref || !ref.startsWith('source:')) return null
  const id = ref.slice('source:'.length)
  return id || null
}

export function FilesView(props: FilesViewProps = {}) {
  const { state } = useShell()
  const taskRef = props.taskRef === undefined ? state.taskRef : props.taskRef
  const runRef = props.runRef === undefined ? state.runRef : props.runRef
  const api = useMemo(
    () => props.api ?? createFilesApi(props.runtime ?? { getApiToken: getRuntimeToken }),
    [props.api, props.runtime],
  )
  const sourcesApi = useMemo(
    () =>
      props.sourcesApi ??
      createSourcesApi(props.sourcesRuntime ?? { getApiToken: getRuntimeToken }),
    [props.sourcesApi, props.sourcesRuntime],
  )
  return (
    <FilesPanel
      taskRef={taskRef}
      runRef={runRef}
      api={api}
      sourcesApi={sourcesApi}
      selectedItemRef={state.selectedItemRef}
      onSelectTaskRef={props.onSelectTaskRef}
    />
  )
}

export function FilesPanel({
  taskRef,
  runRef,
  api,
  sourcesApi,
  selectedItemRef,
  onSelectTaskRef,
}: FilesPanelProps) {
  const [surface, setSurface] = useState<'workspace' | 'materials'>('workspace')
  const [cwd, setCwd] = useState('')
  const [listing, setListing] = useState<FileListing | null>(null)
  const [listError, setListError] = useState<ApiError | null>(null)
  const [listLoading, setListLoading] = useState(false)
  const [selected, setSelected] = useState<FileContent | null>(null)
  const [previewError, setPreviewError] = useState<ApiError | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [artifacts, setArtifacts] = useState<TaskArtifacts | null>(null)
  const [artifactError, setArtifactError] = useState<ApiError | null>(null)
  const [status, setStatus] = useState<StatusMessage | null>(null)
  const [imageUrl, setImageUrl] = useState<string | null>(null)
  const [refreshToken, setRefreshToken] = useState(0)
  const uploadRef = useRef<HTMLInputElement>(null)

  // Task scope: load artifact association and start from its workspace.
  useEffect(() => {
    setSelected(null)
    setPreviewError(null)
    setImageUrl(null)
    setStatus(null)
    if (!taskRef) {
      setArtifacts(null)
      setArtifactError(null)
      setCwd('')
      return
    }
    const controller = new AbortController()
    setArtifacts(null)
    setArtifactError(null)
    api
      .taskArtifacts(taskRef, controller.signal)
      .then((data) => {
        setArtifacts(data)
        setCwd(data.workspace_ref ?? '')
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return
        setArtifactError(asApiError(error))
        setCwd('')
      })
    return () => controller.abort()
  }, [api, taskRef])

  // Directory listing for the current path.
  useEffect(() => {
    const controller = new AbortController()
    setListLoading(true)
    setListError(null)
    api
      .listFiles(cwd, controller.signal)
      .then((data) => setListing(data))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return
        setListError(asApiError(error))
        setListing(null)
      })
      .finally(() => {
        if (!controller.signal.aborted) setListLoading(false)
      })
    return () => controller.abort()
  }, [api, cwd, refreshToken])

  // Revoke the last object URL when it changes or the view unmounts.
  useEffect(() => {
    return () => {
      if (imageUrl) URL.revokeObjectURL(imageUrl)
    }
  }, [imageUrl])

  const openFile = useCallback(
    async (path: string) => {
      setPreviewLoading(true)
      setPreviewError(null)
      setStatus(null)
      try {
        const content = await api.readContent(path)
        setSelected(content)
        if (SAFE_IMAGE_TYPES.has(content.media_type.toLowerCase())) {
          const download = await api.downloadFile(content.path, content.revision)
          setImageUrl(URL.createObjectURL(download.blob))
        } else {
          setImageUrl(null)
        }
      } catch (error) {
        setSelected(null)
        setImageUrl(null)
        setPreviewError(asApiError(error))
      } finally {
        setPreviewLoading(false)
      }
    },
    [api],
  )

  const download = useCallback(
    async (path: string, revision: string | null) => {
      try {
        const result = await api.downloadFile(path, revision)
        const url = URL.createObjectURL(result.blob)
        const anchor = document.createElement('a')
        anchor.href = url
        anchor.download = result.filename
        document.body.appendChild(anchor)
        anchor.click()
        anchor.remove()
        URL.revokeObjectURL(url)
        setStatus({
          kind: 'success',
          text: `Downloaded ${result.filename} (revision ${result.revision ?? 'unknown'})`,
        })
      } catch (error) {
        setStatus({ kind: 'error', text: describeError(asApiError(error), 'Download failed') })
      }
    },
    [api],
  )

  const upload = useCallback(
    async (file: File) => {
      const targetPath = cwd ? `${cwd}/${file.name}` : file.name
      const existing = listing?.items.find(
        (item) => item.type === 'file' && item.path === targetPath,
      )
      const expected =
        selected?.path === targetPath ? selected.revision : existing?.revision ?? null
      setStatus(null)
      try {
        const result = await api.uploadFile(targetPath, file, expected)
        setStatus({
          kind: 'success',
          text: `${result.created ? 'Uploaded' : 'Updated'} ${result.name} (revision ${
            result.revision ?? 'unknown'
          })`,
        })
        setRefreshToken((value) => value + 1)
        if (selected?.path === targetPath) await openFile(targetPath)
      } catch (error) {
        setStatus({ kind: 'error', text: describeError(asApiError(error), 'Upload failed') })
      }
    },
    [api, cwd, listing, openFile, selected],
  )

  const copyPath = useCallback(async (value: string) => {
    try {
      if (navigator.clipboard) {
        await navigator.clipboard.writeText(value)
        setStatus({ kind: 'success', text: `Copied ${value}` })
        return
      }
    } catch {
      /* clipboard may be unavailable; fall through to the honest message */
    }
    setStatus({ kind: 'neutral', text: `Full path: ${value}` })
  }, [])

  const selectArtifact = useCallback(
    (entry: FileEntry) => {
      const parent = entry.path.includes('/')
        ? entry.path.slice(0, entry.path.lastIndexOf('/'))
        : ''
      setCwd(parent)
      void openFile(entry.path)
    },
    [openFile],
  )

  const segments = cwd ? cwd.split('/') : []
  const previewKind = selected ? classify(selected) : null
  const deepLinkedSource = parseSourceRef(selectedItemRef)

  // A `source:<id>` selection (from Chat hits/attachments) opens Materials.
  useEffect(() => {
    if (deepLinkedSource) setSurface('materials')
  }, [deepLinkedSource])

  return (
    <div className="lg-files">
      <header className="lg-files__header">
        <div className="lg-files__scope">
          <span className="lg-files__scope-label">Task scope</span>
          <span className="lg-files__scope-value" title={taskRef ?? 'none'}>
            {taskRef ?? 'Global workspace'}
          </span>
          {runRef ? <StatusBadge kind="neutral">run {runRef}</StatusBadge> : null}
          {taskRef && onSelectTaskRef ? (
            <button
              type="button"
              className="lg-button"
              onClick={() => onSelectTaskRef(null)}
            >
              Clear scope
            </button>
          ) : null}
        </div>
        <div className="lg-files__path" title={cwd || '/'}>
          <span className="lg-files__path-label">Path</span>
          <code className="lg-files__path-value">{cwd || '/'}</code>
          <button
            type="button"
            className="lg-button"
            onClick={() => void copyPath(cwd || '/')}
          >
            Copy path
          </button>
        </div>
        <div className="lg-files__surface-tabs" role="tablist" aria-label="Files surfaces">
          <button
            type="button"
            role="tab"
            aria-selected={surface === 'workspace'}
            className={`lg-files__surface-tab${surface === 'workspace' ? ' is-active' : ''}`}
            onClick={() => setSurface('workspace')}
          >
            Workspace files
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={surface === 'materials'}
            className={`lg-files__surface-tab${surface === 'materials' ? ' is-active' : ''}`}
            onClick={() => setSurface('materials')}
          >
            Materials
          </button>
        </div>
      </header>

      {status ? (
        <p
          className={`lg-files__status lg-files__status--${status.kind}`}
          role={status.kind === 'error' ? 'alert' : 'status'}
        >
          {status.text}
        </p>
      ) : null}

      {surface === 'materials' ? (
        sourcesApi ? (
          <FilesMaterialsPanel
            api={sourcesApi}
            taskRef={taskRef}
            openSourceId={deepLinkedSource}
          />
        ) : (
          <EmptyState title="Materials unavailable" compact>
            No sources client is configured for this runtime.
          </EmptyState>
        )
      ) : null}

      {surface === 'workspace' ? (
      <>
      {taskRef ? (
        <section className="lg-files__artifacts" aria-label="Task artifacts">
          <h2 className="lg-files__section-title">Task artifacts</h2>
          {artifactError ? (
            <ErrorState
              title="Artifacts unavailable"
              message={artifactError.message}
              code={artifactError.code}
              retryable={artifactError.retryable}
              onRetry={() => setRefreshToken((value) => value + 1)}
            />
          ) : !artifacts ? (
            <EmptyState title="Loading task artifacts…" compact />
          ) : (
            <>
              {artifacts.note ? (
                <p className="lg-files__note">{artifacts.note}</p>
              ) : null}
              <div className="lg-files__artifact-grid">
                {ARTIFACT_SECTIONS.map((section) => {
                  const items = artifacts.categories[section.key]
                  return (
                    <div className="lg-files__artifact" key={section.key}>
                      <h3 className="lg-files__artifact-title" title={section.hint}>
                        {section.label} <span className="lg-files__count">{items.length}</span>
                      </h3>
                      {items.length === 0 ? (
                        <p className="lg-files__note">{section.hint}</p>
                      ) : (
                        <ul className="lg-files__artifact-list">
                          {items.map((entry) => (
                            <li key={entry.path}>
                              <button
                                type="button"
                                className="lg-files__artifact-link"
                                title={entry.path}
                                onClick={() => selectArtifact(entry)}
                              >
                                {entry.name}
                              </button>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  )
                })}
              </div>
              {artifacts.candidate_ref ? (
                <p className="lg-files__note">
                  Candidate: <code>{artifacts.candidate_ref}</code>
                </p>
              ) : null}
            </>
          )}
        </section>
      ) : null}

      <div className="lg-files__body">
        <section className="lg-files__tree-panel" aria-label="Workspace files">
          <div className="lg-files__breadcrumb">
            <button
              type="button"
              className="lg-files__crumb"
              onClick={() => setCwd('')}
            >
              workspace
            </button>
            {segments.map((segment, index) => {
              const target = segments.slice(0, index + 1).join('/')
              return (
                <span key={target}>
                  <span aria-hidden="true"> / </span>
                  <button
                    type="button"
                    className="lg-files__crumb"
                    onClick={() => setCwd(target)}
                  >
                    {segment}
                  </button>
                </span>
              )
            })}
          </div>
          {listError ? (
            <ErrorState
              title="Cannot list files"
              message={listError.message}
              code={listError.code}
              retryable={listError.retryable}
              onRetry={() => setRefreshToken((value) => value + 1)}
            />
          ) : listLoading && !listing ? (
            <EmptyState title="Loading files…" compact />
          ) : !listing || listing.items.length === 0 ? (
            <EmptyState title="This directory is empty" compact>
              Upload a file here or select another directory.
            </EmptyState>
          ) : (
            <ul className="lg-files__tree">
              {listing.items.map((entry) => (
                <li key={entry.path}>
                  <button
                    type="button"
                    className={`lg-files__entry${
                      selected?.path === entry.path ? ' is-selected' : ''
                    }`}
                    title={entry.path}
                    onClick={() =>
                      entry.type === 'directory' ? setCwd(entry.path) : void openFile(entry.path)
                    }
                  >
                    <span className="lg-files__entry-name">{entry.name}</span>
                    <span className="lg-files__entry-meta">
                      {entry.type === 'directory' ? 'dir' : formatSize(entry.size)}
                      {entry.symlink ? ' · symlink' : ''}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="lg-files__preview" aria-label="File preview">
          {previewLoading ? (
            <EmptyState title="Loading preview…" compact />
          ) : previewError ? (
            <ErrorState
              title="Cannot preview file"
              message={previewError.message}
              code={previewError.code}
              retryable={previewError.retryable}
              onRetry={selected ? () => void openFile(selected.path) : undefined}
            />
          ) : !selected ? (
            <EmptyState title="No file selected" compact>
              Select a file from the tree to preview it. Markdown, text and safe images render
              here; HTML and other types are download-only.
            </EmptyState>
          ) : (
            <>
              <div className="lg-files__preview-header">
                <span className="lg-files__preview-name" title={selected.path}>
                  {selected.path}
                </span>
                <StatusBadge kind="neutral" title="File revision">
                  rev {selected.revision ?? 'n/a'}
                </StatusBadge>
                <button
                  type="button"
                  className="lg-button lg-button--primary"
                  onClick={() => void download(selected.path, selected.revision)}
                >
                  Download
                </button>
              </div>
              {selected.truncated ? (
                <p className="lg-files__note">
                  Preview truncated at {formatSize(selected.size)}; download the full file.
                </p>
              ) : null}
              <div className="lg-files__preview-body">
                {previewKind === 'markdown' ? (
                  <MarkdownViewer content={selected.content} />
                ) : previewKind === 'text' ? (
                  <pre className="lg-files__code">{selected.content}</pre>
                ) : previewKind === 'image' ? (
                  imageUrl ? (
                    <img className="lg-files__image" src={imageUrl} alt={selected.name} />
                  ) : (
                    <EmptyState title="Loading image…" compact />
                  )
                ) : previewKind === 'html-disabled' ? (
                  <EmptyState title="HTML preview disabled" compact>
                    HTML is never rendered or executed here. Download the file to inspect it.
                  </EmptyState>
                ) : (
                  <EmptyState title="No inline preview" compact>
                    {selected.media_type} is not a supported inline type. Download it instead.
                  </EmptyState>
                )}
              </div>
            </>
          )}
        </section>
      </div>

      <footer className="lg-files__upload">
        <input
          ref={uploadRef}
          type="file"
          className="lg-visually-hidden"
          onChange={(event) => {
            const file = event.target.files?.[0]
            event.target.value = ''
            if (file) void upload(file)
          }}
        />
        <button
          type="button"
          className="lg-button"
          onClick={() => uploadRef.current?.click()}
        >
          Upload to {cwd ? cwd : 'workspace root'}
        </button>
        <span className="lg-files__note">
          Upload is a protected write; without an injected token the backend returns
          unauthorized and nothing is written. The legacy endpoint and its history are kept; to
          add material to the archive, use Chat (the single regular intake entry).
        </span>
      </footer>
      </>
      ) : null}
    </div>
  )
}

function classify(content: FileContent): PreviewKind {
  const media = content.media_type.toLowerCase()
  const name = content.name.toLowerCase()
  if (SAFE_IMAGE_TYPES.has(media)) return 'image'
  if (media === 'text/html' || name.endsWith('.html') || name.endsWith('.htm')) {
    return 'html-disabled'
  }
  if (name.endsWith('.md') || name.endsWith('.markdown') || media === 'text/markdown') {
    return 'markdown'
  }
  if (media.startsWith('text/') || content.encoding === 'utf-8') return 'text'
  return 'unsupported'
}

function formatSize(size: number | null): string {
  if (size === null) return ''
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / (1024 * 1024)).toFixed(1)} MB`
}

function asApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error
  return new ApiError({
    message: error instanceof Error ? error.message : 'Unexpected error',
    code: 'internal_error',
    httpStatus: null,
    retryable: false,
  })
}

function describeError(error: ApiError, prefix: string): string {
  switch (error.code) {
    case 'unauthorized':
      return `${prefix}: a local access token is required and is not configured in this runtime.`
    case 'revision_conflict':
      return `${prefix}: the file changed on disk (${error.message}). Reload before writing again.`
    case 'path_outside_workspace':
      return `${prefix}: the path is outside the authorized workspace.`
    default:
      return `${prefix}: ${error.message}`
  }
}
