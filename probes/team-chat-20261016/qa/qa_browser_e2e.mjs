#!/usr/bin/env node
/**
 * LG-050 QA browser end-to-end (Firefox native WebDriver BiDi).
 *
 * Real Firefox, real built frontend, real server. Two *independent* browser
 * user contexts (Firefox containers) log in as alice and bob. alice sends an
 * ordinary message; bob must see it with the real author without reloading
 * (≈3s polling). Then `@bot`, then alice signs out.
 *
 * No mocking of API responses, no disabled web security, no product changes.
 * Bounded per-call timeouts; launches Firefox in its own process group and only
 * signals that group.
 */
import { spawn } from 'node:child_process'
import net from 'node:net'
import { mkdtempSync, rmSync, readFileSync, existsSync } from 'node:fs'
import { tmpdir, homedir } from 'node:os'
import { join } from 'node:path'

function parseArgs(argv) {
  const out = { url: null, firefox: process.env.FIREFOX_BIN || 'firefox', profileDir: null, deadlineMs: 60000, keep: false, verbose: false }
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i]
    const next = () => argv[++i]
    if (a === '--url') out.url = next()
    else if (a === '--firefox') out.firefox = next()
    else if (a === '--profile-dir') out.profileDir = next()
    else if (a === '--deadline-ms') out.deadlineMs = Number(next())
    else if (a === '--keep') out.keep = true
    else if (a === '--verbose') out.verbose = true
  }
  if (!out.url) throw new Error('--url is required')
  return out
}

const ARGS = parseArgs(process.argv)
const log = (...m) => console.log(...m)
const vlog = (...m) => ARGS.verbose && console.log('[v]', ...m)
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const PASSWORD = 'qa-throwaway-pass-123!' // QA fixture only

let childPid = null
const MARKER = `lg050qa-${process.pid}`

function launchFirefox(binary, args) {
  const child = spawn(binary, args, { detached: true, stdio: ['ignore', 'ignore', 'ignore'] })
  childPid = child.pid
  return child
}
function groupIsOurs(pgid) {
  try {
    const cmd = readFileSync(`/proc/${pgid}/cmdline`, 'utf8')
    return cmd.includes(MARKER) && cmd.includes('firefox')
  } catch { return false }
}
function cleanup() {
  if (childPid == null) return
  try {
    if (groupIsOurs(childPid)) {
      process.kill(-childPid, 'SIGTERM')
      const t0 = Date.now()
      while (Date.now() - t0 < 1500) {
        try { process.kill(-childPid, 0) } catch { return }
        const end = Date.now() + 50
        while (Date.now() < end) { /* spin */ }
      }
      process.kill(-childPid, 'SIGKILL')
    }
  } catch { /* gone */ }
}

class Bidi {
  constructor(ws) {
    this.ws = ws
    this.nextId = 1
    this.pending = new Map()
    ws.addEventListener('message', (ev) => {
      let msg
      try { msg = JSON.parse(typeof ev.data === 'string' ? ev.data : ev.data.toString()) } catch { return }
      if (msg.id !== undefined && this.pending.has(msg.id)) {
        const { resolve, reject } = this.pending.get(msg.id)
        this.pending.delete(msg.id)
        if (msg.type === 'error') reject(new Error(`${msg.error}: ${msg.message}`))
        else resolve(msg.result)
      }
    })
  }
  send(method, params = {}, timeoutMs = 10000) {
    const id = this.nextId++
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { this.pending.delete(id); reject(new Error(`timeout ${method} after ${timeoutMs}ms`)) }, timeoutMs)
      this.pending.set(id, {
        resolve: (r) => { clearTimeout(timer); resolve(r) },
        reject: (e) => { clearTimeout(timer); reject(e) },
      })
      this.ws.send(JSON.stringify({ id, method, params }))
    })
  }
}

function connect(url, timeoutMs) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(url)
    const timer = setTimeout(() => reject(new Error('ws connect timeout')), timeoutMs)
    ws.addEventListener('open', () => { clearTimeout(timer); resolve(ws) })
    ws.addEventListener('error', () => reject(new Error('ws error')))
  })
}

