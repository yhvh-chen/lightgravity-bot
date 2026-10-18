/**
 * LG-044 selected-material frontend tests (docs/10 §2–§5, §8–§9).
 *
 * These are **local mock component/hook tests** — no backend is running, so
 * they cannot prove E2E behaviour (that is LG-047). They cover the checks the
 * task requires:
 *
 *  * selection Task isolation (switching Task clears the selection);
 *  * request serialization: `selected_sources` is omitted when empty and
 *    carries the real `source_id`/`source_version`/`content_hash` (never an
 *    invented hash) when set;
 *  * the 3-source limit;
 *  * error rendering (stale/revoked/capability_unavailable) surfaced honestly;
 *  * meaningful backlink target metadata + Sources truncation feedback;
 *  * legacy responses with no source fields render unchanged.
 */

import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '../src/api/client'
import type {
  ChatApi,
  ChatScope,
  ChatSubmitResult,
  ResolvedSourceBinding,
} from '../src/api/chat'
import type { SourceView, SourcesApi } from '../src/api/sources'
import { ShellProvider } from '../src/app/ShellProvider'
import { ChatBody } from '../src/views/chat/ChatBody'
import { ChatSourcePicker } from '../src/views/chat/ChatSourcePicker'
import { ChatSources } from '../src/views/chat/ChatSources'
import {
  MAX_SELECTED_SOURCES,
  useChatSelection,
  type SelectedMaterial,
} from '../src/views/chat/useChatSelection'

afterEach(cleanup)

function source(overrides: Partial<SourceView> = {}): SourceView {
  return {
    id: 'source_01J',
    source_id: 'source_01J',
    title: 'notes.md',
    title_origin: 'user',
    status: 'extracted',
    context_selectable: true,
    revision: 2,
    etag: 'rev-2',
    scope: { task_ref: null, project_ref: null, inbox_ref: 'inbox_1' },
    origin: { kind: 'upload', external_ref: null, fetched: false },
    content_hash: 'realhash000000000000000000000000000000000000000000000000000000000000',
    stat_revision: '12-1',
    source_version: 3,
    original: null,
    derivatives: [],
    formal: null,
    index: null,
    receipt_ref: null,
    created_at: null,
    updated_at: null,
    path: 'sources/source_01J/SOURCE.md',
    ...overrides,
  }
}

function makeSourcesApi(overrides: Partial<SourcesApi> = {}): SourcesApi {
  return {
    createSource: vi.fn(),
    listSources: vi.fn(async () => ({ items: [source()], next_cursor: null })),
    getSource: vi.fn(async () => source()),
    getReceipt: vi.fn(),
    getContent: vi.fn(),
    downloadSource: vi.fn(),
    editFormal: vi.fn(),
    sourceAction: vi.fn(),
    appendInboxMessage: vi.fn(),
    search: vi.fn(),
    ...overrides,
  } as unknown as SourcesApi
}

function makeChatApi(
  sendResult: ChatSubmitResult = { kind: 'answer', reply: 'ok' },
): ChatApi & {
  sent: Array<{ scope: ChatScope; body: Record<string, unknown> }>
  messages: Record<string, unknown[]>
} {
  const sent: Array<{ scope: ChatScope; body: Record<string, unknown> }> = []
  const messages: Record<string, unknown[]> = {}
  return {
    sent,
    messages,
    readMessages: vi.fn(async (scope: ChatScope) => ({
      items: messages[scope.taskRef ?? 'global'] ?? [],
      next_cursor: null,
    })),
    sendMessage: vi.fn(async (scope, body) => {
      sent.push({ scope, body: body as unknown as Record<string, unknown> })
      return sendResult
    }),
    createTask: vi.fn(async () => ({ kind: 'create_task' })),
  } as unknown as ChatApi & { sent: typeof sent; messages: typeof messages }
}

