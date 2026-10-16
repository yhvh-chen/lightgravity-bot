#!/usr/bin/env node
/**
 * lg040-finalqa-overflow-diff.mjs — LG-040 FINAL-QA independent discrepancy probe.
 *
 * Purpose: resolve the observed conflict between the committed BROWSER-RETEST
 * 19-case driver (which reported narrow-390 Files Materials OVERFLOW=TRUE) and
 * the width driver (OVERFLOW=FALSE at 390). Reproduces the retest driver's
 * EXACT step-H sequence (Files -> Materials, NO source opened, 500 ms, measure)
 * and captures a full DOM offender list + screenshot, then compares against the
 * state WITH a source opened. Read-only; 0 model calls (deny proxy).
 */

import { spawn } from 'node:child_process'
import net from 'node:net'
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

function parseArgs(argv) {
  const out = { url: null, out: '/tmp/lg040-overflow-diff', deadlineMs: 90000,
    firefox: process.env.FIREFOX_BIN || '/snap/bin/firefox', profileDir: null }
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i]; const next = () => argv[++i]
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
const MARKER = `lg040od-${process.pid}`
let childPid = null
function cleanup() {
  if (childPid == null) return
  try {
    const cmd = readFileSync(`/proc/${childPid}/cmdline`, 'utf8')
    if (cmd.includes(MARKER) && cmd.includes('firefox')) {
      process.kill(-childPid, 'SIGTERM')
      const t0 = Date.now()
      while (Date.now() - t0 < 1500) { try { process.kill(-childPid, 0) } catch { return } const e = Date.now()+40; while (Date.now()<e){} }
      process.kill(-childPid, 'SIGKILL')
    }
  } catch { /* gone */ }
}
process.on('exit', cleanup)
process.on('SIGINT', () => { cleanup(); process.exit(130) })
process.on('SIGTERM', () => { cleanup(); process.exit(143) })

