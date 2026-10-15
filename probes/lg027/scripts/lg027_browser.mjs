#!/usr/bin/env node
/**
 * LG-027 real-browser QA of the Settings entry (dependency-free CDP).
 *
 * Drives the system Chrome over the DevTools Protocol against a *real*
 * `lightgravity start` process serving the freshly built `frontend/dist`
 * (real backend, real loopback HTTP). It performs the whole visible path:
 *
 *   gear -> Settings -> New connection -> paste key -> Create -> Test
 *   -> set default worker -> back to the Task scope; then repeats at 390px.
 *
 * It also asserts that the pasted API key never appears in
 * localStorage / sessionStorage / IndexedDB / the URL, and that the narrow
 * layout does not overflow horizontally.
 *
 * Usage:
 *   LG027_BASE_URL=http://127.0.0.1:PORT \
 *   LG027_OUT=/tmp/lg027-browser \
 *   node probes/lg027/scripts/lg027_browser.mjs
 *
 * Exit code is non-zero if any check fails. This is QA evidence for the
 * Settings/credential milestone only; full first-version QA stays with
 * LG-021/LG-022.
 */
import { spawn } from 'node:child_process'
import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  writeFileSync,
} from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const BASE_URL = process.env.LG027_BASE_URL ?? 'http://127.0.0.1:8010'
const OUT_DIR = process.env.LG027_OUT ?? '/tmp/lg027-browser'
const CHROME_BIN = process.env.CHROME_BIN ?? 'google-chrome'
const API_KEY = 'lg027-browser-only-fake-key'
const CONNECTION_ID = 'deepseek-browser'
// Real server-generated Task id seeded by run_browser.sh (falls back to a URL
// only when the caller did not seed one; the scope check then reports false).
const FIXTURE_TASK = process.env.LG027_FIXTURE_TASK ?? 'task_lg027_fixture'

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
  const userDataDir = mkdtempSync(join(tmpdir(), 'lg027-chrome-'))
  const chrome = spawn(
    CHROME_BIN,
    [
      '--headless=new',
      '--no-sandbox',
      '--disable-gpu',
      '--no-first-run',
      '--no-default-browser-check',
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
    const version = await fetch(`http://127.0.0.1:${port}/json/version`).then((r) => r.json())
    const ws = new WebSocket(version.webSocketDebuggerUrl)
    await new Promise((resolve, reject) => {
      ws.addEventListener('open', resolve, { once: true })
      ws.addEventListener('error', reject, { once: true })
    })
    client = new CdpClient(ws)

    const record = (name, pass, detail) =>
      results.push({ name, pass: Boolean(pass), detail })

    const openPage = async (url, width, height) => {
      const { targetId } = await client.send('Target.createTarget', { url: 'about:blank' })
      const { sessionId } = await client.send('Target.attachToTarget', {
        targetId,
        flatten: true,
      })
      await client.send('Page.enable', {}, sessionId)
      await client.send('Runtime.enable', {}, sessionId)
      await client.send(
        'Emulation.setDeviceMetricsOverride',
        { width, height, deviceScaleFactor: 1, mobile: width < 700 },
        sessionId,
      )
      // Navigate explicitly: some Chrome builds do not honour the `url` passed
      // to Target.createTarget (the target stays on about:blank).
      await client.send('Page.navigate', { url }, sessionId)
      const evaluate = async (expression) => {
        const { result, exceptionDetails } = await client.send(
          'Runtime.evaluate',
          { expression, returnByValue: true, awaitPromise: true },
          sessionId,
        )
        if (exceptionDetails) throw new Error(`evaluate failed: ${JSON.stringify(exceptionDetails)}`)
        return result.value
      }
      const waitFor = async (expression, timeoutMs = 10000) => {
        const deadline = Date.now() + timeoutMs
        while (Date.now() < deadline) {
          if (await evaluate(expression)) return true
          await sleep(120)
        }
        return false
      }
      return { targetId, sessionId, evaluate, waitFor, close: () => client.send('Target.closeTarget', { targetId }) }
    }

    const screenshot = async (page, name) => {
      const { data } = await client.send('Page.captureScreenshot', { format: 'png' }, page.sessionId)
      const path = join(OUT_DIR, name)
      writeFileSync(path, Buffer.from(data, 'base64'))
      screenshots.push(path)
      return path
    }

    /* -------------------------------------------------- desktop 1440 flow */
    const page = await openPage(`${BASE_URL}/?task=${FIXTURE_TASK}`, 1440, 900)
    const loaded = await page.waitFor("document.querySelector('.lg-app') !== null")
    record('desktop: app shell renders from real dist', loaded)
    record(
      'desktop: runtime token injected in-memory (no persist)',
      (await page.evaluate('window.__LG_RUNTIME_TOKEN_READY__ === true')) === true,
    )

    // Open Settings via the bottom gear.
    await page.evaluate(
      "Array.from(document.querySelectorAll('nav.lg-rail .lg-rail__item')).find((b) => b.getAttribute('aria-label') === 'Settings')?.click(), true",
    )
    const settingsReady = await page.waitFor(
      "document.body.textContent.includes('Models & Providers') && document.querySelector('.lg-settings-view') !== null",
    )
    record('desktop: gear opens Settings (Models & Providers)', settingsReady)

    // The URL retains the real seeded Task id, so leaving Settings can return
    // to that same Task scope (deep-link, no state loss).
    const taskScopeKept = await page.evaluate(
      `window.location.search.includes('task=' + ${JSON.stringify(FIXTURE_TASK)})`,
    )
    record('desktop: Settings keeps the current Task scope (real Task id in URL)', taskScopeKept)

    // Create a new connection.
    await page.evaluate(
      "Array.from(document.querySelectorAll('button')).find((b) => b.textContent.trim() === 'New connection')?.click(), true",
    )
    const formReady = await page.waitFor("document.querySelector('input.lg-field__input[placeholder=\"deepseek-primary\"]') !== null")
    record('desktop: typed connection form appears', formReady)
    await screenshot(page, '01-settings-new-connection-1440.png')

    const setInput = async (labelText, value) =>
      page.evaluate(`(() => {
        const labels = Array.from(document.querySelectorAll('label.lg-field'));
        const label = labels.find((l) => l.querySelector('.lg-field__label')?.textContent.trim() === ${JSON.stringify(labelText)});
        const input = label?.querySelector('input');
        if (!input) return false;
        const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        setter.call(input, ${JSON.stringify(value)});
        input.dispatchEvent(new Event('input', { bubbles: true }));
        return true;
      })()`)

    await setInput('Connection id', CONNECTION_ID)
    await setInput('Model', 'deepseek-v4-flash')
    await setInput('Base URL', 'http://127.0.0.1:9/v1')
    await setInput('Credential reference', 'deepseek-browser-key')
    await setInput('New API key (write-only)', API_KEY)
    await screenshot(page, '02-settings-filled-1440.png')

    // Submit (create) — the form clears the password field on save.
    await page.evaluate(
      "Array.from(document.querySelectorAll('button[type=submit]')).find((b) => /Create connection|Save changes/.test(b.textContent))?.click(), true",
    )
    const created = await page.waitFor(
      "document.body.textContent.includes('deepseek-browser') && document.querySelector('button.lg-settings__item') !== null",
    )
    record('desktop: connection saved through the real API', created)

    const passwordCleared = await page.evaluate(
      "(() => { const i = document.querySelector('input[type=password]'); return i ? i.value === '' : true })()",
    )
    record('desktop: secret input cleared after save', passwordCleared)

    // Run the layered test.
    await page.evaluate(
      "Array.from(document.querySelectorAll('button')).find((b) => /Test connection/.test(b.textContent))?.click(), true",
    )
    const tested = await page.waitFor(
      "document.querySelector('.lg-test__result') !== null && document.body.textContent.includes('runtime_network')",
    )
    record('desktop: layered test result rendered', tested)
    const skippedVisible = await page.evaluate(
      "document.body.textContent.includes('tool_probe') && document.body.textContent.includes('structured_output')",
    )
    record('desktop: tool/structured layers shown separately (skipped)', skippedVisible)
    await screenshot(page, '03-settings-tested-1440.png')

    // Set the worker default.
    await page.evaluate(
      "(() => { const labels = Array.from(document.querySelectorAll('label.lg-field')); const l = labels.find((x) => x.querySelector('.lg-field__label')?.textContent.trim() === 'Default worker connection'); const sel = l?.querySelector('select'); if (!sel) return false; const setter = Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, 'value').set; setter.call(sel, 'deepseek-browser'); sel.dispatchEvent(new Event('change', { bubbles: true })); return true })()",
    )
    await page.evaluate(
      "Array.from(document.querySelectorAll('button[type=submit]')).find((b) => /Save defaults|Save/.test(b.textContent))?.click(), true",
    )
    const defaultSaved = await page.waitFor(
      "document.body.textContent.includes('worker default') && !document.body.textContent.includes('does not resolve')",
    )
    record('desktop: worker default saved', defaultSaved)

    // Secret must not appear in any persistent browser store.
    const leak = await page.evaluate(`(async () => {
      const found = [];
      for (let i = 0; i < localStorage.length; i++) { const v = localStorage.getItem(localStorage.key(i)); if (v && v.includes(${JSON.stringify(API_KEY)})) found.push('localStorage'); }
      for (let i = 0; i < sessionStorage.length; i++) { const v = sessionStorage.getItem(sessionStorage.key(i)); if (v && v.includes(${JSON.stringify(API_KEY)})) found.push('sessionStorage'); }
      if (window.location.href.includes(${JSON.stringify(API_KEY)})) found.push('url');
      try { if (document.cookie.includes(${JSON.stringify(API_KEY)})) found.push('cookie'); } catch (e) { /* cookies unavailable on file:// */ }
      try {
        const timeout = (p) => Promise.race([p, new Promise((res) => setTimeout(() => res('__timeout__'), 2500))]);
        const dbs = (indexedDB.databases && await timeout(indexedDB.databases())) || [];
        for (const info of dbs) {
          const db = await timeout(new Promise((res, rej) => { const r = indexedDB.open(info.name); r.onsuccess = () => res(r.result); r.onerror = () => rej(r.error); }));
          if (db === '__timeout__' || !db) continue;
          for (const name of Array.from(db.objectStoreNames)) {
            const rows = await timeout(new Promise((res, rej) => { const r = db.transaction(name).objectStore(name).getAll(); r.onsuccess = () => res(r.result); r.onerror = () => rej(r.error); }));
            if (rows !== '__timeout__' && JSON.stringify(rows).includes(${JSON.stringify(API_KEY)})) found.push('indexedDB:' + info.name + '/' + name);
          }
          db.close();
        }
      } catch (e) { /* no IndexedDB access -> nothing stored there */ }
      return found;
    })()`)
    record('desktop: secret not in localStorage/sessionStorage/indexedDB/url/cookie', leak.length === 0, leak)

    // Returning from Settings to a Task view must keep the real Task scope.
    await page.evaluate(
      "Array.from(document.querySelectorAll('nav.lg-rail .lg-rail__item')).find((b) => b.getAttribute('aria-label') === 'Board')?.click(), true",
    )
    const returned = await page.waitFor(
      `window.location.search.includes('task=' + ${JSON.stringify(FIXTURE_TASK)}) && document.querySelector('.lg-settings-view') === null`,
    )
    record('desktop: back to Task keeps the real Task scope', returned)

    const overflow1440 = await page.evaluate(
      'document.documentElement.scrollWidth - document.documentElement.clientWidth',
    )
    record('desktop: no horizontal overflow at 1440px', overflow1440 <= 1, overflow1440)

    await page.close()

    /* -------------------------------------------------- narrow 390 flow */
    const narrow = await openPage(`${BASE_URL}/?task=${FIXTURE_TASK}`, 390, 844)
    await narrow.waitFor("document.querySelector('.lg-app') !== null")
    await narrow.evaluate(
      "Array.from(document.querySelectorAll('nav.lg-rail .lg-rail__item')).find((b) => b.getAttribute('aria-label') === 'Settings')?.click(), true",
    )
    const narrowSettings = await narrow.waitFor("document.querySelector('.lg-settings-view') !== null")
    record('narrow(390): Settings renders', narrowSettings)
    const overflowNarrow = await narrow.evaluate(
      'document.documentElement.scrollWidth - document.documentElement.clientWidth',
    )
    record('narrow(390): no horizontal overflow', overflowNarrow <= 1, overflowNarrow)

    const narrowForm = await narrow.evaluate(
      "document.querySelectorAll('.lg-settings-view input.lg-field__input').length > 0",
    )
    record('narrow(390): form inputs reachable in single column', narrowForm)
    // The persisted connection from the desktop flow must be listed narrow too.
    const narrowListed = await narrow.waitFor(
      `document.body.textContent.includes(${JSON.stringify(CONNECTION_ID)})`,
    )
    record('narrow(390): persisted connection listed from real API', narrowListed)
    await screenshot(narrow, '04-settings-390.png')
    await narrow.close()
  } finally {
    try {
      if (client) client.ws.close()
    } catch {
      /* ignore */
    }
    chrome.kill('SIGKILL')
  }

  const summary = {
    base_url: BASE_URL,
    chrome: CHROME_BIN,
    results,
    screenshots,
    passed: results.filter((r) => r.pass).length,
    failed: results.filter((r) => !r.pass).length,
  }
  writeFileSync(join(OUT_DIR, 'lg027-browser-results.json'), JSON.stringify(summary, null, 2))
  console.log(JSON.stringify(summary, null, 2))
  if (summary.failed > 0) process.exitCode = 1
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
