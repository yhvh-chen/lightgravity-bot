#!/usr/bin/env node
/**
 * lg040-files-narrow-driver.mjs — LG-040 FILES-NARROW-FIX frontend owner probe.
 *
 * Real app (create_app, snapshot data) + real built frontend/dist + real
 * Firefox WebDriver BiDi. Reuses the BROWSER-RETEST-R1 helper pattern (owned
 * copy) and ADDS a DOM/box-level diagnosis of the narrow-390 Files Materials
 * overflow so the fix targets the actual owner element, not a guess.
 *
 * Zero model / OCR / LAN calls: the app runs against a byte-identical copy of
 * the prior real QA snapshot; OCR base URL points at a loopback DENY proxy and
 * the ledger must stay at 0 attempts. No uploads, no reprocess, no revoke here
 * (read-only UI inspection only).
 */

import { spawn } from 'node:child_process'
import net from 'node:net'
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

function parseArgs(argv) {
  const out = {
    url: null,
    out: '/tmp/lg040-files-narrow',
    deadlineMs: 120000,
    firefox: process.env.FIREFOX_BIN || '/snap/bin/firefox',
    profileDir: null,
  }
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i]
    const next = () => argv[++i]
    if (a === '--url') out.url = next()
    else if (a === '--out') out.out = next()
    else if (a === '--deadline-ms') out.deadlineMs = Number(next())
    else if (a === '--firefox') out.firefox = next()
    else if (a === '--profile-dir') out.profileDir = next()
    else throw new Error(`unknown arg: ${a}`)
  }
  if (!out.url) throw new Error('--url is required')
  if (!out.url.endsWith('/')) out.url += '/'
  return out
}

const ARGS = parseArgs(process.argv)
const log = (...m) => console.log(...m)
const MARKER = `lg040fn-${process.pid}`
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

// Overlap/overflow diagnosis: walk the live DOM, report any element whose
// right edge exceeds the viewport (scrollWidth contribution) with its boxes.
const OVERFLOW_PROBE = `(() => {
  const vw = window.innerWidth;
  const limit = vw + 2;
  const offenders = [];
  const all = document.querySelectorAll('body *');
  for (const el of all) {
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) continue;
    if (r.right > limit || el.scrollWidth > el.clientWidth + 2) {
      const cs = getComputedStyle(el);
      offenders.push({
        tag: el.tagName.toLowerCase(),
        cls: (el.className && typeof el.className === 'string') ? el.className : '',
        rect: { x: Math.round(r.x), right: Math.round(r.right), width: Math.round(r.width) },
        scrollW: el.scrollWidth, clientW: el.clientWidth,
        minWidth: cs.minWidth, gridTemplateColumns: cs.gridTemplateColumns,
        display: cs.display, overflowX: cs.overflowX,
      });
    }
  }
  return {
    innerWidth: vw,
    docScrollWidth: document.documentElement.scrollWidth,
    bodyScrollWidth: document.body.scrollWidth,
    overflow: document.documentElement.scrollWidth > limit,
    offenders: offenders.slice(0, 40),
    nOffenders: offenders.length,
  };
})()`

const BOX = (sel) => `(() => {
  const el = document.querySelector(${JSON.stringify(sel)});
  if (!el) return null;
  const r = el.getBoundingClientRect();
  const cs = getComputedStyle(el);
  return {
    sel: ${JSON.stringify(sel)},
    rect: { x: Math.round(r.x), right: Math.round(r.right), width: Math.round(r.width) },
    scrollW: el.scrollWidth, clientW: el.clientWidth,
    minWidth: cs.minWidth, gridTemplateColumns: cs.gridTemplateColumns,
    display: cs.display, flex: cs.flex, overflowX: cs.overflowX,
  };
})()`

