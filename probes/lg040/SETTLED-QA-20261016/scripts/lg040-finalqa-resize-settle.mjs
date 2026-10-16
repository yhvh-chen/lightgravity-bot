#!/usr/bin/env node
/**
 * lg040-finalqa-resize-settle.mjs — LG-040 FINAL-QA independent residual probe.
 *
 * Single bounded run (<= 90 s) that settles the LAST open question: does the
 * candidate frontend's Files/Materials view actually produce a *view content*
 * horizontal overflow at 390 CSS px, and is the previously-observed
 * retest-driver FAIL (.lg-chat-rail present, docScrollWidth 428) a genuine
 * product overflow or a matchMedia/React-not-yet-compact measurement race?
 *
 * It compares, against the SAME freshly built candidate bundle:
 *   A) INITIAL 390  : page first loaded while viewport is already 390
 *                     (compact from first render) -> Files/Materials.
 *   B) 1440->390    : page first used at desktop 1440, then shrunk to 390
 *                     WITHOUT reload (matchMedia change must fire) -> Files/Materials,
 *                     measured both IMMEDIATELY (retest timing) and AFTER settle.
 *
 * For each state it records doc/body scrollWidth, innerWidth, matchMedia
 * compact/mobile, presence + width of .lg-chat-rail, full offender list with
 * computed styles (min-width, display, overflow-x, grid-template-columns),
 * whether the Files/Materials list + detail panels are non-zero, and a
 * screenshot. Read-only; DENY proxy => 0 model calls.
 */

import { spawn } from 'node:child_process'
import net from 'node:net'
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

