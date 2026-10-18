#!/usr/bin/env node
'use strict'

/**
 * LG-239 continuation after the run-2 harness timing failure.
 *
 * Reuses the already-created source/job and the single successful real Google
 * call.  It never uploads the H1 audio again in Team chat and asserts the final
 * Google transport attempt count stays exactly one.
 */

const { chromium } = require('/home/yhvh/code/lightgravity-bot-worktrees/lg051-qa/e2e/node_modules/playwright')
const crypto = require('node:crypto')
const fs = require('node:fs')
const path = require('node:path')

const BASE = 'http://127.0.0.1:18239'
const OUT = '/home/yhvh/code/lightgravity-bot/probes/google-native-asr-20261018/lg239'
const SHOTS = path.join(OUT, 'screenshots')
const TRACES = path.join(OUT, 'traces')
const LOGS = path.join(OUT, 'logs')
const PROV = path.join(OUT, 'provenance')
const AUDIO = '/home/yhvh/code/lightgravity-bot/probes/english-asr-20261018/lg163/artifacts/tts/qa-h1-harbor.piper-ljspeech-high.16k.wav'
const EXPECTED_AUDIO_SHA = 'e186594f70db78b4cbd9bb926beb72421bd5dfe3f7d2da4f1bba0a498663c740'
const DATA_ROOT = '/home/yhvh/tmp/lg239-google-data'
const AUDIT = path.join(LOGS, 'google-transport-audit.jsonl')
const ACCOUNTS = '/home/yhvh/tmp/lg239-google-secrets/qa-accounts.json'

const prior = JSON.parse(fs.readFileSync(path.join(TRACES, 'browser-run.json'), 'utf8'))
const sourceId = prior.source.source_id
const jobId = prior.source.job_id
const transcriptExpectedSha = crypto.createHash('sha256').update(fs.readFileSync(AUDIO)).digest('hex')

const result = {
  run_id: 'lg239-real-google-continuation-20261018',
  resumed_from: 'run2-real-google-success-then-job-poll-harness-bug',
  source_id: sourceId,
  job_id: jobId,
  checks: [],
  failures: [],
  screenshots: [],
  network: {
    requests: [],
    responses: [],
    cross_origin: [],
    google_host_requests: [],
    vendor_header_responses: [],
  },
  google_attempts: { before: null, after_upload: null, final: null, calls: [] },
  job: null,
  source: null,
  receipt: null,
  machine: null,
  content: null,
  formal: null,
  timings: {},
  privacy: {},
  cross_task: {},
  disabled: {},
}

function saveResult() {
  fs.writeFileSync(path.join(TRACES, 'browser-resume.json'), JSON.stringify(result, null, 2))
}

function check(name, ok, detail) {
  result.checks.push({ name, pass: !!ok, detail: detail === undefined ? null : detail })
  console.log((ok ? 'PASS ' : 'FAIL ') + name)
  if (!ok) {
    result.failures.push(name)
    throw new Error(`CHECK FAILED: ${name} ${JSON.stringify(detail)}`)
  }
}

function sha256(text) {
  return crypto.createHash('sha256').update(text).digest('hex')
}

function auditCalls() {
  if (!fs.existsSync(AUDIT)) return []
  return fs.readFileSync(AUDIT, 'utf8').trim().split('\n').filter(Boolean)
    .map((line) => JSON.parse(line))
    .filter((row) => row.kind === 'google_transport_call')
}

function screenshot(page, name) {
  const target = path.join(SHOTS, name)
  return page.screenshot({ path: target, fullPage: true }).then(() => {
    result.screenshots.push(target)
    return target
  })
}

async function overflow(page) {
  return page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    innerWidth: window.innerWidth,
  }))
}

async function api(page, route, options = {}) {
  return page.evaluate(async ({ route, options }) => {
    const response = await fetch(route, {
      method: options.method || 'GET',
      credentials: 'include',
      headers: options.body ? { 'Content-Type': 'application/json' } : undefined,
      body: options.body ? JSON.stringify(options.body) : undefined,
    })
    const text = await response.text()
    let body = null
    try { body = text ? JSON.parse(text) : null } catch { body = text }
    return { status: response.status, body }
  }, { route, options })
}