describe('useChatSelection (LG-044 §2/§8)', () => {
  function Harness({ taskRef }: { taskRef: string | null }) {
    const selection = useChatSelection(taskRef)
    return (
      <div>
        <output data-testid="count">{selection.selection.length}</output>
        <output data-testid="refs">
          {JSON.stringify(selection.requestRefs ?? null)}
        </output>
        <button
          type="button"
          onClick={() => selection.toggle(source(), 'global')}
        >
          add
        </button>
      </div>
    )
  }

  it('omits requestRefs when nothing is selected (legacy unchanged)', () => {
    render(<Harness taskRef={null} />)
    expect(screen.getByTestId('refs').textContent).toBe('null')
  })

  it('clears the selection when the Task scope changes', () => {
    const { rerender } = render(<Harness taskRef={null} />)
    act(() => {
      fireEvent.click(screen.getByText('add'))
    })
    expect(screen.getByTestId('count').textContent).toBe('1')
    expect(screen.getByTestId('refs').textContent).toContain('source_01J')

    rerender(<Harness taskRef="task_2" />)
    expect(screen.getByTestId('count').textContent).toBe('0')
    expect(screen.getByTestId('refs').textContent).toBe('null')
  })

  it('serializes the real version and hash, never a fabricated hash', () => {
    render(<Harness taskRef={null} />)
    act(() => {
      fireEvent.click(screen.getByText('add'))
    })
    const refs = JSON.parse(screen.getByTestId('refs').textContent ?? 'null')
    expect(refs).toEqual([
      {
        source_id: 'source_01J',
        source_version: 3,
        content_hash:
          'realhash000000000000000000000000000000000000000000000000000000000000',
      },
    ])
  })
})

describe('ChatSourcePicker (LG-044 §3/§5)', () => {
  const baseProps = {
    api: makeSourcesApi(),
    taskRef: null as string | null,
    selection: [] as SelectedMaterial[],
    atLimit: false,
    onToggle: vi.fn(),
    onRemove: vi.fn(),
    onClear: vi.fn(),
  }

  it('refuses a 4th selection and states the limit (server validates too)', () => {
    render(
      <ChatSourcePicker
        {...baseProps}
        selection={[1, 2, 3].map((n) => ({
          source_id: `s${n}`,
          source_version: 1,
          title: `t${n}`,
          scope: 'global' as const,
          status: 'extracted',
          selectable: true,
        }))}
        atLimit
      />,
    )
    expect(screen.getByText(`Limit reached: at most ${MAX_SELECTED_SOURCES} sources.`)).toBeTruthy()
  })

  it('does not select failed or revoked sources', async () => {
    const api = makeSourcesApi({
      listSources: vi.fn(async () => ({
        items: [
          source({ source_id: 'ok', title: 'ok.md', status: 'extracted' }),
          source({ source_id: 'bad', title: 'bad.md', status: 'failed' }),
          source({ source_id: 'rev', title: 'rev.md', status: 'archived' }),
        ],
        next_cursor: null,
      })),
    })
    render(<ChatSourcePicker {...baseProps} api={api} />)
    fireEvent.click(screen.getByText('Select materials'))
    const ok = (await screen.findByLabelText('Select ok.md')) as HTMLInputElement
    const bad = screen.getByLabelText('Select bad.md') as HTMLInputElement
    const rev = screen.getByLabelText('Select rev.md') as HTMLInputElement
    expect(ok.disabled).toBe(false)
    expect(bad.disabled).toBe(true)
    expect(rev.disabled).toBe(true)
    expect(screen.getByText('revoked — not selectable')).toBeTruthy()
  })

  it('disables vector-only partial and extracted materials but enables actual text', async () => {
    const api = makeSourcesApi({ listSources: vi.fn(async () => ({ items: [
      source({ source_id: 'media', title: 'audio.wav', status: 'partial', context_selectable: false }),
      source({ source_id: 'image', title: 'image.png', status: 'extracted', context_selectable: false }),
      source({ source_id: 'old', title: 'old.txt', text_status: 'pending', context_selectable: true }),
      source({ source_id: 'unknown', title: 'unknown.txt', context_selectable: undefined }),
    ], next_cursor: null })) })
    render(<ChatSourcePicker {...baseProps} api={api} />)
    fireEvent.click(screen.getByText('Select materials'))
    expect(((await screen.findByLabelText('Select audio.wav')) as HTMLInputElement).disabled).toBe(true)
    expect((screen.getByLabelText('Select image.png') as HTMLInputElement).disabled).toBe(true)
    expect((screen.getByLabelText('Select old.txt') as HTMLInputElement).disabled).toBe(false)
    expect((screen.getByLabelText('Select unknown.txt') as HTMLInputElement).disabled).toBe(true)
    expect(screen.getAllByText('no readable text body — not selectable')).toHaveLength(2)
  })

  it('marks the current Task scope on each row', async () => {
    const api = makeSourcesApi({
      listSources: vi.fn(async () => ({
        items: [
          source({ source_id: 'g', title: 'global.md', scope: { task_ref: null, project_ref: null, inbox_ref: null } }),
          source({ source_id: 't', title: 'task.md', scope: { task_ref: 'task_9', project_ref: null, inbox_ref: null } }),
        ],
        next_cursor: null,
      })),
    })
    render(<ChatSourcePicker {...baseProps} api={api} taskRef="task_9" />)
    fireEvent.click(screen.getByText('Select materials'))
    await screen.findByLabelText('Select global.md')
    expect(screen.getAllByText('global').length).toBeGreaterThan(0)
    expect(screen.getAllByText('task').length).toBeGreaterThan(0)
  })

  it('excludes other Tasks\' sources in Task scope (cross-Task isolation)', async () => {
    const listSources = vi.fn(async (filter?: { task_ref?: string | null }) => {
      if (filter?.task_ref === 'task_9') {
        return {
          items: [
            source({
              source_id: 't9',
              title: 'task9.md',
              scope: { task_ref: 'task_9', project_ref: null, inbox_ref: null },
            }),
          ],
          next_cursor: null,
        }
      }
      return {
        items: [
          source({ source_id: 'g', title: 'global.md', scope: { task_ref: null, project_ref: null, inbox_ref: null } }),
          source({ source_id: 'other', title: 'other-task.md', scope: { task_ref: 'task_other', project_ref: null, inbox_ref: null } }),
        ],
        next_cursor: null,
      }
    })
    render(<ChatSourcePicker {...baseProps} api={makeSourcesApi({ listSources })} taskRef="task_9" />)
    fireEvent.click(screen.getByText('Select materials'))
    await screen.findByLabelText('Select task9.md')
    expect(screen.getByLabelText('Select global.md')).toBeTruthy()
    expect(screen.queryByLabelText('Select other-task.md')).toBeNull()
  })

  it('shows an honest error state when the list fails', async () => {
    const api = makeSourcesApi({
      listSources: vi.fn(async () => {
        throw new ApiError({
          message: 'index unavailable',
          code: 'capability_unavailable',
          httpStatus: 503,
          retryable: true,
        })
      }),
    })
    render(<ChatSourcePicker {...baseProps} api={api} />)
    fireEvent.click(screen.getByText('Select materials'))
    expect(await screen.findByText('index unavailable')).toBeTruthy()
    expect(screen.getByText('(capability_unavailable)')).toBeTruthy()
  })
})

