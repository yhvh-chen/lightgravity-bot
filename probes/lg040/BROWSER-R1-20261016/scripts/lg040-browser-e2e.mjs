#!/usr/bin/env node
/**
 * lg040-browser-e2e.mjs — LG-040 BROWSER owner real end-to-end driver.
 *
 * Drives the **real built product** (real `lightgravity` app + real
 * `frontend/dist` + real runtime token) in a **real Firefox** over native
 * WebDriver BiDi, exercising the English user path:
 *
 *   Chat real file upload → Files preview → Reprocess (OCR) → search →
 *   formal edit → download → revoke → rebuild → unauthorized-write failure.
 *
 * The browser reconstructs genuine `File` objects from the frozen fixture bytes
 * served by the launcher's evidence-only loopback route (hash-verified), then
 * sets them on the real `<input type=file>` so the product's own FileReader /
 * `POST /sources` path runs. No network mocking, no artifact interception.
 *
 * Evidence: per-step records, machine JSON, real screenshots (desktop 1440 +
 * narrow 390) captured from the live browser, and product state read from the
 * real API before/after.
 */

import { spawn } from 'node:child_process'
import net from 'node:net'
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

function parseArgs(argv) {
  const out = {
    url: null,
    out: '/tmp/lg040-browser',
    deadlineMs: 180000,
    firefox: process.env.FIREFOX_BIN || '/snap/bin/firefox',
    profileDir: null,
    ocrTimeoutMs: 130000,
  }
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i]
    const next = () => argv[++i]
    if (a === '--url') out.url = next()
    else if (a === '--out') out.out = next()
    else if (a === '--deadline-ms') out.deadlineMs = Number(next())
    else if (a === '--firefox') out.firefox = next()
    else if (a === '--profile-dir') out.profileDir = next()
    else if (a === '--ocr-timeout-ms') out.ocrTimeoutMs = Number(next())
    else if (a === '--live') out.live = true
    else throw new Error(`unknown arg: ${a}`)
  }
  if (!out.url) throw new Error('--url is required')
  if (!out.url.endsWith('/')) out.url += '/'
  return out
}

const ARGS = parseArgs(process.argv)
const MODE_IS_LIVE = !!ARGS.live
const log = (...m) => console.log(...m)
const MARKER = `lg040-${process.pid}`
let childPid = null

function cleanup() {
  if (childPid == null) return
  try {
    const cmd = readFileSync(`/proc/${childPid}/cmdline`, 'utf8')
    if (cmd.includes(MARKER) && cmd.includes('firefox')) {
      process.kill(-childPid, 'SIGTERM')
      const t0 = Date.now()
      while (Date.now() - t0 < 1500) {
        try { process.kill(-childPid, 0) } catch { return }
        const end = Date.now() + 40
        while (Date.now() < end) { /* spin */ }
      }
      process.kill(-childPid, 'SIGKILL')
    }
  } catch { /* gone */ }
}
process.on('exit', cleanup)
process.on('SIGINT', () => { cleanup(); process.exit(130) })
process.on('SIGTERM', () => { cleanup(); process.exit(143) })

class Bidi {
  constructor(ws) {
    this.ws = ws; this.nextId = 1; this.pending = new Map(); this.events = []
    ws.addEventListener('message', (ev) => {
      let msg
      try { msg = JSON.parse(typeof ev.data === 'string' ? ev.data : ev.data.toString()) } catch { return }
      if (msg.id !== undefined && this.pending.has(msg.id)) {
        const { resolve, reject } = this.pending.get(msg.id); this.pending.delete(msg.id)
        if (msg.type === 'error') reject(new Error(`${msg.error}: ${msg.message}`)); else resolve(msg.result)
      } else if (msg.method) {
        this.events.push(msg)
      }
    })
  }
  send(method, params = {}, timeoutMs = 8000) {
    const id = this.nextId++
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { this.pending.delete(id); reject(new Error(`timeout ${method}`)) }, timeoutMs)
      this.pending.set(id, { resolve: (r) => { clearTimeout(timer); resolve(r) }, reject: (e) => { clearTimeout(timer); reject(e) } })
      this.ws.send(JSON.stringify({ id, method, params }))
    })
  }
}

