#!/usr/bin/env node
/**
 * Bounded loopback-HTTP smoke for a *configurable* Chrome binary.
 *
 * Proves real loopback HTTP end-to-end with two independent facts:
 *   (a) server side: the marker server logged the GET (see its stderr log)
 *   (b) browser side: a page reached the marker (DOM text or fetch body)
 *
 * Two paths are exercised, because they behave very differently on this host:
 *
 *   --path nav     main-frame `Page.navigate` to http://127.0.0.1:PORT/marker
 *                  (on some builds this hangs the frame's loading state)
 *   --path fetch   load a local file:// shell page and have it `fetch()` the
 *                  loopback URL, then poll a side-effect flag. This is the
 *                  reliable path on builds where main-frame HTTP navigation
 *                  hangs. NOTE: an opaque-origin shell (data: URL) fails the
 *                  fetch CORS check *after* the response, so use file://.
 *                  Avoids awaiting a possibly-hung `Page.navigate`, and avoids
 *                  `awaitPromise` (which can hang the whole CDP session).
 *
 * Every CDP call and every wait is hard-bounded. The child Chrome runs in its
 * own session/process-group and is killed by that group only.
 *
 * Usage:
 *   node loopback_smoke.mjs --url http://127.0.0.1:PORT/marker \
 *     [--chrome <path-to-chrome>] [--path nav|fetch] \
 *     [--deadline-ms 10000] [--json]
 *
 * The binary is NOT hardcoded to a user home: pass --chrome or set CHROME_BIN.
 */
