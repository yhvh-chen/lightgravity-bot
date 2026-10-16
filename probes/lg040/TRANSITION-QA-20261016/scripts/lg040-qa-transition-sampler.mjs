#!/usr/bin/env node
/**
 * lg040-qa-transition-sampler.mjs — LG-040 TRANSITION-QA-20261016 own sampler.
 *
 * Independent sampler written for this QA (NOT a new harness framework: it is a
 * bounded single driver modelled on the already-tested transition/starvation
 * drivers, reusing their BiDi helper pattern verbatim).
 *
 * Requirements verified here:
 *   1. Sample documentElement.scrollWidth EVERY rAF through a 1440->390 resize
 *      of Files/Materials and through a 390 initial-load + Chat->Files nav,
 *      asserting NO sample exceeds innerWidth+2 at ANY moment (maxOvershoot).
 *   2. Bounded (<= 2000 ms) geometry readiness after the transition with the
 *      CORRECT predicate (per QA task):
 *          ready = stable Files panels NONZERO width + action buttons VISIBLE
 *                  + rail HIDDEN (CSS display:none / zero rendered width is
 *                  VALID; DOM unmount is NOT required).
 *        If readiness is slower than 2 s the case is a FAIL (threshold NEVER
 *        relaxed).
 *   3. Steady 390 / 1024 / 1440 geometry + Chat@390 + desktop two-panel grid.
 *
 * Read-only UI inspection. Real app + real dist + real Firefox BiDi. DENY proxy.
 */

import { spawn } from 'node:child_process'
import net from 'node:net'
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

function parseArgs(argv) {
  const out = { url: null, out: '/tmp/lg040-qa-transition', deadlineMs: 90000,
    firefox: process.env.FIREFOX_BIN || '/snap/bin/firefox', profileDir: null, boundMs: 2000 }
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i]; const next = () => argv[++i]
    if (a === '--url') out.url = next()
    else if (a === '--out') out.out = next()
    else if (a === '--deadline-ms') out.deadlineMs = Number(next())
    else if (a === '--firefox') out.firefox = next()
    else if (a === '--profile-dir') out.profileDir = next()
    else if (a === '--bound-ms') out.boundMs = Number(next())
    else throw new Error(`unknown arg: ${a}`)
  }
  if (!out.url) throw new Error('--url is required')
  if (!out.url.endsWith('/')) out.url += '/'
  return out
}
const ARGS = parseArgs(process.argv)
const log = (...m) => console.log(...m)
const MARKER = `lg040qa-${process.pid}`
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
async function evalJs(bidi, context, expression, timeoutMs = 20000) {
  const wrapped = `(async () => { const v = await (${expression}); return JSON.stringify(v === undefined ? null : v); })()`
  const res = await bidi.send('script.evaluate', { expression: wrapped, target: { context }, awaitPromise: true, resultOwnership: 'none' }, timeoutMs)
  if (res.type === 'exception') throw new Error(`eval exception: ${res.exceptionDetails?.text ?? JSON.stringify(res.exceptionDetails)}`)
  const raw = res.result ? res.result.value : undefined
  try { return raw == null ? raw : JSON.parse(raw) } catch { return raw }
}

// rAF overshoot sampler (same shape as the already-tested transition driver).
const INSTALL_SAMPLER = `(() => {
  window.__lg040qa = { running: false, samples: [], maxOvershoot: -1, maxDoc: 0, start: 0 };
  const tick = () => {
    const s = window.__lg040qa;
    if (!s.running) return;
    const vw = window.innerWidth;
    const doc = document.documentElement.scrollWidth;
    const rail = document.querySelector('.lg-chat-rail');
    const railW = rail ? Math.round(rail.getBoundingClientRect().width) : 0;
    const railDisplay = rail ? getComputedStyle(rail).display : null;
    const over = doc - vw;
    if (doc > s.maxDoc) s.maxDoc = doc;
    if (over > s.maxOvershoot) s.maxOvershoot = over;
    if (s.samples.length < 4000) s.samples.push({ t: Math.round(performance.now()-s.start), vw, doc, over, railW, railDisplay });
    requestAnimationFrame(tick);
  };
  window.__lg040qa.tick = tick;
  return true;
})()`
const START = `(() => { const s=window.__lg040qa; s.running=true; s.start=performance.now(); s.samples=[]; s.maxOvershoot=-1; s.maxDoc=0; requestAnimationFrame(s.tick); return true; })()`
const STOP = `(() => { const s=window.__lg040qa; s.running=false;
  const samples=s.samples; const over = samples.filter(x=>x.over>2);
  return { nSamples: samples.length, maxOvershoot: s.maxOvershoot, maxDoc: s.maxDoc,
    nOver2: over.length, firstOver: over[0]||null, lastOver: over[over.length-1]||null }; })()`

