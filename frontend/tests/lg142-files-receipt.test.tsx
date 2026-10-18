/**
 * LG-142 Files receipt/control tests.
 *
 * Component tests with injected clients only; real media/OCR/embedding and
 * browser acceptance belong to LG-145. Covered here:
 *  * independent receipt v2 branches, partial and audio transcription honesty;
 *  * authorized original audio preview/download (no localStorage path);
 *  * expected_revision on reprocess and no formal overwrite;
 *  * cancel is only success after a confirmed stop;
 *  * retry uses the intake job action, not a formal/machine overwrite;
 *  * a non-v2 backend shows no inferred branch success.
 */

import { configure, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'

import { ApiError } from '../src/api/client'
import type {
  JobView,
  SourceReceiptV2,
  SourceView,
  SourcesApi,
} from '../src/api/sources'
import { FilesMaterialsPanel } from '../src/views/files/FilesMaterialsPanel'

configure({ asyncUtilTimeout: 3000 })

const createObjectURL = vi.fn(() => 'blob:original')
const revokeObjectURL = vi.fn()

beforeAll(() => {
  Object.defineProperty(URL, 'createObjectURL', { writable: true, value: createObjectURL })
  Object.defineProperty(URL, 'revokeObjectURL', { writable: true, value: revokeObjectURL })
})

afterEach(() => {
  vi.restoreAllMocks()
  createObjectURL.mockClear()
  revokeObjectURL.mockClear()
})

function source(overrides: Partial<SourceView> = {}): SourceView {
  return {
    id: 'source_audio',
    source_id: 'source_audio',
    title: 'meeting.mp3',
    title_origin: 'user',
    status: 'received',
    intake_mode: 'deferred',
    revision: 4,
    etag: 'rev-4',
    scope: { task_ref: null, project_ref: null, inbox_ref: null },
    origin: { kind: 'upload', external_ref: null, fetched: false },
    content_hash: 'content-hash',
    stat_revision: null,
    source_version: 1,
    original: { path: 'original/meeting.mp3', media_type: 'audio/mpeg', bytes: 8 },
    derivatives: [],
    formal: { path: null, revision: null, edited_by: null },
    index: { lexical: 'not_indexed', vector: 'not_indexed' },
    receipt_ref: 'receipt.jsonl',
    created_at: null,
    updated_at: null,
    path: 'sources/source_audio/SOURCE.md',
    ...overrides,
  }
}

function receipt(overrides: Partial<SourceReceiptV2> = {}): SourceReceiptV2 {
  return {
    source_id: 'source_audio',
    revision: 2,
    status: 'extracted',
    source_version: 1,
    receipt_version: 2,
    partial: true,
    items: [
      {
        source_id: 'source_audio',
        filename: 'meeting.mp3',
        status: 'extracted',
        stage: 'done',
        error_code: 'capability_unavailable',
        text: {
          status: 'unavailable',
          reason: 'asr_unavailable',
          error_code: 'capability_unavailable',
        },
        keyword: { status: 'no_text', reason: 'no_trusted_body', error_code: null },
        semantic: {
          status: 'searchable',
          reason: null,
          error_code: null,
          model: 'fixture-embed',
          kinds: ['audio'],
          failed_kinds: [],
        },
      },
    ],
    latest: null,
    ...overrides,
  }
}

function job(overrides: Partial<JobView> = {}): JobView {
  return {
    id: 'job_1',
    job_id: 'job_1',
    source_ref: 'source_audio',
    status: 'running',
    revision: 1,
    request_id: 'req_1',
    stage: 'indexing',
    attempt: 1,
    cancel: { requested: false, confirmed: false },
    fail_reason: null,
    intake_mode: 'deferred',
    queued_at: null,
    started_at: null,
    finished_at: null,
    deadline_at: null,
    waiting_reason: null,
    budget: null,
    created_at: null,
    updated_at: null,
    ...overrides,
  }
}

function makeApi(options: {
  receipt?: SourceReceiptV2
  job?: JobView
  getReceipt?: ReturnType<typeof vi.fn>
  getIntakeJob?: ReturnType<typeof vi.fn>
  intakeJobAction?: ReturnType<typeof vi.fn>
  sourceAction?: ReturnType<typeof vi.fn>
  editFormal?: ReturnType<typeof vi.fn>
  downloadSource?: ReturnType<typeof vi.fn>
} = {}): SourcesApi {
  return {
    createSource: vi.fn(),
    listSources: vi.fn(async () => ({ items: [source()], next_cursor: null })),
    getSource: vi.fn(async () => source()),
    getReceipt: options.getReceipt ?? vi.fn(async () => options.receipt ?? receipt()),
    getIntakeJob: options.getIntakeJob ?? vi.fn(async () => options.job ?? job()),
    intakeJobAction: options.intakeJobAction ?? vi.fn(),
    getContent: vi.fn(async () => {
      throw new ApiError({ message: 'audio has no text body', code: 'not_found', httpStatus: 404, retryable: false })
    }),
    downloadSource: options.downloadSource ?? vi.fn(async () => ({
      blob: new Blob(['audio']),
      filename: 'meeting.mp3',
      mediaType: 'audio/mpeg',
      statRevision: null,
      kind: 'original',
      contentHash: null,
    })),
    editFormal: options.editFormal ?? vi.fn(),
    sourceAction: options.sourceAction ?? vi.fn(async () => ({ source_id: 'source_audio', status: 'processing' })),
    appendInboxMessage: vi.fn(),
    search: vi.fn(),
  } as unknown as SourcesApi
}

async function openSource() {
  fireEvent.click(await screen.findByText('meeting.mp3'))
  await screen.findByText('Processing receipt')
}

describe('LG-142 Files detail receipt', () => {
  it('shows independent branches, partial, audio transcript unavailable, and authorized original preview', async () => {
    const downloadSource = vi.fn(async () => ({
      blob: new Blob(['audio']),
      filename: 'meeting.mp3',
      mediaType: 'audio/mpeg',
      statRevision: null,
      kind: 'original',
      contentHash: null,
    }))
    const sourceAction = vi.fn(async () => ({ source_id: 'source_audio' }))
    const editFormal = vi.fn()
    const api = makeApi({ downloadSource, sourceAction, editFormal })
    render(
      <FilesMaterialsPanel
        api={api}
        taskRef={null}
        materialIntakeV2
        mediaDirectEmbedding
      />,
    )
    await openSource()

    expect(screen.getByText('Transcription unavailable')).toBeInTheDocument()
    expect(screen.getByText('No text')).toBeInTheDocument()
    expect(screen.getByText('Searchable')).toBeInTheDocument()
    expect(screen.getByText('Partial')).toBeInTheDocument()
    expect(screen.getByText(/media vector: audio/)).toBeInTheDocument()
    expect(screen.getByText(/ASR is unavailable; no transcript was created/)).toBeInTheDocument()
    expect(document.querySelector('audio')).not.toBeNull()
    await waitFor(() =>
      expect(downloadSource).toHaveBeenCalledWith('source_audio', 'original', expect.anything()),
    )

    const anchorClick = vi
      .spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(() => undefined)
    fireEvent.click(screen.getByText('Download original'))
    await waitFor(() => expect(downloadSource).toHaveBeenCalledTimes(2))
    anchorClick.mockRestore()

    fireEvent.click(screen.getByText('Reprocess audio (English ASR)'))
    await waitFor(() =>
      expect(sourceAction).toHaveBeenCalledWith(
        'source_audio',
        expect.objectContaining({ action: 'reprocess', expected_revision: 4 }),
      ),
    )
    expect(editFormal).not.toHaveBeenCalled()
  })

  it('keeps the branch list honest when text failed but semantic searchable', async () => {
    const partial = receipt()
    partial.items[0].text = {
      status: 'failed',
      reason: 'ocr_unavailable',
      error_code: 'capability_unavailable',
    }
    const api = makeApi({ receipt: partial })
    render(<FilesMaterialsPanel api={api} taskRef={null} materialIntakeV2 />)
    await openSource()

    expect(screen.getByText('Text failed')).toBeInTheDocument()
    expect(screen.getByText('Searchable')).toBeInTheDocument()
    expect(screen.getByText('Partial')).toBeInTheDocument()
  })

  it.each(['failed', 'partial', 'cancelled', 'processing', 'succeeded', 'unknown'])(
    'uses the reprocess extraction outcome %s rather than HTTP success',
    async (status) => {
      // ProcessingOutcome.to_dict() returns failed/partial at HTTP 200 too.
      const sourceAction = vi.fn(async () => ({
        source_id: 'source_audio', source_version: 1, status,
        total_pages: 2, succeeded_pages: status === 'succeeded' ? 2 : 1,
        failed_pages: status === 'failed' || status === 'partial' ? 1 : 0,
        model: 'fixture-ocr', derivative_path: 'derivative/machine.v1.md',
        reason: status === 'failed' ? 'OCR failed' : null,
      }))
      const api = makeApi({ sourceAction })
      render(<FilesMaterialsPanel api={api} taskRef={null} materialIntakeV2 />)
      await openSource()
      fireEvent.click(screen.getByText('Reprocess audio (English ASR)'))
      const notice = await screen.findByText(
        status === 'failed' ? /Reprocess failed:/ :
        status === 'partial' ? /Reprocess partially completed/ :
        status === 'succeeded' ? /Reprocess completed/ : /Reprocess status:/,
      )
      expect(notice).toHaveClass(`lg-files__status--${
        status === 'failed' ? 'error' : status === 'succeeded' ? 'success' : 'neutral'
      }`)
      expect(notice).toHaveTextContent('original and formal version preserved')
      if (status === 'failed') expect(notice).toHaveTextContent('OCR failed')
      expect(sourceAction).toHaveBeenCalledWith('source_audio', {
        action: 'reprocess', expected_revision: 4,
      })
      expect(api.editFormal).not.toHaveBeenCalled()
      await waitFor(() => expect(api.getSource).toHaveBeenCalledTimes(2))
    },
  )

  it('queues audio reprocess and reports the real job terminal state', async () => {
    const sourceAction = vi.fn(async () => ({
      source_id: 'source_audio',
      kind: 'asr',
      status: 'queued',
      queued: true,
      job_id: 'job_reprocess',
    }))
    const getIntakeJob = vi.fn(async () => job({
      id: 'job_reprocess',
      job_id: 'job_reprocess',
      status: 'succeeded',
      stage: 'done',
      fail_reason: null,
    }))
    const api = makeApi({ sourceAction, getIntakeJob })
    render(<FilesMaterialsPanel api={api} taskRef={null} materialIntakeV2 />)
    await openSource()
    fireEvent.click(screen.getByText('Reprocess audio (English ASR)'))
    await screen.findByText(/queued as a bounded intake job/)
    await screen.findByText(/English audio reprocess completed/, undefined, { timeout: 4000 })
    expect(sourceAction).toHaveBeenCalledWith('source_audio', {
      action: 'reprocess', expected_revision: 4,
    })
    expect(getIntakeJob).toHaveBeenCalledWith('job_reprocess')
  })

  it('never claims cancellation until stop is confirmed', async () => {
    const action = vi
      .fn()
      .mockRejectedValueOnce(
        new ApiError({
          message: 'job still running',
          code: 'cancellation_unconfirmed',
          httpStatus: 409,
          retryable: true,
        }),
      )
      .mockResolvedValueOnce({ job_id: 'job_1', action: 'cancel', status: 'cancelled', confirmed: true })
    const withJob = receipt()
    withJob.items[0] = { ...withJob.items[0], job_id: 'job_1' }
    const api = makeApi({ receipt: withJob, intakeJobAction: action })
    render(<FilesMaterialsPanel api={api} taskRef={null} materialIntakeV2 />)
    await openSource()

    fireEvent.click(await screen.findByText('Cancel intake'))
    expect(await screen.findByText(/still running. Stop is not confirmed yet/i)).toBeInTheDocument()
    expect(screen.queryByText(/Intake cancelled after confirmed stop/)).toBeNull()
    expect(action).toHaveBeenCalledWith('job_1', { action: 'cancel', confirmed: false })

    fireEvent.click(screen.getByText('Cancel intake'))
    expect(await screen.findByText('Intake cancelled after confirmed stop.')).toBeInTheDocument()
    expect(action).toHaveBeenCalledTimes(2)
  })

  it('retries a failed intake job without touching the formal version', async () => {
    const action = vi.fn(async () => ({
      job_id: 'job_1',
      action: 'retry',
      status: 'queued',
      confirmed: true,
    }))
    const editFormal = vi.fn()
    const failed = receipt({
      partial: false,
      items: [
        {
          ...receipt().items[0],
          job_id: 'job_1',
          status: 'failed',
          stage: 'extracting',
          text: { status: 'failed', reason: 'ocr_failed', error_code: 'internal_error' },
          keyword: { status: 'failed', reason: 'index_failed', error_code: 'internal_error' },
          semantic: { status: 'disabled', reason: null, error_code: null, model: null, kinds: [], failed_kinds: [] },
        },
      ],
    })
    const api = makeApi({
      receipt: failed,
      job: job({ status: 'failed', stage: 'extracting', fail_reason: 'OCR failed' }),
      intakeJobAction: action,
      editFormal,
    })
    render(<FilesMaterialsPanel api={api} taskRef={null} materialIntakeV2 />)
    await openSource()

    fireEvent.click(await screen.findByText('Retry intake'))
    expect(await screen.findByText(/Retry accepted; job status is queued/)).toBeInTheDocument()
    expect(action).toHaveBeenCalledWith('job_1', { action: 'retry' })
    expect(editFormal).not.toHaveBeenCalled()
  })

  it('hides v2 branch claims on a backend that does not advertise the capability', async () => {
    const getReceipt = vi.fn(async () => receipt())
    const api = makeApi({ getReceipt })
    render(<FilesMaterialsPanel api={api} taskRef={null} materialIntakeV2={false} />)

    fireEvent.click(await screen.findByText('meeting.mp3'))
    expect(await screen.findByText(/does not advertise material_intake_v2/)).toBeInTheDocument()
    expect(screen.queryByText('Processing receipt')).toBeNull()
    expect(screen.queryByText('Transcription unavailable')).toBeNull()
    expect(getReceipt).not.toHaveBeenCalled()
  })
})
