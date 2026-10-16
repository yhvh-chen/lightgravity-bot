#!/usr/bin/env node
/**
 * LG-047 R2 — critical first flow in a REAL Firefox (WebDriver BiDi).
 *
 * English user path:
 *   Chat global upload (real <input type=file>, fixture bytes over the
 *   evidence-only loopback route) of alpha-brief.txt (human SAMPLE text)
 *   -> native auto-extract (no OCR) receipt `success`/`extracted`
 *   -> select alpha in the real selected-material picker
 *   -> ask an English fact question
 *   -> real DeepSeek direct answer (1 product call)
 *   -> answer contains the fixture facts and NOT the decoy facts
 *   -> the reply `Sources` block renders (provided context, not verified)
 *   -> reload: history keeps BOTH the assistant answer AND the same Sources
 *   -> click `Open in Files` in Sources: Files opens the real material.
 *
 * The browser reconstructs genuine File objects from the frozen fixture bytes
 * served by the launcher; no network mocking.
 */

import { spawn } from 'node:child_process'
import net from 'node:net'
import { mkdirSync, mkdtempSync, readFileSync, readlinkSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

function parseArgs(argv) {
  const out = { url: null, out: '/tmp/lg047r2-chat', deadlineMs: 240000,
    firefox: process.env.FIREFOX_BIN || '/snap/bin/firefox', profileDir: null }
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i]; const next = () => argv[++i]
    if (a === '--url') out.url = next()
    else if (a === '--out') out.out = next()
    else if (a === '--deadline-ms') out.deadlineMs = Number(next())
    else if (a === '--firefox') out.firefox = next()
    else if (a === '--profile-dir') out.profileDir = next()
    else throw new Error(`unknown arg: ${a}`)
  }
  if (!out.url) throw new Error('--url is required')
  if (!out.url.endsWith('/')) out.url += '/'
  return out
}

const ARGS = parseArgs(process.argv)
const log = (...m) => console.log(...m)
const MARKER = `lg047r2-${process.pid}`
let childPid = null

function cleanup() {
  if (childPid == null) return
  try {
    const cmd = readFileSync(`/proc/${childPid}/cmdline`, 'utf8')
    if (cmd.includes(MARKER) && cmd.includes('firefox')) {
      process.kill(-childPid, 'SIGTERM')
      const t0 = Date.now()
      while (Date.now() - t0 < 1500) { try { process.kill(-childPid, 0) } catch { return } awaitSleep(40) }
      process.kill(-childPid, 'SIGKILL')
    }
  } catch { /* gone */ }
}
function awaitSleep(ms) { const end = Date.now() + ms; while (Date.now() < end) {} }
process.on('exit', cleanup)
process.on('SIGINT', () => { cleanup(); process.exit(130) })
process.on('SIGTERM', () => { cleanup(); process.exit(143) })

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
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

// snap Firefox is confined to $HOME/snap/firefox/<rev>/ and CANNOT use a /tmp
// or ~/.cache profile (it exits with "Could not find profile folder" or
// "Firefox is already running"). Resolve a snap-accessible profile root.
function defaultProfileRoot() {
  const home = process.env.HOME || tmpdir()
  const snapRoot = join(home, 'snap', 'firefox')
  try {
    const cur = readlinkSync(join(snapRoot, 'current')).trim()
    const rev = join(snapRoot, cur)
    mkdirSync(rev, { recursive: true })
    return rev
  } catch { /* not snap / no current symlink */ }
  return join(home, '.mozilla', 'firefox', 'lg047r2-profiles')
}
function connect(url, timeoutMs) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(url)
    const timer = setTimeout(() => reject(new Error('ws connect timeout')), timeoutMs)
    ws.addEventListener('open', () => { clearTimeout(timer); resolve(ws) })
    ws.addEventListener('error', (e) => { clearTimeout(timer); reject(new Error('ws error: ' + (e.message || 'unknown'))) })
  })
}
async function evalJs(bidi, context, expression, timeoutMs = 20000) {
  const wrapped = `(async () => { const v = await (${expression}); return JSON.stringify(v === undefined ? null : v); })()`
  const res = await bidi.send('script.evaluate', {
    expression: wrapped, target: { context }, awaitPromise: true, resultOwnership: 'none',
  }, timeoutMs)
  if (res.type === 'exception') throw new Error(`eval exception: ${res.exceptionDetails?.text ?? JSON.stringify(res.exceptionDetails)}`)
  const raw = res.result ? res.result.value : undefined
  try { return raw == null ? raw : JSON.parse(raw) } catch { return raw }
}
async function apiGet(url) {
  const r = await fetch(url, { headers: { Accept: 'application/json' } })
  const text = await r.text(); let body; try { body = JSON.parse(text) } catch { body = text.slice(0, 400) }
  return { status: r.status, body }
}

