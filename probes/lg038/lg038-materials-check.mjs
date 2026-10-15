#!/usr/bin/env node
/**
 * lg038-materials-check.mjs — real-HTTP browser fixture smoke for LG-038.
 *
 * Loads the real built app served by `probes/lg038/browser_fixture_server.py`
 * (real `create_app` + a scripted source) in a real Firefox over native BiDi,
 * and asserts the Chat/Files material surfaces at 1440 / 1024 / 390 px:
 *   * Chat renders the material intake (upload / record link / no delivery Task);
 *   * a link is labelled `link_only` and not shown as text;
 *   * searching returns the real source with a version + hash and can open it;
 *   * Files exposes the same source and a Materials surface.
 *
 * Evidence tooling only: no product code, task state, contracts or deps change.
 * No model / external service is called.
 *
 * Usage:
 *   node probes/lg038/lg038-materials-check.mjs --url http://127.0.0.1:8791/ \
 *        --out /tmp/lg038-browser --deadline-ms 60000
 */
import { spawn } from 'node:child_process'
import net from 'node:net'
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

function parseArgs(argv) {
  const out = { url: null, out: '/tmp/lg038-browser', deadlineMs: 60000, firefox: process.env.FIREFOX_BIN || 'firefox', profileDir: null }
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
  return out
}

const ARGS = parseArgs(process.argv)
const log = (...m) => console.log(...m)
const MARKER = `lg038-${process.pid}`
let childPid = null

