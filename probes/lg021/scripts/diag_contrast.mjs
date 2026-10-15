#!/usr/bin/env node
// LG-021 supplemental contrast diagnostic (NOT a full QA re-run).
//
// Purpose: the 2026-10-16 full browser QA sampled 7 of 24 contrast candidates.
// This probe samples the previously-unsampled visible text classes on the REAL
// running product server in real Firefox, using the same ancestor-compositing
// WCAG math. It does not re-run the other QA checks.
//
// Usage: node diag_contrast.mjs --url http://127.0.0.1:PORT/ [--firefox BIN] [--profile-dir D]
import { spawn } from 'node:child_process';
import net from 'node:net';
import { mkdtempSync, rmSync } from 'node:fs';
import { join } from 'node:path';

const args = process.argv.slice(2);
const getArg = (n, d = null) => { const i = args.indexOf(n); return i >= 0 ? args[i + 1] : d; };
const URL_ = getArg('--url');
const FIREFOX = getArg('--firefox', '/snap/bin/firefox');
const PROFILE_ROOT = getArg('--profile-dir', join(process.env.HOME, 'snap/firefox/current'));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

class Bidi {
  constructor(ws) { this.ws = ws; this.i = 1; this.p = new Map(); ws.addEventListener('message', (e) => { let m; try { m = JSON.parse(typeof e.data === 'string' ? e.data : e.data.toString()); } catch { return; } if (m.id !== undefined && this.p.has(m.id)) { const { resolve, reject } = this.p.get(m.id); this.p.delete(m.id); m.type === 'error' ? reject(new Error(m.error + ':' + m.message)) : resolve(m.result); } }); }
  send(me, pa = {}, t = 10000) { const id = this.i++; return new Promise((res, rej) => { const tm = setTimeout(() => { this.p.delete(id); rej(new Error('timeout ' + me)); }, t); this.p.set(id, { resolve: (r) => { clearTimeout(tm); res(r); }, reject: (e) => { clearTimeout(tm); rej(e); } }); this.ws.send(JSON.stringify({ id, method: me, params: pa })); }); }
}

async function freePort() { return new Promise((res) => { const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); }); }); }

const CONTRAST_EXPR = `(() => {
  function parseColor(s){ if(!s) return null; s=String(s).trim(); if(s==='transparent') return {r:0,g:0,b:0,a:0}; if(s.charAt(0)==='#'){let hex=s.slice(1); if(hex.length===3){hex=hex.split('').map(x=>x+x).join('');} if(hex.length===6||hex.length===8){const r=parseInt(hex.slice(0,2),16),g=parseInt(hex.slice(2,4),16),b=parseInt(hex.slice(4,6),16),a=hex.length===8?parseInt(hex.slice(6,8),16)/255:1; if([r,g,b].every(v=>isFinite(v))) return {r,g,b,a};} return null;} const lp=s.indexOf('('), rp=s.lastIndexOf(')'); if(lp<0||rp<lp) return null; const head=s.slice(0,lp).trim(); if(head!=='rgb'&&head!=='rgba') return null; const parts=s.slice(lp+1,rp).split(',').map(x=>x.trim()).filter(x=>x.length).map(Number); if(parts.length<3||parts.slice(0,4).some(v=>!isFinite(v))) return null; return {r:parts[0],g:parts[1],b:parts[2],a:parts.length>=4?parts[3]:1}; }
  function comp(fg,bg){ const a=fg.a; return {r:fg.r*a+bg.r*(1-a),g:fg.g*a+bg.g*(1-a),b:fg.b*a+bg.b*(1-a),a:1}; }
  function lum(c){ const f=v=>{v=v/255;return v<=0.03928?v/12.92:Math.pow((v+0.055)/1.055,2.4)}; return 0.2126*f(c.r)+0.7152*f(c.g)+0.0722*f(c.b); }
  function ratio(fgc,bgc){ const l1=lum(fgc),l2=lum(bgc); const a=Math.max(l1,l2),b=Math.min(l1,l2); return (a+0.05)/(b+0.05); }
  function effBg(el){ const chain=[]; let n=el; while(n){ const c=parseColor(getComputedStyle(n).backgroundColor); if(c){ chain.push(c); if(c.a>=1) break; } n=n.parentElement; } let acc={r:255,g:255,b:255,a:1}; for(let i=chain.length-1;i>=0;i--){ acc=comp(chain[i],acc); } return acc; }
  function effFg(el,bg0){ const c=parseColor(getComputedStyle(el).color); if(!c) return null; if(c.a>=1) return c; return comp(c,bg0); }
  const sels=['.lg-card__meta','.lg-section__title','.lg-field__label','.lg-scope-field__label','.lg-context__title','.lg-context-item__label','.lg-context-item__meta','.lg-detail-header__title','.lg-detail-header__meta','.lg-state__body','.lg-composer__hint','.lg-message__meta','.lg-notification__meta','.lg-popover__status','.lg-board__count','.lg-main h2','.lg-topbar__scope'];
  const out={}; const missing=[];
  for(const sel of sels){ const el=[...document.querySelectorAll(sel)].filter(e=>e.textContent&&e.textContent.trim().length>1&&e.offsetParent!==null)[0]; if(!el){missing.push(sel);continue;} const bg=effBg(el); const fg=effFg(el,bg); if(!fg){missing.push(sel+':fg?');continue;} const r=ratio(fg,bg); out[sel]={text:el.textContent.trim().slice(0,24),fg:'rgb('+Math.round(fg.r)+', '+Math.round(fg.g)+', '+Math.round(fg.b)+')',bg:'rgb('+Math.round(bg.r)+', '+Math.round(bg.g)+', '+Math.round(bg.b)+')',ratio:Number(r.toFixed(2))}; }
  // disabled-exempt check (explicitly labelled, WCAG 1.4.3 exempts disabled controls)
  const dis={};
  for(const sel of ['.lg-button:disabled','.lg-select:disabled']){ const el=document.querySelector(sel); if(!el){dis[sel]='absent';continue;} const bg=effBg(el); const fg=effFg(el,bg); dis[sel]={fg:'rgb('+Math.round(fg.r)+', '+Math.round(fg.g)+', '+Math.round(fg.b)+')',bg:'rgb('+Math.round(bg.r)+', '+Math.round(bg.g)+', '+Math.round(bg.b)+')',ratio:Number(ratio(fg,bg).toFixed(2)),note:'disabled-control (WCAG 1.4.3 exempt)'}; }
  const urls=[...document.querySelectorAll('.lg-card__meta, .lg-section__title, .lg-field__label, .lg-scope-field__label, .lg-context__title, .lg-context-item__label, .lg-context-item__meta, .lg-detail-header__title, .lg-detail-header__meta, .lg-state__body, .lg-composer__hint, .lg-message__meta, .lg-notification__meta, .lg-popover__status, .lg-board__count, .lg-main h2, .lg-topbar__scope')].length;
  return JSON.stringify({href:location.href, presentClasses:urls, pairs:out, missing, disabledExempt:dis});
})()`;

