#!/usr/bin/env node
/**
 * Real-browser HTTP acceptance smoke: real API + real SSE over the loopback
 * transport that actually works on this host (LG-013/021/027 support).
 *
 * Background (see README.md): on this host every *main-frame Document*
 * navigation to http(s) is parked by Chrome before the network layer, and CDP
 * `Fetch` never receives a `requestPaused` for a Document request — so the
 * requested "intercept the main Document nav and fulfil it from a real Node
 * GET" technique cannot produce an http `frame.location.origin` here. This
 * helper therefore:
 *
 *   1. `--mode doc-int`  : *attempts* exactly that Document interception and
 *                          records the precise, falsifiable outcome (whether
 *                          Fetch.requestPaused ever fired for the Document).
 *   2. `--mode channel`  : proves real browser<->server HTTP using the working
 *                          transport: a file:// shell page that really
 *                          `fetch()`es `/api/echo` and really opens an
 *                          `EventSource` for `/sse`. Two independent facts are
 *                          checked: server-side request log and browser-side
 *                          DOM/state. This is genuine HTTP + streaming, not a
 *                          mock and not a static fake SSE response.
 *   3. `--mode bridge`   : demonstrates the *transparent proxy* transport for a
 *                          subresource: Node performs the real GET against the
 *                          server and `Fetch.fulfillRequest`s the XHR with the
 *                          real status/headers/body. Records which request was
 *                          bridged and which went through the browser natively.
 *
 * Every CDP call and every wait is hard-bounded. Chrome runs in its own
 * process group and is killed only by that group. The binary is configurable
 * (`--chrome` / `CHROME_BIN`), never hardcoded to a user home.
 *
 * Usage:
 *   node http_channel_smoke.mjs --base-url http://127.0.0.1:PORT \
 *     [--mode all|doc-int|channel|bridge] [--chrome <path>] \
 *     [--deadline-ms 10000] [--json]
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

const BASE = arg('base-url')
if (!BASE) {
  console.error('usage: http_channel_smoke.mjs --base-url http://127.0.0.1:PORT [--mode all|doc-int|channel|bridge] [--chrome <path>] [--deadline-ms 10000] [--json]')
  process.exit(2)
}
const MODE = arg('mode', 'all')
const CHROME = arg('chrome', process.env.CHROME_BIN ?? 'google-chrome')
const DEADLINE = Number(arg('deadline-ms', 10000))
const AS_JSON = Boolean(arg('json', false))
const ORIGIN = new URL(BASE).origin
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

const BASE_ARGS = [
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
    this.events = []
    ws.addEventListener('message', (ev) => {
      const m = JSON.parse(ev.data)
      if (!m.id) {
        this.events.push(m)
        return
      }
      if (this.pending.has(m.id)) {
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
  paused(sessionId) {
    return this.events.filter(
      (e) => e.method === 'Fetch.requestPaused' && (!sessionId || e.sessionId === sessionId),
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

/** Connect to a fresh Chrome and return handles for a shell page + CDP. */
async function boot() {
  const userDataDir = mkdtempSync(join(tmpdir(), 'lg-http-smoke-'))
  const args = [...BASE_ARGS, `--user-data-dir=${userDataDir}`, 'about:blank']
  const stderr = []
  const chrome = spawn(CHROME, args, { stdio: ['ignore', 'pipe', 'pipe'], detached: true })
  chrome.stderr.on('data', (d) => {
    for (const l of String(d).split('\n')) if (l.trim()) stderr.push(l)
  })
  const port = await waitForPort(userDataDir)
  const version = await withTimeout(
    fetch(`http://127.0.0.1:${port}/json/version`).then((r) => r.json()),
    5000,
    'json/version',
  )
  const ws = new WebSocket(version.webSocketDebuggerUrl)
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
  writeFileSync(shellFile, '<!doctype html><body data-lg-shell="1">SHELL</body>')
  const bootInfo = { chrome: CHROME, browser: version.Browser, userDataDir, stderr }
  const shutdown = async () => {
    try { ws.close() } catch {}
    try { process.kill(-chrome.pid, 'SIGKILL') } catch {}
    try { chrome.kill('SIGKILL') } catch {}
    await sleep(300)
    try { rmSync(userDataDir, { recursive: true, force: true }) } catch {}
  }
  return { cdp, shellFile, bootInfo, shutdown }
}

