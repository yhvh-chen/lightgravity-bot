/**
 * LG-143 — Keyword/Semantic search panel behaviour.
 *
 * These use injected search clients and deterministic hits. They verify the
 * UI contract (capability gating, separate lists, read-only search calls,
 * honest disabled/mismatch fallback, media kind labels) and make no embedding,
 * OCR or product-model call.
 */

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { SearchApi, SemanticSearchResult, VectorStatusView } from '../src/api/search'
import type { SearchResult, SourcesApi } from '../src/api/sources'
import { AuthProvider } from '../src/app/AuthProvider'
import { ShellProvider } from '../src/app/ShellProvider'
import { MaterialSearch } from '../src/components/MaterialSearch'
import { HEALTH_FIXTURE, backendFetch } from './setup'

beforeEach(() => {
  window.sessionStorage.clear()
  window.history.replaceState(null, '', '/')
})

afterEach(() => {
  cleanup()
  vi.mocked(globalThis.fetch).mockReset()
  vi.mocked(globalThis.fetch).mockImplementation(backendFetch as typeof fetch)
})

function health(semantic: boolean, media = false) {
  return {
    ...HEALTH_FIXTURE,
    contract_version: '1.19.0',
    capabilities: {
      ...HEALTH_FIXTURE.capabilities,
      semantic_search: semantic,
      media_direct_embedding: media,
    },
  }
}

function keywordResult(title = 'keyword hit'): SearchResult {
  return {
    query: 'material',
    kind: [],
    hits: [
      {
        source_id: 'source_keyword',
        source_version: 2,
        content_hash: 'a'.repeat(64),
        basis: 'formal',
        scope: { task_ref: null, project_ref: null, inbox_ref: null },
        title,
        locators: [],
        snippet: 'keyword snippet',
        verified: true,
        stale: false,
        reason: null,
      },
    ],
    stale: [],
    skipped: [],
    index_status: 'ok',
    authorized_scope: {
      task_ref: null,
      project_ref: null,
      inbox_ref: null,
      include_global: true,
    },
  }
}

function semanticResult(kind: 'text' | 'image' | 'audio'): SemanticSearchResult {
  return {
    ...keywordResult('meeting.mp3'),
    hits: [
      {
        source_id: 'source_semantic',
        source_version: 1,
        content_hash: 'b'.repeat(64),
        kind,
        basis: 'original',
        scope: { task_ref: null, project_ref: null, inbox_ref: null },
        title: kind === 'audio' ? 'meeting.mp3' : kind === 'image' ? 'diagram.png' : 'notes.md',
        locators: [],
        snippet: '',
        verified: true,
        stale: false,
        reason: null,
      },
    ],
  }
}

function unavailableResult(reason = 'cache_missing'): SemanticSearchResult {
  return {
    query: 'material',
    kind: [],
    hits: [],
    stale: [],
    skipped: [],
    index_status: 'index_unavailable',
    index_unavailable_reason: reason,
    authorized_scope: {
      task_ref: null,
      project_ref: null,
      inbox_ref: null,
      include_global: true,
    },
  }
}

function status(overrides: Partial<VectorStatusView> = {}): VectorStatusView {
  return {
    enabled: true,
    backend: { configured: true, model: 'fake-embed-v1' },
    cache: { exists: true, readable: true, documents: 3, compatible: true, reason: null },
    model_mismatch_rebuild_required: false,
    reason: null,
    ...overrides,
  }
}

function makeSourcesApi(result: SearchResult = keywordResult()) {
  const search = vi.fn(async (_query: unknown, _signal?: AbortSignal) => result)
  return { api: { search } as unknown as SourcesApi, search }
}

function makeSearchApi(overrides: Partial<SearchApi> = {}) {
  const api: SearchApi = {
    searchKeyword: vi.fn(async () => keywordResult()),
    searchSemantic: vi.fn(async () => semanticResult('text')),
    getVectorStatus: vi.fn(async () => status()),
    rebuildVector: vi.fn(async () => ({
      rebuilt: true,
      indexed: [],
      not_indexed: [],
      documents: 0,
    })),
    ...overrides,
  }
  return api
}

async function renderSearch(
  options: {
    health?: ReturnType<typeof health>
    sources?: ReturnType<typeof makeSourcesApi>
    searchApi?: SearchApi
    canRebuild?: boolean
    role?: string | null
  } = {},
) {
  const sources = options.sources ?? makeSourcesApi()
  const searchApi = options.searchApi ?? makeSearchApi()
  render(
    <AuthProvider>
      <ShellProvider>
        <MaterialSearch
          health={options.health ?? health(false)}
          sourcesApi={sources.api}
          searchApi={searchApi}
          canRebuild={options.canRebuild}
          role={options.role}
        />
      </ShellProvider>
    </AuthProvider>,
  )
  const input = await screen.findByRole('searchbox', { name: 'Search' })
  return { ...sources, searchApi, input }
}

function enter(input: HTMLElement) {
  fireEvent.change(input, { target: { value: 'material' } })
  fireEvent.keyDown(input, { key: 'Enter' })
}