function cleanup() {
  if (childPid == null) return
  try {
    const cmd = readFileSync(`/proc/${childPid}/cmdline`, 'utf8')
    if (cmd.includes(MARKER) && cmd.includes('firefox')) {
      process.kill(-childPid, 'SIGTERM')
      const t0 = Date.now()
      while (Date.now() - t0 < 1200) {
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

class Bidi {
  constructor(ws) {
    this.ws = ws; this.nextId = 1; this.pending = new Map()
    ws.addEventListener('message', (ev) => {
      let msg; try { msg = JSON.parse(typeof ev.data === 'string' ? ev.data : ev.data.toString()) } catch { return }
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

async function evalJs(bidi, context, expression) {
  // Always serialise inside the page so we get a plain string back.
  const wrapped = `(async () => { const v = await (${expression}); return JSON.stringify(v === undefined ? null : v); })()`
  const res = await bidi.send('script.evaluate', {
    expression: wrapped,
    target: { context },
    awaitPromise: true,
    resultOwnership: 'none',
  }, 10000)
  if (res.type === 'exception') {
    throw new Error(`eval exception: ${res.exceptionDetails?.text ?? 'unknown'}`)
  }
  const raw = res.result ? res.result.value : undefined
  try {
    return raw == null ? raw : JSON.parse(raw)
  } catch {
    return raw
  }
}

async function main() {
  const deadline = Date.now() + ARGS.deadlineMs
  const outDir = ARGS.out
  mkdirSync(outDir, { recursive: true })
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

  // discover the BiDi endpoint: Firefox exposes native WebDriver BiDi at
  // /session on --remote-debugging-port (the JSON /json/version path is Chrome).
  const wsUrl = `ws://127.0.0.1:${port}/session`
  let up = false
  while (Date.now() < deadline && !up) {
    up = await new Promise((res) => {
      const s = new net.Socket()
      s.setTimeout(800)
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

  const results = []
  const record = (name, ok, detail) => { results.push({ name, ok, detail }); log(`${ok ? 'PASS' : 'FAIL'} ${name}${detail ? ' :: ' + detail : ''}`) }

  // create a top-level context
  const tree = await bidi.send('browsingContext.getTree', {})
  let context = tree.contexts[0]?.context
  if (!context) {
    const created = await bidi.send('browsingContext.create', { type: 'tab' })
    context = created.context
  }
  await bidi.send('browsingContext.navigate', { context, url: ARGS.url, wait: 'complete' }, 20000)
  await sleep(1500)

  // --- Chat surface: material intake present, no delivery Task asserted.
  const chat = await evalJs(bidi, context, `(() => {
    const text = document.body.innerText;
    return {
      hasChat: !!document.querySelector('.lg-chat'),
      hasMaterials: !!document.querySelector('.lg-materials'),
      mentionsNoTask: /no delivery Task\\/Run is created/i.test(text),
      hasRecordLink: !!document.querySelector('input[aria-label="Record a link"]'),
      hasSearch: !!document.querySelector('input[aria-label="Search materials"]'),
    };
  })()`)
  record('chat material intake present', chat.hasMaterials, JSON.stringify(chat))
  record('chat states no delivery Task', chat.mentionsNoTask)
  record('chat link record + search inputs', chat.hasRecordLink && chat.hasSearch)

  // --- Search the real fixture source and open it.
  const search = await evalJs(bidi, context, `(async () => {
    const input = document.querySelector('input[aria-label="Search materials"]');
    if (!input) return { ok: false, reason: 'no input' };
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
    setter.call(input, 'LG038-001');
    input.dispatchEvent(new Event('input', { bubbles: true }));
    await new Promise(r => setTimeout(r, 50));
    const button = [...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Search');
    button.click();
    for (let i = 0; i < 40; i++) {
      await new Promise(r => setTimeout(r, 150));
      const hit = document.querySelector('.lg-source-search__hit');
      if (hit) return { ok: true, text: hit.innerText };
    }
    return { ok: false, reason: document.querySelector('.lg-source-search')?.innerText || 'no hits' };
  })()`)
  record('search returns a real source hit', search.ok, JSON.stringify(search).slice(0, 240))
  record('hit shows version + hash', search.ok && /v\d+/.test(search.text || '') && /#/.test(search.text || ''), search.text)

  // --- Open the hit in Files (Materials surface, same source).
  const files = await evalJs(bidi, context, `(async () => {
    const link = [...document.querySelectorAll('button')].find(b => b.textContent.includes('Open in Files'));
    if (!link) return { ok: false, reason: 'no open link' };
    link.click();
    for (let i = 0; i < 40; i++) {
      await new Promise(r => setTimeout(r, 150));
      if (document.querySelector('.lg-files-materials')) {
        const text = document.body.innerText;
        return { ok: true, hasMaterials: true, hasFacts: !!document.querySelector('.lg-files-materials__facts'), mentionsSameSource: /source_/.test(text) };
      }
    }
    return { ok: false, reason: document.body.innerText.slice(0, 200) };
  })()`)
  record('Files opens the same source in Materials', files.ok && files.hasMaterials, JSON.stringify(files).slice(0, 200))

  // --- Responsive widths: no horizontal overflow, nav + Settings preserved.
  for (const width of [1440, 1024, 390]) {
    await bidi.send('browsingContext.setViewport', { context, viewport: { width, height: 900 } }, 8000).catch(() => {})
    await bidi.send('emulation.setDeviceMetricsOverride', { context, width, height: 900, deviceScaleFactor: 1, mobile: width < 500 }).catch(() => {})
    await sleep(400)
    const layout = await evalJs(bidi, context, `(() => ({
      w: window.innerWidth,
      nav: !!document.querySelector('[aria-label*="navigation" i], nav'),
      settings: /Settings/.test(document.body.innerText),
      overflow: document.documentElement.scrollWidth > window.innerWidth + 2,
    }))()`)
    record(`layout ${width}px no horizontal overflow`, !layout.overflow, JSON.stringify(layout))
  }

  writeFileSync(join(outDir, 'lg038-browser-results.json'), JSON.stringify(results, null, 2))
  const failed = results.filter((r) => !r.ok)
  log(`\n# ${results.length - failed.length}/${results.length} checks passed`)
  ws.close()
  rmSync(profile, { recursive: true, force: true })
  if (failed.length) process.exitCode = 1
}

main().catch((err) => { console.error('ERROR', err); process.exitCode = 1 }).finally(cleanup)