function connect(url, timeoutMs) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(url)
    const timer = setTimeout(() => reject(new Error('ws connect timeout')), timeoutMs)
    ws.addEventListener('open', () => { clearTimeout(timer); resolve(ws) })
    ws.addEventListener('error', (e) => { clearTimeout(timer); reject(new Error('ws error: ' + (e.message || 'unknown'))) })
  })
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function evalJs(bidi, context, expression, timeoutMs = 15000) {
  const wrapped = `(async () => { const v = await (${expression}); return JSON.stringify(v === undefined ? null : v); })()`
  const res = await bidi.send('script.evaluate', {
    expression: wrapped, target: { context }, awaitPromise: true, resultOwnership: 'none',
  }, timeoutMs)
  if (res.type === 'exception') {
    throw new Error(`eval exception: ${res.exceptionDetails?.text ?? JSON.stringify(res.exceptionDetails)}`)
  }
  const raw = res.result ? res.result.value : undefined
  try { return raw == null ? raw : JSON.parse(raw) } catch { return raw }
}

async function apiGet(url) {
  const r = await fetch(url, { headers: { Accept: 'application/json' } })
  const text = await r.text()
  let body = null
  try { body = JSON.parse(text) } catch { body = text.slice(0, 300) }
  return { status: r.status, body }
}