describe('LG-143 material search modes', () => {
  it('keeps Keyword as the default and hides Semantic without the runtime capability', async () => {
    const { input, search, searchApi } = await renderSearch({ health: health(false) })
    expect(screen.queryByRole('tab', { name: 'Semantic' })).toBeNull()
    expect(screen.queryByRole('tab', { name: 'Keyword' })).toBeNull()

    enter(input)
    expect(await screen.findByText('keyword hit')).toBeInTheDocument()
    expect(search).toHaveBeenCalledTimes(1)
    const query = search.mock.calls[0][0] as unknown as Record<string, unknown>
    expect(query).not.toHaveProperty('rebuild_if_missing')
    expect(searchApi.getVectorStatus).not.toHaveBeenCalled()
    expect(searchApi.rebuildVector).not.toHaveBeenCalled()
  })

  it('shows Semantic only behind the capability and keeps its media hit separate', async () => {
    const searchApi = makeSearchApi({
      searchSemantic: vi.fn(async () => semanticResult('audio')),
    })
    const { input, search, searchApi: api } = await renderSearch({
      health: health(true, true),
      searchApi,
    })
    // A search is the existing explicit action that opens the panel.
    enter(input)
    expect(await screen.findByText('keyword hit')).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Keyword' })).toHaveAttribute('aria-selected', 'true')

    fireEvent.click(screen.getByRole('tab', { name: 'Semantic' }))
    await waitFor(() => expect(api.getVectorStatus).toHaveBeenCalledTimes(1))
    expect(screen.getByText(/Shared materials · Semantic search/)).toBeVisible()

    enter(input)
    expect(await screen.findByText('meeting.mp3')).toBeInTheDocument()
    expect(screen.getByText('Audio')).toBeInTheDocument()
    expect(screen.getByText(/no transcript/i)).toBeInTheDocument()
    expect(screen.getByText('media direct')).toBeInTheDocument()
    expect(screen.getByText('Open in Tasks')).toBeInTheDocument()
    expect(search).toHaveBeenCalledTimes(1)
    expect(api.searchSemantic).toHaveBeenCalledTimes(1)
    const query = vi.mocked(api.searchSemantic).mock.calls[0][0] as unknown as Record<
      string,
      unknown
    >
    expect(query).not.toHaveProperty('rebuild_if_missing')
    expect(api.rebuildVector).not.toHaveBeenCalled()

    // Switching back shows the separate keyword list, not a blended score.
    fireEvent.click(screen.getByRole('tab', { name: 'Keyword' }))
    enter(input)
    expect(await screen.findByText('keyword hit')).toBeInTheDocument()
    expect(screen.queryByText('meeting.mp3')).toBeNull()
  })

  it('reports a model mismatch and falls back explicitly without rebuild actions', async () => {
    const searchApi = makeSearchApi({
      getVectorStatus: vi.fn(async () =>
        status({
          model_mismatch_rebuild_required: true,
          cache: {
            exists: true,
            readable: true,
            compatible: false,
            reason: 'model_mismatch_rebuild_required',
            vector_model: 'old-model',
          },
        }),
      ),
    })
    const { input, search, searchApi: api } = await renderSearch({
      health: health(true),
      searchApi,
      role: 'member',
    })
    enter(input)
    expect(await screen.findByText('keyword hit')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: 'Semantic' }))
    expect(
      await screen.findByText(/does not match the configured model/i),
    ).toBeInTheDocument()
    expect(screen.getByText(/Ask an administrator/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^rebuild/i })).toBeNull()
    expect(api.rebuildVector).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: 'Switch to Keyword' }))
    expect(await screen.findByText('keyword hit')).toBeInTheDocument()
    expect(search).toHaveBeenCalledTimes(2)
    expect(api.searchSemantic).not.toHaveBeenCalled()
  })

  it('reports an unavailable embedding backend and returns to Keyword', async () => {
    const searchApi = makeSearchApi({
      getVectorStatus: vi.fn(async () =>
        status({
          enabled: true,
          backend: { configured: false, model: null },
          reason: 'embedding_disabled',
        }),
      ),
    })
    const { input, search } = await renderSearch({ health: health(true), searchApi })
    enter(input)
    expect(await screen.findByText('keyword hit')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: 'Semantic' }))
    expect(
      await screen.findByText(/Semantic search is unavailable/i),
    ).toBeInTheDocument()
    expect(screen.getByText(/embedding_disabled/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Switch to Keyword' }))
    expect(await screen.findByText('keyword hit')).toBeInTheDocument()
    expect(search).toHaveBeenCalledTimes(2)
    expect(searchApi.searchSemantic).not.toHaveBeenCalled()
  })

  it('surfaces index_unavailable for a semantic query and offers the fallback', async () => {
    const searchApi = makeSearchApi({
      searchSemantic: vi.fn(async () => unavailableResult()),
    })
    const { input, search, searchApi: api } = await renderSearch({
      health: health(true),
      searchApi,
    })
    enter(input)
    expect(await screen.findByText('keyword hit')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: 'Semantic' }))
    await waitFor(() => expect(api.getVectorStatus).toHaveBeenCalled())
    enter(input)

    expect(await screen.findByText(/Semantic index unavailable/i)).toBeInTheDocument()
    expect(screen.getByText(/cache_missing/)).toBeInTheDocument()
    expect(api.rebuildVector).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Switch to Keyword' }))
    expect(await screen.findByText('keyword hit')).toBeInTheDocument()
    expect(search).toHaveBeenCalledTimes(2)
  })

  it('never starts a search from typing alone', async () => {
    const { input, search, searchApi } = await renderSearch({ health: health(true) })
    fireEvent.change(input, { target: { value: 'material' } })
    expect(search).not.toHaveBeenCalled()
    expect(searchApi.searchSemantic).not.toHaveBeenCalled()
    expect(searchApi.getVectorStatus).not.toHaveBeenCalled()
  })
})
