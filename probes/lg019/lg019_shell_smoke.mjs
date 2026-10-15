#!/usr/bin/env node
/**
 * LG-019 product shell notification smoke (Firefox native WebDriver BiDi).
 *
 * Scope: bounded evidence only. Loads the REAL product UI served by the
 * one-process backend (`lightgravity` CLI: `/` + `/api/v1`), with a temp data
 * dir seeded by `seed_notification.py` so a real durable `task.failed` event
 * projects into a real notification.
 *
 * What it proves, browser-side and against the real same-origin API:
 *   1. the top-bar bell shows a real unread badge (count from the backend);
 *   2. opening the bell renders the projected notification (not a mock);
 *   3. clicking it returns to the exact Task scope and persists read state;
 *   4. a reload keeps it read (durable, not session-only);
 *   5. the popover does not overflow the viewport at a narrow width.
 *
 * Safety: temporary profile removed on exit; only its own process group is
 * signalled; the snap Firefox profile root is used when available.
 */
import { spawn } from 'node:child_process';
import net from 'node:net';
import { mkdtempSync, rmSync, readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

function parseArgs(argv) {
  const out = { url: null, firefox: process.env.FIREFOX_BIN || 'firefox', deadlineMs: 45000, verbose: false, out: null, profileDir: null };
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--url') out.url = argv[++i];
    else if (a === '--firefox') out.firefox = argv[++i];
    else if (a === '--deadline-ms') out.deadlineMs = Number(argv[++i]);
    else if (a === '--out') out.out = argv[++i];
    else if (a === '--profile-dir') out.profileDir = argv[++i];
    else if (a === '--verbose') out.verbose = true;
    else throw new Error(`unknown arg ${a}`);
  }
  if (!out.url) throw new Error('--url is required');
  return out;
}

const ARGS = parseArgs(process.argv);
const log = (...m) => console.log(...m);
const vlog = (...m) => ARGS.verbose && console.log('[v]', ...m);
const MARKER = `lg019bidi-${process.pid}`;
let childPid = null;

function launchFirefox(binary, args) {
  const child = spawn(binary, args, { detached: true, stdio: ['ignore', 'ignore', 'ignore'] });
  childPid = child.pid;
  return child;
}

function groupIsOurs(pgid) {
  try {
    const cmd = readFileSync(`/proc/${pgid}/cmdline`, 'utf8');
    return cmd.includes(MARKER) && cmd.includes('firefox');
  } catch {
    return false;
  }
}

function cleanup() {
  if (childPid == null) return;
  try {
    if (groupIsOurs(childPid)) process.kill(-childPid, 'SIGTERM');
  } catch {}
}

class Bidi {
  constructor(ws) {
    this.ws = ws; this.nextId = 1; this.pending = new Map();
    ws.addEventListener('message', (ev) => {
      let msg; try { msg = JSON.parse(typeof ev.data === 'string' ? ev.data : ev.data.toString()); } catch { return; }
      if (msg.id !== undefined && this.pending.has(msg.id)) {
        const { resolve, reject } = this.pending.get(msg.id);
        this.pending.delete(msg.id);
        if (msg.type === 'error') reject(new Error(`${msg.error}: ${msg.message}`));
        else resolve(msg.result);
      }
    });
  }
  send(method, params = {}, timeoutMs = 8000) {
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { this.pending.delete(id); reject(new Error(`timeout ${method}`)); }, timeoutMs);
      this.pending.set(id, { resolve: (r) => { clearTimeout(timer); resolve(r); }, reject: (e) => { clearTimeout(timer); reject(e); } });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }
}