import { spawn } from 'node:child_process'
import { mkdtempSync, readFileSync, existsSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

function arg(name, def = null) {
  const i = process.argv.indexOf(`--${name}`)
  if (i < 0) return def
  const v = process.argv[i + 1]
  return v === undefined || v.startsWith('--') ? true : v
}

const TARGET = arg('url')
if (!TARGET) {
  console.error('usage: loopback_smoke.mjs --url <url> [--chrome <path>] [--path nav|fetch] [--deadline-ms 10000] [--json]')
  process.exit(2)
}
const CHROME = arg('chrome', process.env.CHROME_BIN ?? 'google-chrome')
const PATH_MODE = arg('path', 'fetch')
const DEADLINE = Number(arg('deadline-ms', 10000))
const AS_JSON = Boolean(arg('json', false))
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

const BASE = [
  '--headless=new',
  '--no-sandbox',
  '--disable-gpu',
  '--no-first-run',
  '--no-default-browser-check',
  '--disable-background-networking',
  '--disable-component-update',
  '--disable-sync',
  '--disable-extensions',
  '--no-proxy-server',
  '--remote-debugging-port=0',
]

function withTimeout(promise, ms, label) {
  let t
  const to = new Promise((_, rej) => {
    t = setTimeout(() => rej(new Error(`TIMEOUT ${ms}ms: ${label}`)), ms)
  })
  return Promise.race([promise, to]).finally(() => clearTimeout(t))
}

class Cdp {
  constructor(ws) {
    this.ws = ws
    this.next = 1
    this.pending = new Map()
    ws.addEventListener('message', (ev) => {
      const m = JSON.parse(ev.data)
      if (m.id && this.pending.has(m.id)) {
        const { resolve, reject } = this.pending.get(m.id)
        this.pending.delete(m.id)
        m.error ? reject(new Error(JSON.stringify(m.error))) : resolve(m.result)
      }
    })
  }
  send(method, params = {}, sessionId) {
    const id = this.next++
    const payload = { id, method, params }
    if (sessionId) payload.sessionId = sessionId
    return withTimeout(
      new Promise((resolve, reject) => {
        this.pending.set(id, { resolve, reject })
        this.ws.send(JSON.stringify(payload))
      }),
      DEADLINE + 3000,
      `CDP ${method}`,
    )
  }
}

async function waitForPort(dir, timeoutMs = 15000) {
  const file = join(dir, 'DevToolsActivePort')
  const end = Date.now() + timeoutMs
  while (Date.now() < end) {
    if (existsSync(file)) {
      const [p] = readFileSync(file, 'utf8').split('\n')
      if (p) return Number(p)
    }
    await sleep(100)
  }
  throw new Error('DevToolsActivePort did not appear')
}

async function main() {
  const userDataDir = mkdtempSync(join(tmpdir(), 'lg-smoke-'))
  const args = [...BASE, `--user-data-dir=${userDataDir}`, 'about:blank']
  const stderr = []
  const chrome = spawn(CHROME, args, { stdio: ['ignore', 'pipe', 'pipe'], detached: true })
  chrome.stderr.on('data', (d) => {
    for (const l of String(d).split('\n')) if (l.trim()) stderr.push(l)
  })

  const out = { path: PATH_MODE, chrome: CHROME, url: TARGET, deadline_ms: DEADLINE }
  let ws
  try {
    const port = await waitForPort(userDataDir)
    out.devtools_port = port
    const version = await withTimeout(
      fetch(`http://127.0.0.1:${port}/json/version`).then((r) => r.json()),
      5000,
      'json/version',
    )
    out.browser = version.Browser
    ws = new WebSocket(version.webSocketDebuggerUrl)
    await withTimeout(
      new Promise((res, rej) => {
        ws.addEventListener('open', res, { once: true })
        ws.addEventListener('error', rej, { once: true })
      }),
      5000,
      'ws open',
    )
    const cdp = new Cdp(ws)

    const shellFile = join(userDataDir, 'shell.html')
    if (PATH_MODE !== 'nav') writeFileSync(shellFile, '<body>SHELL</body>')
    const shell = PATH_MODE === 'nav' ? 'about:blank' : `file://${shellFile}`
    const { targetId } = await cdp.send('Target.createTarget', { url: shell })
    const { sessionId } = await cdp.send('Target.attachToTarget', { targetId, flatten: true })
    await cdp.send('Runtime.enable', {}, sessionId)

    if (PATH_MODE === 'nav') {
      await cdp.send('Page.enable', {}, sessionId)
      const started = Date.now()
      cdp.send('Page.navigate', { url: TARGET }, sessionId).catch(() => {})
      let dom = null
      while (Date.now() - started < DEADLINE) {
        dom = await cdp
          .send(
            'Runtime.evaluate',
            { expression: "(document.getElementById('lg-marker')||{}).textContent||null", returnByValue: true },
            sessionId,
          )
          .then((r) => r.result.value)
          .catch((e) => ({ error: String(e.message) }))
        if (dom === 'MARKER-OK') break
        await sleep(200)
      }
      out.navigate_ms = Date.now() - started
      out.dom = dom
      out.ok = dom === 'MARKER-OK'
    } else {
      await sleep(300) // let the file: shell commit
      const expr =
        `(()=>{window.__lg="pending";` +
        `fetch(${JSON.stringify(TARGET)}).then(async res=>{const t=await res.text();` +
        `window.__lg="ok:"+res.status+":"+(t.includes("MARKER-OK")?"MARKER-OK":"nomarker")})` +
        `.catch(e=>{window.__lg="err:"+e.message});return "started"})()`
      out.kick = await cdp
        .send('Runtime.evaluate', { expression: expr, returnByValue: true }, sessionId)
        .then((r) => r.result.value)
        .catch((e) => String(e.message))
      const started = Date.now()
      let flag = null
      while (Date.now() - started < DEADLINE) {
        flag = await cdp
          .send('Runtime.evaluate', { expression: 'window.__lg', returnByValue: true }, sessionId)
          .then((r) => r.result.value)
          .catch((e) => ({ error: String(e.message) }))
        if (typeof flag === 'string' && flag !== 'pending') break
        await sleep(200)
      }
      out.fetch_ms = Date.now() - started
      out.fetch_result = flag
      out.ok = flag === 'ok:200:MARKER-OK'
    }
    await cdp.send('Target.closeTarget', { targetId }).catch(() => {})
  } catch (e) {
    out.fatal_error = String(e.message ?? e)
  } finally {
    try { ws?.close() } catch {}
    try { process.kill(-chrome.pid, 'SIGKILL') } catch {}
    try { chrome.kill('SIGKILL') } catch {}
    await sleep(300)
    try { rmSync(userDataDir, { recursive: true, force: true }) } catch {}
  }
  out.chrome_stderr_tail = stderr.slice(-6)
  if (AS_JSON) {
    console.log(JSON.stringify(out, null, 2))
  } else {
    console.log(
      `path=${out.path} browser=${out.browser ?? '?'} ok=${out.ok} ` +
        `result=${JSON.stringify(out.fetch_result ?? out.dom)} fatal=${out.fatal_error ?? '-'}`,
    )
  }
  process.exitCode = out.ok ? 0 : 1
}

main()
