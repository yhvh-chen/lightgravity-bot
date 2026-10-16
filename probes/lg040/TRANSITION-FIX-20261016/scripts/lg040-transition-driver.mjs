#!/usr/bin/env node
/**
 * lg040-transition-driver.mjs — LG-040 TRANSITION-FIX-20261016 probe.
 *
 * Purpose: catch TRANSIENT horizontal overflow that occurs DURING a viewport
 * resize (1440 -> 390) and DURING in-viewport navigation (Chat -> Files), not
 * only after React state updates land. The earlier settled drivers waited
 * 500-2500 ms after resize, which let React's matchMedia state update remove
 * the inline chat rail before measurement, hiding the transient overflow.
 *
 * Method (single bounded run <= 90 s, DENY proxy => 0 model calls):
 *   - Boot at 1440, open Files/Materials (desktop inline rail + context).
 *   - Sample documentElement.scrollWidth every ~16 ms (rAF) for the WHOLE
 *     window while calling setViewport 390 at the start; assert that NO sample
 *     exceeds innerWidth+2 at any moment (not just at settle).
 *   - Also: at steady 390, navigate Chat -> Files and sample continuously.
 *   - Repeat with 1440 -> 390 -> 1440 -> 390.
 *   - Also steady 1024 / 1440 sanity + Chat reachability.
 *
 * Writes JSON to <out>/transition-results.json and screenshots.
 */

import { spawn } from 'node:child_process'
import net from 'node:net'
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