describe('ChatSources (LG-044 §4)', () => {
  const binding: ResolvedSourceBinding = {
    source_id: 'source_01J',
    source_version: 3,
    content_hash: 'abcdef0123456789',
    layer: 'formal',
    locator: 'source_01J#v3',
    char_count: 4200,
    truncated: false,
    truncation: null,
  }

  it('renders real source metadata, the provided-context note, and a backlink', () => {
    const onOpen = vi.fn()
    render(<ChatSources data={{ resolved_source_bindings: [binding] }} onOpen={onOpen} />)
    expect(screen.getByText('Sources')).toBeTruthy()
    expect(screen.getByText('source_01J')).toBeTruthy()
    expect(screen.getByText('v3')).toBeTruthy()
    expect(screen.getByText('#abcdef012345')).toBeTruthy()
    expect(screen.getByText('formal')).toBeTruthy()
    expect(screen.getByText(/NOT span-verified/)).toBeTruthy()
    fireEvent.click(screen.getByText('Open in Tasks'))
    // Backlink target is the real source id, not a fabricated local path.
    expect(onOpen).toHaveBeenCalledWith('source_01J')
  })

  it('surfaces truncation feedback with kept vs original counts', () => {
    render(
      <ChatSources
        data={{
          context_truncated: true,
          provided_context_note: 'Sources are provided as context; citations are NOT span-verified.',
          resolved_source_bindings: [
            {
              ...binding,
              truncated: true,
              char_count: 10000,
              truncation: {
                reason: 'total_budget',
                original_char_count: 30000,
                kept_char_count: 10000,
                max_total: 12000,
              },
            },
          ],
        }}
        onOpen={vi.fn()}
      />,
    )
    expect(screen.getAllByText('truncated').length).toBeGreaterThan(0)
    expect(screen.getByText(/kept 10000 of 30000 chars/)).toBeTruthy()
    expect(screen.getByText(/max total 12000/)).toBeTruthy()
  })

  it('renders nothing for legacy replies without source fields', () => {
    const { container } = render(<ChatSources data={null} onOpen={vi.fn()} />)
    expect(container.firstChild).toBeNull()
  })
})

