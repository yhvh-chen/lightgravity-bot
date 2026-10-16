#!/usr/bin/env node
/**
 * lg040-settled-discriminate.mjs — LG-040 SETTLED-QA-20261016 discriminator.
 *
 * SINGLE bounded run. Settles the ONE remaining question: is the narrow-390
 * Files/Materials ".lg-chat-rail present + docScrollWidth 428" a genuine
 * product responsive bug or a measurement/ordering artifact?
 *
 * It reproduces the EXACT prior sequence (Chat at 390 -> click Files -> click
 * Materials) and, at EVERY sample, records the product's OWN responsive state
 * (`matchMedia('(max-width:1023px)').matches` = the value useIsCompact() derives
 * `compact` from) alongside the rail presence. If `compact` is TRUE but the rail
 * is still present, that is a genuine product bug (rail not removed while compact).
 * If `compact` is FALSE, the media listener simply had not updated yet at that
 * sample (an ordering/timing fact, not a layout bug).
 *
 * Node-side sampling (page event loop left free); bounded 2000 ms; pure reads.
 * No DOM/style mutation, no hiding/clipping, no threshold change.
 */

import { spawn } from 'node:child_process'
import net from 'node:net'
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

function parseArgs(argv) {
  const out = { url: null, out: '/tmp/lg040-settled-disc', deadlineMs: 90000,
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
const MARKER = `lg040disc-${process.pid}`
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

const SAMPLE = `(() => {
  const vw = innerWidth;
  const doc = document.documentElement.scrollWidth;
  const rail = document.querySelector('.lg-chat-rail');
  const list = document.querySelector('.lg-files-materials__list-panel');
  const detail = document.querySelector('.lg-files-materials__detail-panel');
  const drawer = document.querySelector('.lg-drawer, [data-drawer]');
  return {
    vw, doc, mmCompact: matchMedia('(max-width:1023px)').matches, mmMobile: matchMedia('(max-width:699px)').matches,
    railPresent: !!rail, railW: rail ? Math.round(rail.getBoundingClientRect().width) : null,
    railRight: rail ? Math.round(rail.getBoundingClientRect().right) : null,
    listW: list ? Math.round(list.getBoundingClientRect().width) : 0,
    detailW: detail ? Math.round(detail.getBoundingClientRect().width) : 0,
    detailRendered: !!document.querySelector('.lg-files-materials__detail-panel, .lg-files-materials__facts'),
    overflow: doc > vw + 2, view: document.querySelector('.lg-app')?.getAttribute('data-view') ?? null,
    drawerPresent: !!drawer,
  };
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

  const report = { url: ARGS.url, bound_ms: ARGS.boundMs, captured_at: new Date().toISOString(), scenarios: {} }

  const setVp = (w, h) => bidi.send('browsingContext.setViewport', { context, viewport: { width: w, height: h } }).catch(() => {})

  // Reproduce the prior sequence with the EXACT same setup: load at 1440, Chat,
  // then viewport -> 390, then click Files -> Materials, sampling node-side.
  async function scenario(name, { preReload }) {
    await bidi.send('browsingContext.navigate', { context, url: ARGS.url, wait: 'complete' }, 25000)
    await sleep(1500)
    await setVp(1440, 900); await sleep(600)
    // go Chat at desktop
    await evalJs(bidi, context, `(async () => {
      const b = [...document.querySelectorAll('button[aria-label]')].find(x => x.getAttribute('aria-label') === 'Chat');
      if (b) b.click();
      for (let i=0;i<40;i++){ await new Promise(r=>setTimeout(r,150)); if (document.querySelector('input[aria-label="Search materials"]')) return true; }
      return false;
    })()`, 20000)
    await setVp(390, 900); await sleep(600)
    if (preReload) { await bidi.send('browsingContext.reload', { context }, 25000); await sleep(2500); await setVp(390, 900); await sleep(400) }
    const before = await evalJs(bidi, context, SAMPLE, 10000)
    const t0 = Date.now()
    await evalJs(bidi, context, `(async () => {
      const f = [...document.querySelectorAll('button[aria-label]')].find(x => x.getAttribute('aria-label') === 'Files');
      if (f) f.click();
      for (let i=0;i<40;i++){ await new Promise(r=>setTimeout(r,150)); const m=[...document.querySelectorAll('button')].find(x=>x.textContent.trim()==='Materials'); if(m){m.click();break;} }
      return true;
    })()`, 25000)
    const samples = []
    let settledAt = null
    while (Date.now() - t0 < ARGS.boundMs) {
      const s = await evalJs(bidi, context, SAMPLE, 5000).catch(() => null)
      const now = Date.now() - t0
      if (!s) { await sleep(40); continue }
      samples.push({ t_ms: now, ...s })
      if (s.mmCompact && !s.railPresent && s.detailRendered && !s.overflow && settledAt == null) settledAt = now
      await sleep(40)
    }
    const final = await evalJs(bidi, context, SAMPLE, 10000)
    report.scenarios[name] = { before, settledAt, nSamples: samples.length, samples: samples.slice(-40), final }
    log(`scenario ${name}: before(mmCompact=${before.mmCompact},rail=${before.railPresent},doc=${before.doc}) settledAt=${settledAt} final(mmCompact=${final.mmCompact},rail=${final.railPresent},doc=${final.doc},listW=${final.listW},detailW=${final.detailW})`)
  }

  await scenario('A_chat390_then_Files_noReload', { preReload: false })
  await scenario('B_initial390_reload_then_Files', { preReload: true })

  writeFileSync(join(outDir, 'settled-discriminate.json'), JSON.stringify(report, null, 1))
  log('WROTE ' + join(outDir, 'settled-discriminate.json'))
  try { ws.close() } catch {}
  cleanup()
  process.exit(0)
}
main().catch((e) => { log('FATAL ' + (e && e.stack || e)); cleanup(); process.exit(1) })
