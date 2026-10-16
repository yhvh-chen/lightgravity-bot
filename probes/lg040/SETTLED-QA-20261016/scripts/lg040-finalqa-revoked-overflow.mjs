#!/usr/bin/env node
/**
 * lg040-finalqa-revoked-overflow.mjs — LG-040 FINAL-QA.
 *
 * Decisive reproduction of the retest driver's step-H overflow observation:
 * the retest driver reached 390px Files/Materials AFTER it had locally revoked
 * honest_table_grid_scale4.png and selected that revoked source in the UI
 * (step F 'uiRevoked'). We reproduce that exact preceding state, then run the
 * step-H click sequence and measure doc scrollWidth + offenders.
 *
 * Read-only on product; 0 model calls (deny proxy).
 */

import { spawn } from 'node:child_process'
import net from 'node:net'
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

function parseArgs(argv) {
  const out = { url: null, out: '/tmp/lg040-revoked-overflow', deadlineMs: 90000,
    firefox: process.env.FIREFOX_BIN || '/snap/bin/firefox', profileDir: null }
  for (let i = 2; i < argv.length; i++) { const a = argv[i]; const next = () => argv[++i]
    if (a === '--url') out.url = next(); else if (a === '--out') out.out = next()
    else if (a === '--deadline-ms') out.deadlineMs = Number(next())
    else if (a === '--firefox') out.firefox = next(); else if (a === '--profile-dir') out.profileDir = next()
    else throw new Error(`unknown arg: ${a}`) }
  if (!out.url) throw new Error('--url is required'); if (!out.url.endsWith('/')) out.url += '/'
  return out
}
const ARGS = parseArgs(process.argv); const log = (...m) => console.log(...m)
const MARKER = `lg040ro-${process.pid}`; let childPid = null
function cleanup() { if (childPid == null) return
  try { const cmd = readFileSync(`/proc/${childPid}/cmdline`, 'utf8')
    if (cmd.includes(MARKER) && cmd.includes('firefox')) { process.kill(-childPid, 'SIGTERM')
      const t0 = Date.now(); while (Date.now() - t0 < 1500) { try { process.kill(-childPid, 0) } catch { return } const e=Date.now()+40; while(Date.now()<e){} }
      process.kill(-childPid, 'SIGKILL') } } catch { /* gone */ } }
process.on('exit', cleanup); process.on('SIGINT', () => { cleanup(); process.exit(130) })
process.on('SIGTERM', () => { cleanup(); process.exit(143) })

class Bidi { constructor(ws) { this.ws=ws; this.nextId=1; this.pending=new Map()
  ws.addEventListener('message', (ev) => { let msg; try { msg=JSON.parse(typeof ev.data==='string'?ev.data:ev.data.toString()) } catch { return }
    if (msg.id!==undefined && this.pending.has(msg.id)) { const {resolve,reject}=this.pending.get(msg.id); this.pending.delete(msg.id)
      if (msg.type==='error') reject(new Error(`${msg.error}: ${msg.message}`)); else resolve(msg.result) } }) }
  send(method, params={}, timeoutMs=8000) { const id=this.nextId++
    return new Promise((resolve,reject)=>{ const timer=setTimeout(()=>{this.pending.delete(id);reject(new Error(`timeout ${method}`))},timeoutMs)
      this.pending.set(id,{resolve:(r)=>{clearTimeout(timer);resolve(r)},reject:(e)=>{clearTimeout(timer);reject(e)}}); this.ws.send(JSON.stringify({id,method,params})) }) } }