function parseArgs(argv) {
  const out = { url: null, out: '/tmp/lg040-resize-settle', deadlineMs: 90000,
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
const MARKER = `lg040rs-${process.pid}`
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

// Full overflow probe with offenders + computed styles + panel geometry.
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
        display: cs.display, overflowX: cs.overflowX, gridTemplateColumns: cs.gridTemplateColumns });
    }
  }
  const q = (s) => { const e = document.querySelector(s); if (!e) return null; const r = e.getBoundingClientRect();
    return { x: Math.round(r.x), right: Math.round(r.right), width: Math.round(r.width), height: Math.round(r.height) }; };
  const rail = document.querySelector('.lg-chat-rail');
  return {
    innerWidth: vw, docScrollWidth: document.documentElement.scrollWidth,
    bodyScrollWidth: document.body.scrollWidth, overflow: document.documentElement.scrollWidth > limit,
    mmCompact: window.matchMedia('(max-width:1023px)').matches,
    mmMobile: window.matchMedia('(max-width:699px)').matches,
    chatRailPresent: !!rail, chatRail: rail ? q('.lg-chat-rail') : null,
    materialsPresent: !!document.querySelector('.lg-files-materials'),
    entries: document.querySelectorAll('button.lg-files__entry').length,
    listPanel: q('.lg-files-materials__list-panel'),
    detailPanel: q('.lg-files-materials__detail-panel'),
    nOffenders: offenders.length, offenders: offenders.slice(0, 50),
  };
})()`

const gotoFilesMaterials = `(async () => {
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

  const setVp = (w, h) => bidi.send('browsingContext.setViewport', { context, viewport: { width: w, height: h } }).catch(() => {})
  const shot = async (name) => { const png = await bidi.send('browsingContext.captureScreenshot', { context })
    writeFileSync(join(outDir, name), Buffer.from(png.data, 'base64')) }
  const report = { url: ARGS.url, captured_at: new Date().toISOString() }

  // ---- A) INITIAL 390: load once, then set 390 and RELOAD so the SPA -
  //        boots fresh with compact already true (a genuine initial-390).
  //        (Firefox BiDi ignores setViewport on about:blank before the first
  //        navigation, so a pre-navigation set is a no-op; reload is required.)
  log('STAGE A: navigate warm-up, set 390, RELOAD (true initial-390)')
  await bidi.send('browsingContext.navigate', { context, url: ARGS.url, wait: 'complete' }, 25000)
  await sleep(1500)
  await setVp(390, 900); await sleep(400)
  await bidi.send('browsingContext.reload', { context }, 25000)
  await sleep(2500)
  report.initial390_vpCheck = await evalJs(bidi, context, `(() => ({ innerWidth: window.innerWidth, mmCompact: window.matchMedia('(max-width:1023px)').matches }))()`)
  log('initial390 viewport check: ' + JSON.stringify(report.initial390_vpCheck))
  report.initial390_beforeFiles = await evalJs(bidi, context, OVERFLOW, 25000)
  log('initial390 before Files: ' + JSON.stringify({ overflow: report.initial390_beforeFiles.overflow, docScrollW: report.initial390_beforeFiles.docScrollWidth, mmCompact: report.initial390_beforeFiles.mmCompact, chatRail: report.initial390_beforeFiles.chatRailPresent }))
  report.initial390_goto = await evalJs(bidi, context, gotoFilesMaterials, 30000)
  await sleep(800)
  report.initial390_afterGoto = await evalJs(bidi, context, OVERFLOW, 25000)
  await shot('resize-settle-A-initial390-files.png')
  log('initial390 after Files: ' + JSON.stringify({ overflow: report.initial390_afterGoto.overflow, docScrollW: report.initial390_afterGoto.docScrollWidth, listPanel: report.initial390_afterGoto.listPanel, detailPanel: report.initial390_afterGoto.detailPanel, rail: report.initial390_afterGoto.chatRailPresent }))

  // ---- B) 1440 -> 390 (no reload), measure immediate + settled ----------
  log('STAGE B: setViewport 1440')
  await setVp(1440, 900); await sleep(800)
  report.desktop1440 = await evalJs(bidi, context, OVERFLOW, 25000)
  await shot('resize-settle-B-desktop1440-files.png')
  log('desktop1440: ' + JSON.stringify({ overflow: report.desktop1440.overflow, docScrollW: report.desktop1440.docScrollWidth, mmCompact: report.desktop1440.mmCompact, chatRail: report.desktop1440.chatRailPresent }))

  log('STAGE B: setViewport 390 WITHOUT reload (retest timing)')
  await setVp(390, 900)
  // (B1) reproduce retest-driver timing: re-click Files/Materials, wait only
  // 500 ms, measure immediately.
  await evalJs(bidi, context, `(async () => {
    const f = [...document.querySelectorAll('button[aria-label]')].find(b => b.getAttribute('aria-label') === 'Files');
    if (f) f.click();
    for (let i = 0; i < 40; i++) { await new Promise(r => setTimeout(r, 150)); const m = [...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Materials'); if (m) { m.click(); break; } }
    await new Promise(r => setTimeout(r, 500));
    return true;
  })()`, 30000)
  report.resize1440to390_retestTiming = await evalJs(bidi, context, OVERFLOW, 25000)
  await shot('resize-settle-B1-resize-390-retest-timing.png')
  log('B1 retest-timing: ' + JSON.stringify({ overflow: report.resize1440to390_retestTiming.overflow, docScrollW: report.resize1440to390_retestTiming.docScrollWidth, mmCompact: report.resize1440to390_retestTiming.mmCompact, chatRail: report.resize1440to390_retestTiming.chatRailPresent, railW: report.resize1440to390_retestTiming.chatRail?.width }))

  // (B2) after settle
  await sleep(1500)
  report.resize1440to390_settled = await evalJs(bidi, context, OVERFLOW, 25000)
  await shot('resize-settle-B2-resize-390-settled.png')
  log('B2 settled: ' + JSON.stringify({ overflow: report.resize1440to390_settled.overflow, docScrollW: report.resize1440to390_settled.docScrollWidth, mmCompact: report.resize1440to390_settled.mmCompact, chatRail: report.resize1440to390_settled.chatRailPresent }))

  writeFileSync(join(outDir, 'resize-settle.json'), JSON.stringify(report, null, 1))
  log('WROTE ' + join(outDir, 'resize-settle.json'))
  try { ws.close() } catch {}
  cleanup()
  process.exit(0)
}
main().catch((e) => { log('FATAL ' + (e && e.stack || e)); cleanup(); process.exit(1) })
