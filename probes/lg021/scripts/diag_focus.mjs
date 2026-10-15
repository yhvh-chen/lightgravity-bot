#!/usr/bin/env node
// Minimal focus diagnostic: real Firefox BiDi against a running LG server.
// Usage: node diag_focus.mjs --url http://127.0.0.1:PORT/
import { spawn } from 'node:child_process';
import net from 'node:net';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const args = process.argv.slice(2);
const getArg = (n) => { const i = args.indexOf(n); return i >= 0 ? args[i + 1] : null; };
const URL = getArg('--url');
const FIREFOX = getArg('--firefox') || '/usr/bin/firefox';
const PROFILE_ROOT = getArg('--profile-dir') || join(process.env.HOME, 'snap/firefox/current');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function freePort() {
  return new Promise((res) => { const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); }); });
}

async function main() {
  const profile = mkdtempSync(join(PROFILE_ROOT, 'lg021-focus-'));
  const port = await freePort();
  const child = spawn(FIREFOX, ['--headless', '--no-remote', `--profile=${profile}`, `--remote-debugging-port=${port}`, '--no-first-run', 'about:blank'], { stdio: 'ignore', detached: false });
  const cleanup = () => { try { child.kill('SIGKILL'); } catch {} try { rmSync(profile, { recursive: true, force: true }); } catch {} };
  let ws = `ws://127.0.0.1:${port}/session`;
  // Wait until the BiDi port accepts a connection.
  for (let i = 0; i < 60; i++) {
    const up = await new Promise((res) => { const s = new net.Socket(); s.setTimeout(600); s.once('connect', () => { s.destroy(); res(true); }); s.once('timeout', () => { s.destroy(); res(false); }); s.once('error', () => res(false)); s.connect(port, '127.0.0.1'); });
    if (up) break;
    await sleep(200);
  }
  const sock = new WebSocket(ws);
  let id = 0; const pending = new Map();
  await new Promise((res, rej) => { sock.addEventListener('open', res); sock.addEventListener('error', rej); });
  sock.addEventListener('message', (ev) => { let m; try { m = JSON.parse(typeof ev.data === 'string' ? ev.data : ev.data.toString()); } catch { return; } if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); } });
  const send = (method, params) => new Promise((res) => { const i = ++id; pending.set(i, res); sock.send(JSON.stringify({ id: i, method, params })); });
  await send('session.new', { capabilities: { alwaysMatch: {} } });
  const tree = await send('browsingContext.getTree', {});
  const context = tree.result.contexts[0].context;
  await send('session.subscribe', { events: ['log.entryAdded'] }).catch(() => {});
  await send('browsingContext.navigate', { context, url: URL, wait: 'complete' });
  await sleep(1500);
  const ev = async (expr) => { const r = await send('script.evaluate', { expression: expr, target: { context }, awaitPromise: false, resultOwnership: 'none' }); return r.result?.result?.value; };

  console.log('initial active:', await ev('document.activeElement && document.activeElement.tagName'));
  console.log('rails:', await ev(`document.querySelectorAll('.lg-rail__item').length`));
  // Method A: programmatic focus on first rail item
  console.log('A prog-focus:', await ev(`(()=>{const a=document.querySelector('.lg-rail__item');a.focus();const s=getComputedStyle(a);return JSON.stringify({tag:document.activeElement.tagName,active:a===document.activeElement,outline:s.outlineStyle+' '+s.outlineWidth,matches:a.matches(':focus-visible')});})()`));
  // Method B: real Tab key via performActions
  await ev('(()=>{document.activeElement.blur();document.body.focus();return true;})()');
  const report = [];
  for (let i = 0; i < 8; i++) {
    await send('input.performActions', { context, actions: [{ type: 'key', id: 'kb', actions: [{ type: 'keyDown', value: '\uE004' }, { type: 'keyUp', value: '\uE004' }] }] });
    await sleep(150);
    report.push(await ev(`(()=>{const a=document.activeElement;if(!a)return 'none';const s=getComputedStyle(a);return JSON.stringify({tag:a.tagName,cls:String(a.className||'').slice(0,30),fv:a.matches(':focus-visible'),outline:s.outlineStyle+' '+s.outlineWidth});})()`));
  }
  console.log('B tab sequence:'); report.forEach((r, i) => console.log(' ', i, r));
  // Method C: keyDown with explicit rawKeyDown via Input.dispatch? not available in bidi; try actions with 'pause'
  sock.close(); cleanup();
}
main().catch((e) => { console.error(e); process.exit(1); });