function connect(url, timeoutMs) { return new Promise((resolve,reject)=>{ const ws=new WebSocket(url); const timer=setTimeout(()=>reject(new Error('ws connect timeout')),timeoutMs)
  ws.addEventListener('open',()=>{clearTimeout(timer);resolve(ws)}); ws.addEventListener('error',(e)=>{clearTimeout(timer);reject(new Error('ws error: '+(e.message||'unknown')))}) }) }
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
async function evalJs(bidi, context, expression, timeoutMs = 20000) {
  const wrapped = `(async () => { const v = await (${expression}); return JSON.stringify(v === undefined ? null : v); })()`
  const res = await bidi.send('script.evaluate', { expression: wrapped, target: { context }, awaitPromise: true, resultOwnership: 'none' }, timeoutMs)
  if (res.type === 'exception') throw new Error(`eval exception: ${res.exceptionDetails?.text ?? JSON.stringify(res.exceptionDetails)}`)
  const raw = res.result ? res.result.value : undefined; try { return raw == null ? raw : JSON.parse(raw) } catch { return raw }
}
async function apiPost(url, payload) { const r = await fetch(url, { method:'POST', headers:{'Content-Type':'application/json',Accept:'application/json'}, body: JSON.stringify(payload) })
  const text = await r.text(); let body=null; try { body=JSON.parse(text) } catch { body=text.slice(0,300) }; return { status:r.status, body } }

const OVERFLOW = `(() => {
  const vw = window.innerWidth; const limit = vw + 2; const offenders = [];
  for (const el of document.querySelectorAll('body *')) {
    const r = el.getBoundingClientRect(); if (r.width === 0 && r.height === 0) continue;
    if (r.right > limit || el.scrollWidth > el.clientWidth + 2) { const cs = getComputedStyle(el);
      offenders.push({ tag: el.tagName.toLowerCase(), cls: (typeof el.className==='string'?el.className:''),
        rect:{x:Math.round(r.x),right:Math.round(r.right),width:Math.round(r.width)}, scrollW:el.scrollWidth, clientW:el.clientWidth,
        minWidth:cs.minWidth, display:cs.display, overflowX:cs.overflowX }); } }
  return { innerWidth: vw, docScrollWidth: document.documentElement.scrollWidth, overflow: document.documentElement.scrollWidth > limit,
    nOffenders: offenders.length, offenders: offenders.slice(0,50) };
})()`

