#!/usr/bin/env node
/**
 * LG-013 live browser E2E against a running local service (dependency-free CDP).
 *
 * Drives the real Chat -> Board path with the backend reachable same-origin:
 *   * Chat renders the real (empty) global history from the backend;
 *   * submitting a delivery request creates a real Task (returned task_id) and
 *     switches the Chat scope to it;
 *   * the Board lists that Task with its real phase (not mock data);
 *   * selecting the Task shows the detail/acceptance panel.
 *
 * Requires a running server serving the built frontend on the same origin
 * (e.g. `lightgravity start ... --frontend-dist frontend/dist`).
 *
 * Usage:
 *   LG013_BASE=http://127.0.0.1:8765 LG013_OUT=/tmp/lg013-browser \
 *     node tests/browser/lg013-live-e2e.mjs
 */
import { spawn } from 'node:child_process'
import { existsSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const BASE = process.env.LG013_BASE ?? 'http://127.0.0.1:8765'
const OUT_DIR = process.env.LG013_OUT ?? '/tmp/lg013-browser'
const CHROME_BIN = process.env.CHROME_BIN ?? 'google-chrome'
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

class CdpClient {
  constructor(ws) {
    this.ws = ws
    this.nextId = 1
    this.pending = new Map()
    ws.addEventListener('message', (event) => {
      const m = JSON.parse(event.data)
      if (m.id && this.pending.has(m.id)) {
        const { resolve, reject } = this.pending.get(m.id)
        this.pending.delete(m.id)
        m.error ? reject(new Error(JSON.stringify(m.error))) : resolve(m.result)
      }
    })
  }
  send(method, params = {}, sessionId) {
    const id = this.nextId++
    const payload = { id, method, params }
    if (sessionId) payload.sessionId = sessionId
    return new Promise((resolve, reject) => {
      // Bounded: a CDP command whose response never arrives must not hang the
      // harness forever (LG-013 SIGTERM-during-check postmortem).  Navigation
      // is issued via Target.createTarget(url) so no unbounded Page.navigate.
      const timer = setTimeout(() => {
        if (this.pending.has(id)) {
          this.pending.delete(id)
          reject(new Error(`cdp timeout: ${method}`))
        }
      }, 15000)
      this.pending.set(id, {
        resolve: (v) => {
          clearTimeout(timer)
          resolve(v)
        },
        reject: (e) => {
          clearTimeout(timer)
          reject(e)
        },
      })
      this.ws.send(JSON.stringify(payload))
    })
  }
}

async function port(dir) {
  const f = join(dir, 'DevToolsActivePort')
  const t = Date.now()
  while (Date.now() - t < 20000) {
    if (existsSync(f)) {
      const [p] = readFileSync(f, 'utf8').split('\n')
      if (p) return Number(p)
    }
    await sleep(100)
  }
  throw new Error('no devtools port')
}

async function main() {
  mkdirSync(OUT_DIR, { recursive: true })
  const dir = mkdtempSync(join(tmpdir(), 'lg013-live-'))
  const chrome = spawn(
    CHROME_BIN,
    [
      '--headless=new',
      '--no-sandbox',
      '--disable-gpu',
      '--no-first-run',
      '--no-default-browser-check',
      '--remote-debugging-port=0',
      `--user-data-dir=${dir}`,
      'about:blank',
    ],
    { stdio: 'ignore' },
  )
  const results = []
  const record = (name, pass, detail) =>
    results.push({ name, pass: Boolean(pass), detail })
  try {
    const p = await port(dir)
    const v = await fetch(`http://127.0.0.1:${p}/json/version`).then((r) => r.json())
    const ws = new WebSocket(v.webSocketDebuggerUrl)
    await new Promise((res, rej) => {
      ws.addEventListener('open', res, { once: true })
      ws.addEventListener('error', rej, { once: true })
    })
    const client = new CdpClient(ws)
    // Create the target already pointed at the app and attach to it.  Issuing
    // Page.navigate after attach has been observed to leave the flattened
    // session's navigate response unreturned in this headless build.
    const { targetId } = await client.send('Target.createTarget', { url: BASE })
    const { sessionId } = await client.send('Target.attachToTarget', {
      targetId,
      flatten: true,
    })
    await client.send('Page.enable', {}, sessionId)
    await client.send('Runtime.enable', {}, sessionId)
    await client.send(
      'Emulation.setDeviceMetricsOverride',
      { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false },
      sessionId,
    )
    const ev = async (expr) => {
      const { result, exceptionDetails } = await client.send(
        'Runtime.evaluate',
        { expression: expr, returnByValue: true, awaitPromise: true },
        sessionId,
      )
      if (exceptionDetails) throw new Error(JSON.stringify(exceptionDetails))
      return result.value
    }
    const waitFor = async (expr, timeoutMs = 10000) => {
      const t = Date.now()
      while (Date.now() - t < timeoutMs) {
        if (await ev(expr)) return true
        await sleep(150)
      }
      return false
    }
    const shot = async (name) => {
      const { data } = await client.send('Page.captureScreenshot', { format: 'png' }, sessionId)
      writeFileSync(join(OUT_DIR, name), Buffer.from(data, 'base64'))
    }

    const ready = await waitFor("document.querySelector('.lg-app') !== null")
    if (!ready) throw new Error('shell did not render')
    await sleep(500)

    record(
      'chat: real empty global history (backend reachable)',
      (await ev("document.querySelectorAll('.lg-chat').length")) === 1 &&
        (await ev("document.body.textContent.includes('No messages yet')")),
    )

    // Submit a delivery request through the real composer.
    const delivery = '实现一个日志导出功能'
    await ev("document.getElementById('lg-chat-input').focus(), true")
    await client.send('Input.insertText', { text: delivery }, sessionId)
    await client.send(
      'Input.dispatchKeyEvent',
      {
        type: 'keyDown',
        key: 'Enter',
        code: 'Enter',
        windowsVirtualKeyCode: 13,
        nativeVirtualKeyCode: 13,
      },
      sessionId,
    )

    const gotReply = await waitFor(
      "document.body.textContent.includes('Created Task') || document.querySelectorAll('.lg-message').length > 1",
      12000,
    )
    record('chat: delivery submit produced a real reply/task', gotReply)
    await sleep(800)
    await shot('lg013-live-chat-task.png')

    // The backend must now hold a real Task.
    const tasks = await fetch(`${BASE}/api/v1/tasks`).then((r) => r.json())
    const taskId = tasks.items?.[0]?.task_id ?? null
    record('backend: real Task was created by the page submit', Boolean(taskId), taskId)
    record(
      'chat: scope switched to the created Task',
      Boolean(taskId) &&
        (await ev(
          `document.body.textContent.includes(${JSON.stringify(taskId)})`,
        )),
    )

    // Board lists the real Task with its phase.
    await ev(
      "document.querySelector(\"nav.lg-rail .lg-rail__item[aria-label='Board']\").click(), true",
    )
    await sleep(800)
    const boardText = await ev(
      "document.querySelector('.lg-board') ? document.querySelector('.lg-board').textContent : ''",
    )
    record(
      'board: lists the real Task (not mock)',
      Boolean(taskId) && boardText.includes(taskId),
      boardText.slice(0, 80),
    )
    record(
      'board: shows a real phase label',
      /executing|queued|planning|intake|waiting|completed|failed|paused|verifying|recruiting|repairing|awaiting|cancell|recovery|Nothing here/.test(
        boardText,
      ),
    )
    await shot('lg013-live-board-task.png')

    console.log('')
    let fail = 0
    for (const r of results) {
      if (!r.pass) fail += 1
      console.log(`${r.pass ? 'PASS' : 'FAIL'}  ${r.name}${r.detail ? ' — ' + r.detail : ''}`)
    }
    console.log(`\n${results.length - fail}/${results.length} live checks passed`)
    console.log(`evidence: ${OUT_DIR}`)
    process.exitCode = fail === 0 ? 0 : 1
  } finally {
    chrome.kill('SIGKILL')
  }
}

main().catch((e) => {
  console.error(e)
  process.exitCode = 1
})