async function attachShell(cdp, url) {
  const { targetId } = await cdp.send('Target.createTarget', { url })
  const { sessionId } = await cdp.send('Target.attachToTarget', { targetId, flatten: true })
  await cdp.send('Runtime.enable', {}, sessionId)
  return { targetId, sessionId }
}

/**
 * (1) Attempt the requested Document-navigation interception and record
 * exactly what happened. Negative evidence here is a real, falsifiable fact:
 * whether `Fetch.requestPaused` fired for the Document request.
 */
async function modeDocInt() {
  const out = { mode: 'doc-int', origin: ORIGIN, doc_nav: {}, request_paused: false }
  const { cdp, shellFile, shutdown } = await boot()
  try {
    const { targetId, sessionId } = await attachShell(cdp, `file://${shellFile}`)
    await cdp.send('Page.enable', {}, sessionId)
    await cdp.send(
      'Fetch.enable',
      { patterns: [{ urlPattern: '*', resourceType: 'Document', requestStage: 'Request' }] },
      sessionId,
    )
    // Fulfil any Document pause with real content, so if the pause DID fire we
    // would actually see an http origin + body.
    cdp.ws.addEventListener('message', (ev) => {
      const m = JSON.parse(ev.data)
      if (m.method === 'Fetch.requestPaused' && m.sessionId === sessionId) {
        const body = Buffer.from('<!doctype html><div id="lg-m">FULFILLED-BY-NODE</div>').toString('base64')
        cdp
          .send(
            'Fetch.fulfillRequest',
            {
              requestId: m.params.requestId,
              responseCode: 200,
              responseHeaders: [{ name: 'content-type', value: 'text/html' }],
              body,
            },
            sessionId,
          )
          .catch(() => {})
      }
    })
    const url = `${ORIGIN}/page`
    const started = Date.now()
    let nav = null
    let navError = null
    cdp
      .send('Page.navigate', { url }, sessionId)
      .then((r) => (nav = r))
      .catch((e) => (navError = String(e.message)))
    await sleep(Math.min(DEADLINE, 6000))
    out.doc_nav = {
      url,
      nav_returned: nav,
      nav_error: navError,
      nav_ms: Date.now() - started,
      fetch_paused_for_document: cdp.paused(sessionId).length > 0,
      paused_urls: cdp.paused(sessionId).map((e) => e.params.request.url),
    }
    out.request_paused = out.doc_nav.fetch_paused_for_document
    const ev = await cdp
      .send(
        'Runtime.evaluate',
        { expression: 'JSON.stringify({origin:location.origin,m:(document.getElementById("lg-m")||{}).textContent||null})', returnByValue: true },
        sessionId,
      )
      .then((r) => r.result.value)
      .catch((e) => `EVALERR:${e.message}`)
    out.after_nav = ev
    out.verdict = out.request_paused
      ? 'document-interception-reachable'
      : 'document-interception-unreachable: Fetch.requestPaused never fired for the Document request; main-frame http nav is parked before the Fetch stage on this host'
    await cdp.send('Target.closeTarget', { targetId }).catch(() => {})
  } catch (e) {
    out.fatal_error = String(e.message ?? e)
  } finally {
    await shutdown()
  }
  return out
}

/**
 * (2) The working transport: real browser fetch + real SSE from a file:// shell.
 * Two independent facts: browser-side DOM/state and the caller's server log.
 */