async function main() {
  const deadline = Date.now() + ARGS.deadlineMs; const outDir = ARGS.out; mkdirSync(outDir, { recursive: true })
  const profileRoot = ARGS.profileDir || tmpdir(); mkdirSync(profileRoot, { recursive: true })
  const profile = mkdtempSync(join(profileRoot, `${MARKER}-`))
  const port = await new Promise((res, rej) => { const s=net.createServer(); s.on('error',rej); s.listen(0,'127.0.0.1',()=>{const p=s.address().port; s.close(()=>res(p))}) })
  const child = spawn(ARGS.firefox, ['--headless','--no-remote',`--profile=${profile}`,`--remote-debugging-port=${port}`,'--no-first-run','about:blank'], { detached:true, stdio:['ignore','ignore','ignore'] })
  childPid = child.pid
  const wsUrl = `ws://127.0.0.1:${port}/session`; let up=false
  while (Date.now() < deadline && !up) { up = await new Promise((res)=>{ const s=new net.Socket(); s.setTimeout(800)
    s.once('connect',()=>{s.destroy();res(true)}); s.once('timeout',()=>{s.destroy();res(false)}); s.once('error',()=>{res(false)}); s.connect(port,'127.0.0.1') })
    if (!up) await sleep(300) }
  if (!up) throw new Error('firefox BiDi port never became reachable')
  const ws = await connect(wsUrl, 8000); const bidi = new Bidi(ws)
  await bidi.send('session.new', { capabilities: { alwaysMatch: {} } }, 8000)
  const tree = await bidi.send('browsingContext.getTree', {}); let context = tree.contexts[0]?.context
  if (!context) { const c = await bidi.send('browsingContext.create', { type: 'tab' }); context = c.context }
  await bidi.send('browsingContext.navigate', { context, url: ARGS.url, wait: 'complete' }, 25000); await sleep(2000)
  const shot = async (name,w,h) => { await bidi.send('browsingContext.setViewport',{context,viewport:{width:w,height:h}}).catch(()=>{}); await sleep(500)
    const png = await bidi.send('browsingContext.captureScreenshot',{context}); writeFileSync(join(outDir,name),Buffer.from(png.data,'base64')) }

  const report = {}
  const srcPng = 'source_01M51N3TRHB3Y5KQ5SAPSBEFRB'
  // 1. Revoke on OWN copy (as retest step F).
  report.revoke = await apiPost(`${ARGS.url}api/v1/sources/${srcPng}/actions`, { action:'revoke', confirmed:true })

  // 2. Go to Files->Materials (desktop), select the REVOKED source (as step F uiRevoked).
  await bidi.send('browsingContext.setViewport', { context, viewport: { width: 1440, height: 900 } }).catch(()=>{})
  await sleep(400)
  report.selectRevoked = await evalJs(bidi, context, `(async () => {
    const f = [...document.querySelectorAll('button[aria-label]')].find(b => b.getAttribute('aria-label') === 'Files');
    if (f) f.click();
    for (let i=0;i<60;i++){ await new Promise(r=>setTimeout(r,150)); const m=[...document.querySelectorAll('button')].find(b=>b.textContent.trim()==='Materials'); if(m){m.click();break;} }
    for (let i=0;i<60;i++){ await new Promise(r=>setTimeout(r,150)); if(document.querySelector('.lg-files-materials__facts')) break; }
    const entries=[...document.querySelectorAll('button.lg-files__entry')];
    const e=entries.find(el=>el.textContent.includes('honest_table_grid'));
    if (e) e.click();
    for (let i=0;i<60;i++){ await new Promise(r=>setTimeout(r,150)); if(document.querySelector('.lg-files-materials__facts')) break; }
    await new Promise(r=>setTimeout(r,500));
    return { entries: entries.length, selectedRevoked: !!e };
  })()`)

  // 3. Go to Chat (as step H does) then back to Files->Materials at 390, EXACT timing.
  report.chatThenNarrow = await evalJs(bidi, context, `(async () => {
    const chat=[...document.querySelectorAll('button[aria-label]')].find(b=>b.getAttribute('aria-label')==='Chat'); if(chat) chat.click();
    for(let i=0;i<40;i++){ await new Promise(r=>setTimeout(r,150)); if(document.querySelector('input[aria-label="Search materials"]')) break; }
    return true;
  })()`)
  await shot('revoked-overflow-01-chat-390.png', 390, 900)
  await evalJs(bidi, context, `(async () => {
    const f=[...document.querySelectorAll('button[aria-label]')].find(b=>b.getAttribute('aria-label')==='Files'); if(f) f.click();
    for(let i=0;i<40;i++){ await new Promise(r=>setTimeout(r,150)); const m=[...document.querySelectorAll('button')].find(b=>b.textContent.trim()==='Materials'); if(m){m.click();break;} }
    await new Promise(r=>setTimeout(r,500));
    return true;
  })()`, 30000)
  report.stepH_exact_390 = await evalJs(bidi, context, OVERFLOW, 25000)
  report.stepH_dom = await evalJs(bidi, context, `(() => ({ materials: !!document.querySelector('.lg-files-materials'), entries: document.querySelectorAll('button.lg-files__entry').length, hasFacts: !!document.querySelector('.lg-files-materials__facts'), bodyText: (document.querySelector('.lg-files-materials')?.innerText||'').slice(0,200) }))()`)
  await shot('revoked-overflow-02-stepH-390.png', 390, 900)

  // 4. Wait longer and re-measure (does it settle?).
  await sleep(1500)
  report.stepH_settled_390 = await evalJs(bidi, context, OVERFLOW, 25000)

  writeFileSync(join(outDir, 'revoked-overflow.json'), JSON.stringify(report, null, 2))
  log(JSON.stringify({ revokeStatus: report.revoke?.status, selectRevoked: report.selectRevoked,
    stepH: { overflow: report.stepH_exact_390.overflow, docScrollW: report.stepH_exact_390.docScrollWidth, dom: report.stepH_dom },
    settled: { overflow: report.stepH_settled_390.overflow, docScrollW: report.stepH_settled_390.docScrollWidth },
    offendersH: report.stepH_exact_390.offenders.slice(0,6), offendersSettled: report.stepH_settled_390.offenders.slice(0,6) }, null, 2))
  ws.close(); rmSync(profile, { recursive: true, force: true })
}
main().catch((err) => { console.error('ERROR', err); process.exitCode = 1 }).finally(cleanup)
