/**
 * LG-146 — shared material-intake adapter checks (docs/08 §20).
 *
 * These tests only prove the frozen wire shapes/signatures and capability
 * gates compile and behave as declared. They do not claim the 1.19.0 runtime
 * exists: the product is still 1.18.0 and every gate is false there.
 */

import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  MEDIA_DIRECT_EMBEDDING_CAPABILITY,
  MINIMUM_MATERIAL_INTAKE_CONTRACT,
  SEMANTIC_SEARCH_CAPABILITY,
  MATERIAL_INTAKE_V2_CAPABILITY,
  assertBackendCompatible,
  supportsAccounts,
  supportsMaterialIntakeV2,
  supportsMediaDirectEmbedding,
  supportsPersonalChat,
  supportsSemanticSearch,
} from '../src/api/backendCompatibility'
import { createSourcesApi, isSourceReceiptV2 } from '../src/api/sources'
import type {
  SemanticSearchHit,
  SourceReceipt,
  SourceReceiptV2,
  SourceRef,
} from '../src/api/sources'
import {
  INTAKE_MAX_CONCURRENT_JOBS,
  INTAKE_MAX_EMBEDDING_CALLS,
  INTAKE_MAX_NATIVE_TEXT_BYTES,
  INTAKE_MAX_OCR_PAGES,
  INTAKE_MAX_ORIGINAL_BYTES,
  INTAKE_MAX_RETRIES,
  INTAKE_MAX_TOKENS_PER_PAGE,
  INTAKE_TIMEOUT_SECONDS,
  MESSAGE_SOURCE_REFS_MAX,
} from '../src/api/types'
import { HEALTH_FIXTURE } from './setup'

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

function health(version: string, capabilities: Record<string, boolean> = {}) {
  return {
    ...HEALTH_FIXTURE,
    contract_version: version,
    capabilities: { ...HEALTH_FIXTURE.capabilities, ...capabilities },
  }
}

const V2_RECEIPT: SourceReceiptV2 = {
  source_id: 'source_01J',
  revision: 4,
  status: 'extracted',
  source_version: 1,
  receipt_version: 2,
  partial: true,
  items: [
    {
      filename: 'meeting.mp3',
      status: 'extracted',
      stage: 'done',
      searchable: false,
      text: {
        status: 'unavailable',
        reason: 'asr_unavailable',
        error_code: 'capability_unavailable',
      },
      keyword: {
        status: 'no_text',
        reason: 'no_trusted_body',
        error_code: null,
      },
      semantic: {
        status: 'searchable',
        reason: null,
        error_code: null,
        model: 'embedding-model-id',
        kinds: ['audio'],
        failed_kinds: [],
      },
    },
  ],
  latest: null,
}

const LEGACY_RECEIPT: SourceReceipt = {
  source_id: 'source_01J',
  revision: 1,
  status: 'received',
  source_version: 1,
  items: [{ status: 'received', stage: 'stored', searchable: false }],
  latest: null,
}

const SOURCE_REF: SourceRef = {
  source_id: 'source_01J',
  source_version: 1,
  content_hash: 'sha256-hex',
  scope: { task_ref: null, project_ref: null, inbox_ref: null },
}

const SEMANTIC_HIT: SemanticSearchHit = {
  source_id: 'source_01J',
  source_version: 1,
  content_hash: 'sha256-hex',
  kind: 'audio',
  basis: 'vector',
  scope: { task_ref: null, project_ref: null, inbox_ref: null },
  title: 'meeting.mp3',
  locators: [],
  snippet: '',
  verified: true,
  stale: false,
  reason: null,
}

describe('material intake v2 capability gates', () => {
  it('keeps the existing core compatibility unchanged for 1.18/1.19', () => {
    expect(() => assertBackendCompatible(health('1.18.0'))).not.toThrow()
    expect(() => assertBackendCompatible(health('1.19.0'))).not.toThrow()
  })

  it('keeps the gates false on the current 1.18 contract even if claims appear', () => {
    const claimed = health('1.18.0', {
      [MATERIAL_INTAKE_V2_CAPABILITY]: true,
      [SEMANTIC_SEARCH_CAPABILITY]: true,
      [MEDIA_DIRECT_EMBEDDING_CAPABILITY]: true,
    })
    expect(MINIMUM_MATERIAL_INTAKE_CONTRACT).toBe('1.19.0')
    expect(supportsMaterialIntakeV2(claimed)).toBe(false)
    expect(supportsSemanticSearch(claimed)).toBe(false)
    expect(supportsMediaDirectEmbedding(claimed)).toBe(false)
  })

  it('does not infer support from the version alone', () => {
    const versionOnly = health('1.19.0')
    expect(supportsMaterialIntakeV2(versionOnly)).toBe(false)
    expect(supportsSemanticSearch(versionOnly)).toBe(false)
    expect(supportsMediaDirectEmbedding(versionOnly)).toBe(false)
  })

  it('enables each gate independently at 1.19+', () => {
    const intakeOnly = health('1.19.0', { [MATERIAL_INTAKE_V2_CAPABILITY]: true })
    expect(supportsMaterialIntakeV2(intakeOnly)).toBe(true)
    expect(supportsSemanticSearch(intakeOnly)).toBe(false)
    expect(supportsMediaDirectEmbedding(intakeOnly)).toBe(false)

    const semanticOnly = health('1.19.0', { [SEMANTIC_SEARCH_CAPABILITY]: true })
    expect(supportsMaterialIntakeV2(semanticOnly)).toBe(false)
    expect(supportsSemanticSearch(semanticOnly)).toBe(true)

    const mediaOnly = health('1.19.0', { [MEDIA_DIRECT_EMBEDDING_CAPABILITY]: true })
    expect(supportsMediaDirectEmbedding(mediaOnly)).toBe(true)
  })

  it('rejects garbage and 2.x contracts', () => {
    for (const version of ['garbage', '1.19', '2.0.0']) {
      expect(
        supportsMaterialIntakeV2(
          health(version, { [MATERIAL_INTAKE_V2_CAPABILITY]: true }),
        ),
      ).toBe(false)
    }
  })

  it('keeps the existing additive gates working through the shared helper', () => {
    expect(supportsPersonalChat(health('1.13.9', { personal_chat: true }))).toBe(false)
    expect(supportsPersonalChat(health('1.14.0', { personal_chat: true }))).toBe(true)
    expect(supportsAccounts(health('1.14.0', { accounts: true }))).toBe(false)
    expect(supportsAccounts(health('1.15.0', { accounts: true }))).toBe(true)
  })
})

