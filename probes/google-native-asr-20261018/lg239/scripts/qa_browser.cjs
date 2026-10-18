#!/usr/bin/env node
'use strict'

/**
 * LG-239 real-browser QA for the Google-native English ASR candidate.
 *
 * One browser process, sequential admin/member contexts, one real Google audio
 * upload.  Network capture is sanitized metadata only: no request/response
 * bodies, audio base64, API keys or credential values are written to artifacts.
 */

const { chromium } = require('/home/yhvh/code/lightgravity-bot-worktrees/lg051-qa/e2e/node_modules/playwright')
const { execFileSync } = require('node:child_process')
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
const RESTORE = path.join(OUT, 'scripts', 'restore_real_key.py')
const LIGHT_PY = '/home/yhvh/code/lightgravity-bot-worktrees/google-native-asr-backend-20261018/.venv/bin/python'
const FAKE_UI_KEY = 'lg239-fake-ui-key-not-real-4f1d'

for (const dir of [SHOTS, TRACES, LOGS, PROV]) fs.mkdirSync(dir, { recursive: true })

const result = {
  run_id: 'lg239-real-google-20261018',
  base: BASE,
  candidate: {
    commit: 'ecda49f692097b07d6f574652f9ed72b6387919a',
    tree: 'd96f22b6d5acbb509cb9cbf6c232d557215af19b',
  },
  audio: {
    path: AUDIO,
    expected_sha256: EXPECTED_AUDIO_SHA,
    actual_sha256: crypto.createHash('sha256').update(fs.readFileSync(AUDIO)).digest('hex'),
    bytes: fs.statSync(AUDIO).size,
  },
  checks: [],
  failures: [],
  console_errors: [],
  page_errors: [],
  screenshots: [],
  network: {
    requests: [],
    responses: [],
    cross_origin: [],
    google_host_requests: [],
    vendor_header_responses: [],
  },
  timings: {},
  source: null,
  receipt: null,
  machine: null,
  content: null,
  formal: null,
  google_attempts: { before: 0, after_upload: null, final: null, calls: [] },
  admin: {},
  member: {},
  privacy: {},
  cross_task: {},
  disabled: {},
  limitations: [],
}