async function main() {
  const deadline = Date.now() + ARGS.deadlineMs
  const outDir = ARGS.out
  mkdirSync(outDir, { recursive: true })
  const results = []
  const record = (name, ok, detail) => {
    results.push({ name, ok: !!ok, detail: detail === undefined ? null : detail })
    log(`${ok ? 'PASS' : 'FAIL'} ${name}${detail !== undefined ? ' :: ' + JSON.stringify(detail) : ''}`)
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
  record('real same-origin http document', origin === ARGS.url.replace(/\/$/, ''), { origin })

  const shot = async (name, width, height) => {
    await bidi.send('browsingContext.setViewport', { context, viewport: { width, height } }).catch(() => {})
    await sleep(500)
    const png = await bidi.send('browsingContext.captureScreenshot', { context })
    writeFileSync(join(outDir, name), Buffer.from(png.data, 'base64'))
  }

  const viewport = async (w, h) => {
    await bidi.send('browsingContext.setViewport', { context, viewport: { width: w, height: h } }).catch(() => {})
    await sleep(500)
  }

  // Navigate to Files → Materials with a real source selected (read-only).
  const gotoMaterials = async () => evalJs(bidi, context, `(async () => {
    const f = [...document.querySelectorAll('button[aria-label]')].find(b => b.getAttribute('aria-label') === 'Files');
    if (f) f.click();
    for (let i = 0; i < 60; i++) { await new Promise(r => setTimeout(r, 150)); const m = [...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Materials'); if (m) { m.click(); break; } }
    for (let i = 0; i < 60; i++) { await new Promise(r => setTimeout(r, 150)); const list = document.querySelector('.lg-files-materials__list'); if (list && list.querySelectorAll('button.lg-files__entry').length >= 2) return true; }
    return false;
  })()`)

  const gotoChat = async () => evalJs(bidi, context, `(async () => {
    const railBtn = () => [...document.querySelectorAll('button[aria-label]')].find(b => b.getAttribute('aria-label') === 'Chat')
      || [...document.querySelectorAll('button')].find(b => (b.textContent || '').trim() === 'Chat');
    let c = railBtn();
    if (!c) {
      // Narrow widths can hide the rail behind a drawer toggle; open it first.
      const toggle = [...document.querySelectorAll('button[aria-label]')].find(b => /navigation|drawer|menu/i.test(b.getAttribute('aria-label') || ''));
      if (toggle) { toggle.click(); for (let i = 0; i < 20 && !c; i++) { await new Promise(r => setTimeout(r, 150)); c = railBtn(); } }
    }
    if (c) c.click();
    for (let i = 0; i < 40; i++) { await new Promise(r => setTimeout(r, 150)); if (document.querySelector('input[aria-label="Search materials"]')) return true; }
    return false;
  })()`)

  // Open the PDF source (long real material) so the detail panel has content.
  const openSource = async () => evalJs(bidi, context, `(async () => {
    const entries = [...document.querySelectorAll('button.lg-files__entry')];
    const e = entries.find(el => el.textContent.includes('clear_real.pdf')) || entries[0];
    if (!e) return false;
    e.click();
    for (let i = 0; i < 60; i++) { await new Promise(r => setTimeout(r, 150)); if (document.querySelector('.lg-files-materials__facts')) return true; }
    return false;
  })()`)

  // ---------------------------------------------------------------
  // 1. DIAGNOSE narrow-390 Files Materials overflow (real DOM boxes)
  // ---------------------------------------------------------------
  record('Files Materials reachable', await gotoMaterials())

  const NARROW_VIEWS = [
    { w: 390, h: 844, tag: 'narrow-390' },
    { w: 1024, h: 900, tag: 'mid-1024' },
    { w: 1440, h: 900, tag: 'desktop-1440' },
  ]

  const diag = {}
  for (const v of NARROW_VIEWS) {
    await viewport(v.w, v.h)
    await gotoMaterials()
    await openSource()
    await sleep(400)
    const probe = await evalJs(bidi, context, OVERFLOW_PROBE)
    const boxes = {}
    for (const sel of [
      '.lg-app', '.lg-workspace', '.lg-main', '.lg-view',
      '.lg-files', '.lg-files-materials', '.lg-files-materials__body',
      '.lg-files-materials__list-panel', '.lg-files-materials__detail-panel',
      '.lg-files-materials__facts', '.lg-files-materials__actions',
      '.lg-files-materials__textarea', '.lg-files__preview-body',
    ]) {
      boxes[sel] = await evalJs(bidi, context, BOX(sel))
    }
    diag[v.tag] = { probe, boxes }
    await shot(`diag-files-materials-${v.tag}.png`, v.w, v.h)
    record(`Files Materials ${v.tag}: no horizontal overflow (doc scrollWidth <= innerWidth+2)`,
      !probe.overflow, { innerWidth: probe.innerWidth, docScrollWidth: probe.docScrollWidth, nOffenders: probe.nOffenders, offenders: probe.offenders.slice(0, 8) })
  }

  writeFileSync(join(outDir, 'dom-diagnosis.json'), JSON.stringify(diag, null, 2))

  // ---------------------------------------------------------------
  // 2. Visible English action buttons in Materials detail (all widths)
  // ---------------------------------------------------------------
  for (const v of NARROW_VIEWS) {
    await viewport(v.w, v.h)
    await gotoMaterials()
    await openSource()
    await sleep(300)
    const actions = await evalJs(bidi, context, `(() => {
      const btns = [...document.querySelectorAll('.lg-files-materials__actions button')];
      return btns.map(b => {
        const r = b.getBoundingClientRect();
        return { text: b.textContent.trim(), visible: r.width > 0 && r.height > 0,
                 inViewport: r.left >= -1 && r.right <= window.innerWidth + 2, right: Math.round(r.right) };
      });
    })()`)
    const names = actions.map((a) => a.text)
    record(`Files Materials ${v.tag}: English actions preserved and in-viewport`,
      actions.length >= 5 && actions.every((a) => a.visible && a.inViewport)
        && names.includes('Download original') && names.includes('Save correction') && names.includes('Archive') && names.includes('Reprocess (OCR)'),
      { names, actions })
  }

  // ---------------------------------------------------------------
  // 3. Long filenames / long paths do not force page overflow
  // ---------------------------------------------------------------
  await viewport(390, 844)
  await gotoMaterials()
  await openSource()
  const longName = await evalJs(bidi, context, `(() => {
    const n = document.querySelector('.lg-files__preview-name');
    const entry = document.querySelector('.lg-files__entry-name');
    const cs = n ? getComputedStyle(n) : null;
    return {
      previewName: n ? n.textContent : null,
      entryName: entry ? entry.textContent : null,
      nameEllipsis: cs ? { overflow: cs.overflow, textOverflow: cs.textOverflow, whiteSpace: cs.whiteSpace, minWidth: cs.minWidth } : null,
    };
  })()`)
  const longProbe = await evalJs(bidi, context, OVERFLOW_PROBE)
  record('long material name/path does not force page overflow at 390',
    !longProbe.overflow && !!longName.previewName, { longName, overflow: longProbe.overflow, docScrollWidth: longProbe.docScrollWidth })

  // ---------------------------------------------------------------
  // 4. Preview body own-scroll preserved (code/table can scroll internally)
  // ---------------------------------------------------------------
  await viewport(390, 844)
  await gotoMaterials()
  await openSource()
  await sleep(400)
  const scrollProbe = await evalJs(bidi, context, `(() => {
    const pb = document.querySelector('.lg-files-materials .lg-files__preview-body');
    if (!pb) return { present: false };
    const cs = getComputedStyle(pb);
    return { present: true, overflowY: cs.overflowY, overflowX: cs.overflowX,
             scrollH: pb.scrollHeight, clientH: pb.clientHeight,
             canScroll: pb.scrollHeight > pb.clientHeight || cs.overflowY === 'auto' || cs.overflowY === 'scroll' };
  })()`)
  record('Materials preview body keeps its own scroll (no page-level clipping)',
    scrollProbe.present && (scrollProbe.overflowY === 'auto' || scrollProbe.overflowY === 'scroll'),
    scrollProbe)

  // ---------------------------------------------------------------
  // 5. Chat 390 unchanged (no overflow, search present)
  // ---------------------------------------------------------------
  await viewport(390, 844)
  record('Chat reachable at 390', await gotoChat())
  await sleep(300)
  const chatProbe = await evalJs(bidi, context, OVERFLOW_PROBE)
  const chatHasSearch = await evalJs(bidi, context, `!!document.querySelector('input[aria-label="Search materials"]')`)
  await shot('verify-chat-narrow-390.png', 390, 844)
  record('Chat 390 unchanged: no horizontal overflow and search still present',
    !chatProbe.overflow && !!chatHasSearch,
    { innerWidth: chatProbe.innerWidth, docScrollWidth: chatProbe.docScrollWidth, hasSearch: chatHasSearch, nOffenders: chatProbe.nOffenders })

  // ---------------------------------------------------------------
  // 6. Desktop layout normal (multi-column two-panel grid at 1440)
  // ---------------------------------------------------------------
  await viewport(1440, 900)
  await gotoMaterials()
  await openSource()
  await sleep(300)
  const desktopGrid = await evalJs(bidi, context, `(() => {
    const body = document.querySelector('.lg-files-materials__body');
    const cs = body ? getComputedStyle(body) : null;
    const list = document.querySelector('.lg-files-materials__list-panel')?.getBoundingClientRect();
    const detail = document.querySelector('.lg-files-materials__detail-panel')?.getBoundingClientRect();
    return { gridTemplateColumns: cs ? cs.gridTemplateColumns : null,
             sideBySide: !!(list && detail && detail.x > list.x + 50),
             listW: list ? Math.round(list.width) : null, detailW: detail ? Math.round(detail.width) : null };
  })()`)
  record('desktop 1440 Materials layout is still the normal two-panel grid',
    desktopGrid.sideBySide && !!desktopGrid.gridTemplateColumns && desktopGrid.gridTemplateColumns.split(' ').length === 2,
    desktopGrid)
  await shot('verify-files-materials-desktop-1440.png', 1440, 900)

  const failed = results.filter((r) => r.ok === false)
  writeFileSync(join(outDir, 'lg040-files-narrow-results.json'), JSON.stringify({
    url: ARGS.url, tested_at: new Date().toISOString(),
    counts: { total: results.length, passed: results.length - failed.length, failed: failed.length },
    results,
  }, null, 2))
  log(`\n# ${results.length - failed.length}/${results.length} passed, ${failed.length} failed`)
  ws.close()
  rmSync(profile, { recursive: true, force: true })
  if (failed.length) process.exitCode = 1
}

main().catch((err) => { console.error('ERROR', err); process.exitCode = 1 }).finally(cleanup)
