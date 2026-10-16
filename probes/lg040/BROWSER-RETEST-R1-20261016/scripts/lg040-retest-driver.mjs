#!/usr/bin/env node
/**
 * lg040-retest-driver.mjs — LG-040 BROWSER RETEST R1 (fresh independent recheck).
 *
 * Focus: close the TWO prior UNVERIFIED search cases with a CORRECTED term taken
 * from an ACTUAL trusted body, plus a SINGLE true end-of-run state capture.
 *
 * Hard constraints honoured here:
 *  - 0 new uploads, 0 live OCR / reprocess, 0 model calls. The app is launched
 *    against the SNAPSHOT COPY of the prior live data dir, so the two real
 *    sources + the real OCR'd bodies + the real lexical index already exist.
 *  - The revoke fix is exercised LOCALLY on this owner's copy only.
 *  - The end-state is captured ONCE, after all browser actions.
 *
 * Real app (create_app) + real built frontend/dist + real Firefox WebDriver BiDi.
 * No mocks, no interception, no file:// E2E.
 */

import { spawn } from 'node:child_process'
import net from 'node:net'
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

function parseArgs(argv) {
  const out = {
    url: null,
    out: '/tmp/lg040-browser-retest',
    deadlineMs: 120000,
    firefox: process.env.FIREFOX_BIN || '/snap/bin/firefox',
    profileDir: null,
    uiTerm: 'correction',
    apiTerm: 'marker',
  }
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i]
    const next = () => argv[++i]
    if (a === '--url') out.url = next()
    else if (a === '--out') out.out = next()
    else if (a === '--deadline-ms') out.deadlineMs = Number(next())
    else if (a === '--firefox') out.firefox = next()
    else if (a === '--profile-dir') out.profileDir = next()
    else if (a === '--ui-term') out.uiTerm = next()
    else if (a === '--api-term') out.apiTerm = next()
    else throw new Error(`unknown arg: ${a}`)
  }
  if (!out.url) throw new Error('--url is required')
  if (!out.url.endsWith('/')) out.url += '/'
  return out
}

