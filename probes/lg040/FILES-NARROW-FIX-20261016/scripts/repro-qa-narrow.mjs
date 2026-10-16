#!/usr/bin/env node
/**
 * repro-qa-narrow.mjs — reproduce the EXACT QA narrow sequence and dump the
 * overflow offenders at the moment of measurement. Temporary diagnosis script.
 *
 * Sequence copied from BROWSER-RETEST-R1 driver section H:
 *  1. go to Chat, setViewport 390, measure chat.
 *  2. go to Files, click Materials, sleep 500, measure documentElement.scrollWidth.
 * Prints offenders + computed styles for the transcript.
 */
import { spawn } from 'node:child_process'
import net from 'node:net'
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const url = (process.argv[2] || '').endsWith('/') ? process.argv[2] : (process.argv[2] || '') + '/'
const outDir = process.argv[3] || '/tmp/lg040-fn-repro'
const firefox = process.env.FIREFOX_BIN || '/snap/bin/firefox'
const MARKER = `lg040repro-${process.pid}`
let childPid = null
function cleanup() {
  if (childPid == null) return
  try {
    const cmd = readFileSync(`/proc/${childPid}/cmdline`, 'utf8')
    if (cmd.includes(MARKER) && cmd.includes('firefox')) {
      process.kill(-childPid, 'SIGTERM')
      const t0 = Date.now()
      while (Date.now() - t0 < 1500) { try { process.kill(-childPid, 0) } catch { return } const e = Date.now() + 40; while (Date.now() < e) {} }
      process.kill(-childPid, 'SIGKILL')
    }
  } catch {}
}
process.on('exit', cleanup)
process.on('SIGTERM', () => { cleanup(); process.exit(143) })