function saveResult() {
  fs.writeFileSync(path.join(TRACES, 'browser-run.json'), JSON.stringify(result, null, 2))
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

async function openAsrDialog(page) {
  const button = page.getByRole('button', { name: /Configure English transcription/i })
  await button.waitFor({ timeout: 20000 })
  await button.click()
  const dialog = page.getByRole('dialog')
  await dialog.waitFor({ timeout: 10000 })
  return dialog
}

async function closeDialog(page, dialog) {
  const cancel = dialog.getByRole('button', { name: 'Cancel', exact: true })
  if (await cancel.isVisible().catch(() => false)) {
    await cancel.click()
    await dialog.waitFor({ state: 'detached', timeout: 10000 }).catch(() => {})
  }
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
  page.on('response', async (response) => {
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
  page.on('console', (message) => {
    if (message.type() === 'error') result.console_errors.push(message.text())
  })
  page.on('pageerror', (error) => result.page_errors.push(error.message))
}

async function main() {
  check('audio input SHA-256 matches the frozen H1 holdout', result.audio.actual_sha256 === EXPECTED_AUDIO_SHA, result.audio.actual_sha256)
  check('no Google transport call happened before browser/trace started', auditCalls().length === 0, auditCalls().length)
  result.google_attempts.before = auditCalls().length
  check('no Torch/numpy/transformers/Reader is loaded at app start', (() => {
    const lines = fs.readFileSync(AUDIT, 'utf8').trim().split('\n').map(JSON.parse)
    const installed = lines.find((row) => row.kind === 'audit_installed')
    return installed && Object.values(installed.modules || {}).every((value) => value === false)
  })(), null)

  const accounts = JSON.parse(fs.readFileSync(ACCOUNTS, 'utf8'))
  const browser = await chromium.launch({
    executablePath: '/usr/bin/google-chrome',
    headless: true,
    args: ['--no-sandbox'],
  })

  try {
    // ------------------------------------------------------------ admin config
    const adminContext = await browser.newContext({ viewport: { width: 1440, height: 900 } })
    const adminPage = await adminContext.newPage()
    attachSanitizedNetwork(adminPage)
    await login(adminPage, accounts.admin.username, accounts.admin.password)

    const widths = [
      [1440, 900],
      [1024, 768],
      [390, 844],
    ]
    for (const [width, height] of widths) {
      const t0 = Date.now()
      await adminPage.setViewportSize({ width, height })
      await adminPage.goto(`${BASE}/?view=settings`, { waitUntil: 'networkidle' })
      const ov = await overflow(adminPage)
      check(`admin Settings ${width}px has no horizontal overflow`, ov.scrollWidth <= ov.innerWidth + 1, ov)
      const dialog = await openAsrDialog(adminPage)
      const text = await dialog.innerText()
      const modelValue = await dialog.getByLabel('Model', { exact: true }).inputValue()
      const baseUrlValue = await dialog.getByLabel('Base URL', { exact: true }).inputValue()
      check(`admin Google config ${width}px names the native provider and model`,
        /Google native/i.test(text) && modelValue === 'gemini-3.8-flash' && baseUrlValue === 'https://generativelanguage.googleapis.com/v1beta',
        { text_preview: text.slice(0, 1200), model: modelValue, base_url: baseUrlValue })
      check(`admin Google config ${width}px has no Reader directories or 30-second cap`,
        !/Model assets directory/i.test(text) && !/Reader assets directory/i.test(text) && !/Maximum audio seconds\s*\(1[–-]30\)/i.test(text) && !/Pinned models and hashes/i.test(text), null)
      check(`admin Google config ${width}px shows configured/capability-not-verified truth`,
        /configured/i.test(text) && /available/i.test(text) && /API key configured/i.test(text) && /not verified/i.test(text) && /does not run transcription/i.test(text), text.slice(0, 1600))
      const keyInput = dialog.getByLabel(/Google API key \(write-only\)/i)
      check(`admin Google config ${width}px key field is blank/password/write-only`,
        (await keyInput.getAttribute('type')) === 'password' && (await keyInput.inputValue()) === '', null)
      const modalOverflow = await overflow(adminPage)
      check(`admin Google modal ${width}px has no horizontal overflow`, modalOverflow.scrollWidth <= modalOverflow.innerWidth + 1, modalOverflow)
      await screenshot(adminPage, `admin-google-config-${width}.png`)
      result.admin[`width_${width}`] = {
        overflow: ov,
        modal_overflow: modalOverflow,
        model: modelValue,
        base_url: baseUrlValue,
        dialog_text_preview: text.slice(0, 2200),
        duration_ms: Date.now() - t0,
      }
      await closeDialog(adminPage, dialog)
    }

    // Fake key through the real protected UI: this must not infer or call Google.
    await adminPage.setViewportSize({ width: 1440, height: 900 })
    await adminPage.goto(`${BASE}/?view=settings`, { waitUntil: 'networkidle' })
    let dialog = await openAsrDialog(adminPage)
    await dialog.getByLabel(/Google API key \(write-only\)/i).fill(FAKE_UI_KEY)
    await dialog.getByRole('button', { name: /Save English transcription settings/i }).click()
    await dialog.getByText(/settings saved at revision/i).waitFor({ timeout: 20000 })
    const afterFakeSaveText = await dialog.innerText()
    check('UI fake-key save clears the write-only field',
      (await dialog.getByLabel(/Google API key \(write-only\)/i).inputValue()) === '', null)
    check('UI fake-key save states saving does not transcribe/verify',
      /does not run transcription|not verified/i.test(afterFakeSaveText), afterFakeSaveText.slice(-1800))
    check('fake key never appears in the browser document',
      !(await adminPage.content()).includes(FAKE_UI_KEY), null)
    check('fake-key UI save made no Google transport call',
      auditCalls().length === 0, auditCalls().length)
    await screenshot(adminPage, 'admin-google-config-fake-key-saved-1440.png')
    result.admin.fake_key_ui_save = {
      field_cleared: true,
      inference_requests: 0,
      google_attempts_after: auditCalls().length,
    }
    await closeDialog(adminPage, dialog)

    // Out-of-trace protected API restores the real key before any upload.
    const restoreOut = execFileSync(LIGHT_PY, [RESTORE, BASE], {
      env: process.env,
      encoding: 'utf8',
      timeout: 30000,
    })
    result.admin.real_key_restored_out_of_trace = JSON.parse(restoreOut.trim())
    check('real key restored out-of-trace and still no Google call',
      auditCalls().length === 0, result.admin.real_key_restored_out_of_trace)

    await adminPage.reload({ waitUntil: 'networkidle' })
    dialog = await openAsrDialog(adminPage)
    const restoredText = await dialog.innerText()
    check('restored real key is reported configured without echoing it',
      /API key configured/i.test(restoredText) && !/API key not configured/i.test(restoredText), null)
    // UI blank-retain save: the real key must survive this save.
    await dialog.getByRole('button', { name: /Save English transcription settings/i }).click()
    await dialog.getByText(/settings saved at revision/i).waitFor({ timeout: 20000 })
    const settingsAfterBlank = await api(adminPage, '/api/v1/settings')
    check('UI blank secret save retains credential_configured',
      settingsAfterBlank.status === 200 && settingsAfterBlank.body.english_asr.credential_configured === true,
      { status: settingsAfterBlank.status, revision: settingsAfterBlank.body?.english_asr?.revision })
    result.admin.blank_retain_ui_save = {
      status: settingsAfterBlank.status,
      revision: settingsAfterBlank.body.english_asr.revision,
      credential_configured: settingsAfterBlank.body.english_asr.credential_configured,
      google_attempts: auditCalls().length,
    }
    await closeDialog(adminPage, dialog)

    // ------------------------------------------------------------- member flow
    const memberContext = await browser.newContext({ viewport: { width: 1440, height: 900 } })
    const memberPage = await memberContext.newPage()
    attachSanitizedNetwork(memberPage)
    await login(memberPage, accounts.member.username, accounts.member.password)

    const memberSettings = await api(memberPage, '/api/v1/settings')
    check('ordinary member cannot read admin Google config over the API',
      memberSettings.status === 403, { status: memberSettings.status, body: memberSettings.body })

    await memberPage.goto(`${BASE}/?view=chat`, { waitUntil: 'networkidle' })
    const teamTab = memberPage.getByRole('tab', { name: 'Team' })
    if (await teamTab.isVisible().catch(() => false)) await teamTab.click()
    await memberPage.locator('#lg-chat-input').waitFor({ timeout: 20000 })

    const sourcesBefore = await api(memberPage, '/api/v1/sources?limit=20')
    const tasksBefore = await api(memberPage, '/api/v1/tasks')
    const attemptsBeforeUpload = auditCalls().length
    result.member.sources_before = sourcesBefore.body
    result.member.tasks_before = tasksBefore.body
    result.google_attempts.before = attemptsBeforeUpload
    check('no Task exists and no source exists before the single real upload',
      (sourcesBefore.body.items || []).length === 0 && (tasksBefore.body.items || []).length === 0,
      { sources: (sourcesBefore.body.items || []).length, tasks: (tasksBefore.body.items || []).length })

    let sourceCreate = null
    memberPage.on('response', async (response) => {
      const url = new URL(response.url())
      if (response.request().method() === 'POST' && url.pathname === '/api/v1/sources') {
        let body = null
        try { body = await response.json() } catch {}
        sourceCreate = body
          ? {
              status: response.status(),
              source_id: body.source?.source_id ?? null,
              job_id: body.job?.job_id ?? body.job?.id ?? null,
              intake_mode: body.intake_mode ?? null,
              created: body.created ?? null,
              deduplicated: body.deduplicated ?? null,
            }
          : { status: response.status(), parse_error: true }
      }
    })

    const tUpload = Date.now()
    await memberPage.locator('input[type=file][aria-label^="Upload file for"]').setInputFiles(AUDIO)
    await memberPage.getByText(/qa-h1-harbor/i).first().waitFor({ timeout: 15000 })
    check('ordinary Team message can attach audio without @bot and without chat text',
      (await memberPage.locator('#lg-chat-input').inputValue()) === '', null)
    await screenshot(memberPage, 'member-h1-draft-1440.png')
    await memberPage.getByRole('button', { name: 'Send message' }).click()
    result.timings.upload_clicked_ms = Date.now() - tUpload

    for (let i = 0; i < 60 && !sourceCreate; i += 1) await memberPage.waitForTimeout(250)
    check('UI POST /sources returned a real source/job envelope',
      sourceCreate && sourceCreate.status < 300 && sourceCreate.source_id && sourceCreate.job_id, sourceCreate)
    const sourceId = sourceCreate.source_id
    const jobId = sourceCreate.job_id
    result.source = { source_id: sourceId, job_id: jobId, create: sourceCreate }

    let sourceView = null
    let jobView = null
    const tReady = Date.now()
    for (let i = 0; i < 180; i += 1) {
      const [sourceResponse, jobResponse] = await Promise.all([
        api(memberPage, `/api/v1/sources/${sourceId}`),
        api(memberPage, `/api/v1/intake/jobs/${jobId}`),
      ])
      sourceView = sourceResponse.body
      jobView = jobResponse.body
      const status = sourceView?.text_status
      if (status === 'ready' || status === 'failed' || status === 'unavailable') break
      if (jobView?.status === 'failed' || jobView?.status === 'cancelled') break
      await memberPage.waitForTimeout(1000)
    }
    result.timings.source_terminal_ms = Date.now() - tReady
    result.member.job = jobView
    check('deferred intake job completed exactly one attempt with one ASR budget',
      jobView && jobView.attempt === 1 && jobView.budget?.max_asr_calls === 1 &&
        ['succeeded', 'partial'].includes(jobView.status) && !jobView.fail_reason,
      { status: jobView?.status, attempt: jobView?.attempt, budget: jobView?.budget, fail_reason: jobView?.fail_reason })
    check('source text branch is ready and English (no fake success)',
      sourceView?.text_status === 'ready' && sourceView?.language === 'en', {
        text_status: sourceView?.text_status,
        language: sourceView?.language,
        status: sourceView?.status,
      })

    const receiptResponse = await api(memberPage, `/api/v1/sources/${sourceId}/receipt`)
    const contentResponse = await api(memberPage, `/api/v1/sources/${sourceId}/content?kind=machine`)
    const receipt = receiptResponse.body
    const content = contentResponse.body
    result.receipt = receipt
    result.content = content
    const machine = receipt?.text?.machine ?? null
    result.machine = machine
    check('receipt has a ready English text branch with Google machine provenance',
      receiptResponse.status === 200 &&
        receipt.text?.status === 'ready' &&
        receipt.text?.language === 'en' &&
        machine?.provider === 'google' &&
        machine?.engine === 'google-native' &&
        machine?.runtime === 'google-native' &&
        machine?.model === 'gemini-3.8-flash' &&
        machine?.prompt_version === 'google-native-transcribe-v1' &&
        machine?.endpoint_host === 'generativelanguage.googleapis.com' &&
        machine?.endpoint_path === '/v1beta/interactions',
      { status: receiptResponse.status, text: receipt?.text })
    check('receipt leaves timestamps null and does not Fake encoder/Reader provenance',
      receipt.text?.timestamps === null && !('encoder' in machine) && !('reader' in machine),
      { timestamps: receipt.text?.timestamps, machine_keys: Object.keys(machine || {}) })
    check('machine content is nonempty real transcript text',
      contentResponse.status === 200 && content.kind === 'machine' &&
        typeof content.content === 'string' && content.content.trim().length > 0,
      { status: contentResponse.status, kind: content?.kind, preview: (content?.content || '').slice(0, 240) })
    const transcript = (content?.content || '').trim()
    result.content.content_sha256 = sha256(transcript)
    check('machine provenance hashes/bytes match the frozen input audio',
      machine?.audio_sha256 === EXPECTED_AUDIO_SHA &&
        machine?.audio_bytes === result.audio.bytes &&
        machine?.mime_type === 'audio/wav' &&
        typeof machine?.request_bytes === 'number' && machine.request_bytes > machine.audio_bytes,
      {
        audio_sha256: machine?.audio_sha256,
        audio_bytes: machine?.audio_bytes,
        request_bytes: machine?.request_bytes,
        mime_type: machine?.mime_type,
      })
    check('native Google usage/latency are recorded (usage missing would be null, not zero)',
      machine?.usage && typeof machine.usage.total_tokens === 'number' &&
        typeof machine?.latency_ms === 'number' && machine.latency_ms > 0,
      { usage: machine?.usage, latency_ms: machine?.latency_ms })

    const original = sourceView?.original ?? {}
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
    result.source.original_reported = original
    result.source.original_on_disk = onDisk
    check('actual persisted source file matches the input SHA-256',
      (sourceView?.content_hash === EXPECTED_AUDIO_SHA) &&
        (!onDisk || onDisk.sha256 === EXPECTED_AUDIO_SHA) &&
        (!onDisk || onDisk.bytes === result.audio.bytes),
      { content_hash: sourceView?.content_hash, on_disk: onDisk })
    check('source original path is source-root relative, not an absolute path',
      typeof original.path === 'string' && !original.path.startsWith('/') && !original.path.includes(DATA_ROOT),
      original.path)

    // Formal boundary: write a human formal version, prove machine unchanged.
    const formalBefore = await api(memberPage, `/api/v1/sources/${sourceId}/content?kind=formal`)
    check('no formal version exists before the human edit (machine is not formal)',
      formalBefore.status === 404, { status: formalBefore.status, body: formalBefore.body })
    const formalText = transcript
    const formalWrite = await api(memberPage, `/api/v1/sources/${sourceId}/formal`, {
      method: 'POST',
      body: { content: formalText, edited_by: accounts.member.username },
    })
    const formalRead = await api(memberPage, `/api/v1/sources/${sourceId}/content?kind=formal`)
    const machineAfterFormal = await api(memberPage, `/api/v1/sources/${sourceId}/content?kind=machine`)
    result.formal = { write: formalWrite, read: formalRead, machine_after: machineAfterFormal }
    check('human formal write succeeds and leaves the machine body unchanged',
      formalWrite.status < 300 && formalRead.status === 200 && formalRead.body.kind === 'formal' &&
        machineAfterFormal.status === 200 && machineAfterFormal.body.content.trim() === transcript,
      { write: formalWrite.status, read: formalRead.status, machine: machineAfterFormal.status })

    const callsAfterUpload = auditCalls()
    result.google_attempts.after_upload = callsAfterUpload.length
    result.google_attempts.calls = callsAfterUpload
    check('exactly one real Google transport attempt was made end-to-end',
      callsAfterUpload.length === 1, callsAfterUpload)
    const call = callsAfterUpload[0]
    check('audit wrapper forwarded a real 200 native interactions request with no model imports',
      call.status === 200 &&
        call.endpoint_host === 'generativelanguage.googleapis.com' &&
        call.endpoint_path === '/v1beta/interactions' &&
        call.key_header_present === true &&
        Object.values(call.modules || {}).every((value) => value === false) &&
        typeof call.rss_kib_before === 'number' && typeof call.rss_kib_after === 'number',
      {
        status: call.status,
        endpoint: `${call.endpoint_host}${call.endpoint_path}`,
        request_bytes: call.request_bytes,
        latency_ms: call.latency_ms,
        key_header_present: call.key_header_present,
        modules: call.modules,
        rss_kib_before: call.rss_kib_before,
        rss_kib_after: call.rss_kib_after,
      })

    // Chat receipt, text selection, keyword search, and source backlink.
    await memberPage.waitForFunction(
      () => /machine Google transcript|Google native/i.test(document.body.innerText),
      null,
      { timeout: 60000 },
    ).catch(() => {})
    const chatText = await memberPage.locator('body').innerText()
    check('Chat receipt shows truthful Google transcript provenance',
      /machine Google transcript/i.test(chatText) && /gemini-3\.8-flash/i.test(chatText) && transcript.slice(0, 30).replace(/\s+/g, ' ').slice(0, 18) && chatText.includes(transcript.split(/\s+/).slice(0, 5).join(' ')),
      chatText.slice(-2400))
    await screenshot(memberPage, 'member-h1-receipt-1440.png')

    const viewMaterial = memberPage.getByRole('button', { name: 'View material' }).first()
    await viewMaterial.waitFor({ timeout: 20000 })
    await viewMaterial.click()
    await memberPage.waitForFunction(
      (text) => document.body.innerText.includes(text),
      transcript.split(/\s+/).slice(0, 5).join(' '),
      { timeout: 30000 },
    )
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
    check('machine transcript is selectable text in the Tasks material detail',
      selectedText.includes('North Harbor'), selectedText.slice(0, 200))
    await screenshot(memberPage, 'member-h1-detail-1440.png')

    const searchInput = memberPage.locator('input[aria-label="Search"]')
    await searchInput.fill('Cedar Island')
    await searchInput.press('Enter')
    await memberPage.locator('#lg-material-search').waitFor({ timeout: 15000 })
    await memberPage.waitForTimeout(1200)
    const searchText = await memberPage.locator('#lg-material-search').innerText()
    check('Keyword search finds the real transcript phrase and source',
      /qa-h1-harbor/i.test(searchText) && /Cedar Island/i.test(searchText), searchText.slice(0, 1600))
    await screenshot(memberPage, 'member-keyword-search-1440.png')
    await memberPage.getByRole('button', { name: 'Open in Tasks' }).first().click()
    await memberPage.waitForFunction(
      (text) => document.body.innerText.includes(text),
      transcript.split(/\s+/).slice(0, 5).join(' '),
      { timeout: 20000 },
    )
    result.member.search = { query: 'Cedar Island', panel_preview: searchText.slice(0, 1600), backlink: true }
    check('search result backlink opens the same source in Tasks',
      (await memberPage.locator('body').innerText()).includes(transcript.split(/\s+/).slice(0, 5).join(' ')), null)

    // Existing material remains usable at 1024/390 without another ASR call.
    for (const [width, height] of [[1024, 768], [390, 844]]) {
      await memberPage.setViewportSize({ width, height })
      await memberPage.waitForTimeout(500)
      const ov = await overflow(memberPage)
      const body = await memberPage.locator('body').innerText()
      check(`member material detail ${width}px has no horizontal overflow and keeps history`,
        ov.scrollWidth <= ov.innerWidth + 1 && body.includes(transcript.split(/\s+/).slice(0, 5).join(' ')),
        { overflow: ov, transcript_present: body.includes(transcript.split(/\s+/).slice(0, 5).join(' ')) })
      await screenshot(memberPage, `member-history-${width}.png`)
    }

    // Personal private audio must not enter shared ASR/index.
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
    check('Personal private audio creates no shared source and no shared ASR attempt',
      auditCalls().length === attemptsBeforePrivate &&
        (sourcesAfterPrivate.body.items || []).length === (sourcesBeforePrivate.body.items || []).length,
      {
        google_attempts_before: attemptsBeforePrivate,
        google_attempts_after: auditCalls().length,
        sources_before: (sourcesBeforePrivate.body.items || []).length,
        sources_after: (sourcesAfterPrivate.body.items || []).length,
      })
    const personalText = await memberPage.locator('body').innerText()
    check('Personal private audio UI does not claim a shared transcript/index',
      !/machine Google transcript/i.test(personalText), personalText.slice(-1200))
    result.privacy = {
      shared_source_count_before: (sourcesBeforePrivate.body.items || []).length,
      shared_source_count_after: (sourcesAfterPrivate.body.items || []).length,
      google_attempts_before: attemptsBeforePrivate,
      google_attempts_after: auditCalls().length,
    }
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
        /reference_invalid|outside the message scope/i.test(JSON.stringify(appendOutOfScope.body)),
      result.cross_task)

    // -------------------------------------------------- disable + history retained
    await adminPage.setViewportSize({ width: 1440, height: 900 })
    await adminPage.goto(`${BASE}/?view=settings`, { waitUntil: 'networkidle' })
    dialog = await openAsrDialog(adminPage)
    await dialog.getByLabel(/Enable English transcription/i).uncheck()
    await dialog.getByRole('button', { name: /Save English transcription settings/i }).click()
    await dialog.getByText(/settings saved at revision/i).waitFor({ timeout: 20000 })
    const disabledText = await dialog.innerText()
    const settingsDisabled = await api(adminPage, '/api/v1/settings')
    check('disabled Google config is honest: disabled/unavailable with no fake success',
      settingsDisabled.status === 200 &&
        settingsDisabled.body.english_asr.enabled === false &&
        settingsDisabled.body.english_asr.available === false &&
        settingsDisabled.body.english_asr.reason === 'disabled' &&
        /disabled/i.test(disabledText) && /no transcription is generated|No transcription success is claimed/i.test(disabledText),
      { view: settingsDisabled.body.english_asr, text: disabledText.slice(0, 1200) })
    await screenshot(adminPage, 'admin-google-disabled-1440.png')
    result.disabled = {
      status: settingsDisabled.status,
      english_asr: settingsDisabled.body.english_asr,
      google_attempts: auditCalls().length,
    }
    await closeDialog(adminPage, dialog)

    const attemptsBeforeReload = auditCalls().length
    await memberPage.setViewportSize({ width: 1440, height: 900 })
    await memberPage.goto(`${BASE}/?view=chat`, { waitUntil: 'networkidle' })
    const searchAgain = memberPage.locator('input[aria-label="Search"]')
    await searchAgain.fill('Cedar Island')
    await searchAgain.press('Enter')
    await memberPage.locator('#lg-material-search').waitFor({ timeout: 15000 })
    await memberPage.waitForTimeout(1000)
    await memberPage.getByRole('button', { name: 'Open in Tasks' }).first().click()
    await memberPage.waitForFunction(
      (text) => document.body.innerText.includes(text),
      transcript.split(/\s+/).slice(0, 5).join(' '),
      { timeout: 20000 },
    )
    const historyAfterDisable = await memberPage.locator('body').innerText()
    const machineWhileDisabled = await api(memberPage, `/api/v1/sources/${sourceId}/content?kind=machine`)
    check('historical machine transcript remains readable after reload and disable',
      historyAfterDisable.includes(transcript.split(/\s+/).slice(0, 5).join(' ')) &&
        machineWhileDisabled.status === 200 &&
        machineWhileDisabled.body.content.trim() === transcript,
      { content_status: machineWhileDisabled.status, google_attempts: auditCalls().length })
    check('history/reload/disable never triggered a second Google call',
      auditCalls().length === attemptsBeforeReload && auditCalls().length === 1,
      { before: attemptsBeforeReload, after: auditCalls().length })
    await screenshot(memberPage, 'member-history-after-disable-1440.png')

    result.google_attempts.final = auditCalls().length
    result.timings.total_ms = Date.now() - tUpload
    result.member.transcript = transcript
    result.member.transcript_sha256 = sha256(transcript)
    result.member.receipt_machine = machine
    result.member.search = { query: 'Cedar Island', found: true, backlink: true }
    result.network.request_count = result.network.requests.length
    result.network.response_count = result.network.responses.length
    result.network.method_path_counts = result.network.requests.reduce((acc, entry) => {
      const key = `${entry.method} ${entry.path}`
      acc[key] = (acc[key] || 0) + 1
      return acc
    }, {})

    check('browser made no cross-origin or direct Google request',
      result.network.cross_origin.length === 0 && result.network.google_host_requests.length === 0,
      { cross_origin: result.network.cross_origin, google: result.network.google_host_requests })
    check('browser never received a Google vendor header',
      result.network.vendor_header_responses.length === 0,
      result.network.vendor_header_responses)
    check('final real Google attempt count is exactly one',
      result.google_attempts.final === 1, result.google_attempts)

    fs.writeFileSync(
      path.join(LOGS, 'request-counts.json'),
      JSON.stringify({
        network_requests: result.network.request_count,
        network_responses: result.network.response_count,
        method_path_counts: result.network.method_path_counts,
        google_transport_attempts: result.google_attempts.final,
        cross_origin_requests: result.network.cross_origin.length,
        direct_google_browser_requests: result.network.google_host_requests.length,
        vendor_header_responses: result.network.vendor_header_responses.length,
      }, null, 2),
    )
    fs.writeFileSync(
      path.join(PROV, 'google-attempts-before-after.json'),
      JSON.stringify(result.google_attempts, null, 2),
    )
    fs.writeFileSync(
      path.join(TRACES, 'browser-network-sanitized.json'),
      JSON.stringify(result.network, null, 2),
    )
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
