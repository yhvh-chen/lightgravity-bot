/**
 * Files view + client smoke tests (LG-014).
 *
 * The view is exercised against an injected ``FilesApi`` double so no backend
 * or fabricated JSON is required; the client test asserts that the runtime
 * token is injected only when configured (readonly browsing stays anonymous).
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  createFilesApi,
  type FileContent,
  type FileEntry,
  type FilesApi,
  type TaskArtifacts,
} from '../src/api/files'
import { ShellProvider } from '../src/app/ShellProvider'
import { FilesPanel, FilesView } from '../src/views/files/FilesView'

const createObjectURL = vi.fn(() => 'blob:files')
const revokeObjectURL = vi.fn()

beforeAll(() => {
  Object.defineProperty(URL, 'createObjectURL', { writable: true, value: createObjectURL })
  Object.defineProperty(URL, 'revokeObjectURL', { writable: true, value: revokeObjectURL })
})

beforeEach(() => {
  vi.clearAllMocks()
})

function entry(
  path: string,
  type: FileEntry['type'] = 'file',
  mediaType: string | null = 'application/octet-stream',
): FileEntry {
  return {
    name: path.includes('/') ? path.slice(path.lastIndexOf('/') + 1) : path,
    path,
    type,
    size: type === 'file' ? 12 : null,
    modified_at: '2026-10-15T00:00:00Z',
    symlink: false,
    media_type: type === 'file' ? mediaType : null,
    revision: type === 'file' ? '12-1' : null,
  }
}

function content(overrides: Partial<FileContent> = {}): FileContent {
  return {
    path: 'notes.md',
    name: 'notes.md',
    size: 12,
    truncated: false,
    media_type: 'text/markdown',
    encoding: 'utf-8',
    revision: '12-1',
    content: 'body',
    ...overrides,
  }
}

function makeApi(overrides: Partial<FilesApi> = {}): FilesApi {
  return {
    listFiles: vi.fn(async () => ({ path: '', items: [], next_cursor: null })),
    readContent: vi.fn(async () => content()),
    downloadFile: vi.fn(async () => ({
      blob: new Blob(['x']),
      filename: 'x.bin',
      mediaType: 'application/octet-stream',
      revision: '1-1',
    })),
    uploadFile: vi.fn(async () => ({
      path: 'x.bin',
      name: 'x.bin',
      size: 1,
      revision: '2-2',
      created: true,
    })),
    taskArtifacts: vi.fn(async () => {
      throw new Error('not stubbed')
    }),
    ...overrides,
  }
}

function renderPanel(api: FilesApi, taskRef: string | null = null) {
  return render(<FilesPanel taskRef={taskRef} runRef={null} api={api} />)
}

describe('FilesPanel', () => {
  it('lists the workspace and previews markdown without executing HTML', async () => {
    const api = makeApi({
      listFiles: vi.fn(async () => ({
        path: '',
        items: [entry('notes.md', 'file', 'text/markdown'), entry('docs', 'directory', null)],
        next_cursor: null,
      })),
      readContent: vi.fn(async () =>
        content({ content: '# Title\n<script>alert(1)</script>' }),
      ),
    })
    renderPanel(api)

    expect(screen.getByText('Global workspace')).toBeInTheDocument()
    fireEvent.click(await screen.findByTitle('notes.md'))

    expect(await screen.findByRole('heading', { name: 'Title' })).toBeInTheDocument()
    expect(screen.getByText('<script>alert(1)</script>')).toBeInTheDocument()
    expect(document.querySelector('script')).toBeNull()
  })

  it('never renders HTML and offers it for download only', async () => {
    const api = makeApi({
      listFiles: vi.fn(async () => ({
        path: '',
        items: [entry('page.html', 'file', 'text/html')],
        next_cursor: null,
      })),
      readContent: vi.fn(async () =>
        content({ path: 'page.html', name: 'page.html', media_type: 'text/html' }),
      ),
    })
    renderPanel(api)

    fireEvent.click(await screen.findByTitle('page.html'))
    expect(await screen.findByText('HTML preview disabled')).toBeInTheDocument()
    expect(api.readContent).toHaveBeenCalledWith('page.html')
  })

  it('shows an honest unsupported state for binary types', async () => {
    const api = makeApi({
      listFiles: vi.fn(async () => ({
        path: '',
        items: [entry('doc.pdf', 'file', 'application/pdf')],
        next_cursor: null,
      })),
      readContent: vi.fn(async () =>
        content({
          path: 'doc.pdf',
          name: 'doc.pdf',
          media_type: 'application/pdf',
          encoding: 'base64',
        }),
      ),
    })
    renderPanel(api)

    fireEvent.click(await screen.findByTitle('doc.pdf'))
    expect(await screen.findByText('No inline preview')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Download' })).toBeInTheDocument()
  })

  it('renders safe images through the download path', async () => {
    const api = makeApi({
      listFiles: vi.fn(async () => ({
        path: '',
        items: [entry('photo.png', 'file', 'image/png')],
        next_cursor: null,
      })),
      readContent: vi.fn(async () =>
        content({ path: 'photo.png', name: 'photo.png', media_type: 'image/png' }),
      ),
    })
    renderPanel(api)

    fireEvent.click(await screen.findByTitle('photo.png'))
    const image = await screen.findByRole('img', { name: 'photo.png' })
    expect(image).toHaveAttribute('src', 'blob:files')
    expect(api.downloadFile).toHaveBeenCalledWith('photo.png', '12-1')
  })

  it('associates task artifacts while keeping the task scope visible', async () => {
    const artifacts: TaskArtifacts = {
      task_id: 'task_1',
      task_revision: 3,
      requirements_revision: 1,
      deliverable_revision: 0,
      candidate_ref: 'run_candidate',
      evidence_refs: ['artifacts/report.md'],
      check_records: [],
      workspace_ref: 'taskws',
      categories: {
        inputs: [entry('taskws/inputs/spec.md', 'file', 'text/markdown')],
        candidates: [],
        deliverables: [],
        evidence: [entry('taskws/runs/run_1/events.jsonl', 'file', 'application/json')],
        other: [],
      },
      note: null,
    }
    const api = makeApi({
      taskArtifacts: vi.fn(async () => artifacts),
      listFiles: vi.fn(async () => ({ path: 'taskws', items: [], next_cursor: null })),
    })
    renderPanel(api, 'task_1')

    expect(await screen.findByText('Task artifacts')).toBeInTheDocument()
    expect(screen.getByText('task_1')).toBeInTheDocument()
    expect(screen.getByText('run_candidate')).toBeInTheDocument()
    expect(screen.getByText('Run evidence')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'spec.md' }))
    await waitFor(() => expect(api.readContent).toHaveBeenCalledWith('taskws/inputs/spec.md'))
  })

  it('inherits the active task scope from the shell when mounted without props', async () => {
    window.history.replaceState(null, '', '?view=files&task=task_shell')
    const scoped: TaskArtifacts = {
      task_id: 'task_shell',
      task_revision: 1,
      requirements_revision: 1,
      deliverable_revision: 0,
      candidate_ref: null,
      evidence_refs: [],
      check_records: [],
      workspace_ref: null,
      categories: {
        inputs: [],
        candidates: [],
        deliverables: [],
        evidence: [],
        other: [],
      },
      note: 'Task has no workspace_ref; no files to associate.',
    }
    const api = makeApi({ taskArtifacts: vi.fn(async () => scoped) })
    render(
      <ShellProvider>
        <FilesView api={api} />
      </ShellProvider>,
    )

    expect(await screen.findByText('task_shell')).toBeInTheDocument()
    expect(api.taskArtifacts).toHaveBeenCalledWith('task_shell', expect.anything())
    window.history.replaceState(null, '', '/')
  })
})

describe('files client token injection', () => {
  function jsonResponse(body: unknown): Response {
    return {
      ok: true,
      status: 200,
      headers: { get: (name: string) => (name.toLowerCase() === 'content-type' ? 'application/json' : null) },
      json: async () => body,
    } as unknown as Response
  }

  it('does not send a token for readonly browsing', async () => {
    const fetchMock = vi.mocked(globalThis.fetch)
    fetchMock.mockResolvedValueOnce(jsonResponse({ path: '', items: [], next_cursor: null }))
    await createFilesApi().listFiles('docs')
    const [url, init] = fetchMock.mock.calls.at(-1)!
    expect(String(url)).toContain('/api/v1/files?path=docs')
    expect(init?.headers).not.toHaveProperty('X-LG-Token')
  })

  it('injects the runtime token on protected uploads', async () => {
    const fetchMock = vi.mocked(globalThis.fetch)
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ path: 'a.txt', name: 'a.txt', size: 1, revision: '1-1', created: true }),
    )
    await createFilesApi({ getApiToken: () => 'tok' }).uploadFile(
      'a.txt',
      new Blob(['x']),
      '0-0',
    )
    const [url, init] = fetchMock.mock.calls.at(-1)!
    expect(String(url)).toContain('/api/v1/files/upload?path=a.txt&expected_revision=0-0')
    expect((init?.headers as Record<string, string>)['X-LG-Token']).toBe('tok')
  })
})


describe('Task definition and canonical Markdown artifacts (LG242/245)', () => {
  const ref = 'evidence:run_1/launch-brief.md@sha256:abc'
  const artifacts: TaskArtifacts = {
    task_id: 'task_1', task_revision: 1, requirements_revision: 1,
    deliverable_revision: 0, candidate_ref: null, evidence_refs: [ref],
    check_records: [], workspace_ref: 'tasks/task_1', note: null,
    categories: { inputs: [], candidates: [], deliverables: [], other: [],
      evidence: [{ ...entry('run_1/launch-brief.md'), evidence_ref: ref }] },
  }

  it('opens canonical evidence via its Task resolver and renders Markdown', async () => {
    const api = makeApi({
      taskArtifacts: vi.fn(async () => artifacts),
      readArtifact: vi.fn(async () => content({ path: ref, evidence_ref: ref,
        name: 'launch-brief.md', content: '# Launch brief\n<script>unsafe()</script>' })),
      downloadArtifact: vi.fn(async () => ({ blob: new Blob(['brief']), filename: 'launch-brief.md',
        mediaType: 'text/markdown', revision: '12-1' })),
    })
    renderPanel(api, 'task_1')
    fireEvent.click(await screen.findByRole('button', { name: 'launch-brief.md' }))
    expect(await screen.findByRole('heading', { name: 'Launch brief' })).toBeInTheDocument()
    expect(api.readArtifact).toHaveBeenCalledWith('task_1', ref)
    expect(api.readContent).not.toHaveBeenCalled()
    expect(document.querySelector('script')).toBeNull()
  })

  it('shows raw canonical TASK.md frontmatter read-only, outside the worktree', async () => {
    const api = makeApi({
      taskArtifacts: vi.fn(async () => artifacts),
      readTaskDefinition: vi.fn(async () => content({ path: 'TASK.md', name: 'TASK.md',
        read_only: true, content: '---\nrequirements_revision: 3\nacceptance:\n  status: accepted\n---\n# Task' })),
    })
    renderPanel(api, 'task_1')
    fireEvent.click(screen.getByRole('button', { name: 'TASK.md · Read-only' }))
    expect(await screen.findByText(/requirements_revision: 3/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Download' })).not.toBeInTheDocument()
    expect(api.readTaskDefinition).toHaveBeenCalledWith('task_1')
    expect(api.readContent).not.toHaveBeenCalled()
  })

  it('does not let a late artifact response replace another Task preview', async () => {
    let resolve!: (value: FileContent) => void
    const api = makeApi({ taskArtifacts: vi.fn(async () => artifacts),
      readArtifact: vi.fn(() => new Promise<FileContent>((done) => { resolve = done })),
    })
    const view = renderPanel(api, 'task_1')
    fireEvent.click(await screen.findByRole('button', { name: 'launch-brief.md' }))
    view.rerender(<FilesPanel taskRef="task_2" runRef={null} api={api} />)
    resolve(content({ content: '# Stale artifact' }))
    await waitFor(() => expect(screen.getByText('No file selected')).toBeInTheDocument())
    expect(screen.queryByRole('heading', { name: 'Stale artifact' })).not.toBeInTheDocument()
  })
})


it('requests canonical content and download endpoints without treating their envelope as a file', async () => {
  const ref = 'evidence:run_1/launch-brief.md@sha256:abc'
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(new Response(JSON.stringify({ ...content(), evidence_ref: ref }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
    .mockResolvedValueOnce(new Response('# Launch brief', { status: 200,
      headers: { 'Content-Disposition': 'attachment; filename="launch-brief.md"', 'X-LG-Revision': '12-1' } }))
  vi.stubGlobal('fetch', fetchMock)
  const api = createFilesApi()
  const opened = await api.readArtifact!('task_1', ref)
  expect(opened.path).toBe(ref)
  expect(opened.content).toBe('body')
  const downloaded = await api.downloadArtifact!('task_1', ref, opened.revision)
  expect(downloaded.filename).toBe('launch-brief.md')
  const first = new URL(String(fetchMock.mock.calls[0][0]), 'http://localhost')
  const second = new URL(String(fetchMock.mock.calls[1][0]), 'http://localhost')
  expect(first.pathname).toBe('/api/v1/tasks/task_1/artifacts/content')
  expect(first.searchParams.get('evidence_ref')).toBe(ref)
  expect(second.pathname).toBe('/api/v1/tasks/task_1/artifacts/download')
  expect(second.searchParams.get('revision')).toBe('12-1')
  vi.unstubAllGlobals()
})