class Bidi {
  constructor(ws) { this.ws = ws; this.nextId = 1; this.pending = new Map()
    ws.addEventListener('message', (ev) => {
      let msg; try { msg = JSON.parse(typeof ev.data === 'string' ? ev.data : ev.data.toString()) } catch { return }
      if (msg.id !== undefined && this.pending.has(msg.id)) {
        const { resolve, reject } = this.pending.get(msg.id); this.pending.delete(msg.id)
        if (msg.type === 'error') reject(new Error(`${msg.error}: ${msg.message}`)); else resolve(msg.result)
      }})
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
  const res = await bidi.send('script.evaluate', { expression: wrapped, target: { context }, awaitPromise: true, resultOwnership: 'none' }, timeoutMs)
  if (res.type === 'exception') throw new Error(`eval exception: ${res.exceptionDetails?.text ?? JSON.stringify(res.exceptionDetails)}`)
  const raw = res.result ? res.result.value : undefined
  try { return raw == null ? raw : JSON.parse(raw) } catch { return raw }
}

const OVERFLOW = `(() => {
  const vw = window.innerWidth; const limit = vw + 2; const offenders = [];
  for (const el of document.querySelectorAll('body *')) {
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) continue;
    if (r.right > limit || el.scrollWidth > el.clientWidth + 2) {
      const cs = getComputedStyle(el);
      offenders.push({ tag: el.tagName.toLowerCase(), cls: (typeof el.className==='string'?el.className:''),
        rect: { x: Math.round(r.x), right: Math.round(r.right), width: Math.round(r.width) },
        scrollW: el.scrollWidth, clientW: el.clientWidth, minWidth: cs.minWidth,
        display: cs.display, overflowX: cs.overflowX, position: cs.position, transform: cs.transform });
    }
  }
  return { innerWidth: vw, docScrollWidth: document.documentElement.scrollWidth,
    bodyScrollWidth: document.body.scrollWidth, overflow: document.documentElement.scrollWidth > limit,
    nOffenders: offenders.length, offenders: offenders.slice(0, 50) };
})()`

async function main() {
  const deadline = Date.now() + ARGS.deadlineMs
  const outDir = ARGS.out; mkdirSync(outDir, { recursive: true })
  const profileRoot = ARGS.profileDir || tmpdir(); mkdirSync(profileRoot, { recursive: true })
  const profile = mkdtempSync(join(profileRoot, `${MARKER}-`))
  const port = await new Promise((res, rej) => { const s = net.createServer(); s.on('error', rej)
    s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)) }) })
  const child = spawn(ARGS.firefox, ['--headless','--no-remote',`--profile=${profile}`,
    `--remote-debugging-port=${port}`,'--no-first-run','about:blank'], { detached: true, stdio: ['ignore','ignore','ignore'] })
  childPid = child.pid
  const wsUrl = `ws://127.0.0.1:${port}/session`
  let up = false
  while (Date.now() < deadline && !up) {
    up = await new Promise((res) => { const s = new net.Socket(); s.setTimeout(800)
      s.once('connect', () => { s.destroy(); res(true) }); s.once('timeout', () => { s.destroy(); res(false) })
      s.once('error', () => { res(false) }); s.connect(port, '127.0.0.1') })
    if (!up) await sleep(300)
  }
  if (!up) throw new Error('firefox BiDi port never became reachable')
  const ws = await connect(wsUrl, 8000); const bidi = new Bidi(ws)
  await bidi.send('session.new', { capabilities: { alwaysMatch: {} } }, 8000)
  const tree = await bidi.send('browsingContext.getTree', {})
  let context = tree.contexts[0]?.context
  if (!context) { const c = await bidi.send('browsingContext.create', { type: 'tab' }); context = c.context }
  await bidi.send('browsingContext.navigate', { context, url: ARGS.url, wait: 'complete' }, 25000)
  await sleep(2000)
  const shot = async (name, w, h) => { await bidi.send('browsingContext.setViewport', { context, viewport: { width: w, height: h } }).catch(()=>{})
    await sleep(500); const png = await bidi.send('browsingContext.captureScreenshot', { context })
    writeFileSync(join(outDir, name), Buffer.from(png.data, 'base64')) }

  const report = {}

  // --- Phase 0: reproduce retest driver ordering — page first used at DESKTOP
  // 1440, then shrink to 390 WITHOUT a reload (tests matchMedia/React staleness).
  log('STAGE phase0 setViewport 1440')
  await bidi.send('browsingContext.setViewport', { context, viewport: { width: 1440, height: 900 } }).catch(()=>{})
  await sleep(800)
  report.media_at_1440 = await evalJs(bidi, context, `(() => ({ innerWidth: window.innerWidth, mm1023: window.matchMedia('(max-width:1023px)').matches, chatRail: !!document.querySelector('.lg-chat-rail') }))()`)

  // --- Phase 1: EXACT retest driver step-H sequence (no source opened) ---
  log('STAGE phase1 setViewport 390 (no reload)')
  await bidi.send('browsingContext.setViewport', { context, viewport: { width: 390, height: 900 } }).catch(()=>{})
  await sleep(800)
  log('STAGE phase1 click Files/Materials (proven goto)')
  const p1goto = await evalJs(bidi, context, `(async () => {
    const railBtn = () => [...document.querySelectorAll('button[aria-label]')].find(b => b.getAttribute('aria-label') === 'Files')
      || [...document.querySelectorAll('button')].find(b => (b.textContent||'').trim() === 'Files');
    let f = railBtn();
    if (!f) {
      const toggle = [...document.querySelectorAll('button[aria-label]')].find(b => /navigation|drawer|menu/i.test(b.getAttribute('aria-label')||''));
      if (toggle) { toggle.click(); for (let i=0;i<20 && !f;i++){ await new Promise(r=>setTimeout(r,150)); f = railBtn(); } }
    }
    if (f) f.click();
    for (let i = 0; i < 60; i++) { await new Promise(r => setTimeout(r, 150)); const m = [...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Materials'); if (m) { m.click(); break; } }
    for (let i = 0; i < 60; i++) { await new Promise(r => setTimeout(r, 150)); const l = document.querySelector('.lg-files-materials__list'); if (l && l.querySelectorAll('button.lg-files__entry').length >= 2) return { ok: true, entries: l.querySelectorAll('button.lg-files__entry').length }; }
    return { ok: false, hasMaterials: !!document.querySelector('.lg-files-materials') };
  })()`, 30000)
  log('phase1 goto result: ' + JSON.stringify(p1goto))
  report.phase1_goto = p1goto
  report.media_at_390 = await evalJs(bidi, context, `(() => ({ innerWidth: window.innerWidth, mm1023: window.matchMedia('(max-width:1023px)').matches, mm699: window.matchMedia('(max-width:699px)').matches, chatRail: !!document.querySelector('.lg-chat-rail'), chatRailW: document.querySelector('.lg-chat-rail')?.getBoundingClientRect().width ?? null }))()`)

  // Phase 1b: EXACT retest-driver step-H timing (click Materials when found,
  // wait only 500 ms, measure immediately) — reproduce the reported overflow.
  log('STAGE phase1b exact-retest-timing')
  try {
    await evalJs(bidi, context, `(async () => {
      const f = [...document.querySelectorAll('button[aria-label]')].find(b => b.getAttribute('aria-label') === 'Files');
      if (f) f.click();
      for (let i = 0; i < 40; i++) { await new Promise(r => setTimeout(r, 150)); const m = [...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Materials'); if (m) { m.click(); break; } }
      await new Promise(r => setTimeout(r, 500));
      return true;
    })()`, 30000)
    report.exact_timing_390 = await evalJs(bidi, context, OVERFLOW, 25000)
    report.exact_timing_390.dom = await evalJs(bidi, context, `(() => ({ materials: !!document.querySelector('.lg-files-materials'), entries: document.querySelectorAll('button.lg-files__entry').length, railVisible: (()=>{const r=document.querySelector('.lg-rail'); return !!r && getComputedStyle(r).display!=='none';})() }))()`)
    log('phase1b: ' + JSON.stringify({ overflow: report.exact_timing_390.overflow, docScrollW: report.exact_timing_390.docScrollWidth, dom: report.exact_timing_390.dom }))
  } catch (e) { report.exact_timing_error = String(e); log('phase1b error:', String(e)) }
  await sleep(500)
  log('STAGE phase1 overflow probe')
  report.exact_retest_seq_390 = await evalJs(bidi, context, OVERFLOW, 25000)
  log('STAGE phase1 dom probe')
  report.exact_retest_seq_390.dom = await evalJs(bidi, context, `(() => ({
    materialsPresent: !!document.querySelector('.lg-files-materials'),
    listPanel: !!document.querySelector('.lg-files-materials__list-panel'),
    detailPanel: !!document.querySelector('.lg-files-materials__detail-panel'),
    railVisible: !!document.querySelector('.lg-rail') && getComputedStyle(document.querySelector('.lg-rail')).display !== 'none',
    entries: document.querySelectorAll('button.lg-files__entry').length,
  }))()`)
  log('STAGE phase1 shot')
  await shot('overflow-diff-01-retest-exact-390.png', 390, 900)

  // --- Phase 2: same page but open a source (like width driver) ---
  log('STAGE phase2 open source')
  await evalJs(bidi, context, `(async () => {
    const entries = [...document.querySelectorAll('button.lg-files__entry')];
    const e = entries.find(el => el.textContent.includes('clear_real.pdf')) || entries[0];
    if (e) e.click();
    for (let i = 0; i < 60; i++) { await new Promise(r => setTimeout(r, 150)); if (document.querySelector('.lg-files-materials__facts')) break; }
    await new Promise(r => setTimeout(r, 400));
    return true;
  })()`)
  log('STAGE phase2 overflow probe')
  report.with_source_open_390 = await evalJs(bidi, context, OVERFLOW, 25000)
  await shot('overflow-diff-02-with-source-390.png', 390, 900)

  // --- Phase 3: re-measure the exact retest seq AFTER a hard reload (fresh doc) ---
  try {
    log('STAGE phase3 reload')
    await bidi.send('browsingContext.navigate', { context, url: ARGS.url, wait: 'complete' }, 25000)
    await sleep(2000)
    await bidi.send('browsingContext.setViewport', { context, viewport: { width: 390, height: 900 } }).catch(()=>{})
    await sleep(600)
    await evalJs(bidi, context, `(async () => {
      const f = [...document.querySelectorAll('button[aria-label]')].find(b => b.getAttribute('aria-label') === 'Files');
      if (f) f.click();
      for (let i = 0; i < 60; i++) { await new Promise(r => setTimeout(r, 150)); const m = [...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Materials'); if (m) { m.click(); break; } }
      for (let i = 0; i < 60; i++) { await new Promise(r => setTimeout(r, 150)); const l = document.querySelector('.lg-files-materials__list'); if (l && l.querySelectorAll('button.lg-files__entry').length >= 2) break; }
      await new Promise(r => setTimeout(r, 500));
      return true;
    })()`, 30000)
    log('STAGE phase3 overflow probe')
    report.fresh_reload_retest_seq_390 = await evalJs(bidi, context, OVERFLOW, 25000)
    await shot('overflow-diff-03-fresh-reload-390.png', 390, 900)
  } catch (e) {
    report.fresh_reload_error = String(e)
    log('phase3 error (non-fatal):', String(e))
  }

  writeFileSync(join(outDir, 'overflow-diff.json'), JSON.stringify(report, null, 2))
  log(JSON.stringify(report, null, 2))
  ws.close(); rmSync(profile, { recursive: true, force: true })
}
main().catch((err) => { console.error('ERROR', err); process.exitCode = 1 }).finally(cleanup)