function parseArgs(argv) {
  const out = { url: null, out: '/tmp/lg040-transition', deadlineMs: 90000,
    firefox: process.env.FIREFOX_BIN || '/snap/bin/firefox', profileDir: null,
    boundMs: 2000 }
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
const MARKER = `lg040tr-${process.pid}`
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

// Install a sampler in the page that records overshoot samples on every rAF.
const INSTALL_SAMPLER = `(() => {
  window.__lg040tr = { running: false, samples: [], maxOvershoot: -1, maxDoc: 0,
    maxRailW: 0, start: 0, sawRailAfterResize: false };
  const tick = () => {
    const s = window.__lg040tr;
    if (!s.running) return;
    const vw = window.innerWidth;
    const doc = document.documentElement.scrollWidth;
    const rail = document.querySelector('.lg-chat-rail');
    const railW = rail ? rail.getBoundingClientRect().width : 0;
    const railDisplay = rail ? getComputedStyle(rail).display : null;
    const ctx = document.querySelector('.lg-context--inline');
    const ctxW = ctx ? ctx.getBoundingClientRect().width : 0;
    const ctxDisplay = ctx ? getComputedStyle(ctx).display : null;
    const hRes = document.querySelector('.lg-workspace > .lg-resizer');
    const hResW = hRes ? hRes.getBoundingClientRect().width : null;
    const over = doc - vw;
    if (doc > s.maxDoc) s.maxDoc = doc;
    if (over > s.maxOvershoot) s.maxOvershoot = over;
    if (railW > s.maxRailW) s.maxRailW = railW;
    if (s.samples.length < 4000) s.samples.push({ t: Math.round(performance.now()-s.start), vw, doc, over, railW: Math.round(railW), railDisplay, ctxW: Math.round(ctxW || 0), ctxDisplay, hResW: hResW == null ? null : Math.round(hResW) });
    requestAnimationFrame(tick);
  };
  window.__lg040tr.tick = tick;
  return true;
})()`

const START = `(() => { const s=window.__lg040tr; s.running=true; s.start=performance.now(); s.samples=[]; s.maxOvershoot=-1; s.maxDoc=0; s.maxRailW=0; requestAnimationFrame(s.tick); return true; })()`
const STOP = `(() => { const s=window.__lg040tr; s.running=false;
  const samples=s.samples; const over = samples.filter(x=>x.over>2);
  return { nSamples: samples.length, maxOvershoot: s.maxOvershoot, maxDoc: s.maxDoc, maxRailW: s.maxRailW,
    nOver2: over.length, firstOver: over[0]||null, lastOver: over[over.length-1]||null,
    firstSamples: samples.slice(0,6), lastSamples: samples.slice(-6) }; })()`

const gotoView = (label) => `(async () => {
  const railBtn = () => [...document.querySelectorAll('button[aria-label]')].find(b => b.getAttribute('aria-label') === '${label}')
    || [...document.querySelectorAll('button')].find(b => (b.textContent||'').trim() === '${label}');
  let b = railBtn();
  if (!b) {
    const toggle = [...document.querySelectorAll('button[aria-label]')].find(x => /navigation|drawer|menu/i.test(x.getAttribute('aria-label')||''));
    if (toggle) { toggle.click(); for (let i=0;i<20 && !b;i++){ await new Promise(r=>setTimeout(r,150)); b = railBtn(); } }
  }
  if (b) b.click();
  await new Promise(r=>setTimeout(r,400));
  return { ok: true, view: '${label}' };
})()`

// measure a view for `ms` continuously after starting sampler
async function sampleState(bidi, context, label, ms) {
  await evalJs(bidi, context, START)
  await sleep(ms)
  const r = await evalJs(bidi, context, STOP)
  return { state: label, ...r }
}

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

  const report = { url: ARGS.url, bound_ms: ARGS.boundMs, captured_at: new Date().toISOString(), states: [], transition: {} }

  log('boot warm-up at 1440, reload for clean SPA')
  await bidi.send('browsingContext.navigate', { context, url: ARGS.url, wait: 'complete' }, 25000)
  await sleep(1200)
  await setVp(1440, 900); await sleep(300)
  await bidi.send('browsingContext.reload', { context }, 25000)
  await sleep(2500)
  await evalJs(bidi, context, INSTALL_SAMPLER)

  // --- desktop steady: Chat and Files ---
  report.states.push(await sampleState(bidi, context, 'steady_1440_chat', 900))
  await evalJs(bidi, context, gotoView('Files')); await sleep(300)
  report.states.push(await sampleState(bidi, context, 'steady_1440_files', 900))
  await shot('steady-1440-files.png')

  // --- TRANSITION 1: 1440 -> 390 with continuous sampling THROUGH resize ---
  log('TRANSITION 1440->390 (continuous rAF sampling)')
  await evalJs(bidi, context, START)
  await setVp(390, 900)              // resize happens mid-sample
  await sleep(ARGS.boundMs + 1200)   // keep sampling past the 2s readiness bound
  const t1 = await evalJs(bidi, context, STOP)
  report.transition['resize_1440_to_390_files'] = t1
  await shot('transition-1440-to-390-files.png')

  // --- TRANSITION 2: at 390, navigate Chat -> Files with continuous sampling ---
  log('TRANSITION nav at 390 Chat->Files (continuous rAF sampling)')
  await evalJs(bidi, context, gotoView('Chat')); await sleep(500)
  await evalJs(bidi, context, START)
  await evalJs(bidi, context, gotoView('Files'))
  await sleep(1500)
  const t2 = await evalJs(bidi, context, STOP)
  report.transition['nav_390_chat_to_files'] = t2
  await shot('transition-nav-390-chat-to-files.png')

  // --- TRANSITION 3: 390 -> 1440 -> 390 round trip continuous ---
  log('TRANSITION round trip 390->1440->390 (continuous rAF sampling)')
  await evalJs(bidi, context, START)
  await setVp(1440, 900); await sleep(900)
  await setVp(390, 900); await sleep(ARGS.boundMs + 1200)
  const t3 = await evalJs(bidi, context, STOP)
  report.transition['roundtrip_390_1440_390_files'] = t3
  await shot('transition-roundtrip-390-1440-390-files.png')

  // --- TRANSITION 4: exact settled-QA case-17 path (boot 1440, resize to 390
  //     WITHOUT reload, then click Chat->Files->Materials) sampled for the full
  //     bound so a sustained rail-present overflow would be caught. ---
  log('TRANSITION settled-case17 path (1440 boot -> 390 -> Files/Materials)')
  await setVp(1440, 900); await sleep(600)
  await evalJs(bidi, context, gotoView('Chat')); await sleep(400)
  await setVp(390, 900)                       // resize without reload (React compact lags)
  await evalJs(bidi, context, START)          // start sampling BEFORE nav
  await evalJs(bidi, context, gotoView('Files'))
  // click Materials if present, like the settled driver
  await evalJs(bidi, context, `(async () => {
    for (let i=0;i<40;i++){ await new Promise(r=>setTimeout(r,150)); const m=[...document.querySelectorAll('button')].find(b=>b.textContent.trim()==='Materials'); if(m){m.click();break;} }
    return true; })()`)
  await sleep(ARGS.boundMs + 800)
  const t4 = await evalJs(bidi, context, STOP)
  report.transition['case17_1440_to_390_files'] = t4
  await shot('transition-case17-390-files.png')

  // --- steady 390 / 1024 / 1440 ---
  report.states.push(await sampleState(bidi, context, 'steady_390_files', 700))
  await setVp(1024, 900); await sleep(500)
  report.states.push(await sampleState(bidi, context, 'steady_1024_files', 700))
  await shot('steady-1024-files.png')
  await setVp(1440, 900); await sleep(500)
  report.states.push(await sampleState(bidi, context, 'steady_1440_files_again', 700))

  // final geometry snapshot at 390 (sanity that layout settled)
  await setVp(390, 900); await sleep(ARGS.boundMs)
  report.final390 = await evalJs(bidi, context, `(() => {
    const vw = window.innerWidth;
    const rail = document.querySelector('.lg-chat-rail');
    const q = (s)=>{const e=document.querySelector(s); if(!e) return null; const r=e.getBoundingClientRect(); return {w:Math.round(r.width),x:Math.round(r.x)};};
    return { innerWidth: vw, docScrollWidth: document.documentElement.scrollWidth,
      bodyScrollWidth: document.body.scrollWidth,
      mmCompact: window.matchMedia('(max-width:1023px)').matches,
      chatRailPresent: !!rail, chatRailW: rail?Math.round(rail.getBoundingClientRect().width):0,
      materialsPresent: !!document.querySelector('.lg-files-materials'),
      listPanel: q('.lg-files-materials__list-panel'), detailPanel: q('.lg-files-materials__detail-panel'),
      entries: document.querySelectorAll('button.lg-files__entry').length }; })()`)
  await shot('final-390-files.png')

  const boundMs = ARGS.boundMs
  report.verdict = {
    bound_ms: boundMs,
    transition_no_overflow: Object.fromEntries(Object.entries(report.transition).map(([k,v]) => [k, v.nOver2 === 0])),
    steady_no_overflow: Object.fromEntries(report.states.map(s => [s.state, s.nOver2 === 0])),
    all_transitions_clean: Object.values(report.transition).every(v => v.nOver2 === 0),
    all_steady_clean: report.states.every(s => s.nOver2 === 0),
  }
  writeFileSync(join(outDir, 'transition-results.json'), JSON.stringify(report, null, 1))
  log('VERDICT: ' + JSON.stringify(report.verdict))
  log('WROTE ' + join(outDir, 'transition-results.json'))
  try { ws.close() } catch {}
  cleanup()
  process.exit(0)
}
main().catch((e) => { log('FATAL ' + (e && e.stack || e)); cleanup(); process.exit(1) })