class Bidi {
  constructor(ws) { this.ws = ws; this.nextId = 1; this.pending = new Map()
    ws.addEventListener('message', (ev) => { let m; try { m = JSON.parse(typeof ev.data === 'string' ? ev.data : ev.data.toString()) } catch { return }
      if (m.id !== undefined && this.pending.has(m.id)) { const { resolve, reject } = this.pending.get(m.id); this.pending.delete(m.id)
        if (m.type === 'error') reject(new Error(`${m.error}: ${m.message}`)); else resolve(m.result) } }) }
  send(method, params = {}, timeoutMs = 8000) { const id = this.nextId++
    return new Promise((resolve, reject) => { const t = setTimeout(() => { this.pending.delete(id); reject(new Error('timeout ' + method)) }, timeoutMs)
      this.pending.set(id, { resolve: (r) => { clearTimeout(t); resolve(r) }, reject: (e) => { clearTimeout(t); reject(e) } }); this.ws.send(JSON.stringify({ id, method, params })) }) }
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
async function evalJs(bidi, context, expression, timeoutMs = 15000) {
  const wrapped = `(async () => { const v = await (${expression}); return JSON.stringify(v === undefined ? null : v); })()`
  const res = await bidi.send('script.evaluate', { expression: wrapped, target: { context }, awaitPromise: true, resultOwnership: 'none' }, timeoutMs)
  if (res.type === 'exception') throw new Error('exception: ' + (res.exceptionDetails?.text || JSON.stringify(res.exceptionDetails)))
  const raw = res.result ? res.result.value : undefined
  try { return raw == null ? raw : JSON.parse(raw) } catch { return raw }
}

async function main() {
  mkdirSync(outDir, { recursive: true })
  const profileRoot = join(process.env.HOME || tmpdir(), 'snap', 'firefox', 'current')
  mkdirSync(profileRoot, { recursive: true })
  const profile = mkdtempSync(join(profileRoot, `${MARKER}-`))
  const port = await new Promise((res) => { const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)) }) })
  const child = spawn(firefox, ['--headless', '--no-remote', `--profile=${profile}`, `--remote-debugging-port=${port}`, '--no-first-run', 'about:blank'], { detached: true, stdio: ['ignore', 'ignore', 'ignore'] })
  childPid = child.pid
  const deadline = Date.now() + 90000
  let up = false
  while (Date.now() < deadline && !up) {
    up = await new Promise((res) => { const s = new net.Socket(); s.setTimeout(800); s.once('connect', () => { s.destroy(); res(true) }); s.once('timeout', () => { s.destroy(); res(false) }); s.once('error', () => res(false)); s.connect(port, '127.0.0.1') })
    if (!up) await sleep(300)
  }
  let ws = null
  for (let attempt = 0; attempt < 40 && !ws; attempt++) {
    ws = await new Promise((resolve) => { const w = new WebSocket(`ws://127.0.0.1:${port}/session`); const t = setTimeout(() => { try { w.close() } catch {} ; resolve(null) }, 3000); w.addEventListener('open', () => { clearTimeout(t); resolve(w) }); w.addEventListener('error', () => { clearTimeout(t); resolve(null) }) })
    if (!ws) await sleep(400)
  }
  if (!ws) throw new Error('ws never connected')
  const bidi = new Bidi(ws)
  await bidi.send('session.new', { capabilities: { alwaysMatch: {} } }, 8000)
  const tree = await bidi.send('browsingContext.getTree', {})
  const context = tree.contexts[0]?.context
  await bidi.send('browsingContext.navigate', { context, url, wait: 'complete' }, 25000)
  await sleep(2000)

  const MEASURE = `(() => {
    const vw = window.innerWidth; const limit = vw + 2;
    const off = [];
    for (const el of document.querySelectorAll('body *')) {
      const r = el.getBoundingClientRect();
      if (r.width === 0 && r.height === 0) continue;
      if (r.right > limit) {
        const cs = getComputedStyle(el);
        off.push({ tag: el.tagName.toLowerCase(), cls: typeof el.className === 'string' ? el.className : '',
          x: Math.round(r.x), right: Math.round(r.right), width: Math.round(r.width),
          minWidth: cs.minWidth, grid: cs.gridTemplateColumns, display: cs.display, position: cs.position, overflowX: cs.overflowX });
      }
    }
    const body = document.querySelector('.lg-files-materials__body');
    const cs = body ? getComputedStyle(body) : null;
    return { vw, docScrollW: document.documentElement.scrollWidth, bodyScrollW: document.body.scrollWidth,
      overflow: document.documentElement.scrollWidth > limit, offenders: off.slice(0, 25), n: off.length,
      materialsGrid: cs ? cs.gridTemplateColumns : null,
      activeView: document.querySelector('.lg-view')?.firstElementChild?.className || null };
  })()`

  const result = {}
  // Step 1: Chat 390 (as QA did)
  await evalJs(bidi, context, `(async () => { const c=[...document.querySelectorAll('button[aria-label]')].find(b=>b.getAttribute('aria-label')==='Chat'); if(c)c.click(); for(let i=0;i<40;i++){await new Promise(r=>setTimeout(r,150)); if(document.querySelector('input[aria-label="Search materials"]')) return true;} return false; })()`)
  await bidi.send('browsingContext.setViewport', { context, viewport: { width: 390, height: 900 } }).catch(() => {})
  await sleep(500)
  result.chat390 = await evalJs(bidi, context, MEASURE)

  // Step 2: Files -> Materials at 390, measure immediately (QA order)
  await evalJs(bidi, context, `(async () => { const f=[...document.querySelectorAll('button[aria-label]')].find(b=>b.getAttribute('aria-label')==='Files'); if(f)f.click(); for(let i=0;i<40;i++){await new Promise(r=>setTimeout(r,150)); const m=[...document.querySelectorAll('button')].find(b=>b.textContent.trim()==='Materials'); if(m){m.click();break;}} await new Promise(r=>setTimeout(r,500)); return true; })()`)
  result.filesImmediate = await evalJs(bidi, context, MEASURE)

  // Step 3: wait longer and re-measure (does it settle?)
  await sleep(2000)
  result.filesSettled = await evalJs(bidi, context, MEASURE)

  // Step 4: force a reflow/re-resize and re-measure
  await bidi.send('browsingContext.setViewport', { context, viewport: { width: 391, height: 900 } }).catch(() => {})
  await sleep(300)
  await bidi.send('browsingContext.setViewport', { context, viewport: { width: 390, height: 900 } }).catch(() => {})
  await sleep(800)
  result.filesAfterResize = await evalJs(bidi, context, MEASURE)

  writeFileSync(join(outDir, 'repro.json'), JSON.stringify(result, null, 2))
  console.log(JSON.stringify(result, null, 2))
  ws.close()
  rmSync(profile, { recursive: true, force: true })
  cleanup()
}
main().catch((e) => { console.error('ERROR', e); cleanup(); process.exit(1) })