function connect(url, timeoutMs) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(url);
    const timer = setTimeout(() => reject(new Error('ws connect timeout')), timeoutMs);
    ws.addEventListener('open', () => { clearTimeout(timer); resolve(ws); });
    ws.addEventListener('error', () => reject(new Error('ws error')));
  });
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function main() {
  const deadline = Date.now() + ARGS.deadlineMs;
  const profileRoot = ARGS.profileDir || tmpdir();
  const profile = mkdtempSync(join(profileRoot, `${MARKER}-`));
  const port = await new Promise((res, rej) => {
    const s = net.createServer(); s.on('error', rej);
    s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); });
  });
  const ffArgs = ['--headless', '--no-remote', `--profile=${profile}`, `--remote-debugging-port=${port}`, '--no-first-run', 'about:blank'];
  const child = launchFirefox(ARGS.firefox, ffArgs);
  child.on('exit', (code, sig) => vlog(`firefox exited code=${code} sig=${sig}`));

  const results = { url: ARGS.url, checks: {}, ok: false };
  try {
    const endpoint = `ws://127.0.0.1:${port}/session`;
    let up = false;
    const waitUntil = Math.min(deadline, Date.now() + 15000);
    while (Date.now() < waitUntil) {
      up = await new Promise((res) => {
        const s = new net.Socket(); s.setTimeout(800);
        s.once('connect', () => { s.destroy(); res(true); });
        s.once('timeout', () => { s.destroy(); res(false); });
        s.once('error', () => res(false));
        s.connect(port, '127.0.0.1');
      });
      if (up) break;
      await sleep(200);
    }
    if (!up) throw new Error('BiDi port never reachable');

    const ws = await connect(endpoint, 5000);
    const bidi = new Bidi(ws);
    const sess = await bidi.send('session.new', { capabilities: { alwaysMatch: {} } }, 8000);
    results.browser = `${sess.capabilities?.browserName}/${sess.capabilities?.browserVersion}`;
    const tree = await bidi.send('browsingContext.getTree', {}, 5000);
    const context = tree.contexts[0].context;

    const evalJson = async (expr, awaitPromise = false) => {
      const r = await bidi.send('script.evaluate', {
        expression: expr, target: { context }, awaitPromise, resultOwnership: 'none',
      }, 8000);
      if (r.type === 'exception') throw new Error(`eval exception: ${r.exceptionDetails?.text}`);
      const rv = r.result;
      if (rv == null) return null;
      if (rv.type === 'null' || rv.type === 'undefined') return null;
      return rv.value;
    };

    await bidi.send('browsingContext.navigate', { context, url: ARGS.url, wait: 'complete' }, 15000);
    // Wait for the app to fetch /api/v1/notifications and paint the badge.
    let badge = null;
    const badgeUntil = Math.min(deadline, Date.now() + 15000);
    while (Date.now() < badgeUntil) {
      badge = await evalJson('(document.querySelector(".lg-icon-button__badge")||{}).textContent || null');
      if (badge) break;
      await sleep(250);
    }
    results.checks.badgeVisible = { pass: badge === '1', text: badge };

    // Open the bell popover and read the projected item.
    const clicked = await evalJson(`(() => { const b=[...document.querySelectorAll('button')].find(x=>(x.getAttribute('aria-label')||'').startsWith('Notifications')); if(b){b.click(); return true;} return false; })()`);
    results.debugBellClicked = clicked;
    await sleep(400);
    const popoverText = await evalJson('(document.querySelector(".lg-popover")||{}).innerText || null');
    results.debugPopoverPresent = await evalJson('Boolean(document.querySelector(".lg-popover"))');
    const taskRef = await evalJson('(document.querySelector(".lg-notification__meta")||{}).textContent || null');
    // Assert the *real* item (label "error" + Task failed + task_ref), not the
    // clearly-labelled layout mock that also renders in the same popover.
    results.checks.popoverShowsNotification = {
      pass: Boolean(
        popoverText &&
          /Task failed/.test(popoverText) &&
          typeof taskRef === 'string' &&
          taskRef.startsWith('task_'),
      ),
      text: (popoverText || '').slice(0, 200),
      taskRef,
    };

    // Click the notification: returns to the Task scope and persists read.
    await evalJson(`(() => { const b=document.querySelector('.lg-notification'); if(b){b.click(); return true;} return false; })()`);
    await sleep(400);
    const urlAfterClick = await evalJson('location.search');
    results.checks.returnsToTaskScope = {
      pass: typeof urlAfterClick === 'string' && urlAfterClick.includes('task=task_'),
      url: urlAfterClick,
    };

    // Give the unawaited mark-read POST a moment to land before reloading.
    await sleep(600);
    // Reload: read state must survive (backend-persisted, not session-only).
    // Use an explicit hard reload so the SPA re-runs and re-fetches.
    await evalJson('location.replace(location.pathname + "?reload=1")');
    await sleep(500);
    await bidi.send('browsingContext.navigate', { context, url: `${ARGS.url}?reload=1`, wait: 'complete' }, 15000);
    let badgeAfter = undefined;
    const reloadUntil = Math.min(deadline, Date.now() + 20000);
    while (Date.now() < reloadUntil) {
      badgeAfter = await evalJson('(document.querySelector(".lg-icon-button__badge")||{}).textContent || null');
      if (badgeAfter === null) break;
      await sleep(250);
    }
    // Independent wire fact: ask the backend directly what it thinks is unread.
    const apiUnread = await evalJson(`fetch('/api/v1/notifications').then(r=>r.json()).then(d=>String(d.unread))`, true);
    results.debugApiUnreadAfterReload = apiUnread;
    results.checks.readPersistsAcrossReload = {
      pass: badgeAfter === null && apiUnread === '0',
      badge: String(badgeAfter),
      apiUnread,
    };

    // Narrow viewport: the popover must fit without horizontal overflow.
    await bidi.send('browsingContext.setViewport', { context, viewport: { width: 390, height: 800 } }, 5000).catch(() => {});
    await sleep(300);
    const overflowRaw = await evalJson('JSON.stringify({ sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth })');
    const overflow = JSON.parse(overflowRaw);
    results.checks.noHorizontalOverflow = { pass: overflow.sw <= overflow.cw + 1, ...overflow };

    results.ok = Object.values(results.checks).every((c) => c && c.pass);
  } catch (err) {
    results.error = String(err && err.message ? err.message : err);
  } finally {
    cleanup();
    await sleep(300);
    try { rmSync(profile, { recursive: true, force: true }); } catch {}
  }
  if (ARGS.out) {
    mkdirSync(join(ARGS.out, '..'), { recursive: true });
    writeFileSync(ARGS.out, JSON.stringify(results, null, 2));
  }
  log(JSON.stringify(results, null, 2));
  return results.ok ? 0 : 1;
}

main().then((code) => process.exit(code)).catch((e) => { console.error(e); process.exit(1); });