const ARGS = parseArgs(process.argv)
const log = (...m) => console.log(...m)
const MARKER = `lg040ret-${process.pid}`
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
    this.ws = ws; this.nextId = 1; this.pending = new Map()
    ws.addEventListener('message', (ev) => {
      let msg
      try { msg = JSON.parse(typeof ev.data === 'string' ? ev.data : ev.data.toString()) } catch { return }
      if (msg.id !== undefined && this.pending.has(msg.id)) {
        const { resolve, reject } = this.pending.get(msg.id); this.pending.delete(msg.id)
        if (msg.type === 'error') reject(new Error(`${msg.error}: ${msg.message}`)); else resolve(msg.result)
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

async function apiPost(url, payload) {
  const r = await fetch(url, {
    method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(payload),
  })
  const text = await r.text()
  let body = null
  try { body = JSON.parse(text) } catch { body = text.slice(0, 400) }
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
  const unverified = (name, detail) => {
    results.push({ name, ok: null, detail: detail === undefined ? null : detail })
    log(`UNVERIFIED ${name}${detail !== undefined ? ' :: ' + JSON.stringify(detail) : ''}`)
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

  const shot = async (name, width, height) => {
    await bidi.send('browsingContext.setViewport', { context, viewport: { width, height } }).catch(() => {})
    await sleep(500)
    const png = await bidi.send('browsingContext.captureScreenshot', { context })
    writeFileSync(join(outDir, name), Buffer.from(png.data, 'base64'))
    return png.data.length
  }

  // ------------------------------------------------------------------
  // A. Snapshot identity: the two real sources exist with real hashes.
  // ------------------------------------------------------------------
  await bidi.send('browsingContext.setViewport', { context, viewport: { width: 1440, height: 900 } }).catch(() => {})
  const sources = await apiGet(`${ARGS.url}api/v1/sources`)
  const items = sources.body?.items ?? []
  // The frozen prior-run snapshot contains THREE real sources: the two OCR'd
  // fixtures (clear_real.pdf, honest_table_grid_scale4.png) plus a 1-byte
  // `g.txt` upload ('received', not indexed) created during the prior run.
  // Assert on that REAL set (not a wrong 'exactly 2' assumption).
  const titles = items.map((s) => s.title).sort()
  const expectedTitles = ['clear_real.pdf', 'g.txt', 'honest_table_grid_scale4.png']
  record('snapshot exposes the real prior-run sources (clear_real.pdf, honest_table_grid_scale4.png, g.txt)',
    sources.status === 200 && JSON.stringify(titles) === JSON.stringify(expectedTitles),
    { status: sources.status, n: items.length, titles })

  const srcPdf = items.find((s) => (s.title || '').includes('clear_real.pdf'))?.id
    ?? 'source_01M51N3TJT5QQGYGNB92V5C7MH'
  const srcPng = items.find((s) => (s.title || '').includes('honest_table_grid'))?.id
    ?? 'source_01M51N3TRHB3Y5KQ5SAPSBEFRB'

  // ------------------------------------------------------------------
  // B. UI search (corrected term from ACTUAL trusted body) — prior UNVERIFIED #1
  // ------------------------------------------------------------------
  const goChat = await evalJs(bidi, context, `(async () => {
    const btn = [...document.querySelectorAll('button[aria-label]')].find(b => b.getAttribute('aria-label') === 'Chat');
    if (btn) btn.click();
    for (let i = 0; i < 40; i++) { await new Promise(r => setTimeout(r, 150)); if (document.querySelector('input[aria-label="Search materials"]')) return true; }
    return false;
  })()`)
  record('Chat search input available', goChat)

  const search = await evalJs(bidi, context, `(async () => {
    const input = document.querySelector('input[aria-label="Search materials"]');
    if (!input) return { ok: false, reason: 'no input' };
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
    setter.call(input, ${JSON.stringify(ARGS.uiTerm)});
    input.dispatchEvent(new Event('input', { bubbles: true }));
    await new Promise(r => setTimeout(r, 60));
    const button = [...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Search');
    button.click();
    for (let i = 0; i < 80; i++) {
      await new Promise(r => setTimeout(r, 150));
      const hit = document.querySelector('.lg-source-search__hit');
      if (hit) {
        const open = hit.querySelector('button.lg-link-button');
        return {
          ok: true, text: hit.innerText,
          source_id: (hit.innerText.match(/source_[A-Za-z0-9]+/) || [null])[0],
          hasVersion: /v\\d+/.test(hit.innerText),
          hasHash: /#[0-9a-f]{6,}/.test(hit.innerText),
          hasOpen: !!open,
          basis: (hit.innerText.match(/basis:\\s*(\\w+)/) || [null, null])[1],
          snippet: hit.querySelector('.lg-source-search__snippet')?.innerText ?? null,
        };
      }
      const err = document.querySelector('.lg-source-search [role=alert]');
      if (err) return { ok: false, error: err.innerText };
      const empty = document.querySelector('.lg-source-search .lg-empty, .lg-source-search');
      if (empty && /No matching material/i.test(empty.innerText)) return { ok: false, empty: empty.innerText };
    }
    return { ok: false, reason: document.querySelector('.lg-source-search')?.innerText || 'no hits' };
  })()`, 25000)
  record(
    `UI search "${ARGS.uiTerm}" returns expected source + v + hash back-reference`,
    search.ok && search.source_id === srcPdf && search.hasVersion && search.hasHash && search.hasOpen,
    search,
  )
  await shot('01-chat-search-desktop-1440.png', 1440, 900)

  // ------------------------------------------------------------------
  // C. rebuild_if_missing hash back-check — prior UNVERIFIED #2
  // ------------------------------------------------------------------
  const rebuild = await apiGet(`${ARGS.url}api/v1/search?q=${encodeURIComponent(ARGS.apiTerm)}&include_global=true&rebuild_if_missing=true&limit=10`)
  const hits = rebuild.body?.hits ?? []
  record(
    `search rebuild_if_missing "${ARGS.apiTerm}" returns hit with hash back-check`,
    rebuild.status === 200 && hits.length >= 1 &&
      hits.every((h) => h.source_id && h.content_hash !== undefined) &&
      hits.some((h) => h.source_id === srcPdf),
    { status: rebuild.status, n: hits.length, first: hits[0] ?? null },
  )

  // ------------------------------------------------------------------
  // D. Empty / error truthfulness for a genuinely absent term.
  // ------------------------------------------------------------------
  const emptyRes = await apiGet(`${ARGS.url}api/v1/search?q=zzzz_no_such_token_zzzz&include_global=true&rebuild_if_missing=true&limit=10`)
  record(
    'search for absent term is an honest empty result (index ok, 0 hits)',
    emptyRes.status === 200 && Array.isArray(emptyRes.body?.hits) && emptyRes.body.hits.length === 0 && emptyRes.body?.index_status === 'ok',
    { status: emptyRes.status, hits: emptyRes.body?.hits?.length, index_status: emptyRes.body?.index_status },
  )

  // ------------------------------------------------------------------
  // E. Files preview + download of real (non-revoked) source = real data
  // ------------------------------------------------------------------
  const goFiles = await evalJs(bidi, context, `(async () => {
    const btn = [...document.querySelectorAll('button[aria-label]')].find(b => b.getAttribute('aria-label') === 'Files');
    if (btn) btn.click();
    for (let i = 0; i < 60; i++) { await new Promise(r => setTimeout(r, 150)); const t = [...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Materials'); if (t) { t.click(); break; } }
    for (let i = 0; i < 60; i++) {
      await new Promise(r => setTimeout(r, 150));
      const list = document.querySelector('.lg-files-materials__list');
      if (list && list.querySelectorAll('button.lg-files__entry').length >= 2) return true;
    }
    return false;
  })()`)
  record('Files Materials lists the real snapshot sources', goFiles)

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
  record(
    'Files preview opens real source with English actions (preview/download/reprocess)',
    openPdf.ok && openPdf.actions?.includes('Download original'),
    openPdf,
  )
  await shot('02-files-materials-desktop-1440.png', 1440, 900)

  const realDownload = await evalJs(bidi, context, `(async () => {
    const btn = [...document.querySelectorAll('.lg-files-materials__actions button')].find(b => b.textContent.trim() === 'Download original');
    if (!btn) return { ok: false, reason: 'missing' };
    btn.click();
    for (let i = 0; i < 50; i++) {
      await new Promise(r => setTimeout(r, 150));
      const s = document.querySelector('.lg-files__status');
      if (s && /Downloaded /.test(s.innerText)) return { ok: true, status: s.innerText };
    }
    return { ok: false, reason: 'no downloaded status' };
  })()`)
  record('non-revoked source download via UI returns real data', realDownload.ok, realDownload)

  // ------------------------------------------------------------------
  // F. LOCAL revoke on OWN copy only → preview/download must fail honestly (fix)
  // ------------------------------------------------------------------
  const revokeResp = await apiPost(`${ARGS.url}api/v1/sources/${srcPng}/actions`, { action: 'revoke', confirmed: true })
  record('revoke action on OWN copy accepted', revokeResp.status === 200, { status: revokeResp.status, body: revokeResp.body })

  const afterRevoke = await apiGet(`${ARGS.url}api/v1/sources/${srcPng}`)
  const svPng = afterRevoke.body?.source ?? afterRevoke.body
  record('revoked source status is archived (honest, reversible flag preserved)',
    afterRevoke.status === 200 && svPng?.status === 'archived',
    { status: svPng?.status, archived: svPng?.archived, index: svPng?.index })

  // The fix: content_view / download_view must fail closed with 404 not_found + details.revoked.
  const contentAfter = await apiGet(`${ARGS.url}api/v1/sources/${srcPng}/content?kind=machine`)
  const downloadAfter = await apiGet(`${ARGS.url}api/v1/sources/${srcPng}/download?kind=original`)
  record(
    'revoked source preview (content) fails honestly: 404 not_found + details.revoked',
    contentAfter.status === 404 && contentAfter.body?.error?.code === 'not_found' && contentAfter.body?.error?.details?.revoked === true,
    { status: contentAfter.status, error: contentAfter.body?.error },
  )
  record(
    'revoked source download fails honestly: 404 not_found + details.revoked',
    downloadAfter.status === 404 && downloadAfter.body?.error?.code === 'not_found' && downloadAfter.body?.error?.details?.revoked === true,
    { status: downloadAfter.status, error: downloadAfter.body?.error },
  )

  // Raw file bytes preserved on disk (never written by us: verified read-only by the runner).
  // The other (non-revoked) source archive/open must still work.
  const otherOpen = await apiGet(`${ARGS.url}api/v1/sources/${srcPdf}/content?kind=machine`)
  record('other non-revoked source preview still functional after revoke',
    otherOpen.status === 200, { status: otherOpen.status })

  // UI: revoked source still selectable but its preview/download must be honest (no fake body)
  const uiRevoked = await evalJs(bidi, context, `(async () => {
    const entries = [...document.querySelectorAll('button.lg-files__entry')];
    const e = entries.find(el => el.textContent.includes('honest_table_grid_scale4.png'));
    if (e) e.click();
    for (let i = 0; i < 60; i++) { await new Promise(r => setTimeout(r, 150)); if (document.querySelector('.lg-files-materials__facts')) break; }
    await new Promise(r => setTimeout(r, 400));
    const status = document.querySelector('.lg-files__status')?.innerText ?? '';
    const bodyText = document.querySelector('.lg-files-materials')?.innerText ?? '';
    const errState = document.querySelector('.lg-files-materials [role=alert], .lg-state--error')?.innerText ?? null;
    return { status, errState, hasNoFakeBody: !/Base quantity/.test(bodyText), snippet: bodyText.slice(0, 300) };
  })()`)
  record(
    'UI does not render a fake revoked body (no leaked table content)',
    uiRevoked.hasNoFakeBody,
    uiRevoked,
  )
  await shot('03-files-revoked-desktop-1440.png', 1440, 900)

  // ------------------------------------------------------------------
  // G. Cross-view scope: default source scope (global/inbox) preserved.
  // ------------------------------------------------------------------
  const svAfter = await apiGet(`${ARGS.url}api/v1/sources`)
  const globalScope = (svAfter.body?.items ?? []).every((s) => s.scope && !s.scope.task_ref)
  record('default source scope (no task_ref, global/inbox) preserved after actions',
    svAfter.status === 200 && (svAfter.body?.items ?? []).length === 3 && globalScope,
    { status: svAfter.status, n: svAfter.body?.items?.length })

  // ------------------------------------------------------------------
  // H. Narrow 390 layout, no horizontal overflow (Chat + Files).
  // ------------------------------------------------------------------
  await evalJs(bidi, context, `(async () => {
    const chat = [...document.querySelectorAll('button[aria-label]')].find(b => b.getAttribute('aria-label') === 'Chat');
    if (chat) chat.click();
    for (let i = 0; i < 40; i++) { await new Promise(r => setTimeout(r, 150)); if (document.querySelector('input[aria-label="Search materials"]')) return true; }
    return false;
  })()`)
  await shot('04-chat-narrow-390.png', 390, 900)
  const narrowChat = await evalJs(bidi, context, `(() => ({ w: window.innerWidth, overflow: document.documentElement.scrollWidth > window.innerWidth + 2, hasSearch: !!document.querySelector('input[aria-label="Search materials"]') }))()`)
  record('narrow 390 Chat: no horizontal overflow', !narrowChat.overflow && narrowChat.hasSearch, narrowChat)

  await evalJs(bidi, context, `(async () => {
    const f = [...document.querySelectorAll('button[aria-label]')].find(b => b.getAttribute('aria-label') === 'Files');
    if (f) f.click();
    for (let i = 0; i < 40; i++) { await new Promise(r => setTimeout(r, 150)); const m = [...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Materials'); if (m) { m.click(); break; } }
    await new Promise(r => setTimeout(r, 500));
    return true;
  })()`)
  await shot('05-files-materials-narrow-390.png', 390, 900)
  const narrowFiles = await evalJs(bidi, context, `(() => ({ w: window.innerWidth, overflow: document.documentElement.scrollWidth > window.innerWidth + 2 }))()`)
  record('narrow 390 Files Materials: no horizontal overflow', !narrowFiles.overflow, narrowFiles)

  // ------------------------------------------------------------------
  // I. TRUE END-STATE capture — ONCE, after all browser actions.
  // ------------------------------------------------------------------
  await bidi.send('browsingContext.setViewport', { context, viewport: { width: 1440, height: 900 } }).catch(() => {})
  await sleep(600)
  const endList = await apiGet(`${ARGS.url}api/v1/sources`)
  const endState = {
    captured_at: new Date().toISOString(),
    note: 'single end-state, after ALL browser actions and LOCAL revoke on this owner copy',
    url: ARGS.url,
    sources: (endList.body?.items ?? []).map((s) => ({
      id: s.id, title: s.title, status: s.status, archived: s.archived ?? null,
      index: s.index ?? null, scope: s.scope ?? null,
    })),
    uiFileExplorer: await evalJs(bidi, context, `(() => {
      const entries = [...document.querySelectorAll('button.lg-files__entry')].map(b => b.innerText.replace(/\\s+/g,' ').trim());
      return { entries, status: document.querySelector('.lg-files__status')?.innerText ?? null };
    })()`),
  }
  writeFileSync(join(outDir, 'end-state.json'), JSON.stringify(endState, null, 2))
  log('end-state:', JSON.stringify(endState.sources))
  record('single end-state captured after all actions', endState.sources.length === 3, { sources: endState.sources })

  const failed = results.filter((r) => r.ok === false)
  const unv = results.filter((r) => r.ok === null)
  writeFileSync(join(outDir, 'lg040-retest-results.json'), JSON.stringify({
    url: ARGS.url, ui_term: ARGS.uiTerm, api_term: ARGS.apiTerm,
    tested_at: new Date().toISOString(),
    counts: { total: results.length, passed: results.length - failed.length - unv.length, failed: failed.length, unverified: unv.length },
    results,
  }, null, 2))
  log(`\n# ${results.length - failed.length - unv.length}/${results.length} passed, ${failed.length} failed, ${unv.length} unverified`)
  ws.close()
  rmSync(profile, { recursive: true, force: true })
  if (failed.length) process.exitCode = 1
}

main().catch((err) => { console.error('ERROR', err); process.exitCode = 1 }).finally(cleanup)
