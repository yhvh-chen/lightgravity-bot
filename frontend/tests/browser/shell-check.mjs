#!/usr/bin/env node
/**
 * LG-011 real-browser shell check (dependency-free).
 *
 * Drives a system Chrome/Chromium over the DevTools Protocol using Node's
 * built-in WebSocket + fetch — no Playwright and no extra npm dependency. It
 * verifies navigation, layout, keyboard focus, scope/draft preservation,
 * empty/error states and narrow-screen drawers, and writes real screenshots.
 *
 * There is no Page.navigate here: pages are opened with `Target.createTarget`
 * so the same script works against a dev server or a self-contained file URL.
 *
 * Usage against a built preview (when loopback HTTP is reachable):
 *   npm run build
 *   npx vite preview --host 127.0.0.1 --port 4173 --strictPort &
 *   SHELL_URL=http://127.0.0.1:4173/ node tests/browser/shell-check.mjs
 *
 * Usage in a sandbox that only allows file:// (used for LG-011 evidence):
 *   node tests/browser/inline-build.mjs            # writes /tmp/lg011-inline.html
 *   SHELL_URL=file:///tmp/lg011-inline.html node tests/browser/shell-check.mjs
 *
 * Exit code is non-zero if any check fails. Local shell smoke evidence only;
 * full view/E2E acceptance stays with the version QA tasks.
 */
import { spawn } from 'node:child_process'
import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const SHELL_URL =
  process.env.SHELL_URL ?? 'file:///tmp/lg011-inline.html'
const OUT_DIR = process.env.SHELL_OUT ?? '/tmp/lg011-evidence'
const CHROME_BIN = process.env.CHROME_BIN ?? 'google-chrome'

class CdpClient {
  constructor(ws) {
    this.ws = ws
    this.nextId = 1
    this.pending = new Map()
    this.listeners = new Map()
    ws.addEventListener('message', (event) => {
      const message = JSON.parse(event.data)
      if (message.id && this.pending.has(message.id)) {
        const { resolve, reject } = this.pending.get(message.id)
        this.pending.delete(message.id)
        if (message.error) reject(new Error(JSON.stringify(message.error)))
        else resolve(message.result)
      } else if (message.method) {
        for (const listener of this.listeners.get(message.method) ?? []) {
          listener(message.params)
        }
      }
    })
  }