async function modeChannel() {
  const out = { mode: 'channel', transport: 'file:// shell + fetch()/EventSource (real network)', origin: ORIGIN, api: {}, sse: {} }
  const { cdp, shellFile, shutdown } = await boot()
  try {
    const { targetId, sessionId } = await attachShell(cdp, `file://${shellFile}`)
    // real API
    out.api.kick = await cdp
      .send(
        'Runtime.evaluate',
        {
          expression:
            `(()=>{window.__api="pending";` +
            `fetch(${JSON.stringify(ORIGIN + '/api/echo')}).then(r=>r.text().then(t=>{window.__api="ok:"+r.status+":"+t})).catch(e=>{window.__api="err:"+e.message});return "started"})()`,
          returnByValue: true,
        },
        sessionId,
      )
      .then((r) => r.result.value)
      .catch((e) => String(e.message))
    {
      const start = Date.now()
      let flag = null
      while (Date.now() - start < DEADLINE) {
        flag = await cdp
          .send('Runtime.evaluate', { expression: 'window.__api', returnByValue: true }, sessionId)
          .then((r) => r.result.value)
          .catch((e) => `EVALERR:${e.message}`)
        if (typeof flag === 'string' && flag !== 'pending') break
        await sleep(150)
      }
      out.api.result = flag
      out.api.ok = typeof flag === 'string' && flag.startsWith('ok:200:') && flag.includes('"source":"server"')
    }
    // real SSE
    const sseExpr =
      `(()=>{window.__sse={ev:[],done:false,err:null};try{` +
      `var es=new EventSource(${JSON.stringify(ORIGIN + '/sse')});` +
      `es.addEventListener('tick',e=>window.__sse.ev.push(JSON.parse(e.data).n));` +
      `es.addEventListener('done',e=>{window.__sse.done=true;es.close()});` +
      `es.onerror=()=>{window.__sse.err='onerror'}}catch(e){window.__sse.err=e.message}` +
      `return "started"})()`
    out.sse.kick = await cdp
      .send('Runtime.evaluate', { expression: sseExpr, returnByValue: true }, sessionId)
      .then((r) => r.result.value)
      .catch((e) => String(e.message))
    {
      const start = Date.now()
      let state = null
      while (Date.now() - start < DEADLINE) {
        state = await cdp
          .send('Runtime.evaluate', { expression: 'JSON.stringify(window.__sse)', returnByValue: true }, sessionId)
          .then((r) => r.result.value)
          .catch((e) => `EVALERR:${e.message}`)
        if (state && state.includes('"done":true')) break
        await sleep(150)
      }
      out.sse.state = state
      try {
        const parsed = JSON.parse(state)
        out.sse.ok = parsed.done === true && Array.isArray(parsed.ev) && parsed.ev.length > 0
        out.sse.events_received = parsed.ev
      } catch {
        out.sse.ok = false
      }
    }
    out.ok = out.api.ok === true && out.sse.ok === true
    await cdp.send('Target.closeTarget', { targetId }).catch(() => {})
  } catch (e) {
    out.fatal_error = String(e.message ?? e)
    out.ok = false
  } finally {
    await shutdown()
  }
  return out
}

/**
 * (3) Transparent-proxy transport for a subresource: Node does the real GET and
 * Fetch.fulfillRequest carries the real status/headers/body to the XHR. This
 * proves the bridge works where the browser actually reaches the Fetch stage.
 */
