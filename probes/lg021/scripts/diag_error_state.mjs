#!/usr/bin/env node
/** Focused diagnostic: does a genuinely intercepted 503 on /api/v1/tasks
 *  make the Board render its ErrorState, and what does fetch see? */
import { spawn } from 'node:child_process';
import net from 'node:net';
import { mkdtempSync, rmSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const URL_ = process.argv[2];
const FIREFOX = process.argv[3] || '/snap/bin/firefox';
const PROFILE_ROOT = process.argv[4] || tmpdir();
const MARKER = `lg021diag-${process.pid}`;
let childPid = null;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
function cleanup() { if (childPid) { try { const c = readFileSync(`/proc/${childPid}/cmdline`, 'utf8'); if (c.includes(MARKER)) process.kill(-childPid, 'SIGTERM'); } catch {} } }
class Bidi { constructor(ws){this.ws=ws;this.i=1;this.p=new Map();this.ev=[];this.h=new Map();ws.addEventListener('message',(e)=>{let m;try{m=JSON.parse(typeof e.data==='string'?e.data:e.data.toString())}catch{return}if(m.id!==undefined&&this.p.has(m.id)){const{resolve,reject}=this.p.get(m.id);this.p.delete(m.id);m.type==='error'?reject(new Error(m.error+':'+m.message)):resolve(m.result)}else if(m.method){this.ev.push(m);const f=this.h.get(m.method);if(f)for(const fn of f)try{fn(m.params)}catch{}}})}
 on(me,fn){if(!this.h.has(me))this.h.set(me,[]);this.h.get(me).push(fn)}
 send(me,pa={},t=10000){const id=this.i++;return new Promise((res,rej)=>{const tm=setTimeout(()=>{this.p.delete(id);rej(new Error('timeout '+me))},t);this.p.set(id,{resolve:r=>{clearTimeout(tm);res(r)},reject:e=>{clearTimeout(tm);rej(e)}});this.ws.send(JSON.stringify({id,method:me,params:pa}))})}}

async function main() {
  const profile = mkdtempSync(join(PROFILE_ROOT, `${MARKER}-`));
  const port = await new Promise((res) => { const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); }); });
  const child = spawn(FIREFOX, ['--headless','--no-remote',`--profile=${profile}`,`--remote-debugging-port=${port}`,'--no-first-run','about:blank'], { detached: true, stdio: ['ignore','ignore','ignore'] });
  childPid = child.pid;
  const out = {};
  try {
    let up = false;
    for (let i = 0; i < 60; i++) { up = await new Promise((res) => { const s = new net.Socket(); s.setTimeout(800); s.once('connect',()=>{s.destroy();res(true)}); s.once('timeout',()=>{s.destroy();res(false)}); s.once('error',()=>res(false)); s.connect(port,'127.0.0.1'); }); if (up) break; await sleep(200); }
    const ws = await new Promise((res) => { const w = new WebSocket(`ws://127.0.0.1:${port}/session`); w.addEventListener('open',()=>res(w)); });
    const bidi = new Bidi(ws);
    await bidi.send('session.new', { capabilities: { alwaysMatch: {} } }, 8000);
    const tree = await bidi.send('browsingContext.getTree', {}, 5000);
    const context = tree.contexts[0].context;
    const evalj = async (e, ap = false) => { const r = await bidi.send('script.evaluate', { expression: e, target: { context }, awaitPromise: ap, resultOwnership: 'none' }, 10000); return r.type === 'exception' ? '__EXC__' + r.exceptionDetails?.text : (r.result?.value ?? null); };
    await bidi.send('session.subscribe', { events: ['network.beforeRequestSent'] }, 5000);
    let provided = 0;
    bidi.on('network.beforeRequestSent', (params) => {
      const url = params?.request?.url || '';
      out.lastUrl = url;
      if (false) {
        provided++;
        bidi.send('network.provideResponse', { request: params.request.request, statusCode: 503, reasonPhrase: 'QA blocked', body: { type: 'string', value: JSON.stringify({ error: { code: 'internal_error', message: 'QA blocked', retryable: true } }) } }, 8000).catch((e) => { out.provideErr = e.message; });
      }
    });
    const itc = await bidi.send('network.addIntercept', { phases: ['beforeRequestSent'], urlPatterns: [{ type: 'pattern', protocol: 'http', hostname: '127.0.0.1', pathname: '/api/v1/tasks' }] }, 5000);
    out.intercept = itc.intercept;
    await bidi.send('browsingContext.navigate', { context, url: `${URL_}?view=board&err=diag`, wait: 'complete' }, 15000);
    await sleep(3000);
    out.provided = provided;
    out.hasErrorState = await evalj(`Boolean(document.querySelector('.lg-state--error'))`);
    out.errorText = await evalj(`(document.querySelector('.lg-state--error')||{}).innerText || null`);
    out.cardCount = await evalj(`document.querySelectorAll('.lg-card').length`);
    out.boardText = await evalj(`(document.querySelector('.lg-board')||{}).innerText || null`);

    out.contrastDebug = await evalj(`(() => {
      const el = document.querySelector('.lg-board__title') || document.querySelector('.lg-rail__item');
      if(!el) return 'NOEL';
      const cs = getComputedStyle(el);
      const c = cs.color;
      const m = c.match(/\\d+(?:\\.\\d+)?/g);
      return JSON.stringify({color:c, typeofColor: typeof c, match: m, el: el.className});
    })()`);
    out.directFetch = await evalj(`fetch('/api/v1/tasks?limit=1').then(async r=>'status='+r.status+' body='+((await r.text()).slice(0,80))).catch(e=>'REJECT:'+e.message)`, true);
  } catch (e) { out.error = String(e.stack || e); } finally {
    cleanup(); await sleep(300); try { rmSync(profile, { recursive: true, force: true }); } catch {}
  }
  console.log(JSON.stringify(out, null, 2));
}
main().then(() => process.exit(0));