async function main() {
  const profile = mkdtempSync(join(PROFILE_ROOT, 'lg021-contrast-'));
  const port = await freePort();
  const child = spawn(FIREFOX, ['--headless', '--no-remote', `--profile=${profile}`, `--remote-debugging-port=${port}`, '--no-first-run', 'about:blank'], { detached: true, stdio: ['ignore', 'ignore', 'ignore'] });
  const cleanup = () => { try { process.kill(-child.pid, 'SIGKILL'); } catch { } try { child.kill('SIGKILL'); } catch { } try { rmSync(profile, { recursive: true, force: true }); } catch { } };
  const results = {};
  try {
    for (let i = 0; i < 60; i++) { const up = await new Promise((res) => { const s = new net.Socket(); s.setTimeout(800); s.once('connect', () => { s.destroy(); res(true); }); s.once('timeout', () => { s.destroy(); res(false); }); s.once('error', () => res(false)); s.connect(port, '127.0.0.1'); }); if (up) break; await sleep(200); }
    const ws = await new Promise((res, rej) => { const w = new WebSocket(`ws://127.0.0.1:${port}/session`); w.addEventListener('open', () => res(w)); w.addEventListener('error', rej); });
    const bidi = new Bidi(ws);
    await bidi.send('session.new', { capabilities: { alwaysMatch: {} } }, 8000);
    const tree = await bidi.send('browsingContext.getTree', {}, 5000);
    const context = tree.contexts[0].context;
    const evj = async (e) => { const r = await bidi.send('script.evaluate', { expression: e, target: { context }, awaitPromise: false, resultOwnership: 'none' }, 10000); return r.type === 'exception' ? '__EXC__' + (r.exceptionDetails?.text || '') : (r.result?.value ?? null); };
    const visits = [
      ['board', URL_ + '?view=board'],
      ['settings', URL_ + '?view=settings'],
      ['chat', URL_ + ''],
    ];
    for (const [name, url] of visits) {
      await bidi.send('browsingContext.navigate', { context, url, wait: 'complete' }, 15000);
      await sleep(1200);
      const raw = await evj(CONTRAST_EXPR);
      try { results[name] = JSON.parse(raw || '{}'); } catch { results[name] = { raw: String(raw).slice(0, 400) }; }
    }
    ws.close();
  } finally { cleanup(); }
  console.log(JSON.stringify(results, null, 2));
}
main().catch((e) => { console.error('ERR', e && e.message); process.exit(1); });