async function modeBridge() {
  const out = {
    mode: 'bridge',
    note: 'subresource transparent bridge: Node GET -> Fetch.fulfillRequest (real server round trip)',
    origin: ORIGIN,
    bridged: [],
    native: [],
  }
  const { cdp, shellFile, shutdown } = await boot()
  try {
    const { targetId, sessionId } = await attachShell(cdp, `file://${shellFile}`)
    await cdp.send(
      'Fetch.enable',
      { patterns: [{ urlPattern: `${ORIGIN}/api/*`, requestStage: 'Request' }] },
      sessionId,
    )
    cdp.ws.addEventListener('message', async (ev) => {
      const m = JSON.parse(ev.data)
      if (m.method !== 'Fetch.requestPaused' || m.sessionId !== sessionId) return
      const req = m.params.request
      try {
        // real round trip to the real server
        const r = await fetch(req.url, { method: req.method })
        const buf = Buffer.from(await r.arrayBuffer())
        const headers = []
        r.headers.forEach((v, k) => {
          if (!['content-encoding', 'transfer-encoding', 'connection', 'content-length'].includes(k.toLowerCase())) {
            headers.push({ name: k, value: v })
          }
        })
        out.bridged.push({ url: req.url, resourceType: m.params.resourceType, status: r.status, bytes: buf.length })
        await cdp.send(
          'Fetch.fulfillRequest',
          { requestId: m.params.requestId, responseCode: r.status, responseHeaders: headers, body: buf.toString('base64') },
          sessionId,
        )
      } catch (e) {
        out.bridged.push({ url: req.url, error: String(e.message) })
        await cdp.send('Fetch.failRequest', { requestId: m.params.requestId, errorReason: 'Failed' }, sessionId).catch(() => {})
      }
    })
    // Kick a subresource XHR: this one is bridged by Node.
    out.kick_bridged = await cdp
      .send(
        'Runtime.evaluate',
        {
          expression:
            `(()=>{window.__b="pending";` +
            `fetch(${JSON.stringify(ORIGIN + '/api/echo')}).then(r=>r.text().then(t=>{window.__b="ok:"+r.status+":"+t})).catch(e=>{window.__b="err:"+e.message});return "started"})()`,
          returnByValue: true,
        },
        sessionId,
      )
      .then((r) => r.result.value)
      .catch((e) => String(e.message))
    {
      const start = Date.now()
      let flag = null
      while (Date.now() - start < DEADLINE) {
        flag = await cdp
          .send('Runtime.evaluate', { expression: 'window.__b', returnByValue: true }, sessionId)
          .then((r) => r.result.value)
          .catch((e) => `EVALERR:${e.message}`)
        if (typeof flag === 'string' && flag !== 'pending') break
        await sleep(150)
      }
      out.bridged_result = flag
      out.bridge_ok = typeof flag === 'string' && flag.startsWith('ok:200:') && flag.includes('"source":"server"')
    }
    // With Fetch disabled, the same XHR goes natively through the browser.
    await cdp.send('Fetch.disable', {}, sessionId).catch(() => {})
    {
      const start = Date.now()
      await cdp.send('Runtime.evaluate', { expression: 'window.__n="pending";fetch(' + JSON.stringify(ORIGIN + '/health') + ').then(r=>r.text()).then(t=>window.__n="native:"+t).catch(e=>window.__n="err:"+e.message)', returnByValue: true }, sessionId).catch(() => {})
      let flag = null
      while (Date.now() - start < DEADLINE) {
        flag = await cdp
          .send('Runtime.evaluate', { expression: 'window.__n', returnByValue: true }, sessionId)
          .then((r) => r.result.value)
          .catch((e) => `EVALERR:${e.message}`)
        if (typeof flag === 'string' && flag !== 'pending') break
        await sleep(150)
      }
      out.native_result = flag
      out.native.push({ url: `${ORIGIN}/health`, how: 'browser native (Fetch disabled)', result: flag })
    }
    out.ok = out.bridge_ok === true
    await cdp.send('Target.closeTarget', { targetId }).catch(() => {})
  } catch (e) {
    out.fatal_error = String(e.message ?? e)
    out.ok = false
  } finally {
    await shutdown()
  }
  return out
}

async function main() {
  const results = {}
  const modes = MODE === 'all' ? ['doc-int', 'channel', 'bridge'] : [MODE]
  for (const m of modes) {
    if (m === 'doc-int') results['doc-int'] = await modeDocInt()
    else if (m === 'channel') results.channel = await modeChannel()
    else if (m === 'bridge') results.bridge = await modeBridge()
    else {
      results[m] = { error: `unknown mode ${m}` }
    }
  }
  const okAll = modes.every((m) => m === 'doc-int' || results[m]?.ok === true)
  const summary = {
    base_url: BASE,
    chrome: CHROME,
    modes,
    results,
    ok: okAll,
    note:
      'doc-int records whether CDP Fetch could intercept the main Document; channel is the real-browser fetch+SSE acceptance; bridge is the subresource transparent-proxy transport.',
  }
  if (AS_JSON) {
    console.log(JSON.stringify(summary, null, 2))
  } else {
    for (const m of modes) {
      const r = results[m]
      if (m === 'doc-int') {
        console.log(`mode=doc-int fetch_paused_for_document=${r.request_paused} verdict=${r.verdict ?? r.fatal_error}`)
      } else {
        console.log(`mode=${m} ok=${r?.ok} ${m === 'channel' ? `api=${JSON.stringify(r?.api?.result)} sse=${JSON.stringify(r?.sse?.events_received)}` : `bridged=${JSON.stringify(r?.bridged)} native=${JSON.stringify(r?.native?.map((n) => n.result))}`} fatal=${r?.fatal_error ?? '-'}`)
      }
    }
  }
  process.exitCode = okAll ? 0 : 1
}

main()