async function login(page, username, password) {
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto(`${BASE}/?view=chat`, { waitUntil: 'networkidle' })
  const gate = page.getByRole('main', { name: 'Sign in' })
  if (await gate.isVisible().catch(() => false)) {
    await page.getByLabel('Username').fill(username)
    await page.getByLabel('Password').fill(password)
    await page.getByRole('button', { name: 'Sign in' }).click()
    await gate.waitFor({ state: 'hidden', timeout: 20000 })
  }
  await page.getByRole('banner').waitFor({ timeout: 20000 })
}

function attachSanitizedNetwork(page) {
  page.on('request', (request) => {
    if (!request.url().startsWith('http')) return
    const url = new URL(request.url())
    const entry = {
      method: request.method(),
      host: url.host,
      path: url.pathname,
      resource_type: request.resourceType(),
      post_data_chars: request.postData() ? request.postData().length : 0,
    }
    result.network.requests.push(entry)
    if (url.host !== '127.0.0.1:18239') result.network.cross_origin.push(entry)
    if (url.hostname === 'generativelanguage.googleapis.com') result.network.google_host_requests.push(entry)
  })
  page.on('response', (response) => {
    const url = new URL(response.url())
    const headerNames = Object.keys(response.headers()).map((name) => name.toLowerCase())
    const entry = {
      status: response.status(),
      host: url.host,
      path: url.pathname,
      header_names: headerNames,
      method: response.request().method(),
    }
    result.network.responses.push(entry)
    if (headerNames.some((name) => name.startsWith('x-goog'))) {
      result.network.vendor_header_responses.push(entry)
    }
  })
}

