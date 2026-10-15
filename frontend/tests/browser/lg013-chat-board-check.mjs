#!/usr/bin/env node
/**
 * LG-013 real-browser check for the Chat and Board views (dependency-free).
 *
 * Loads a self-contained build (no backend reachable) and verifies the LG-013
 * acceptance-visible behaviours that do not need a live server:
 *   * Board renders a real "cannot load / empty" state, never mock task data;
 *   * switching Chat <-> Board keeps task scope and the draft while exactly one
 *     `.lg-chat` surface exists;
 *   * the Chat composer is present and the view never fabricates messages.
 *
 * A live backend (global/Task history, task creation, acceptance) is proven at
 * the service layer in tests/api/test_lg013_chat_board_flow.py; full browser E2E
 * against a running server stays with the version QA tasks.
 *
 * Usage:
 *   npm run build
 *   node tests/browser/inline-build.mjs            # writes /tmp/lg011-inline.html
 *   SHELL_URL=file:///tmp/lg011-inline.html LG013_OUT=/tmp/lg013-browser \
 *     node tests/browser/lg013-chat-board-check.mjs
 */
import { spawn } from 'node:child_process'
import { existsSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const SHELL_URL = process.env.SHELL_URL ?? 'file:///tmp/lg011-inline.html'
const OUT_DIR = process.env.LG013_OUT ?? '/tmp/lg013-browser'
const CHROME_BIN = process.env.CHROME_BIN ?? 'google-chrome'

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

class CdpClient {
  constructor(ws) {
    this.ws = ws
    this.nextId = 1
    this.pending = new Map()
    ws.addEventListener('message', (event) => {
      const message = JSON.parse(event.data)
      if (message.id && this.pending.has(message.id)) {
        const { resolve, reject } = this.pending.get(message.id)
        this.pending.delete(message.id)
        if (message.error) reject(new Error(JSON.stringify(message.error)))
        else resolve(message.result)
      }
    })
  }

  send(method, params = {}, sessionId) {
    const id = this.nextId++
    const payload = { id, method, params }
    if (sessionId) payload.sessionId = sessionId
    return new Promise((resolve, reject) => {
      // Bounded: a missing CDP response must not hang the check forever.
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

async function waitForDevtoolsPort(userDataDir, timeoutMs = 20000) {
  const portFile = join(userDataDir, 'DevToolsActivePort')
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    if (existsSync(portFile)) {
      const [port] = readFileSync(portFile, 'utf8').split('\n')
      if (port) return Number(port)
    }
    await sleep(100)
  }
  throw new Error('Chrome DevTools port did not appear')
}

async function main() {
  mkdirSync(OUT_DIR, { recursive: true })
  const userDataDir = mkdtempSync(join(tmpdir(), 'lg013-chrome-'))
  const chrome = spawn(
    CHROME_BIN,
    [
      '--headless=new',
      '--no-sandbox',
      '--disable-gpu',
      '--no-first-run',
      '--no-default-browser-check',
      '--allow-file-access-from-files',
      '--disable-web-security',
      '--remote-debugging-port=0',
      `--user-data-dir=${userDataDir}`,
      'about:blank',
    ],
    { stdio: 'ignore' },
  )

  const results = []
  const screenshots = []
  const record = (name, pass, detail) =>
    results.push({ name, pass: Boolean(pass), detail })

  try {
    const port = await waitForDevtoolsPort(userDataDir)
    const version = await fetch(`http://127.0.0.1:${port}/json/version`).then((r) =>
      r.json(),
    )
    const ws = new WebSocket(version.webSocketDebuggerUrl)
    await new Promise((resolve, reject) => {
      ws.addEventListener('open', resolve, { once: true })
      ws.addEventListener('error', reject, { once: true })
    })
    const client = new CdpClient(ws)
    const { targetId } = await client.send('Target.createTarget', { url: SHELL_URL })
    const { sessionId } = await client.send('Target.attachToTarget', {
      targetId,
      flatten: true,
    })
    await client.send('Page.enable', {}, sessionId)
    await client.send('Runtime.enable', {}, sessionId)
    await client.send(
      'Emulation.setDeviceMetricsOverride',
      { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false },
      sessionId,
    )

    const evaluate = async (expression) => {
      const { result, exceptionDetails } = await client.send(
        'Runtime.evaluate',
        { expression, returnByValue: true, awaitPromise: true },
        sessionId,
      )
      if (exceptionDetails) throw new Error(`evaluate failed: ${JSON.stringify(exceptionDetails)}`)
      return result.value
    }
    const waitFor = async (expression, timeoutMs = 8000) => {
      const deadline = Date.now() + timeoutMs
      while (Date.now() < deadline) {
        if (await evaluate(expression)) return true
        await sleep(100)
      }
      return false
    }
    const ready = await waitFor("document.querySelector('.lg-app') !== null")
    if (!ready) throw new Error('shell did not render')

    const screenshot = async (name) => {
      const { data } = await client.send('Page.captureScreenshot', { format: 'png' }, sessionId)
      const path = join(OUT_DIR, name)
      writeFileSync(path, Buffer.from(data, 'base64'))
      screenshots.push(path)
    }
    const click = (selector) =>
      evaluate(`document.querySelector(${JSON.stringify(selector)})?.click(), true`)
    const nav = (label) => click(`nav.lg-rail .lg-rail__item[aria-label='${label}']`)

    // 1. Chat is the default view and shows a real state (not mock data).
    await sleep(300)
    record(
      'chat: exactly one chat surface',
      (await evaluate("document.querySelectorAll('.lg-chat').length")) === 1,
    )
    const chatText = await evaluate('document.body.textContent')
    record(
      'chat: shows a real empty/error state, not mock data',
      chatText.includes('No messages yet') ||
        chatText.includes('Could not load messages') ||
        chatText.includes('Backend not connected'),
    )
    record('chat: no mock layout data label', !chatText.includes('MOCK LAYOUT DATA'))
    record(
      'chat: composer present for the global scope',
      (await evaluate("document.querySelectorAll('textarea#lg-chat-input').length")) === 1,
    )
    await screenshot('lg013-chat-empty.png')

    // 2. Type a draft, switch to Board, switch back: draft + scope preserved.
    await evaluate(
      "(() => { const el = document.getElementById('lg-chat-input'); el.focus(); return true })()",
    )
    await client.send(
      'Input.insertText',
      { text: 'lg013 browser draft' },
      sessionId,
    )
    await nav('Board')
    await sleep(300)
    // Only the Board body must avoid mock data; the shell's optional demo
    // layout mock (LG-011, toggled off by default in real use) is out of scope.
    const boardBodyText = await evaluate(
      "document.querySelector('.lg-board') ? document.querySelector('.lg-board').textContent : ''",
    )
    record(
      'board: renders a real empty/error state, not mock task data',
      (await evaluate("document.querySelector('.lg-board') !== null")) === true &&
        !boardBodyText.includes('mock-task-') &&
        (boardBodyText.includes('Could not load tasks') ||
          boardBodyText.includes('No tasks yet') ||
          boardBodyText.includes('Nothing here')),
    )
    record(
      'board: exactly one chat surface retained (right rail)',
      (await evaluate("document.querySelectorAll('.lg-chat').length")) === 1,
    )
    await screenshot('lg013-board-empty.png')

    await nav('Chat')
    await sleep(300)
    record(
      'scope/draft: chat draft survives the view switch',
      (await evaluate("document.getElementById('lg-chat-input').value")) ===
        'lg013 browser draft',
    )
    record(
      'single chat: still exactly one surface after switching back',
      (await evaluate("document.querySelectorAll('.lg-chat').length")) === 1,
    )

    console.log('')
    let failures = 0
    for (const item of results) {
      if (!item.pass) failures += 1
      console.log(
        `${item.pass ? 'PASS' : 'FAIL'}  ${item.name}${item.detail ? ' — ' + item.detail : ''}`,
      )
    }
    console.log(`\n${results.length - failures}/${results.length} checks passed`)
    console.log(`evidence: ${OUT_DIR} (${screenshots.length} screenshots)`)
    process.exitCode = failures === 0 ? 0 : 1
  } finally {
    chrome.kill('SIGKILL')
  }
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