  send(method, params = {}, sessionId) {
    const id = this.nextId++
    const payload = { id, method, params }
    if (sessionId) payload.sessionId = sessionId
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject })
      this.ws.send(JSON.stringify(payload))
    })
  }
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

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
  const userDataDir = mkdtempSync(join(tmpdir(), 'lg011-chrome-'))
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
  let client
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
    client = new CdpClient(ws)

    const opened = []

    const openPage = async (width, height) => {
      const { targetId } = await client.send('Target.createTarget', {
        url: SHELL_URL,
      })
      const { sessionId } = await client.send('Target.attachToTarget', {
        targetId,
        flatten: true,
      })
      await client.send('Target.activateTarget', { targetId }).catch(() => undefined)
      await client.send('Page.enable', {}, sessionId)
      await client.send('Runtime.enable', {}, sessionId)
      await client.send(
        'Emulation.setDeviceMetricsOverride',
        { width, height, deviceScaleFactor: 1, mobile: width < 700 },
        sessionId,
      )

      const evaluate = async (expression) => {
        const { result, exceptionDetails } = await client.send(
          'Runtime.evaluate',
          { expression, returnByValue: true, awaitPromise: true },
          sessionId,
        )
        if (exceptionDetails) {
          throw new Error(`evaluate failed: ${JSON.stringify(exceptionDetails)}`)
        }
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

      const ready = await waitFor(
        "document.querySelector('.lg-app') !== null && document.querySelectorAll('.lg-topbar__actions button').length > 0",
      )
      if (!ready) throw new Error(`shell did not render at ${width}px`)
      await sleep(150)

      const page = {
        targetId,
        sessionId,
        evaluate,
        waitFor,
        close: () => client.send('Target.closeTarget', { targetId }),
      }
      opened.push(page)
      return page
    }

    const screenshot = async (page, name) => {
      const { data } = await client.send(
        'Page.captureScreenshot',
        { format: 'png' },
        page.sessionId,
      )
      const path = join(OUT_DIR, name)
      writeFileSync(path, Buffer.from(data, 'base64'))
      screenshots.push(path)
      return path
    }

    const record = (name, pass, detail) => {
      results.push({ name, pass: Boolean(pass), detail })
    }

    const click = (page, selector) =>
      page.evaluate(`document.querySelector(${JSON.stringify(selector)})?.click(), true`)

    const key = async (page, keyName, code, keyCode) => {
      await client.send(
        'Input.dispatchKeyEvent',
        {
          type: 'keyDown',
          key: keyName,
          code,
          windowsVirtualKeyCode: keyCode,
          nativeVirtualKeyCode: keyCode,
        },
        page.sessionId,
      )
      await client.send(
        'Input.dispatchKeyEvent',
        { type: 'keyUp', key: keyName, code, windowsVirtualKeyCode: keyCode },
        page.sessionId,
      )
      await sleep(60)
    }

    /* ---------------------------------------------------- 1440 desktop */
    const desktop = await openPage(1440, 900)

    const navLabels = await desktop.evaluate(
      "Array.from(document.querySelectorAll('nav.lg-rail .lg-rail__item')).map((b) => b.getAttribute('aria-label'))",
    )
    record(
      'desktop: five work entries + Settings in order',
      JSON.stringify(navLabels) ===
        JSON.stringify(['Chat', 'Board', 'Files', 'Team', 'Resources', 'Settings']),
      navLabels,
    )
    record(
      'desktop: Chat is aria-current',
      (await desktop.evaluate(
        "document.querySelector('nav.lg-rail .lg-rail__item[aria-current=\\'page\\']')?.getAttribute('aria-label')",
      )) === 'Chat',
    )
    record(
      'desktop: no primary view tabs in top bar',
      (await desktop.evaluate(
        "document.querySelectorAll('.lg-topbar nav button').length === 0 && Array.from(document.querySelectorAll('.lg-topbar__actions button')).every((b) => !['Chat','Board','Files','Team','Resources'].includes(b.getAttribute('aria-label')))",
      )) === true,
    )
    record(
      'desktop: context panel + exactly one chat surface/composer',
      (await desktop.evaluate(
        "document.querySelectorAll('.lg-context--inline').length === 1 && document.querySelectorAll('.lg-chat').length === 1 && document.querySelectorAll('textarea#lg-chat-input').length === 1",
      )) === true,
    )
    record(
      'desktop: design token background applied',
      (await desktop.evaluate('getComputedStyle(document.body).backgroundColor')) ===
        'rgb(248, 250, 252)',
      await desktop.evaluate('getComputedStyle(document.body).backgroundColor'),
    )
    record(
      'desktop: layout mock is explicitly labelled',
      (await desktop.evaluate(
        "document.body.textContent.includes('MOCK LAYOUT DATA — not from backend')",
      )) === true,
    )
    const chatState = await desktop.evaluate(
      "document.body.textContent.includes('Backend not connected') ? 'error' : (document.body.textContent.includes('No messages yet') ? 'empty' : 'unknown')",
    )
    record(
      'desktop: chat shows a real error/empty state (not fake data)',
      chatState === 'error' || chatState === 'empty',
      chatState,
    )

    // Panel collapse/restore.
    await click(desktop, '#lg-toggle-context')
    record(
      'desktop: context toggle collapses the panel',
      (await desktop.evaluate(
        "document.querySelectorAll('.lg-context--inline').length === 0 && document.getElementById('lg-toggle-context').getAttribute('aria-pressed') === 'false'",
      )) === true,
    )
    await click(desktop, '#lg-toggle-context')
    record(
      'desktop: context toggle restores the panel',
      (await desktop.evaluate(
        "document.querySelectorAll('.lg-context--inline').length === 1",
      )) === true,
    )

    // Scope + draft preservation across a view switch.
    await desktop.evaluate(`
      (() => {
        const el = document.getElementById('lg-scope-task');
        const setter = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set;
        setter.call(el, 'mock-task-1');
        el.dispatchEvent(new Event('change', { bubbles: true }));
        return true;
      })()
    `)
    await desktop.evaluate("document.getElementById('lg-chat-input').focus(), true")
    await client.send(
      'Input.insertText',
      { text: 'browser draft' },
      desktop.sessionId,
    )
    await sleep(120)
    await click(desktop, "nav.lg-rail .lg-rail__item[aria-label='Board']")
    await sleep(150)
    const scopeAfter = await desktop.evaluate(
      "document.getElementById('lg-scope-task').value",
    )
    const draftAfter = await desktop.evaluate(
      "document.querySelector('textarea#lg-chat-input')?.value",
    )
    record(
      'desktop: switching views keeps task scope',
      scopeAfter === 'mock-task-1',
      scopeAfter,
    )
    record(
      'desktop: switching views keeps the chat draft',
      draftAfter === 'browser draft',
      draftAfter,
    )
    record(
      'desktop: still exactly one chat after switching (now the rail)',
      (await desktop.evaluate(
        "document.querySelectorAll('textarea#lg-chat-input').length === 1 && document.querySelectorAll('.lg-chat--rail').length === 1 && document.querySelectorAll('.lg-chat').length === 1",
      )) === true,
    )
    record(
      'desktop: view switch is reflected in the URL route',
      (await desktop.evaluate('window.location.search')).includes('view=board'),
      await desktop.evaluate('window.location.search'),
    )

    // Keyboard focus order reaches the primary navigation with a visible ring.
    await desktop.evaluate(
      "document.body.setAttribute('tabindex','-1'); document.body.focus(); true",
    )
    const focusOrder = []
    for (let i = 0; i < 16; i += 1) {
      await key(desktop, 'Tab', 'Tab', 9)
      const info = await desktop.evaluate(`
        (() => {
          const el = document.activeElement;
          if (!el || el === document.body) return null;
          return {
            label: el.getAttribute('aria-label') || (el.textContent || '').trim().slice(0, 24),
            focusVisible: el.matches(':focus-visible'),
          };
        })()
      `)
      if (info) focusOrder.push(info)
    }
    const navFocus = focusOrder.filter((entry) =>
      ['Chat', 'Board', 'Files', 'Team', 'Resources', 'Settings'].includes(entry.label),
    )
    record(
      'desktop: Tab reaches all six rail entries',
      navFocus.length === 6,
      focusOrder.map((entry) => entry.label),
    )
    record(
      'desktop: focused rail entry has a visible focus ring',
      navFocus.some((entry) => entry.focusVisible),
      navFocus,
    )

    await screenshot(desktop, 'shell-1440-desktop.png')
    record('desktop: screenshot written', true, screenshots.at(-1))

    /* --------------------------------------------------- 1024 desktop */
    const mid = await openPage(1024, 900)
    record(
      '1024: still multi-column (context inline, no drawer)',
      (await mid.evaluate(
        "document.querySelectorAll('.lg-context--inline').length === 1 && document.querySelectorAll('.lg-drawer').length === 0",
      )) === true,
    )
    await screenshot(mid, 'shell-1024.png')
    record('1024: screenshot written', true, screenshots.at(-1))

    /* ---------------------------------------------------- 390 compact */
    const phone = await openPage(390, 780)
    record(
      '390: rail becomes a drawer, not inline',
      (await phone.evaluate("document.querySelectorAll('nav.lg-rail').length")) === 0,
    )
    await click(phone, '#lg-toggle-context')
    await sleep(150)
    record(
      '390: context opens as a modal drawer',
      (await phone.evaluate(
        "document.querySelector('[role=dialog][aria-label=\\'Context panel\\']') !== null",
      )) === true,
    )
    await screenshot(phone, 'shell-390-drawer.png')
    record('390: drawer screenshot written', true, screenshots.at(-1))
    await key(phone, 'Escape', 'Escape', 27)
    record(
      '390: Escape closes the drawer and restores the toggle',
      (await phone.evaluate(
        "document.querySelector('[role=dialog]') === null && document.activeElement.id === 'lg-toggle-context'",
      )) === true,
    )
    record(
      '390: no horizontal page overflow',
      (await phone.evaluate(
        'document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1',
      )) === true,
      await phone.evaluate(
        'document.documentElement.scrollWidth + "/" + document.documentElement.clientWidth',
      ),
    )

    for (const page of opened) {
      await page.close().catch(() => undefined)
    }

    writeFileSync(
      join(OUT_DIR, 'shell-check-report.json'),
      JSON.stringify({ url: SHELL_URL, results, screenshots }, null, 2),
    )
  } finally {
    try {
      client?.ws?.close()
    } catch {
      /* ignore */
    }
    chrome.kill('SIGKILL')
    rmSync(userDataDir, { recursive: true, force: true })
  }

  const failed = results.filter((entry) => !entry.pass)
  for (const entry of results) {
    const mark = entry.pass ? 'PASS' : 'FAIL'
    const detail =
      entry.detail === undefined ? '' : ` — ${JSON.stringify(entry.detail)}`
    console.log(`${mark}  ${entry.name}${detail}`)
  }
  console.log(`\n${results.length - failed.length}/${results.length} checks passed`)
  console.log(`evidence: ${OUT_DIR}`)
  if (failed.length > 0) process.exitCode = 1
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