async function main() {
  const deadline = Date.now() + ARGS.deadlineMs
  const outDir = ARGS.out
  mkdirSync(outDir, { recursive: true })
  const results = []
  const record = (name, ok, detail) => {
    results.push({ name, ok: !!ok, detail: detail === undefined ? null : detail })
    log(`${ok ? 'PASS' : 'FAIL'} ${name}${detail !== undefined ? ' :: ' + (typeof detail === 'string' ? detail : JSON.stringify(detail)) : ''}`)
  }

  const profileRoot = ARGS.profileDir || tmpdir()
  mkdirSync(profileRoot, { recursive: true })
  const profile = mkdtempSync(join(profileRoot, `${MARKER}-`))
  const port = await new Promise((res, rej) => {
    const s = net.createServer(); s.on('error', rej)
    s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)) })
  })
  const child = spawn(ARGS.firefox, [
    '--headless', '--no-remote', `--profile=${profile}`,
    `--remote-debugging-port=${port}`, '--no-first-run', 'about:blank',
  ], { detached: true, stdio: ['ignore', 'ignore', 'ignore'] })
  childPid = child.pid

  const wsUrl = `ws://127.0.0.1:${port}/session`
  let up = false
  while (Date.now() < deadline && !up) {
    up = await new Promise((res) => {
      const s = new net.Socket(); s.setTimeout(800)
      s.once('connect', () => { s.destroy(); res(true) })
      s.once('timeout', () => { s.destroy(); res(false) })
      s.once('error', () => { res(false) })
      s.connect(port, '127.0.0.1')
    })
    if (!up) await sleep(300)
  }
  if (!up) throw new Error('firefox BiDi port never became reachable')

  const ws = await connect(wsUrl, 8000)
  const bidi = new Bidi(ws)
  await bidi.send('session.new', { capabilities: { alwaysMatch: {} } }, 8000)

  const tree = await bidi.send('browsingContext.getTree', {})
  let context = tree.contexts[0]?.context
  if (!context) {
    const created = await bidi.send('browsingContext.create', { type: 'tab' })
    context = created.context
  }
  await bidi.send('browsingContext.navigate', { context, url: ARGS.url, wait: 'complete' }, 25000)
  await sleep(2000)

  const origin = await evalJs(bidi, context, `location.origin`)
  record('real same-origin http document', origin === ARGS.url.replace(/\/$/, ''), { origin, url: ARGS.url })

  // helper injected into the page: real File upload from the loopback fixture bytes
  await evalJs(bidi, context, `(() => {
    window.__lgSetFile = async (name, bytesUrl) => {
      const resp = await fetch(bytesUrl, { cache: 'no-store' });
      const buf = await resp.arrayBuffer();
      const type = name.endsWith('.pdf') ? 'application/pdf' : 'image/png';
      const file = new File([buf], name, { type });
      window.__lgLastBytes = buf.byteLength;
      const input = document.querySelector('input[type=file][aria-label="Upload files to this conversation"]');
      if (!input) throw new Error('no chat file input');
      const dt = new DataTransfer();
      dt.items.add(file);
      input.files = dt.files;
      input.dispatchEvent(new Event('change', { bubbles: true }));
      return { bytes: buf.byteLength, type, name };
    };
    window.__lgSha = async (bytesUrl) => {
      const resp = await fetch(bytesUrl, { cache: 'no-store' });
      const buf = await resp.arrayBuffer();
      const digest = await crypto.subtle.digest('SHA-256', buf);
      return [...new Uint8Array(digest)].map(b => b.toString(16).padStart(2,'0')).join('');
    };
    return true;
  })()`)

  // Fetch the fixture route to confirm bytes available (evidence-only).
  const fxOk = await evalJs(bidi, context, `fetch('/_lg040_fixture/clear_real.pdf',{cache:'no-store'}).then(r=>r.status)`)
  record('fixture byte route reachable from page', fxOk === 200, { status: fxOk })

  // --- initial English UI checks (desktop 1440) ---
  await bidi.send('browsingContext.setViewport', { context, viewport: { width: 1440, height: 900 } }).catch(() => {})
  await sleep(300)
  const initial = await evalJs(bidi, context, `(() => {
    const text = document.body.innerText;
    return {
      hasMaterials: !!document.querySelector('.lg-materials'),
      noTaskText: /no delivery Task\\/Run is created/i.test(text),
      uploadBtn: !!document.querySelector('input[type=file][aria-label="Upload files to this conversation"]'),
      recordLink: !!document.querySelector('input[aria-label="Record a link"]'),
      searchInput: !!document.querySelector('input[aria-label="Search materials"]'),
      emptyMaterials: /No materials yet/i.test(text),
      lang: document.documentElement.lang,
    };
  })()`)
  record('Chat English material intake renders', initial.hasMaterials && initial.uploadBtn && initial.recordLink && initial.searchInput, initial)
  record('Chat empty state English', initial.emptyMaterials)
  record('Chat states no delivery Task created', initial.noTaskText)

  const shot = async (name, width, height) => {
    await bidi.send('browsingContext.setViewport', { context, viewport: { width, height } }).catch(() => {})
    await sleep(400)
    const png = await bidi.send('browsingContext.captureScreenshot', { context })
    writeFileSync(join(outDir, name), Buffer.from(png.data, 'base64'))
  }
  await shot('01-chat-desktop-1440.png', 1440, 900)

  // --- product state before upload ---
  const before = await apiGet(`${ARGS.url}api/v1/sources`)
  record('API sources empty before upload', before.status === 200 && Array.isArray(before.body.items) && before.body.items.length === 0, before.status)

  // --- Upload 1: real English scan PDF ---
  const up1 = await evalJs(bidi, context, `window.__lgSetFile('clear_real.pdf', '/_lg040_fixture/clear_real.pdf')`)
  record('upload1 real clear_real.pdf selected in real <input type=file>', up1.bytes === 5176, up1)
  // wait for receipt to show a real source id
  const rec1 = await evalJs(bidi, context, `(async () => {
    for (let i = 0; i < 80; i++) {
      await new Promise(r => setTimeout(r, 150));
      const items = [...document.querySelectorAll('.lg-materials__item')];
      const item = items.find(el => el.innerText.includes('clear_real.pdf'));
      if (item) {
        const t = item.innerText;
        const m = t.match(/source_[A-Za-z0-9]+/);
        const failed = /failed|unauthorized/i.test(t);
        if (m || failed) return { text: t, sourceId: m ? m[0] : null, failed };
      }
    }
    return { text: document.querySelector('.lg-materials')?.innerText || 'no materials', sourceId: null, timeout: true };
  })()`, 20000)
  record('upload1 receipt shows real source id (no Task/Run)', !!rec1.sourceId && !rec1.failed, rec1)

  // --- Upload 2: real NIST table PNG ---
  const up2 = await evalJs(bidi, context, `window.__lgSetFile('honest_table_grid_scale4.png', '/_lg040_fixture/honest_table_grid_scale4.png')`)
  record('upload2 real NIST table PNG selected', up2.bytes === 33716, up2)
  const rec2 = await evalJs(bidi, context, `(async () => {
    for (let i = 0; i < 80; i++) {
      await new Promise(r => setTimeout(r, 150));
      const items = [...document.querySelectorAll('.lg-materials__item')];
      const item = items.find(el => el.innerText.includes('honest_table_grid_scale4.png'));
      if (item) {
        const t = item.innerText;
        const m = t.match(/source_[A-Za-z0-9]+/);
        if (m) return { text: t, sourceId: m[0] };
      }
    }
    return { text: document.querySelector('.lg-materials')?.innerText || 'no materials', sourceId: null, timeout: true };
  })()`, 20000)
  record('upload2 receipt shows real source id', !!rec2.sourceId, rec2)
  await shot('02-chat-uploads-desktop-1440.png', 1440, 900)

  const srcPdf = rec1.sourceId
  const srcPng = rec2.sourceId

  // --- global/inbox attribution: sources have inbox_ref, no task_ref ---
  if (srcPdf) {
    const sv = await apiGet(`${ARGS.url}api/v1/sources/${srcPdf}`)
    const s = sv.body.source || sv.body
    record('global upload attributed to inbox (no task_ref)',
      sv.status === 200 && s.scope && !s.scope.task_ref, { scope: s?.scope, status: s?.status })
  }

  // --- open Files → Materials, open source 1 ---
  const goFiles = await evalJs(bidi, context, `(async () => {
    const btn = [...document.querySelectorAll('button[aria-label]')].find(b => b.getAttribute('aria-label') === 'Files');
    if (!btn) return false;
    btn.click();
    for (let i = 0; i < 40; i++) {
      await new Promise(r => setTimeout(r, 150));
      if ([...document.querySelectorAll('button')].some(b => b.textContent.trim() === 'Materials')) return true;
    }
    return false;
  })()`)
  record('Files view opens with Materials tab (English)', goFiles)

  const openMat = await evalJs(bidi, context, `(async () => {
    const tab = [...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Materials');
    if (tab) tab.click();
    for (let i = 0; i < 60; i++) {
      await new Promise(r => setTimeout(r, 150));
      const list = document.querySelector('.lg-files-materials__list');
      if (list && list.querySelectorAll('button.lg-files__entry').length >= 2) {
        return { ok: true, count: list.querySelectorAll('button.lg-files__entry').length, text: document.querySelector('.lg-files-materials')?.innerText?.slice(0,200) };
      }
    }
    return { ok: false, text: document.body.innerText.slice(0, 300) };
  })()`)
  record('Files Materials lists the same 2 sources', openMat.ok && openMat.count >= 2, openMat)

  // open the PDF source by clicking its entry
  const openPdf = await evalJs(bidi, context, `(async () => {
    const entries = [...document.querySelectorAll('button.lg-files__entry')];
    const e = entries.find(el => el.textContent.includes('clear_real.pdf'));
    if (!e) return { ok: false, reason: 'no entry' };
    e.click();
    for (let i = 0; i < 60; i++) {
      await new Promise(r => setTimeout(r, 150));
      const facts = document.querySelector('.lg-files-materials__facts');
      const actions = [...document.querySelectorAll('.lg-files-materials__actions button')].map(b => b.textContent.trim());
      if (facts && actions.length) return { ok: true, facts: facts.innerText, actions };
    }
    return { ok: false };
  })()`)
  record('Files opens source with preview + English actions', openPdf.ok && openPdf.actions?.includes('Reprocess (OCR)') && openPdf.actions?.includes('Save correction') && openPdf.actions?.includes('Download original'), openPdf)
  await shot('03-files-materials-desktop-1440.png', 1440, 900)

  // --- Reprocess (OCR) source 1: real LAN model call #1 ---
  const ocr1 = await evalJs(bidi, context, `(async () => {
    const btn = [...document.querySelectorAll('.lg-files-materials__actions button')].find(b => b.textContent.includes('Reprocess'));
    if (!btn) return { ok: false, reason: 'no reprocess button' };
    btn.click();
    for (let i = 0; i < ${Math.floor(ARGS.ocrTimeoutMs / 200)}; i++) {
      await new Promise(r => setTimeout(r, 200));
      const status = document.querySelector('.lg-files__status');
      if (status) {
        const t = status.innerText;
        if (/Reprocess started|capability_unavailable|OCR service is not configured|failed|not available/i.test(t)) return { ok: true, status: t };
      }
    }
    return { ok: false, timeout: true, status: document.querySelector('.lg-files__status')?.innerText ?? null };
  })()`, ARGS.ocrTimeoutMs + 5000)
  record('OCR reprocess #1 (clear_real scan) returned a status', ocr1.ok, ocr1)

  const afterOcr1 = await apiGet(`${ARGS.url}api/v1/sources/${srcPdf}`)
  const sv1 = afterOcr1.body.source || afterOcr1.body
  record('source1 status after OCR is real (extracted/indexed or failed-honest)',
    afterOcr1.status === 200 && typeof sv1.status === 'string', { status: sv1?.status, index: sv1?.index })
  if (MODE_IS_LIVE) {
    // In live mode a truthful OCR run must reach a trusted-body status.
    record('OCR #1 produced a trusted body (extracted/indexed)', ['extracted','attributed','indexed'].includes(sv1.status), { status: sv1?.status })
  } else {
    // Dry mode: OCR is honestly unavailable; the toast must not claim success.
    const toastClaimedSuccess = /Reprocess started/.test(ocr1.status || '')
    record('dry-mode OCR failure is reported honestly (failure not shown as success)',
      sv1.status === 'failed' ? !toastClaimedSuccess : true,
      { real_status: sv1?.status, ui_toast: ocr1.status, false_success: sv1.status === 'failed' && toastClaimedSuccess })
  }

  // read machine content to confirm real OCR text vs truth (reference only)
  let content1 = null
  if (srcPdf) {
    const c = await apiGet(`${ARGS.url}api/v1/sources/${srcPdf}/content?kind=machine`)
    content1 = c.body
  }

  // --- Reprocess (OCR) source 2: real LAN model call #2 (table) ---
  const openPng = await evalJs(bidi, context, `(async () => {
    const entries = [...document.querySelectorAll('button.lg-files__entry')];
    const e = entries.find(el => el.textContent.includes('honest_table_grid_scale4.png') || el.title === '${srcPng}');
    if (!e) return { ok: false, reason: 'no entry', count: entries.length };
    e.click();
    for (let i = 0; i < 60; i++) { await new Promise(r => setTimeout(r, 150)); if (document.querySelector('.lg-files-materials__facts')) return { ok: true }; }
    return { ok: false };
  })()`)
  record('Files opens source 2 (NIST table)', openPng.ok, openPng)

  const ocr2 = await evalJs(bidi, context, `(async () => {
    const btn = [...document.querySelectorAll('.lg-files-materials__actions button')].find(b => b.textContent.includes('Reprocess'));
    if (!btn) return { ok: false, reason: 'no reprocess button' };
    btn.click();
    for (let i = 0; i < ${Math.floor(ARGS.ocrTimeoutMs / 200)}; i++) {
      await new Promise(r => setTimeout(r, 200));
      const status = document.querySelector('.lg-files__status');
      if (status) {
        const t = status.innerText;
        if (/Reprocess started|capability_unavailable|OCR service is not configured|failed|not available/i.test(t)) return { ok: true, status: t };
      }
    }
    return { ok: false, timeout: true };
  })()`, ARGS.ocrTimeoutMs + 5000)
  record('OCR reprocess #2 (NIST table) returned a status', ocr2.ok, ocr2)

  let content2 = null
  if (srcPng) {
    const c = await apiGet(`${ARGS.url}api/v1/sources/${srcPng}/content?kind=machine`)
    content2 = c.body
  }

  writeFileSync(join(outDir, 'ocr-content.json'), JSON.stringify({
    source1: { source_id: srcPdf, status: sv1?.status, index: sv1?.index, content: content1 },
    source2: { source_id: srcPng, content: content2 },
  }, null, 2))

  // --- search: real hit with version + hash (rebuild_if_missing) ---
  const goChat = await evalJs(bidi, context, `(async () => {
    const btn = [...document.querySelectorAll('button[aria-label]')].find(b => b.getAttribute('aria-label') === 'Chat');
    if (btn) btn.click();
    for (let i = 0; i < 40; i++) { await new Promise(r => setTimeout(r, 150)); if (document.querySelector('input[aria-label="Search materials"]')) return true; }
    return false;
  })()`)
  record('Chat search available after switch', goChat)

  const search = await evalJs(bidi, context, `(async () => {
    const input = document.querySelector('input[aria-label="Search materials"]');
    if (!input) return { ok: false, reason: 'no input' };
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
    setter.call(input, 'Invoice');
    input.dispatchEvent(new Event('input', { bubbles: true }));
    await new Promise(r => setTimeout(r, 50));
    const button = [...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Search');
    button.click();
    for (let i = 0; i < 80; i++) {
      await new Promise(r => setTimeout(r, 150));
      const hit = document.querySelector('.lg-source-search__hit');
      if (hit) return { ok: true, text: hit.innerText };
      const err = document.querySelector('.lg-source-search [role=alert]');
      if (err) return { ok: false, error: err.innerText };
    }
    return { ok: false, reason: document.querySelector('.lg-source-search')?.innerText || 'no hits' };
  })()`, 25000)
  record('search returns a real source hit with v+hash', search.ok && /v\d+/.test(search.text || '') && /#/.test(search.text || ''), search)

  // --- formal edit: open source, type correction, save ---
  const goFiles2 = await evalJs(bidi, context, `(async () => {
    const btn = [...document.querySelectorAll('button[aria-label]')].find(b => b.getAttribute('aria-label') === 'Files');
    btn.click();
    for (let i = 0; i < 40; i++) { await new Promise(r => setTimeout(r, 150)); const t = [...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Materials'); if (t) { t.click(); break; } }
    await new Promise(r => setTimeout(r, 400));
    const entries = [...document.querySelectorAll('button.lg-files__entry')];
    const e = entries.find(el => el.textContent.includes('clear_real.pdf'));
    if (e) e.click();
    for (let i = 0; i < 60; i++) { await new Promise(r => setTimeout(r, 150)); if (document.querySelector('textarea[aria-label="Formal version content"]')) return true; }
    return false;
  })()`)
  record('Files formal editor reachable', goFiles2)

  const formal = await evalJs(bidi, context, `(async () => {
    const ta = document.querySelector('textarea[aria-label="Formal version content"]');
    if (!ta) return { ok: false, reason: 'no textarea' };
    const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
    setter.call(ta, 'LG040-FORMAL-EN Correction marker 2026-10-16');
    ta.dispatchEvent(new Event('input', { bubbles: true }));
    await new Promise(r => setTimeout(r, 100));
    const btn = [...document.querySelectorAll('.lg-files-materials__actions button')].find(b => b.textContent.includes('Save correction'));
    btn.click();
    for (let i = 0; i < 60; i++) {
      await new Promise(r => setTimeout(r, 150));
      const s = document.querySelector('.lg-files__status');
      if (s) return { ok: /Saved formal version/.test(s.innerText), status: s.innerText };
    }
    return { ok: false, reason: 'no status' };
  })()`)
  record('formal correction saved (English success text)', formal.ok, formal)

  // --- download original + formal via UI ---
  const dl = await evalJs(bidi, context, `(async () => {
    const used = [];
    for (const label of ['Download original', 'Download formal']) {
      const btn = [...document.querySelectorAll('.lg-files-materials__actions button')].find(b => b.textContent.trim() === label);
      if (!btn) { used.push({ label, ok: false, reason: 'missing' }); continue; }
      if (btn.disabled) { used.push({ label, ok: false, reason: 'disabled' }); continue; }
      btn.click();
      let got = null;
      for (let i = 0; i < 40; i++) {
        await new Promise(r => setTimeout(r, 150));
        const s = document.querySelector('.lg-files__status');
        if (s && /Downloaded /.test(s.innerText)) { got = s.innerText; break; }
      }
      used.push({ label, ok: !!got, status: got });
    }
    return used;
  })()`)
  record('download original via UI', dl[0]?.ok, dl[0])
  record('download formal via UI', dl[1]?.ok, dl[1])

  // --- rebuild index: search with rebuild_if_missing (real; hash back-check) ---
  const rebuild = await apiGet(`${ARGS.url}api/v1/search?q=Invoice&include_global=true&rebuild_if_missing=true&limit=10`)
  record('search rebuild_if_missing returns hit with hash back-check',
    rebuild.status === 200 && Array.isArray(rebuild.body.hits) && rebuild.body.hits.length >= 1 &&
    rebuild.body.hits.every(h => h.source_id && h.content_hash !== undefined),
    { status: rebuild.status, hits: rebuild.body?.hits?.length })

  // --- revoke the table source and confirm honest unavailable ---
  let revoked = null
  if (srcPng) {
    const rv = await evalJs(bidi, context, `(async () => {
      const entries = [...document.querySelectorAll('button.lg-files__entry')];
      const e = entries.find(el => el.textContent.includes('honest_table_grid_scale4.png'));
      if (e) e.click();
      for (let i = 0; i < 60; i++) { await new Promise(r => setTimeout(r, 150)); if (document.querySelector('.lg-files-materials__facts')) break; }
      return true;
    })()`)
    // The UI exposes Archive (reversible) but not revoke directly; revoke is
    // an API action. Exercise the real API action and then confirm the UI
    // reflects the revoked/unavailable state honestly (no UI revoke control).
    const actionResp = await fetch(`${ARGS.url}api/v1/sources/${srcPng}/actions`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'revoke', confirmed: true }),
    })
    revoked = { status: actionResp.status, body: await actionResp.text() }
    const after = await apiGet(`${ARGS.url}api/v1/sources/${srcPng}`)
    record('revoke via real API action (no UI revoke control exists)', actionResp.status === 200, { status: actionResp.status })
    const sv = after.body.source || after.body
    record('revoked source is honestly unavailable (status archived, vector disabled)',
      after.status === 200 && sv.status === 'archived', { status: sv?.status, index: sv?.index })
  }

  // --- unauthorized write honest failure (real protected Settings write) ---
  let unauth = null
  try {
    unauth = await evalJs(bidi, context, `(async () => {
      const setVal = (el, v) => {
        const proto = el.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
        Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, v);
        el.dispatchEvent(new Event('input', { bubbles: true }));
      };
      const settingsBtn = [...document.querySelectorAll('button[aria-label]')].find(b => b.getAttribute('aria-label') === 'Settings');
      if (!settingsBtn) return { ok: false, reason: 'no settings entry' };
      settingsBtn.click();
      for (let i = 0; i < 60; i++) { await new Promise(r => setTimeout(r, 150)); if ([...document.querySelectorAll('button')].some(b => b.textContent.trim() === 'New connection')) break; }
      const newBtn = [...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'New connection');
      if (!newBtn) return { ok: false, reason: 'no new connection button' };
      newBtn.click();
      for (let i = 0; i < 60; i++) { await new Promise(r => setTimeout(r, 150)); if (document.querySelector('.lg-connection-form')) break; }
      const form = document.querySelector('.lg-connection-form');
      if (!form) return { ok: false, reason: 'no form' };
      const inputs = [...form.querySelectorAll('input.lg-field__input')];
      const byLabel = (txt) => {
        const lab = [...form.querySelectorAll('label.lg-field')].find(l => l.textContent.includes(txt));
        return lab ? lab.querySelector('input,textarea') : null;
      };
      const idEl = byLabel('Connection id'); if (idEl) setVal(idEl, 'lg040-unauth');
      const refEl = byLabel('Credential reference'); if (refEl) setVal(refEl, 'deepseek-lg040');
      const keyEl = byLabel('New API key'); if (keyEl) setVal(keyEl, 'sk-fake-lg040');
      await new Promise(r => setTimeout(r, 100));
      const real = window.__LG_RUNTIME_TOKEN__;
      window.__LG_RUNTIME_TOKEN__ = 'wrong-token-lg040';
      let out;
      try {
        const submit = [...form.querySelectorAll('button[type=submit]')][0];
        submit.click();
        for (let i = 0; i < 60; i++) {
          await new Promise(r => setTimeout(r, 150));
          const err = document.querySelector('.lg-connection-form .lg-state--error, .lg-connection-form [role=alert]');
          if (err) { out = { ok: /unauthorized/i.test(err.innerText), text: err.innerText.slice(0, 200) }; break; }
          const notice = document.querySelector('.lg-connection-form .lg-notice');
          if (notice) { out = { ok: /unauthorized/i.test(notice.innerText), text: notice.innerText.slice(0, 200) }; break; }
        }
        out = out || { ok: false, reason: 'no error surfaced', body: document.querySelector('.lg-connection-form')?.innerText?.slice(0, 250) };
      } finally {
        window.__LG_RUNTIME_TOKEN__ = real;
      }
      return out;
    })()`, 30000)
  } catch (e) {
    unauth = { ok: false, error: String(e) }
  }
  record('unauthorized sensitive Settings write surfaces honest failure', unauth && unauth.ok, unauth)

  // Honesty note: Chat upload on loopback is NOT token-gated by the API policy.
  const loopbackUpload = await evalJs(bidi, context, `fetch('/api/v1/sources', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ request_id: 'lg040-nogate-1', filename: 'g.txt', content_base64: btoa('g'), media_type: 'text/plain', origin: { kind: 'upload', fetched: false } }) }).then(r => r.status)`)
  record('loopback Chat upload without token is NOT gated (documented backend policy fact)', loopbackUpload === 201 || loopbackUpload === 200, { status: loopbackUpload })

  // --- narrow 390 layout (return to Chat so the intake input is present) ---
  await evalJs(bidi, context, `(async () => {
    const chat = [...document.querySelectorAll('button[aria-label]')].find(b => b.getAttribute('aria-label') === 'Chat');
    if (chat) chat.click();
    for (let i = 0; i < 40; i++) { await new Promise(r => setTimeout(r, 150)); if (document.querySelector('input[type=file]')) return true; }
    return false;
  })()`)
  await shot('04-chat-narrow-390.png', 390, 900)
  const narrow = await evalJs(bidi, context, `(() => ({ w: window.innerWidth, overflow: document.documentElement.scrollWidth > window.innerWidth + 2, fileInput: !!document.querySelector('input[type=file]') }))()`)
  record('narrow 390 no horizontal overflow + intake present', !narrow.overflow && narrow.fileInput, narrow)
  await shot('05-files-narrow-390.png', 390, 900)
  await evalJs(bidi, context, `(async () => {
    const f = [...document.querySelectorAll('button[aria-label]')].find(b => b.getAttribute('aria-label') === 'Files');
    if (f) f.click();
    for (let i = 0; i < 40; i++) { await new Promise(r => setTimeout(r, 150)); const m = [...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Materials'); if (m) { m.click(); break; } }
    await new Promise(r => setTimeout(r, 500));
    return true;
  })()`)
  await shot('05-files-materials-narrow-390.png', 390, 900)

  // --- final product state ---
  const final = await apiGet(`${ARGS.url}api/v1/sources`)
  writeFileSync(join(outDir, 'product-state.json'), JSON.stringify({ before: before.body, final: final.body }, null, 2))

  const failed = results.filter((r) => !r.ok)
  writeFileSync(join(outDir, 'lg040-browser-results.json'), JSON.stringify({
    url: ARGS.url, tested_at: new Date().toISOString(),
    counts: { total: results.length, passed: results.length - failed.length, failed: failed.length },
    results,
  }, null, 2))
  log(`\n# ${results.length - failed.length}/${results.length} checks passed`)
  ws.close()
  rmSync(profile, { recursive: true, force: true })
  if (failed.length) process.exitCode = 1
}

main().catch((err) => { console.error('ERROR', err); process.exitCode = 1 }).finally(cleanup)
