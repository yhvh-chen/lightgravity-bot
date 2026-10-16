#!/usr/bin/env node
/**
 * lg040-starvation-probe.mjs — LG-040 TRANSITION-FIX-20261016 focused probe.
 *
 * Reproduces the exact condition under which the settled QA harness observed
 * sustained narrow-390 overflow (docScrollWidth 428, .lg-chat-rail present):
 * the SPA mounted at desktop 1440 and the page's main thread is kept busy by a
 * tight Node-side evalJs polling loop, so React's matchMedia 'change' handler
 * does not get a chance to commit `compact=true` before/while the viewport is
 * shrunk to 390. Under this condition the inline rail keeps its JS width.
 *
 * The probe measures, at each poll: viewport, doc/body scrollWidth, the
 * rendered width AND computed display of `.lg-chat-rail` and
 * `.lg-context--inline`, and whether Files/Materials actually renders usable
 * panels. It asserts NO poll exceeds innerWidth+2 for the whole bound.
 *
 * Read-only. DENY proxy => 0 model calls.
 */

import { spawn } from 'node:child_process'
import net from 'node:net'
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

function parseArgs(argv) {
  const out = { url: null, out: '/tmp/lg040-starvation', deadlineMs: 90000,
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
const MARKER = `lg040st-${process.pid}`
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
async function evalJs(bidi, context, expression, timeoutMs = 8000) {
  const wrapped = `(async () => { const v = await (${expression}); return JSON.stringify(v === undefined ? null : v); })()`
  const res = await bidi.send('script.evaluate', { expression: wrapped, target: { context }, awaitPromise: true, resultOwnership: 'none' }, timeoutMs)
  if (res.type === 'exception') throw new Error(`eval exception: ${res.exceptionDetails?.text ?? JSON.stringify(res.exceptionDetails)}`)
  const raw = res.result ? res.result.value : undefined
  try { return raw == null ? raw : JSON.parse(raw) } catch { return raw }
}

const SAMPLE = `(() => {
  const vw = innerWidth;
  const limit = vw + 2;
  const rail = document.querySelector('.lg-chat-rail');
  const ctx = document.querySelector('.lg-context--inline');
  const cstyle = (e) => e ? { w: Math.round(e.getBoundingClientRect().width), x: Math.round(e.getBoundingClientRect().x), display: getComputedStyle(e).display } : null;
  const list = document.querySelector('.lg-files-materials__list-panel');
  const detail = document.querySelector('.lg-files-materials__detail-panel');
  return { vw, doc: document.documentElement.scrollWidth, body: document.body.scrollWidth,
    overflow: document.documentElement.scrollWidth > limit,
    mmCompact: matchMedia('(max-width:1023px)').matches,
    rail: cstyle(rail), ctx: cstyle(ctx),
    listW: list ? Math.round(list.getBoundingClientRect().width) : null,
    detailW: detail ? Math.round(detail.getBoundingClientRect().width) : null,
    entries: document.querySelectorAll('button.lg-files__entry').length };
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

  const report = { url: ARGS.url, bound_ms: ARGS.boundMs, captured_at: new Date().toISOString(), samples: [] }

  // Mount at desktop 1440 (React compact=false), exactly like the settled QA run.
  await bidi.send('browsingContext.navigate', { context, url: ARGS.url, wait: 'complete' }, 25000)
  await setVp(1440, 900); await sleep(1500)
  await bidi.send('browsingContext.reload', { context }, 25000)
  await setVp(1440, 900)
  await sleep(2500)
  // Navigate to Files so the inline chat rail is actually mounted at desktop
  // (the rail only renders when view !== 'chat').
  await evalJs(bidi, context, `(async () => {
    const f = [...document.querySelectorAll('button[aria-label]')].find(b => b.getAttribute('aria-label') === 'Files');
    if (f) f.click();
    await new Promise(r=>setTimeout(r,500));
    return { rail: !!document.querySelector('.lg-chat-rail') };
  })()`)
  report.mount = await evalJs(bidi, context, SAMPLE)
  log('mount@1440: ' + JSON.stringify({ vw: report.mount.vw, rail: report.mount.rail, ctx: report.mount.ctx, mm: report.mount.mmCompact }))

  // Starve the page main thread: shrink to 390 and immediately hammer evalJs
  // round-trips (each SAMPLE evaluation competes with React's commit), mirroring
  // the settled driver's Node-side polling.
  await setVp(390, 900)
  const t0 = Date.now()
  let maxDoc = 0, maxOver = -1, nOver = 0, firstOver = null, lastOver = null
  let clicked = false
  while (Date.now() - t0 < ARGS.boundMs) {
    if (!clicked) {
      clicked = true
      // Mirror the settled QA run: enter Files -> Materials at 390.
      await evalJs(bidi, context, `(async () => {
        const f = [...document.querySelectorAll('button[aria-label]')].find(b => b.getAttribute('aria-label') === 'Files');
        if (f) f.click();
        for (let i=0;i<40;i++){ await new Promise(r=>setTimeout(r,150)); const m=[...document.querySelectorAll('button')].find(b=>b.textContent.trim()==='Materials'); if(m){m.click();break;} }
        return true; })()`).catch(() => null)
    }
    const s = await evalJs(bidi, context, SAMPLE, 5000).catch(() => null)
    if (!s) { continue }
    const t = Date.now() - t0
    if (s.doc > maxDoc) maxDoc = s.doc
    if (s.doc - s.vw > maxOver) maxOver = s.doc - s.vw
    if (s.overflow) { nOver++; if (!firstOver) firstOver = { t, ...s }; lastOver = { t, ...s } }
    if (report.samples.length < 4000) report.samples.push({ t, ...s })
  }
  report.summary = { nSamples: report.samples.length, maxDoc, maxOvershoot: maxOver,
    nOverflow: nOver, firstOverflow: firstOver, lastOverflow: lastOver,
    finalSample: report.samples[report.samples.length - 1] || null }
  await shot('starvation-390-files.png')

  const fin = report.samples[report.samples.length - 1] || {}
  report.verdict = {
    no_overflow_throughout: nOver === 0,
    rail_hidden_or_absent_at_390: !fin.rail || fin.rail.display === 'none' || fin.rail.w === 0,
    materials_panels_usable: (fin.listW ?? 0) > 0 && (fin.detailW ?? 0) > 0,
  }
  writeFileSync(join(outDir, 'starvation-results.json'), JSON.stringify(report, null, 1))
  log('SUMMARY: ' + JSON.stringify(report.summary))
  log('VERDICT: ' + JSON.stringify(report.verdict))
  try { ws.close() } catch {}
  cleanup()
  process.exit(0)
}
main().catch((e) => { log('FATAL ' + (e && e.stack || e)); cleanup(); process.exit(1) })