async function main() {
  const deadline = Date.now() + ARGS.deadlineMs
  const outDir = ARGS.out; mkdirSync(outDir, { recursive: true })
  const results = []
  const record = (name, ok, detail) => {
    results.push({ name, ok: !!ok, detail: detail === undefined ? null : detail })
    log(`${ok ? 'PASS' : 'FAIL'} ${name}${detail !== undefined ? ' :: ' + JSON.stringify(detail).slice(0, 500) : ''}`)
  }

  const factsPath = process.env.LG047R2_FACTS || new URL('../../../../examples/selected-material-prototype/expected-facts.json', import.meta.url).pathname
  const facts = JSON.parse(readFileSync(factsPath))
  const alphaFacts = facts.fixtures['alpha-brief.txt']
  const decoyFacts = Object.entries(facts.fixtures['gamma-decoy.txt']).filter(([, v]) => typeof v === 'string')
  const required = ['ORION-71', 'Halden Reyes', '2027-03-14', '418,250', 'PRJ-ORION-71', 'CB-8842']

  const profileRoot = ARGS.profileDir || process.env.LG047R2_PROFILE_DIR || defaultProfileRoot()
  mkdirSync(profileRoot, { recursive: true })
  const profile = mkdtempSync(join(profileRoot, `${MARKER}-`))
  const port = await new Promise((res, rej) => {
    const s = net.createServer(); s.on('error', rej)
    s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)) })
  })
  const child = spawn(ARGS.firefox, [
    '--headless', '--no-remote', `--profile=${profile}`,
    `--remote-debugging-port=${port}`, '--no-first-run', 'about:blank',
  ], { detached: true, stdio: ['ignore', 'ignore', 'pipe'] })
  childPid = child.pid
  let ffErr = ''
  child.stderr.on('data', (d) => { ffErr += d.toString(); if (ffErr.length > 4000) ffErr = ffErr.slice(-4000) })

  const wsUrl = `ws://127.0.0.1:${port}/session`
  let up = false
  const launchDeadline = Math.min(deadline, Date.now() + 30000)
  while (Date.now() < launchDeadline && !up) {
    up = await new Promise((res) => {
      const s = new net.Socket(); s.setTimeout(800)
      s.once('connect', () => { s.destroy(); res(true) })
      s.once('timeout', () => { s.destroy(); res(false) })
      s.once('error', () => { res(false) })
      s.connect(port, '127.0.0.1')
    })
    if (!up) await sleep(300)
  }
  if (!up) throw new Error(`firefox BiDi port never reachable (profile=${profile}, bin=${ARGS.firefox}); firefox stderr: ${ffErr.trim() || '(none)'}`)

  const ws = await connect(wsUrl, 8000)
  const bidi = new Bidi(ws)
  await bidi.send('session.new', { capabilities: { alwaysMatch: {} } }, 8000)
  const tree = await bidi.send('browsingContext.getTree', {})
  let context = tree.contexts[0]?.context
  if (!context) { const c = await bidi.send('browsingContext.create', { type: 'tab' }); context = c.context }
  await bidi.send('browsingContext.navigate', { context, url: ARGS.url, wait: 'complete' }, 30000)
  await sleep(2500)

  const realDoc = await evalJs(bidi, context, `location.origin`)
  record('real same-origin document', realDoc === ARGS.url.replace(/\/$/, ''), { origin: realDoc })

  const genBefore = await apiGet(`${ARGS.url}_lg047r2_generation`)
  log('generation before:', JSON.stringify(genBefore.body))

  // Install helpers: real file upload from the loopback fixture route.
  await evalJs(bidi, context, `(() => {
    window.__lgSetTextFile = async (name, bytesUrl, mediaType) => {
      const resp = await fetch(bytesUrl, { cache: 'no-store' });
      const buf = await resp.arrayBuffer();
      const file = new File([buf], name, { type: mediaType || 'text/plain' });
      window.__lgLastBytes = buf.byteLength;
      const input = document.querySelector('input[type=file][aria-label="Upload files to this conversation"]');
      if (!input) throw new Error('no chat file input');
      const dt = new DataTransfer();
      dt.items.add(file);
      input.files = dt.files;
      input.dispatchEvent(new Event('change', { bubbles: true }));
      return { bytes: buf.byteLength, name, type: file.type };
    };
    return true;
  })()`)

  const fixtureStatus = await evalJs(bidi, context, `fetch('/_lg047r2_fixture/alpha-brief.txt',{cache:'no-store'}).then(r=>r.status)`)
  record('fixture byte route reachable from page', fixtureStatus === 200, { status: fixtureStatus })
  const fixtureSha = await evalJs(bidi, context, `(async () => {
    const r = await fetch('/_lg047r2_fixture/alpha-brief.txt',{cache:'no-store'});
    const b = await r.arrayBuffer();
    const d = await crypto.subtle.digest('SHA-256', b);
    return [...new Uint8Array(d)].map(x=>x.toString(16).padStart(2,'0')).join('');
  })()`)
  const fixtureShaExpect = await evalJs(bidi, context, `fetch('/_lg047r2_fixture/alpha-brief.txt',{cache:'no-store'}).then(r=>r.headers.get('X-LG047R2-Fixture-Sha256'))`)
  record('fixture bytes hash-verified from page', fixtureSha === fixtureShaExpect, { sha: fixtureSha, header: fixtureShaExpect })

  const shot = async (name, width, height) => {
    await bidi.send('browsingContext.setViewport', { context, viewport: { width, height } }).catch(() => {})
    await sleep(400)
    const png = await bidi.send('browsingContext.captureScreenshot', { context })
    writeFileSync(join(outDir, name), Buffer.from(png.data, 'base64'))
  }

  await bidi.send('browsingContext.setViewport', { context, viewport: { width: 1440, height: 900 } }).catch(() => {})
  await sleep(300)

  // --- B1: real UI upload of alpha (global chat) ---
  const upRes = await evalJs(bidi, context, `window.__lgSetTextFile('alpha-brief.txt', '/_lg047r2_fixture/alpha-brief.txt', 'text/plain')`)
  record('B1 upload alpha via real <input type=file>', upRes.bytes > 0, upRes)
  const rec = await evalJs(bidi, context, `(async () => {
    for (let i = 0; i < 120; i++) {
      await new Promise(r => setTimeout(r, 200));
      const items = [...document.querySelectorAll('.lg-materials__item')];
      const item = items.find(el => el.innerText.includes('alpha-brief.txt'));
      if (item) {
        const t = item.innerText;
        const m = t.match(/source_[A-Za-z0-9]+/);
        if (m && /success|extracted|indexed/.test(t)) return { text: t, sourceId: m[0], done: true };
        if (/failed|unauthorized/i.test(t)) return { text: t, failed: true };
      }
    }
    return { text: (document.querySelector('.lg-materials')?.innerText || 'none'), timeout: true };
  })()`, 60000)
  record('B1 receipt reaches native extracted/success (no OCR)', rec.done && !rec.failed, rec)
  const sid = rec.sourceId

  // Read the real source object from the API (from the page context, same origin)
  const srcInfo = sid ? await evalJs(bidi, context,
    `fetch('/api/v1/sources/${sid}').then(r=>r.json()).then(j=>({status:j.status||j.source?.status, version:j.source_version||j.source?.source_version, hash:j.content_hash||j.source?.content_hash}))`) : null
  record('B1 source has a real version+hash', !!(srcInfo && srcInfo.version != null && srcInfo.hash), srcInfo)

  const contentRead = sid ? await evalJs(bidi, context,
    `fetch('/api/v1/sources/${sid}/content?kind=auto').then(r=>r.json()).then(j=>({kind:j.kind, chars:(j.content||'').length, orion:(j.content||'').includes('ORION-71'), extractor:j.extractor||j.model_version||null}))`) : null
  record('B1 GET content returns the native body (noqa fixture)', !!(contentRead && contentRead.orion), contentRead)

  // --- B2: select the FRESHLY UPLOADED alpha source in the real picker ---
  // The picker is a checkbox list; select by the fresh source id (a prior run
  // leaves an older alpha-brief.txt source with a different id, so title alone
  // is ambiguous). Verify the resulting chip carries the fresh id.
  const picker = await evalJs(bidi, context, `(async () => {
    const btn = [...document.querySelectorAll('button')].find(b => /Select materials/.test(b.textContent));
    if (!btn) return { ok:false, reason:'no select button' };
    btn.click();
    const targetId = ${JSON.stringify(sid)};
    for (let i = 0; i < 80; i++) {
      await new Promise(r => setTimeout(r, 200));
      const boxes = [...document.querySelectorAll('.lg-source-picker__list input[type=checkbox]')];
      // Prefer the checkbox whose item text carries the fresh source id.
      let cb = boxes.find(b => { const li = b.closest('li'); return li && li.innerText.includes(targetId); });
      if (!cb) {
        // Fallback: first alpha-brief.txt checkbox that is selectable (not disabled/checked).
        cb = boxes.find(b => { const li = b.closest('li'); return li && /alpha-brief\.txt/.test(li.innerText) && !b.disabled && !b.checked; });
      }
      if (cb) {
        cb.click();
        for (let j = 0; j < 30; j++) {
          await new Promise(r => setTimeout(r, 100));
          const chips = [...document.querySelectorAll('.lg-source-picker__chips .lg-chip')];
          const chip = chips.find(c => c.innerText.includes(targetId)) || chips.find(c => /alpha-brief/.test(c.innerText));
          if (chips.length > 0) return { ok:true, chips: chips.length, chipText: chip ? chip.innerText : null,
            hasFreshId: chips.some(c => c.innerText.includes(targetId)),
            text: document.querySelector('.lg-source-picker')?.innerText?.slice(0,400) };
        }
        return { ok:false, reason:'chip never appeared after click', text: document.querySelector('.lg-source-picker')?.innerText?.slice(0,400) };
      }
    }
    return { ok:false, reason:'fresh alpha checkbox not found', targetId, text: document.querySelector('.lg-source-picker')?.innerText?.slice(0,400) };
  })()`, 40000)
  record('B2 fresh alpha selected in real picker (chip carries fresh source id)',
    picker.ok && picker.chips >= 1 && picker.hasFreshId === true, picker)
  await shot('01-chat-selected-1440.png', 1440, 900)

  // --- B3: ask the English fact question ---
  // NOTE: the product's deterministic classifier routes messages containing
  // decision/control/status/retry keywords (e.g. "approve" inside "approved",
  // "accept", "status", "budget" is fine but "approved" is not) to
  // control/clarify instead of a direct answer. This is expected product
  // behaviour; the QA question is worded to classify as a plain question.
  const question = 'From the selected brief only, what is the project code name, the programme owner, the primary launch date, and the total budget? Reply in one short line.'
  const sendInfo = await evalJs(bidi, context, `(async () => {
    const ta = document.querySelector('.lg-chat__footer textarea') || [...document.querySelectorAll('textarea')].pop();
    if (!ta) return { ok:false, reason:'no textarea' };
    const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
    setter.call(ta, ${JSON.stringify(question)});
    ta.dispatchEvent(new Event('input', { bubbles: true }));
    await new Promise(r=>setTimeout(r,150));
    const sendBtn = document.querySelector('.lg-chat__footer .lg-button--primary') || [...document.querySelectorAll('button')].find(b=>/^Send/.test(b.textContent));
    if (!sendBtn) return { ok:false, reason:'no send button' };
    sendBtn.click();
    return { ok:true };
  })()`)
  record('B3 question submitted', sendInfo.ok, sendInfo)

  // Wait for a real assistant answer containing ORION-71 (or an error envelope)
  const answer = await evalJs(bidi, context, `(async () => {
    for (let i = 0; i < 300; i++) {
      await new Promise(r => setTimeout(r, 500));
      const bubbles = [...document.querySelectorAll('.lg-message--assistant .lg-message__bubble')];
      const texts = bubbles.map(b => b.innerText);
      const hit = texts.find(t => /ORION-71/.test(t));
      if (hit) return { text: hit, all: texts };
      const err = document.querySelector('.lg-notice--error');
      if (err && /error|failed|budget|429/i.test(err.innerText)) return { error: err.innerText, all: texts };
    }
    const bubbles = [...document.querySelectorAll('.lg-message--assistant .lg-message__bubble')];
    return { text: bubbles.map(b=>b.innerText).join('\\n---\\n'), all: bubbles.map(b=>b.innerText), timeout:true };
  })()`, 200000)
  record('B3 real assistant answer returned', !!answer.text && !answer.error, { text: (answer.text||'').slice(0, 400), error: answer.error })

  const finalText = (answer.text || '')
  const missing = required.filter((f) => !finalText.includes(f))
  record('B3 answer contains all required fixture facts', missing.length === 0, { missing })
  const decoyLeak = decoyFacts.filter(([, v]) => typeof v === 'string' && v.length > 3 && finalText.includes(v)).map(([k]) => k)
  record('B3 answer contains NO decoy facts', decoyLeak.length === 0, { decoyLeak })

  // --- B4: Sources block in the reply ---
  const sourcesBlock = await evalJs(bidi, context, `(() => {
    const s = document.querySelector('.lg-chat-sources');
    if (!s) return null;
    return { text: s.innerText, title: s.querySelector('.lg-chat-sources__title')?.innerText,
      badge: s.querySelector('.lg-chat-sources__header .lg-status-badge, .lg-chat-sources__header span:nth-child(2)')?.innerText,
      note: s.querySelector('.lg-chat-sources__note')?.innerText,
      hasFilesLink: [...s.querySelectorAll('button')].some(b=>/Open in Files/.test(b.textContent)) };
  })()`)
  record('B4 Sources block renders (provided context, not verified)',
    !!sourcesBlock && /Sources/.test(sourcesBlock.title || '') &&
    /not span-verified/i.test(sourcesBlock.note || '') &&
    !/verified citation/i.test(sourcesBlock.text || '') && sourcesBlock.hasFilesLink,
    sourcesBlock)
  await shot('02-chat-answer-sources-1440.png', 1440, 900)

  const genAfter = await apiGet(`${ARGS.url}_lg047r2_generation`)
  log('generation after:', JSON.stringify(genAfter.body))

  // --- B5: reload keeps BOTH assistant answer AND the same Sources ---
  await bidi.send('browsingContext.navigate', { context, url: ARGS.url, wait: 'complete' }, 30000)
  await sleep(2500)
  const afterReload = await evalJs(bidi, context, `(async () => {
    for (let i = 0; i < 60; i++) {
      await new Promise(r => setTimeout(r, 300));
      const bubbles = [...document.querySelectorAll('.lg-message--assistant .lg-message__bubble')];
      const hit = bubbles.find(b => /ORION-71/.test(b.innerText));
      const src = document.querySelector('.lg-chat-sources');
      if (hit && src) return { text: hit.innerText, sourcesText: src.innerText,
        sourcesCount: document.querySelectorAll('.lg-chat-sources__item').length,
        answerCount: bubbles.filter(b=>/ORION-71/.test(b.innerText)).length };
    }
    const bubbles = [...document.querySelectorAll('.lg-message--assistant .lg-message__bubble')];
    return { text: bubbles.map(b=>b.innerText).join('|').slice(0,300), sourcesText: document.querySelector('.lg-chat-sources')?.innerText||null };
  })()`, 40000)
  record('B5 reload keeps assistant answer (exactly one)', /ORION-71/.test(afterReload.text || '') && afterReload.answerCount === 1, afterReload)
  record('B5 reload keeps the same Sources (>=1, alpha)',
    (afterReload.sourcesCount || 0) >= 1 && /alpha|source_/.test(afterReload.sourcesText || ''), afterReload)
  record('B5 no duplicate answer after reload', afterReload.answerCount === 1, { answerCount: afterReload.answerCount })
  await shot('03-chat-reload-history-1440.png', 1440, 900)

  // --- B6: Sources "Open in Files" opens the real material ---
  const openFiles = await evalJs(bidi, context, `(async () => {
    const src = document.querySelector('.lg-chat-sources');
    const btn = src && [...src.querySelectorAll('button')].find(b=>/Open in Files/.test(b.textContent));
    if (!btn) return { ok:false, reason:'no open-in-files button' };
    btn.click();
    for (let i = 0; i < 80; i++) {
      await new Promise(r => setTimeout(r, 250));
      const body = document.body.innerText;
      const hasMaterials = !!document.querySelector('.lg-files-materials') || /Materials/.test(body);
      const hasAlpha = /alpha-brief/.test(body);
      if (hasMaterials && hasAlpha) return { ok:true, hasAlpha, url: location.href, text: body.slice(0, 400) };
    }
    return { ok:false, url: location.href, text: document.body.innerText.slice(0, 400) };
  })()`, 40000)
  record('B6 Open in Files navigates to real material', openFiles.ok, openFiles)
  await shot('04-files-from-sources-1440.png', 1440, 900)

  // --- B7: geometry checks 390 / 1024 / 1440 + 1440->390 overshoot ---
  const geo = {}
  for (const [w, h] of [[1440, 900], [1024, 800], [390, 844]]) {
    await bidi.send('browsingContext.setViewport', { context, viewport: { width: w, height: h } }).catch(() => {})
    await sleep(500)
    geo[w] = await evalJs(bidi, context, `(() => {
      const de = document.documentElement;
      const overflow = de.scrollWidth - de.clientWidth;
      const nav = document.querySelector('.lg-nav, nav');
      const chat = document.querySelector('.lg-chat');
      const clipped = [...document.querySelectorAll('.lg-chat__footer button, .lg-chat__footer textarea')]
        .filter(el => { const r = el.getBoundingClientRect(); return r.width < 8 || r.height < 8 }).length;
      return { overflow, navVisible: !!nav, chatVisible: !!chat, clipped, scrollWidth: de.scrollWidth, clientWidth: de.clientWidth };
    })()`)
    record(`B7 width ${w} no horizontal overflow`, geo[w].overflow <= 0, geo[w])
    await shot(`05-width-${w}.png`, w, h)
  }
  // 1440 -> 390 transition overshoot (max overshoot 0) + readiness <= 2s
  await bidi.send('browsingContext.setViewport', { context, viewport: { width: 1440, height: 900 } }).catch(() => {})
  await sleep(600)
  const t0 = Date.now()
  await bidi.send('browsingContext.setViewport', { context, viewport: { width: 390, height: 844 } }).catch(() => {})
  let readiness = null
  for (let i = 0; i < 40; i++) {
    await sleep(50)
    const r = await evalJs(bidi, context, `({ o: document.documentElement.scrollWidth - document.documentElement.clientWidth })`)
    if (r.o <= 0) { readiness = Date.now() - t0; break }
  }
  record('B7 1440->390 transition settles (max overshoot 0) <=2s',
    readiness != null && readiness <= 2000, { readinessMs: readiness })

  writeFileSync(join(outDir, 'flow_chat.json'), JSON.stringify({ results, genBefore: genBefore.body, genAfter: genAfter.body, sid, srcInfo, contentRead, sourcesBlock, required, missing, decoyLeak }, null, 2))
  const fails = results.filter(r => !r.ok)
  log(`\nSUMMARY: ${results.length - fails.length}/${results.length} pass; fails: ${fails.map(f=>f.name).join(', ') || 'none'}`)
  process.exitCode = fails.length ? 1 : 0
}

main().catch((e) => { console.error('FATAL', e); cleanup(); process.exit(2) })