// GEOMETRY READINESS PROBE — corrected predicate per QA task.
const READY_PROBE = `(() => {
  const vw = innerWidth;
  const rail = document.querySelector('.lg-chat-rail');
  const railW = rail ? Math.round(rail.getBoundingClientRect().width) : 0;
  const railDisplay = rail ? getComputedStyle(rail).display : null;
  const railHidden = !rail || railDisplay === 'none' || railW === 0;
  const list = document.querySelector('.lg-files-materials__list-panel');
  const detail = document.querySelector('.lg-files-materials__detail-panel');
  const listW = list ? Math.round(list.getBoundingClientRect().width) : 0;
  const detailW = detail ? Math.round(detail.getBoundingClientRect().width) : 0;
  const panelsNonzero = listW > 0 && detailW > 0;
  const actionsVisible = (() => {
    const re = /^(Download original|Revoke|Reprocess \(OCR\)|Open|Archive|Unarchive|Save correction)$/;
    const vis = [];
    for (const b of document.querySelectorAll('.lg-files-materials__actions button')) {
      const t = (b.textContent || '').trim();
      if (re.test(t)) { const r = b.getBoundingClientRect(); if (r.width > 0 && r.height > 0) vis.push(t); }
    }
    return vis;
  })();
  return { vw, doc: document.documentElement.scrollWidth, body: document.body.scrollWidth,
    overflow: document.documentElement.scrollWidth > vw + 2,
    railPresent: !!rail, railW, railDisplay, railHidden,
    listW, detailW, panelsNonzero,
    actionsVisible, actionsOk: actionsVisible.length > 0,
    geometryKey: vw + '|' + document.documentElement.scrollWidth + '|' + listW + '|' + detailW + '|' + railW };
})()`

// Bounded readiness observation: NODE-SIDE sampling so the page event loop is
// NOT starved by the observer (does not perturb the transition it measures).
async function observeReadiness(bidi, context, boundMs) {
  const t0 = Date.now()
  let stableCount = 0, lastKey = null, ready = false, readyAtMs = null
  let sawTransientOverflow = false, transientMaxScrollWidth = 0
  const samples = []
  while (Date.now() - t0 < boundMs) {
    const s = await evalJs(bidi, context, READY_PROBE, 5000).catch(() => null)
    const now = Date.now() - t0
    if (!s) { await sleep(30); continue }
    if (s.overflow) { sawTransientOverflow = true; if (s.doc > transientMaxScrollWidth) transientMaxScrollWidth = s.doc }
    if (s.geometryKey === lastKey) stableCount += 1; else { stableCount = 0; lastKey = s.geometryKey }
    samples.push({ t_ms: now, ...s, stableCount })
    const thisReady = s.vw === 390 && s.railHidden && s.panelsNonzero && s.actionsOk && stableCount >= 2
    if (thisReady && !ready) { ready = true; readyAtMs = now; break }
    await sleep(30)
  }
  const fin = samples[samples.length - 1] || {}
  return {
    boundMs, ready, readyAtMs, sawTransientOverflow, transientMaxScrollWidth,
    final: { listW: fin.listW ?? null, detailW: fin.detailW ?? null, docScrollWidth: fin.doc ?? null,
      railHidden: !!fin.railHidden, railPresent: !!fin.railPresent, railDisplay: fin.railDisplay ?? null,
      actionsVisible: fin.actionsVisible ?? [], overflow: !!fin.overflow },
    nSamples: samples.length, samples: samples.slice(-40),
  }
}

const gotoView = (label) => `(async () => {
  const railBtn = () => [...document.querySelectorAll('button[aria-label]')].find(b => b.getAttribute('aria-label') === '${label}')
    || [...document.querySelectorAll('button')].find(b => (b.textContent||'').trim() === '${label}');
  let b = railBtn();
  if (!b) { const toggle = [...document.querySelectorAll('button[aria-label]')].find(x => /navigation|drawer|menu/i.test(x.getAttribute('aria-label')||'')); if (toggle) { toggle.click(); for (let i=0;i<20 && !b;i++){ await new Promise(r=>setTimeout(r,150)); b = railBtn(); } } }
  if (b) b.click();
  await new Promise(r=>setTimeout(r,400));
  return { ok: true, view: '${label}' };
})()`
const clickMaterials = `(async () => {
  for (let i=0;i<40;i++){ await new Promise(r=>setTimeout(r,150)); const m=[...document.querySelectorAll('button')].find(b=>b.textContent.trim()==='Materials'); if(m){m.click(); return true;} }
  return false; })()`
