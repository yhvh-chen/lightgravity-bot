#!/usr/bin/env node
/**
 * Bounded Chrome loopback-HTTP probe.
 *
 * Compares navigation strategies against a minimal localhost marker server:
 *   A. Page.navigate  (the historically "hanging" call)
 *   B. Target.createTarget(url)  (what shell-check.mjs uses)
 * plus Runtime.evaluate to read the DOM marker, and a netlog capture.
 *
 * Every CDP promise is raced against a hard deadline so a hung call is
 * *reported as a hang*, not left dangling. No SSE/React/secrets involved.
 *
 * Usage:
 *   node chrome_probe.mjs <url> <label> [--strategy page_navigate|create_target|both]
 */
import { spawn } from 'node:child_process'
import { mkdtempSync, readFileSync, existsSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const URL_ARG = process.argv[2]
const LABEL = process.argv[3] ?? 'probe'
const strategyArgIndex = process.argv.indexOf('--strategy')
const STRATEGY = strategyArgIndex >= 0 ? process.argv[strategyArgIndex + 1] : 'both'
if (!URL_ARG) {
  console.error('usage: chrome_probe.mjs <url> <label> [--strategy …]')
  process.exit(2)
}

const CHROME = process.env.CHROME_BIN ?? 'google-chrome'
const HARD = 25000
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

function withTimeout(promise, ms, label) {
  let timer
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(
      () => reject(new Error(`TIMEOUT after ${ms}ms: ${label}`)),
      ms,
    )
  })
  return Promise.race([promise, timeout]).finally(() => clearTimeout(timer))
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
      HARD,
      `CDP ${method}`,
    )
  }
}

async function waitForPort(dir, timeoutMs = 15000) {
  const file = join(dir, 'DevToolsActivePort')
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    if (existsSync(file)) {
      const [port] = readFileSync(file, 'utf8').split('\n')
      if (port) return Number(port)
    }
    await sleep(100)
  }
  throw new Error('DevToolsActivePort did not appear')
}

async function main() {
  const userDataDir = mkdtempSync(join(tmpdir(), `lg-probe-${LABEL}-`))
  const netlog = join(userDataDir, 'netlog.json')
  const args = [
    '--headless=new',
    '--no-sandbox',
    '--disable-gpu',
    '--no-first-run',
    '--no-default-browser-check',
    '--disable-background-networking',
    '--disable-component-update',
    '--disable-sync',
    '--no-proxy-server',
    '--enable-logging=stderr',
    '--v=1',
    `--log-net-log=${netlog}`,
    `--user-data-dir=${userDataDir}`,
    '--remote-debugging-port=0',
    'about:blank',
  ]
  const stderrLines = []
  const chrome = spawn(CHROME, args, {
    stdio: ['ignore', 'pipe', 'pipe'],
    detached: true, // own session/group
  })
  chrome.stderr.on('data', (d) => {
    for (const l of String(d).split('\n')) if (l.trim()) stderrLines.push(l)
  })

  const out = { label: LABEL, url: URL_ARG, chrome_args: args, strategies: {} }
  try {
    const port = await waitForPort(userDataDir)
    out.devtools_port = port
    const version = await withTimeout(
      fetch(`http://127.0.0.1:${port}/json/version`).then((r) => r.json()),
      5000,
      'GET /json/version',
    )
    out.browser = version.Browser

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
    const targetUrl = URL_ARG

    const readMarker = async (sessionId) => {
      try {
        const r = await cdp.send(
          'Runtime.evaluate',
          {
            expression:
              "({url:location.href, marker:(document.getElementById('lg-marker')||{}).textContent||null, ready:document.readyState, title:document.title})",
            returnByValue: true,
          },
          sessionId,
        )
        return r.result.value
      } catch (e) {
        return { error: String(e.message) }
      }
    }

    if (STRATEGY === 'page_navigate' || STRATEGY === 'both') {
      const t0 = Date.now()
      const { targetId } = await cdp.send('Target.createTarget', {
        url: 'about:blank',
      })
      const { sessionId } = await cdp.send('Target.attachToTarget', {
        targetId,
        flatten: true,
      })
      await cdp.send('Page.enable', {}, sessionId)
      await cdp.send('Runtime.enable', {}, sessionId)
      let navResult = null
      let navError = null
      const navStart = Date.now()
      try {
        navResult = await cdp.send('Page.navigate', { url: targetUrl }, sessionId)
      } catch (e) {
        navError = String(e.message)
      }
      const navMs = Date.now() - navStart
      const dom = await readMarker(sessionId)
      out.strategies.page_navigate = {
        nav_return_ms: navMs,
        nav_result: navResult,
        nav_error: navError,
        dom_after_navigate: dom,
        total_ms: Date.now() - t0,
      }
      await cdp.send('Target.closeTarget', { targetId }).catch(() => {})
    }

    if (STRATEGY === 'create_target' || STRATEGY === 'both') {
      const t0 = Date.now()
      let created = null
      let err = null
      try {
        created = await cdp.send('Target.createTarget', { url: targetUrl })
      } catch (e) {
        err = String(e.message)
      }
      const createMs = Date.now() - t0
      let dom = null
      if (created) {
        const { sessionId } = await cdp.send('Target.attachToTarget', {
          targetId: created.targetId,
          flatten: true,
        })
        await cdp.send('Page.enable', {}, sessionId).catch(() => {})
        await cdp.send('Runtime.enable', {}, sessionId).catch(() => {})
        // poll for marker up to 3s
        const deadline = Date.now() + 3000
        while (Date.now() < deadline) {
          dom = await readMarker(sessionId)
          if (dom && dom.marker) break
          await sleep(150)
        }
        out.strategies.create_target = {
          create_return_ms: createMs,
          create_result: created,
          dom_after_create: dom,
          total_ms: Date.now() - t0,
        }
        await cdp.send('Target.closeTarget', { targetId: created.targetId }).catch(() => {})
      } else {
        out.strategies.create_target = {
          create_return_ms: createMs,
          create_error: err,
          total_ms: Date.now() - t0,
        }
      }
    }

    try {
      ws.close()
    } catch {}
  } catch (e) {
    out.fatal_error = String(e.message)
  } finally {
    try {
      process.kill(-chrome.pid, 'SIGKILL')
    } catch {}
    try {
      chrome.kill('SIGKILL')
    } catch {}
    await sleep(300)
    try {
      rmSync(userDataDir, { recursive: true, force: true })
    } catch {}
  }

  out.chrome_stderr_tail = stderrLines.slice(-25)
  console.log(JSON.stringify(out, null, 2))
  if (out.fatal_error || Object.values(out.strategies).some((s) => s.nav_error)) {
    process.exitCode = 1
  }
}

main()