async function main() {
  const deadline = Date.now() + ARGS.deadlineMs
  const profileRoot = ARGS.profileDir || (existsSync(join(homedir(), 'snap/firefox/current')) ? join(homedir(), 'snap/firefox/current') : tmpdir())
  const profile = mkdtempSync(join(profileRoot, `${MARKER}-`))
  const port = await freePort()
  const ffArgs = ['--headless', '--no-remote', `--profile=${profile}`, `--remote-debugging-port=${port}`, '--no-first-run', 'about:blank']
  log(`# lg050_browser_e2e firefox=${ARGS.firefox}`)
  log(`# profile=${profile} bidi-port=${port} url=${ARGS.url}`)
  const results = { url: ARGS.url, firefox: ARGS.firefox, checks: {}, ok: false }

  try {
    launchFirefox(ARGS.firefox, ffArgs)
    const endpoint = `ws://127.0.0.1:${port}/session`
    let up = false
    const waitUntil = Math.min(deadline, Date.now() + 15000)
    while (Date.now() < waitUntil) {
      up = await new Promise((res) => {
        const s = new net.Socket(); s.setTimeout(800)
        s.once('connect', () => { s.destroy(); res(true) })
        s.once('timeout', () => { s.destroy(); res(false) })
        s.once('error', () => res(false))
        s.connect(port, '127.0.0.1')
      })
      if (up) break
      await sleep(200)
    }
    if (!up) throw new Error(`BiDi port ${port} not reachable`)
    const ws = await connect(endpoint, 5000)
    const bidi = new Bidi(ws)
    const sess = await bidi.send('session.new', { capabilities: { alwaysMatch: {} } }, 8000)
    results.browser = `${sess.capabilities?.browserName}/${sess.capabilities?.browserVersion}`
    log(`# session.new ${results.browser} headless=${sess.capabilities?.['moz:headless']}`)

    const evalIn = async (context, expression) => {
      const r = await bidi.send('script.evaluate', { expression, target: { context }, awaitPromise: true, resultOwnership: 'none' }, 10000)
      if (r.type === 'exception') throw new Error(`eval exception: ${r.exceptionDetails?.text}`)
      return r.result?.value
    }
    const openContext = async () => {
      const uc = await bidi.send('browser.createUserContext', {}, 8000)
      const userContext = uc.userContext
      const created = await bidi.send('browsingContext.create', { type: 'tab', userContext }, 8000)
      return created.context
    }
    const navigate = (context, url) => bidi.send('browsingContext.navigate', { context, url, wait: 'complete' }, 20000)
    const waitFor = async (context, expr, timeoutMs, label) => {
      const end = Date.now() + timeoutMs
      let last
      while (Date.now() < end) {
        try { last = await evalIn(context, expr); if (last) return last } catch (e) { last = String(e.message) }
        await sleep(200)
      }
      throw new Error(`waitFor ${label} timed out; last=${JSON.stringify(last)}`)
    }

    const ctxAlice = await openContext()
    const ctxBob = await openContext()
    results.checks.userContextsIsolated = ctxAlice !== ctxBob
    log(`# contexts alice=${ctxAlice} bob=${ctxBob}`)

    await navigate(ctxAlice, ARGS.url)
    await navigate(ctxBob, ARGS.url)

    const loginJs = (user) => `(async () => {
      const setVal = (el, v) => {
        const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
        Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, v);
        el.dispatchEvent(new Event('input', { bubbles: true }));
      };
      const u = document.querySelector('input[name="username"]');
      const p = document.querySelector('input[name="password"]');
      if (!u || !p) return 'no-form';
      setVal(u, ${JSON.stringify(user)});
      setVal(p, ${JSON.stringify(PASSWORD)});
      await new Promise(r => setTimeout(r, 80));
      document.querySelector('.lg-auth__card').requestSubmit();
      return 'submitted';
    })()`

    // Login alice
    let r = await waitFor(ctxAlice, `document.querySelector('.lg-auth__card') ? 'ready' : ''`, 12000, 'alice login form')
    log(`# alice login form ${r}`)
    await evalIn(ctxAlice, loginJs('alice'))
    await waitFor(ctxAlice, `document.querySelector('.lg-topbar__logout') ? (document.querySelector('.lg-topbar__identity-user')||{}).textContent : ''`, 15000, 'alice workspace')
    const aliceIdentity = await evalIn(ctxAlice, `(document.querySelector('.lg-topbar__identity-user')||{}).textContent || ''`)
    results.checks.aliceLogin = aliceIdentity === 'alice'
    log(`# alice logged in as ${JSON.stringify(aliceIdentity)}`)

    // Login bob
    await waitFor(ctxBob, `document.querySelector('.lg-auth__card') ? 'ready' : ''`, 12000, 'bob login form')
    await evalIn(ctxBob, loginJs('bob'))
    await waitFor(ctxBob, `document.querySelector('.lg-topbar__logout') ? (document.querySelector('.lg-topbar__identity-user')||{}).textContent : ''`, 15000, 'bob workspace')
    const bobIdentity = await evalIn(ctxBob, `(document.querySelector('.lg-topbar__identity-user')||{}).textContent || ''`)
    results.checks.bobLogin = bobIdentity === 'bob'
    log(`# bob logged in as ${JSON.stringify(bobIdentity)}`)

    const sendJs = (text) => `(async () => {
      const setVal = (el, v) => {
        Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(el, v);
        el.dispatchEvent(new Event('input', { bubbles: true }));
      };
      const ta = document.querySelector('#lg-chat-input');
      if (!ta) return 'no-composer';
      setVal(ta, ${JSON.stringify(text)});
      await new Promise(r => setTimeout(r, 120));
      const btn = [...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Send');
      if (!btn) return 'no-send';
      btn.click();
      return 'sent';
    })()`

    const contentA = `qa-real-http-alice-${Date.now()}`
    r = await evalIn(ctxAlice, sendJs(contentA))
    log(`# alice send -> ${r}`)
    // alice sees her own message with author alice
    await waitFor(ctxAlice, `document.body.innerText.includes(${JSON.stringify(contentA)}) ? 'seen' : ''`, 10000, 'alice own message')
    results.checks.aliceSeesOwnWithAuthor = await evalIn(
      ctxAlice,
      `(() => { const arts=[...document.querySelectorAll('.lg-message')]; const m=arts.find(a=>a.innerText.includes(${JSON.stringify(contentA)})); return m ? m.querySelector('.lg-message__meta span').textContent : null })()`,
    ) === 'alice'

    // bob must see it via polling WITHOUT reload
    const bobSeen = await waitFor(
      ctxBob,
      `(() => { const arts=[...document.querySelectorAll('.lg-message')]; const m=arts.find(a=>a.innerText.includes(${JSON.stringify(contentA)})); return m ? m.querySelector('.lg-message__meta span').textContent : '' })()`,
      10000,
      'bob poll sees alice message + author',
    )
    results.checks.bobSawAliceMessageWithAuthor = bobSeen === 'alice'
    log(`# bob saw alice message, author=${JSON.stringify(bobSeen)}`)

    // @bot from bob; the assistant reply appears (bob's own context) and is
    // then shared to alice via polling.
    const assistantBefore = await evalIn(ctxBob, `document.querySelectorAll('.lg-message--assistant').length`)
    const botPrompt = `@bot hello from bob ${Date.now()}`
    r = await evalIn(ctxBob, sendJs(botPrompt))
    log(`# bob @bot send -> ${r}`)
    const assistantAfter = await waitFor(
      ctxBob,
      `document.querySelectorAll('.lg-message--assistant').length > ${assistantBefore} ? document.querySelectorAll('.lg-message--assistant').length : 0`,
      20000,
      'assistant reply visible',
    )
    results.checks.botReplyVisible = assistantAfter > assistantBefore
    // alice's own tab pauses polling while hidden (document.hidden guard in useChat),
    // which is real product behaviour. Activate it, then verify shared delivery.
    await bidi.send('browsingContext.activate', { context: ctxAlice }, 8000).catch(() => {})
    const aliceSeesReply = await waitFor(
      ctxAlice,
      `document.querySelectorAll('.lg-message--assistant').length >= ${assistantAfter} ? 'shared' : ''`,
      12000,
      'alice sees assistant reply',
    )
    results.checks.aliceSeesBotReply = aliceSeesReply === 'shared'
    const assistantAuthors = JSON.parse(await evalIn(ctxAlice, `JSON.stringify([...document.querySelectorAll('.lg-message--assistant .lg-message__meta span')].map(s=>s.textContent).slice(-3))`))
    results.checks.botReplyAuthor = Array.isArray(assistantAuthors) && (assistantAuthors.includes('bot') || assistantAuthors.includes('Bot'))
    log(`# assistant before=${assistantBefore} after=${assistantAfter} aliceSees=${aliceSeesReply} authors=${JSON.stringify(assistantAuthors)}`)

    // alice signs out; bob's independent session must remain valid
    await evalIn(ctxAlice, `document.querySelector('.lg-topbar__logout').click(); 'clicked'`)
    await waitFor(ctxAlice, `document.querySelector('.lg-auth__card') ? 'login' : ''`, 12000, 'alice login gate after logout')
    results.checks.aliceLogoutShowsGate = true
    const bobStillIn = await evalIn(ctxBob, `document.querySelector('.lg-topbar__identity-user') ? document.querySelector('.lg-topbar__identity-user').textContent : ''`)
    results.checks.bobSessionIndependent = bobStillIn === 'bob'
    log(`# after alice logout, bob identity=${JSON.stringify(bobStillIn)}`)

    results.checks.browserOk = true
    ws.close()
    results.ok = Object.values(results.checks).every(Boolean)
  } catch (err) {
    results.error = String(err && err.message ? err.message : err)
    log(`# ERROR: ${results.error}`)
  } finally {
    cleanup()
    if (!ARGS.keep) { try { rmSync(profile, { recursive: true, force: true }) } catch { /* ignore */ } }
  }
  log('RESULT ' + JSON.stringify(results))
  process.exit(results.ok ? 0 : 1)
}

async function freePort() {
  return await new Promise((res, rej) => {
    const s = net.createServer()
    s.on('error', rej)
    s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)) })
  })
}

main().catch((e) => { console.error('fatal', e); cleanup(); process.exit(2) })