const selectEntry = `(async () => {
  for (let i=0;i<40;i++){ await new Promise(r=>setTimeout(r,150)); const e=document.querySelector('button.lg-files__entry'); if(e){e.click(); return true;} }
  return false; })()`

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

  const report = { url: ARGS.url, bound_ms: ARGS.boundMs, captured_at: new Date().toISOString(), cases: {} }

  // boot at desktop 1440, open Files/Materials (inline rail mounted)
  await bidi.send('browsingContext.navigate', { context, url: ARGS.url, wait: 'complete' }, 25000)
  await setVp(1440, 900); await sleep(1500)
  await bidi.send('browsingContext.reload', { context }, 25000)
  await setVp(1440, 900); await sleep(2500)
  await evalJs(bidi, context, INSTALL_SAMPLER)
  await evalJs(bidi, context, gotoView('Files')); await sleep(400)
  await evalJs(bidi, context, clickMaterials); await sleep(400)
  await evalJs(bidi, context, selectEntry); await sleep(400)
  report.desktop_boot = await evalJs(bidi, context, `(() => ({ vw: innerWidth, doc: document.documentElement.scrollWidth, rail: !!document.querySelector('.lg-chat-rail') }))()`)

  // CASE A: resize 1440 -> 390 with continuous rAF sampling + bounded readiness
  await evalJs(bidi, context, START)
  await setVp(390, 900)
  await sleep(ARGS.boundMs + 1200)
  report.cases.resize_1440_to_390 = { sampling: await evalJs(bidi, context, STOP) }

  // CASE B: reload at INITIAL 390 (compact from first paint) + nav Chat->Files
  await setVp(390, 900); await sleep(300)
  await bidi.send('browsingContext.reload', { context }, 25000); await sleep(2000)
  await evalJs(bidi, context, INSTALL_SAMPLER)
  await evalJs(bidi, context, gotoView('Chat')); await sleep(400)
  await evalJs(bidi, context, START)
  await evalJs(bidi, context, gotoView('Files'))
  await evalJs(bidi, context, clickMaterials)
  await evalJs(bidi, context, selectEntry)
  // bounded readiness observation (correct predicate, clock starts now)
  report.cases.initial_390 = await observeReadiness(bidi, context, ARGS.boundMs)
  await sleep(500)
  report.cases.initial_390_chat_to_files = { sampling: await evalJs(bidi, context, STOP) }

  // steady geometry at 390 / 1024 / 1440
  const steady = async (w) => {
    await setVp(w, 900); await sleep(700)
    return evalJs(bidi, context, `(() => {
      const grid = document.querySelector('.lg-files-materials__body');
      const cs = grid ? getComputedStyle(grid) : null;
      const list = document.querySelector('.lg-files-materials__list-panel');
      const detail = document.querySelector('.lg-files-materials__detail-panel');
      const rail = document.querySelector('.lg-chat-rail');
      return { vw: innerWidth, doc: document.documentElement.scrollWidth, body: document.body.scrollWidth,
        overflow: document.documentElement.scrollWidth > innerWidth + 2,
        listW: list ? Math.round(list.getBoundingClientRect().width) : null,
        detailW: detail ? Math.round(detail.getBoundingClientRect().width) : null,
        railPresent: !!rail, railW: rail ? Math.round(rail.getBoundingClientRect().width) : 0,
        gridTemplateColumns: cs ? cs.gridTemplateColumns : null,
        entries: document.querySelectorAll('button.lg-files__entry').length }; })()`)
  }
  report.steady_390 = await steady(390)
  report.steady_1024 = await steady(1024)
  report.steady_1440 = await steady(1440)

  // Chat reachable at 390
  await setVp(390, 900); await sleep(500)
  await evalJs(bidi, context, gotoView('Chat')); await sleep(500)
  report.chat_390 = await evalJs(bidi, context, `(() => ({ vw: innerWidth, doc: document.documentElement.scrollWidth, overflow: document.documentElement.scrollWidth > innerWidth + 2, hasSearch: !!document.querySelector('input[aria-label="Search materials"]') }))()`)

  const r = report.cases.resize_1440_to_390.sampling
  const b = report.cases.initial_390_chat_to_files.sampling
  report.verdict = {
    bound_ms: ARGS.boundMs,
    resize_no_overshoot: r.nOver2 === 0,
    initial390_nav_no_overshoot: b.nOver2 === 0,
    steady_no_overflow: [report.steady_390, report.steady_1024, report.steady_1440].every(s => !s.overflow),
    steady390_panels_nonzero: report.steady_390.listW > 0 && report.steady_390.detailW > 0,
    desktop_two_panel: report.steady_1440.gridTemplateColumns,
    readiness_ready_within_2s: report.cases.initial_390.ready,
    readiness_readyAtMs: report.cases.initial_390.readyAtMs,
    chat390_no_overflow: !report.chat_390.overflow && report.chat_390.hasSearch,
  }
  writeFileSync(join(outDir, 'qa-transition-sampler.json'), JSON.stringify(report, null, 1))
  log('VERDICT: ' + JSON.stringify(report.verdict))
  log('WROTE ' + join(outDir, 'qa-transition-sampler.json'))
  try { ws.close() } catch {}
  cleanup()
  process.exit(0)
}
main().catch((e) => { log('FATAL ' + (e && e.stack || e)); cleanup(); process.exit(1) })