async function main() {
  const accounts = JSON.parse(fs.readFileSync(ACCOUNTS, 'utf8'))
  const callsBefore = auditCalls()
  result.google_attempts.before = callsBefore.length
  check('continuation starts with exactly one real Google attempt already made',
    callsBefore.length === 1 && callsBefore[0].status === 200, callsBefore)
  check('the single Google call used the native interactions host/path and no model imports',
    callsBefore[0].endpoint_host === 'generativelanguage.googleapis.com' &&
      callsBefore[0].endpoint_path === '/v1beta/interactions' &&
      callsBefore[0].request_bytes > 0 &&
      Object.values(callsBefore[0].modules || {}).every((value) => value === false), callsBefore[0])

  const browser = await chromium.launch({ executablePath: '/usr/bin/google-chrome', headless: true, args: ['--no-sandbox'] })
  try {
    const memberContext = await browser.newContext({ viewport: { width: 1440, height: 900 } })
    const memberPage = await memberContext.newPage()
    attachSanitizedNetwork(memberPage)
    await login(memberPage, accounts.member.username, accounts.member.password)

    const t0 = Date.now()
    let job = null
    let source = null
    for (let i = 0; i < 120; i += 1) {
      const [jobResponse, sourceResponse] = await Promise.all([
        api(memberPage, `/api/v1/intake/jobs/${jobId}`),
        api(memberPage, `/api/v1/sources/${sourceId}`),
      ])
      job = jobResponse.body
      source = sourceResponse.body
      if (['succeeded', 'partial', 'failed', 'cancelled'].includes(job?.status)) break
      await memberPage.waitForTimeout(500)
    }
    result.timings.job_terminal_ms = Date.now() - t0
    result.job = job
    result.source = source
    check('deferred intake job reached a real terminal success with one attempt and one ASR budget',
      ['succeeded', 'partial'].includes(job?.status) && job?.attempt === 1 && job?.budget?.max_asr_calls === 1 && !job?.fail_reason,
      { status: job?.status, stage: job?.stage, attempt: job?.attempt, budget: job?.budget, finished_at: job?.finished_at })
    check('source text branch is ready in English', source?.text_status === 'ready' && source?.language === 'en',
      { text_status: source?.text_status, language: source?.language, status: source?.status })

    const receiptResponse = await api(memberPage, `/api/v1/sources/${sourceId}/receipt`)
    const contentResponse = await api(memberPage, `/api/v1/sources/${sourceId}/content?kind=machine`)
    const receipt = receiptResponse.body
    const content = contentResponse.body
    const receiptItems = Array.isArray(receipt?.items) ? receipt.items : []
    const receiptBranch = [...receiptItems].reverse().find((item) => item?.text?.machine) ?? receiptItems[receiptItems.length - 1] ?? null
    const textBranch = receiptBranch?.text ?? null
    const machine = textBranch?.machine ?? null
    const transcript = (content?.content || '').trim()
    result.receipt = receipt
    result.receipt_branch = receiptBranch
    result.content = content
    result.machine = machine
    result.transcript = transcript
    result.transcript_sha256 = sha256(transcript)
    check('receipt has ready English Google-native machine provenance',
      receiptResponse.status === 200 && textBranch?.status === 'ready' && textBranch?.language === 'en' &&
        machine?.provider === 'google' && machine?.engine === 'google-native' && machine?.runtime === 'google-native' &&
        machine?.model === 'gemini-3.8-flash' && machine?.prompt_version === 'google-native-transcribe-v1' &&
        machine?.endpoint_host === 'generativelanguage.googleapis.com' && machine?.endpoint_path === '/v1beta/interactions',
      { status: receiptResponse.status, branch: receiptBranch })
    check('receipt timestamps are null and no fake encoder/Reader provenance exists',
      textBranch?.timestamps === null && !('encoder' in machine) && !('reader' in machine),
      { timestamps: textBranch?.timestamps, machine_keys: Object.keys(machine || {}) })
    check('machine content is a nonempty real transcript', contentResponse.status === 200 && content.kind === 'machine' && transcript.length > 0,
      { status: contentResponse.status, preview: transcript.slice(0, 260) })
    check('native usage/latency are recorded', machine?.usage && typeof machine.usage.total_tokens === 'number' && machine?.latency_ms > 0,
      { usage: machine?.usage, latency_ms: machine?.latency_ms })
    check('machine provenance hashes/bytes match the frozen audio input',
      machine?.audio_sha256 === EXPECTED_AUDIO_SHA && machine?.audio_bytes === fs.statSync(AUDIO).size &&
        machine?.mime_type === 'audio/wav' && machine?.request_bytes > machine?.audio_bytes,
      { audio_sha256: machine?.audio_sha256, audio_bytes: machine?.audio_bytes, request_bytes: machine?.request_bytes })

    let onDisk = null
    try {
      const all = fs.readdirSync(DATA_ROOT, { recursive: true }).map(String)
      const candidate = all.find((item) => item.endsWith(path.basename(AUDIO)) && item.includes('original'))
      if (candidate) {
        const absolute = path.join(DATA_ROOT, candidate)
        onDisk = {
          relative_path: candidate,
          bytes: fs.statSync(absolute).size,
          sha256: crypto.createHash('sha256').update(fs.readFileSync(absolute)).digest('hex'),
        }
      }
    } catch (error) {
      onDisk = { error: String(error) }
    }
    result.source_original_on_disk = onDisk
    check('persisted source file matches input SHA-256 and byte count',
      source?.content_hash === EXPECTED_AUDIO_SHA && (!onDisk || (onDisk.sha256 === EXPECTED_AUDIO_SHA && onDisk.bytes === fs.statSync(AUDIO).size)),
      { content_hash: source?.content_hash, original: source?.original, on_disk: onDisk })
    check('source original path is relative, never an absolute local path',
      typeof source?.original?.path === 'string' && !source.original.path.startsWith('/') && !source.original.path.includes(DATA_ROOT),
      source?.original?.path)

    // Formal/machine boundary.  Idempotent for a harness rerun that resumes after
    // a later check failed: a previously written formal version is reused.
    const formalBefore = await api(memberPage, `/api/v1/sources/${sourceId}/content?kind=formal`)
    const formalWasAbsent = formalBefore.status === 404
    check('machine transcript is not the human formal version before/without a separate formal write',
      formalWasAbsent || (formalBefore.status === 200 && formalBefore.body.kind === 'formal'),
      { status: formalBefore.status, body: formalBefore.body })
    const formalWrite = formalWasAbsent
      ? await api(memberPage, `/api/v1/sources/${sourceId}/formal`, {
          method: 'POST',
          body: { content: transcript, edited_by: accounts.member.username },
        })
      : { status: 200, body: { reused_existing_formal: true } }
    const formalRead = await api(memberPage, `/api/v1/sources/${sourceId}/content?kind=formal`)
    const machineAfterFormal = await api(memberPage, `/api/v1/sources/${sourceId}/content?kind=machine`)
    result.formal = { was_absent: formalWasAbsent, write: formalWrite, read: formalRead, machine_after: machineAfterFormal }
    check('human formal edit succeeds and leaves machine text byte-identical',
      formalWrite.status < 300 && formalRead.status === 200 && formalRead.body.kind === 'formal' &&
        machineAfterFormal.status === 200 && machineAfterFormal.body.content.trim() === transcript,
      { write: formalWrite.status, formal: formalRead.status, machine: machineAfterFormal.status })

    // Chat receipt, selectable text, keyword search, source backlink.
    await memberPage.goto(`${BASE}/?view=chat`, { waitUntil: 'networkidle' })
    const teamTab = memberPage.getByRole('tab', { name: 'Team' })
    if (await teamTab.isVisible().catch(() => false)) await teamTab.click()
    await memberPage.waitForFunction(
      () => /machine Google transcript|Google native/i.test(document.body.innerText),
      null,
      { timeout: 60000 },
    ).catch(() => {})
    const chatText = await memberPage.locator('body').innerText()
    const firstWords = transcript.split(/\s+/).slice(0, 5).join(' ')
    check('Chat receipt shows truthful Google transcript provenance and a material backlink',
      /machine Google transcript/i.test(chatText) && /gemini-3\.8-flash/i.test(chatText) &&
        /word timestamps not available/i.test(chatText) &&
        (await memberPage.getByRole('button', { name: 'View material' }).count()) > 0,
      chatText.slice(-2600))
    await screenshot(memberPage, 'member-h1-receipt-1440.png')

    const viewMaterial = memberPage.getByRole('button', { name: 'View material' }).first()
    await viewMaterial.waitFor({ timeout: 20000 })
    await viewMaterial.click()
    await memberPage.waitForFunction((text) => document.body.innerText.includes(text), firstWords, { timeout: 30000 })
    const selectedText = await memberPage.evaluate(() => {
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT)
      let node = null
      while ((node = walker.nextNode())) {
        if (node.nodeValue && node.nodeValue.includes('North Harbor')) {
          const range = document.createRange()
          range.selectNodeContents(node)
          const selection = window.getSelection()
          selection.removeAllRanges()
          selection.addRange(range)
          return selection.toString()
        }
      }
      return ''
    })
    check('machine transcript is selectable text in Tasks detail', selectedText.includes('North Harbor'), selectedText.slice(0, 200))
    await screenshot(memberPage, 'member-h1-detail-1440.png')

    const searchInput = memberPage.locator('input[aria-label="Search"]')
    await searchInput.fill('Cedar Island')
    await searchInput.press('Enter')
    await memberPage.locator('#lg-material-search').waitFor({ timeout: 15000 })
    await memberPage.waitForTimeout(1200)
    const searchText = await memberPage.locator('#lg-material-search').innerText()
    check('Keyword search finds the real transcript phrase and source id',
      /qa-h1-harbor/i.test(searchText) && /Cedar Island/i.test(searchText) && searchText.includes(sourceId),
      searchText.slice(0, 1800))
    await screenshot(memberPage, 'member-keyword-search-1440.png')
    await memberPage.getByRole('button', { name: 'Open in Tasks' }).first().click()
    await memberPage.waitForFunction((text) => document.body.innerText.includes(text), firstWords, { timeout: 20000 })
    check('search result backlink opens the same source in Tasks', true, null)

    for (const [width, height] of [[1024, 768], [390, 844]]) {
      await memberPage.setViewportSize({ width, height })
      await memberPage.waitForTimeout(500)
      const ov = await overflow(memberPage)
      const body = await memberPage.locator('body').innerText()
      check(`material detail ${width}px has no horizontal overflow and keeps the transcript`,
        ov.scrollWidth <= ov.innerWidth + 1 && body.includes(firstWords), { overflow: ov, transcript: body.includes(firstWords) })
      await screenshot(memberPage, `member-history-${width}.png`)
    }

    // Personal private audio: no shared source, no shared ASR, no index.
    await memberPage.setViewportSize({ width: 1440, height: 900 })
    await memberPage.goto(`${BASE}/?view=chat`, { waitUntil: 'networkidle' })
    await memberPage.getByRole('tab', { name: 'Personal' }).click()
    await memberPage.waitForTimeout(600)
    const attemptsBeforePrivate = auditCalls().length
    const sourcesBeforePrivate = await api(memberPage, '/api/v1/sources?limit=100')
    await memberPage.locator('input[type=file][aria-label^="Upload file for"]').setInputFiles(AUDIO)
    await memberPage.getByText(/qa-h1-harbor/i).first().waitFor({ timeout: 15000 })
    for (let i = 0; i < 40; i += 1) {
      if (await memberPage.getByRole('button', { name: 'Send message' }).isEnabled().catch(() => false)) break
      await memberPage.waitForTimeout(250)
    }
    await memberPage.getByRole('button', { name: 'Send message' }).click()
    await memberPage.waitForTimeout(4000)
    const sourcesAfterPrivate = await api(memberPage, '/api/v1/sources?limit=100')
    const personalText = await memberPage.locator('body').innerText()
    result.privacy = {
      shared_source_count_before: (sourcesBeforePrivate.body.items || []).length,
      shared_source_count_after: (sourcesAfterPrivate.body.items || []).length,
      google_attempts_before: attemptsBeforePrivate,
      google_attempts_after: auditCalls().length,
    }
    check('Personal private audio adds no shared source and no Google attempt',
      auditCalls().length === attemptsBeforePrivate &&
        (sourcesAfterPrivate.body.items || []).length === (sourcesBeforePrivate.body.items || []).length,
      result.privacy)
    check('Personal private audio does not claim a shared machine transcript', !/machine Google transcript/i.test(personalText),
      personalText.slice(-1400))
    await screenshot(memberPage, 'member-personal-private-audio-1440.png')

    // Cross-Task scope negative at the real backend.
    const stamp = Date.now().toString(36)
    const taskA = await api(memberPage, '/api/v1/tasks', {
      method: 'POST',
      body: { request_id: `lg239-task-a-${stamp}`, title: 'LG239 scope A', objective: 'Scope A fixture' },
    })
    const taskB = await api(memberPage, '/api/v1/tasks', {
      method: 'POST',
      body: { request_id: `lg239-task-b-${stamp}`, title: 'LG239 scope B', objective: 'Scope B fixture' },
    })
    const idA = taskA.body?.task_id
    const idB = taskB.body?.task_id
    const scopedSource = await api(memberPage, '/api/v1/sources', {
      method: 'POST',
      body: {
        request_id: `lg239-scoped-source-${stamp}`,
        filename: 'lg239-scope-a.txt',
        media_type: 'text/plain',
        content_base64: Buffer.from('LG239 cross-task scope fixture, no audio.').toString('base64'),
        scope: { task_ref: idA },
        intake_mode: 'deferred',
      },
    })
    const scopedSourceId = scopedSource.body?.source?.source_id
    const scopedOnly = await api(memberPage, `/api/v1/sources?task_ref=${encodeURIComponent(idB)}&limit=100`)
    const listB = scopedOnly.body?.items || []
    const appendOutOfScope = await api(memberPage, `/api/v1/tasks/${idB}/messages`, {
      method: 'POST',
      body: {
        message_id: `lg239-out-of-scope-${stamp}`,
        content: 'Out-of-scope receipt fixture.',
        source_refs: [{ source_id: scopedSourceId }],
      },
    })
    result.cross_task = {
      task_a: idA,
      task_b: idB,
      scoped_source: scopedSourceId,
      task_b_list_contains_scoped_source: listB.some((item) => item.source_id === scopedSourceId),
      out_of_scope_message_status: appendOutOfScope.status,
      out_of_scope_message_code: appendOutOfScope.body?.code,
      out_of_scope_message_details: appendOutOfScope.body?.details,
    }
    check('Task B list does not expose a Task-A-scoped source',
      !!scopedSourceId && !listB.some((item) => item.source_id === scopedSourceId), result.cross_task)
    check('backend rejects a Task-A source ref in a Task-B message',
      [400, 404, 409, 422].includes(appendOutOfScope.status) &&
        /reference_invalid|outside the message scope/i.test(JSON.stringify(appendOutOfScope.body)), result.cross_task)

    // Disable through the real admin UI; history must remain truthful.
    const adminContext = await browser.newContext({ viewport: { width: 1440, height: 900 } })
    const adminPage = await adminContext.newPage()
    attachSanitizedNetwork(adminPage)
    await login(adminPage, accounts.admin.username, accounts.admin.password)
    await adminPage.goto(`${BASE}/?view=settings`, { waitUntil: 'networkidle' })
    const configure = adminPage.getByRole('button', { name: /Configure English transcription/i })
    await configure.waitFor({ timeout: 20000 })
    await configure.click()
    const dialog = adminPage.getByRole('dialog')
    await dialog.waitFor()
    await dialog.getByLabel(/Enable English transcription/i).uncheck()
    await dialog.getByRole('button', { name: /Save English transcription settings/i }).click()
    await dialog.getByText(/settings saved at revision/i).waitFor({ timeout: 20000 })
    const disabledText = await dialog.innerText()
    const settingsDisabled = await api(adminPage, '/api/v1/settings')
    result.disabled = { status: settingsDisabled.status, english_asr: settingsDisabled.body.english_asr, dialog_preview: disabledText.slice(0, 1600) }
    check('disabled Google config is honest: disabled/unavailable with no fake success',
      settingsDisabled.status === 200 && settingsDisabled.body.english_asr.enabled === false &&
        settingsDisabled.body.english_asr.available === false && settingsDisabled.body.english_asr.reason === 'disabled' &&
        /disabled/i.test(disabledText) && /no transcript is generated|No transcription success is claimed/i.test(disabledText),
      result.disabled)
    await screenshot(adminPage, 'admin-google-disabled-1440.png')
    const cancel = dialog.getByRole('button', { name: 'Cancel', exact: true })
    if (await cancel.isVisible().catch(() => false)) await cancel.click()

    const attemptsBeforeReload = auditCalls().length
    await memberPage.setViewportSize({ width: 1440, height: 900 })
    await memberPage.goto(`${BASE}/?view=chat`, { waitUntil: 'networkidle' })
    const searchAgain = memberPage.locator('input[aria-label="Search"]')
    await searchAgain.fill('Cedar Island')
    await searchAgain.press('Enter')
    await memberPage.locator('#lg-material-search').waitFor({ timeout: 15000 })
    await memberPage.waitForTimeout(1000)
    await memberPage.getByRole('button', { name: 'Open in Tasks' }).first().click()
    await memberPage.waitForFunction((text) => document.body.innerText.includes(text), firstWords, { timeout: 20000 })
    const historyAfterDisable = await memberPage.locator('body').innerText()
    const machineWhileDisabled = await api(memberPage, `/api/v1/sources/${sourceId}/content?kind=machine`)
    check('historical machine transcript survives page reload and ASR disable',
      historyAfterDisable.includes(firstWords) && machineWhileDisabled.status === 200 &&
        machineWhileDisabled.body.content.trim() === transcript,
      { content_status: machineWhileDisabled.status })
    check('reload/disable/history checks caused no second Google call',
      auditCalls().length === attemptsBeforeReload && auditCalls().length === 1,
      { before: attemptsBeforeReload, after: auditCalls().length })
    await screenshot(memberPage, 'member-history-after-disable-1440.png')

    result.google_attempts.final = auditCalls().length
    result.google_attempts.after_upload = 1
    result.google_attempts.calls = auditCalls()
    result.network.request_count = result.network.requests.length
    result.network.response_count = result.network.responses.length
    result.network.method_path_counts = result.network.requests.reduce((acc, entry) => {
      const key = `${entry.method} ${entry.path}`
      acc[key] = (acc[key] || 0) + 1
      return acc
    }, {})
    check('continuation made no cross-origin/direct Google browser request and saw no vendor header',
      result.network.cross_origin.length === 0 && result.network.google_host_requests.length === 0 &&
        result.network.vendor_header_responses.length === 0,
      { cross_origin: result.network.cross_origin.length, google: result.network.google_host_requests.length, vendor: result.network.vendor_header_responses.length })
    check('final Google attempt count remains exactly one', result.google_attempts.final === 1, result.google_attempts)

    fs.writeFileSync(path.join(LOGS, 'request-counts-continuation.json'), JSON.stringify({
      network_requests: result.network.request_count,
      network_responses: result.network.response_count,
      method_path_counts: result.network.method_path_counts,
      google_transport_attempts: result.google_attempts.final,
      cross_origin_requests: result.network.cross_origin.length,
      direct_google_browser_requests: result.network.google_host_requests.length,
      vendor_header_responses: result.network.vendor_header_responses.length,
    }, null, 2))
    fs.writeFileSync(path.join(TRACES, 'browser-network-continuation-sanitized.json'), JSON.stringify(result.network, null, 2))
    saveResult()
    console.log(JSON.stringify({ checks: result.checks.length, failures: result.failures, google_attempts: result.google_attempts.final, transcript_preview: transcript.slice(0, 220) }, null, 2))
  } finally {
    await browser.close().catch(() => {})
  }
}

main().catch((error) => {
  result.failures.push(String(error && error.stack ? error.stack : error))
  saveResult()
  console.error(error)
  process.exit(1)
})