describe('frozen intake constants', () => {
  it('matches docs/08 §20.3/§20.5/§20.8', () => {
    expect(MESSAGE_SOURCE_REFS_MAX).toBe(10)
    expect(INTAKE_MAX_ORIGINAL_BYTES).toBe(10_000_000)
    expect(INTAKE_MAX_NATIVE_TEXT_BYTES).toBe(2_000_000)
    expect(INTAKE_MAX_OCR_PAGES).toBe(100)
    expect(INTAKE_MAX_TOKENS_PER_PAGE).toBe(2000)
    expect(INTAKE_MAX_EMBEDDING_CALLS).toBe(2)
    expect(INTAKE_MAX_RETRIES).toBe(1)
    expect(INTAKE_TIMEOUT_SECONDS).toBe(900)
    expect(INTAKE_MAX_CONCURRENT_JOBS).toBe(2)
  })
})

describe('receipt v2 typing', () => {
  it('narrows only real v2 receipts with all three branches', () => {
    expect(isSourceReceiptV2(V2_RECEIPT)).toBe(true)
    expect(isSourceReceiptV2(LEGACY_RECEIPT)).toBe(false)
    expect(isSourceReceiptV2(null)).toBe(false)
    expect(
      isSourceReceiptV2({
        ...V2_RECEIPT,
        items: [{ status: 'extracted' }],
      } as SourceReceipt),
    ).toBe(false)
  })

  it('keeps legacy branch-independent fields readable', () => {
    expect(LEGACY_RECEIPT.items[0].status).toBe('received')
    expect(V2_RECEIPT.items[0].semantic.kinds).toEqual(['audio'])
    expect(V2_RECEIPT.items[0].text.status).toBe('unavailable')
  })
})

describe('source_refs and semantic hit shapes', () => {
  it('accepts server-normalized refs and a media hit kind', () => {
    expect(SOURCE_REF.scope.task_ref).toBeNull()
    expect(SEMANTIC_HIT.kind).toBe('audio')
  })
})

describe('sources client wire signatures', () => {
  it('forwards intake_mode in the normal POST /sources body', async () => {
    const fetchSpy = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit) =>
        new Response(
          JSON.stringify({
            source: {},
            job: null,
            deduplicated: false,
            created: true,
            receipts: [],
            intake_mode: 'deferred',
          }),
          { status: 201, headers: { 'content-type': 'application/json' } },
        ),
    )
    vi.stubGlobal('fetch', fetchSpy)

    const result = await createSourcesApi().createSource({
      request_id: 'req_01J',
      filename: 'meeting.mp3',
      content_base64: '',
      media_type: 'audio/mpeg',
      intake_mode: 'deferred',
    })
    expect(result.intake_mode).toBe('deferred')

    const [url, init] = fetchSpy.mock.calls[0]
    expect(String(url)).toContain('/api/v1/sources')
    expect(init?.method).toBe('POST')
    expect(JSON.parse(String(init?.body))).toMatchObject({
      request_id: 'req_01J',
      filename: 'meeting.mp3',
      intake_mode: 'deferred',
    })
  })

  it('exposes job read/action endpoints without requiring them from old doubles', async () => {
    const fetchSpy = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit) =>
        new Response(JSON.stringify({ job_id: 'job_01J', status: 'queued' }), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        }),
    )
    vi.stubGlobal('fetch', fetchSpy)

    const api = createSourcesApi()
    expect(typeof api.getIntakeJob).toBe('function')
    expect(typeof api.intakeJobAction).toBe('function')
    await api.getIntakeJob?.('job_01J')
    await api.intakeJobAction?.('job_01J', { action: 'retry' })

    expect(String(fetchSpy.mock.calls[0][0])).toContain('/api/v1/intake/jobs/job_01J')
    expect(JSON.parse(String(fetchSpy.mock.calls[1][1]?.body))).toMatchObject({
      action: 'retry',
      confirmed: false,
    })
  })
})