describe('ChatBody integration (LG-044 §8)', () => {
  function renderChat(api: ChatApi, sourcesApi: SourcesApi, taskRefFromUrl?: string) {
    if (taskRefFromUrl) window.history.replaceState(null, '', `/?task=${taskRefFromUrl}`)
    return render(
      <ShellProvider>
        <ChatBody variant="main" api={api} sourcesApi={sourcesApi} />
      </ShellProvider>,
    )
  }

  it('sends selected_sources when a material is selected and clears it after', async () => {
    const sourcesApi = makeSourcesApi({
      listSources: vi.fn(async () => ({ items: [source()], next_cursor: null })),
    })
    const api = makeChatApi()
    renderChat(api, sourcesApi)
    window.history.replaceState(null, '', '/')

    // Open the picker and select the material.
    fireEvent.click(await screen.findByText('Select materials'))
    const checkbox = (await screen.findByLabelText('Select notes.md')) as HTMLInputElement
    fireEvent.click(checkbox)
    expect(checkbox.checked).toBe(true)

    const composer = screen.getByLabelText('Message for Global')
    fireEvent.change(composer, { target: { value: 'summarize' } })
    fireEvent.keyDown(composer, { key: 'Enter' })

    await waitFor(() => expect(api.sent).toHaveLength(1))
    expect(api.sent[0].body.selected_sources).toEqual([
      {
        source_id: 'source_01J',
        source_version: 3,
        content_hash:
          'realhash000000000000000000000000000000000000000000000000000000000000',
      },
    ])
    // Implementation choice: selection cleared after a successful send.
    await waitFor(() =>
      expect(screen.getByText(/No materials selected/)).toBeTruthy(),
    )
  })

  it('omits selected_sources entirely when nothing is selected', async () => {
    const sourcesApi = makeSourcesApi()
    const api = makeChatApi()
    renderChat(api, sourcesApi)

    const composer = await screen.findByLabelText('Message for Global')
    fireEvent.change(composer, { target: { value: 'plain' } })
    fireEvent.keyDown(composer, { key: 'Enter' })

    await waitFor(() => expect(api.sent).toHaveLength(1))
    expect('selected_sources' in api.sent[0].body).toBe(false)
  })

  it('renders reply Sources from the send response data', async () => {
    const sourcesApi = makeSourcesApi()
    const api = makeChatApi({
      kind: 'answer',
      reply: 'here you go',
      data: {
        resolved_source_bindings: [
          {
            source_id: 'source_01J',
            source_version: 3,
            content_hash: 'abcdef0123456789',
            layer: 'machine',
            locator: 'source_01J#v3',
            char_count: 10,
            truncated: false,
            truncation: null,
          },
        ],
        provided_context_note: 'Sources are provided as context; citations are NOT span-verified.',
      },
    })
    renderChat(api, sourcesApi)

    const composer = await screen.findByLabelText('Message for Global')
    fireEvent.change(composer, { target: { value: 'summarize' } })
    fireEvent.keyDown(composer, { key: 'Enter' })

    expect(await screen.findByText('Sources')).toBeTruthy()
    expect(screen.getByText('source_01J')).toBeTruthy()
    expect(screen.getByText(/NOT span-verified/)).toBeTruthy()
  })

  it('surfaces a stale send error honestly and keeps the draft', async () => {
    const sourcesApi = makeSourcesApi()
    const api = makeChatApi()
    api.sendMessage = vi.fn(async () => {
      throw new ApiError({
        message: 'source version changed',
        code: 'source_stale',
        httpStatus: 409,
        retryable: false,
      })
    })
    renderChat(api, sourcesApi)

    const composer = await screen.findByLabelText('Message for Global')
    fireEvent.change(composer, { target: { value: 'summarize' } })
    fireEvent.keyDown(composer, { key: 'Enter' })

    expect(await screen.findByText(/Send failed:/)).toBeTruthy()
    expect(screen.getByText('(source_stale)')).toBeTruthy()
    expect(composer).toHaveValue('summarize')
  })
})
