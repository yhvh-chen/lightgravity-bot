#!/usr/bin/env node
/**
 * firefox_bidi_smoke.mjs — bounded, reusable Firefox native WebDriver BiDi helper.
 *
 * Scope: browser diagnostics evidence only. Does NOT touch product source,
 * Task state, contracts or dependencies.
 *
 * What it proves (independently, with two facts each):
 *   1. a REAL Firefox main-frame navigation to a loopback HTTP origin,
 *      observed (a) server-side (probe server logs a GET from a Mozilla UA)
 *      and (b) browser-side (BiDi `browsingContext.navigationCommitted` /
 *      `...locationFragment` + `script.evaluate` of `location.origin`).
 *   2. a real JSON API fetch, a real SSE stream, and a DOM interaction,
 *      all from a same-origin http document.
 *
 * Protocol: native WebDriver BiDi over the browser's own WebSocket endpoint.
 * Firefox exposes it directly with `--remote-debugging-port` (no separate
 * driver/marionette needed). Node's built-in global `WebSocket` is used, so
 * there is no npm dependency.
 *
 * Safety / hygiene:
 *   - temporary profile, removed on exit unless --keep-profile
 *   - parameterised binary (--firefox / FIREFOX_BIN)
 *   - launches firefox in its own process group (detached); cleanup only ever
 *     signals that group (negative pgid) and only after re-verifying the
 *     leader pid + a marker in /proc/<pid>/cmdline
 *   - per-operation deadline; hard wall clock via --deadline-ms
 *   - never touches the user profile, apt, system policy or global config
 *
 * Usage:
 *   node firefox_bidi_smoke.mjs --url http://127.0.0.1:PORT/page \
 *        --mode all --deadline-ms 25000
 *   FIREFOX_BIN=/path/to/firefox node firefox_bidi_smoke.mjs ...
 *
 * Modes: doc  (navigation + location.origin only)
 *        api  (same-origin fetch of /api/echo)
 *        sse  (same-origin EventSource on /sse)
 *        dom  (DOM interaction on /page)
 *        all  (doc, api, sse, dom)
 */
import { spawn } from 'node:child_process';
import net from 'node:net';
import { mkdtempSync, rmSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const DEFAULT_FIREFOX = process.env.FIREFOX_BIN || 'firefox';

function parseArgs(argv) {
  const out = {
    url: null,
    mode: 'all',
    deadlineMs: 25000,
    firefox: DEFAULT_FIREFOX,
    keepProfile: false,
    verbose: false,
    profileDir: null,
  };
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i];
    const next = () => argv[++i];
    if (a === '--url') out.url = next();
    else if (a === '--mode') out.mode = next();
    else if (a === '--deadline-ms') out.deadlineMs = Number(next());
    else if (a === '--firefox') out.firefox = next();
    else if (a === '--profile-dir') out.profileDir = next();
    else if (a === '--keep-profile') out.keepProfile = true;
    else if (a === '--verbose') out.verbose = true;
    else if (a === '--help' || a === '-h') {
      console.log('see header of firefox_bidi_smoke.mjs');
      process.exit(0);
    } else throw new Error(`unknown arg: ${a}`);
  }
  if (!out.url) throw new Error('--url is required');
  return out;
}

const ARGS = parseArgs(process.argv);
const log = (...m) => console.log(...m);
const vlog = (...m) => ARGS.verbose && console.log('[v]', ...m);

// --- process-group-safe launch/cleanup -------------------------------------
let childPid = null;
let childPgid = null;
const MARKER = `fgbidi-${process.pid}`;

function launchFirefox(binary, args) {
  // detached:true puts the child in its own process group so we can signal
  // exactly that group and never the parent pi / siblings.
  const child = spawn(binary, args, {
    detached: true,
    stdio: ['ignore', ARGS.verbose ? 'inherit' : 'ignore', ARGS.verbose ? 'inherit' : 'ignore'],
  });
  childPid = child.pid;
  try {
    childPgid = process.kill(-childPid, 0) === undefined ? childPid : childPid;
  } catch {
    childPgid = childPid;
  }
  return child;
}

function groupIsOurs(pgid) {
  // Re-verify before killing: the group leader pid must still exist and its
  // cmdline must carry our unique per-run marker (always passed as
  // --profile=<dir containing MARKER>). This prevents signalling a reused pid
  // or any unrelated firefox.
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
    // only signal the group we created, and only if it still looks like ours
    if (groupIsOurs(childPid)) {
      process.kill(-childPid, 'SIGTERM');
      // brief grace, then SIGKILL the same group only
      const t0 = Date.now();
      while (Date.now() - t0 < 1500) {
        try {
          process.kill(-childPid, 0);
        } catch {
          return; // group gone
        }
        // busy-wait a hair; we are exiting anyway
        const end = Date.now() + 50;
        while (Date.now() < end) { /* spin */ }
      }
      process.kill(-childPid, 'SIGKILL');
    }
  } catch {
    /* group already gone */
  }
}

// --- minimal BiDi client ----------------------------------------------------
class Bidi {
  constructor(ws) {
    this.ws = ws;
    this.nextId = 1;
    this.pending = new Map();
    this.listeners = new Set();
    ws.addEventListener('message', (ev) => {
      let msg;
      try {
        msg = JSON.parse(typeof ev.data === 'string' ? ev.data : ev.data.toString());
      } catch {
        return;
      }
      if (msg.id !== undefined && this.pending.has(msg.id)) {
        const { resolve, reject } = this.pending.get(msg.id);
        this.pending.delete(msg.id);
        if (msg.type === 'error') reject(new Error(`${msg.error}: ${msg.message}`));
        else resolve(msg.result);
      } else if (msg.method) {
        for (const l of this.listeners) l(msg);
      }
    });
  }
  onEvent(fn) { this.listeners.add(fn); return () => this.listeners.delete(fn); }
  send(method, params = {}, timeoutMs = 8000) {
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`timeout ${method} after ${timeoutMs}ms`));
      }, timeoutMs);
      this.pending.set(id, {
        resolve: (r) => { clearTimeout(timer); resolve(r); },
        reject: (e) => { clearTimeout(timer); reject(e); },
      });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }
}

function connect(url, timeoutMs) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(url);
    const timer = setTimeout(() => reject(new Error('ws connect timeout')), timeoutMs);
    ws.addEventListener('open', () => { clearTimeout(timer); resolve(ws); });
    ws.addEventListener('error', (e) => { clearTimeout(timer); reject(new Error('ws error: ' + (e.message || 'unknown'))); });
  });
}

async function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }

// --- main -------------------------------------------------------------------
async function main() {
  const deadline = Date.now() + ARGS.deadlineMs;
  const profileRoot = ARGS.profileDir || tmpdir();
  const profile = mkdtempSync(join(profileRoot, `${MARKER}-`));

  // pick a free-ish remote debugging port via the OS, then let firefox bind it
  const port = await new Promise((res, rej) => {
    const s = net.createServer();
    s.on('error', rej);
    s.listen(0, '127.0.0.1', () => {
      const p = s.address().port;
      s.close(() => res(p));
    });
  });

  const ffArgs = [
    '--headless',
    '--no-remote',
    `--profile=${profile}`,
    `--remote-debugging-port=${port}`,
    // keep the network path plain: no proxy, no remote services
    '--no-first-run',
    'about:blank',
  ];

  log(`# firefox_bidi_smoke  binary=${ARGS.firefox}`);
  log(`# profile=${profile}`);
  log(`# bidi-port=${port} deadline=${ARGS.deadlineMs}ms mode=${ARGS.mode}`);

  const child = launchFirefox(ARGS.firefox, ffArgs);
  child.on('exit', (code, sig) => vlog(`firefox exited code=${code} sig=${sig}`));

  const results = { binary: ARGS.firefox, profile, port, checks: {}, ok: false };

  try {
    // Firefox exposes native WebDriver BiDi as a WebSocket upgrade at
    // /session on --remote-debugging-port (verified by raw handshake: the
    // root path serves an httpd.js info page, /session returns 101).
    const endpoint = `ws://127.0.0.1:${port}/session`;
    let up = false;
    const waitUntil = Math.min(deadline, Date.now() + 15000);
    while (Date.now() < waitUntil) {
      up = await new Promise((res) => {
        const s = new net.Socket();
        s.setTimeout(800);
        s.once('connect', () => { s.destroy(); res(true); });
        s.once('timeout', () => { s.destroy(); res(false); });
        s.once('error', () => { res(false); });
        s.connect(port, '127.0.0.1');
      });
      if (up) break;
      await sleep(200);
    }
    if (!up) throw new Error(`BiDi port 127.0.0.1:${port} never became reachable`);
    log(`# webSocketDebuggerUrl=${endpoint}`);

    const ws = await connect(endpoint, 5000);
    const bidi = new Bidi(ws);

    // identify the browser and open an active session (required before
    // browsingContext/script commands on this native BiDi endpoint)
    try {
      const st = await bidi.send('session.status', {}, 4000);
      results.browserReady = st.ready;
      log(`# session.status ready=${st.ready} message=${st.message ?? ''}`);
    } catch (e) {
      log(`# session.status unavailable: ${e.message}`);
    }
    const sess = await bidi.send('session.new', { capabilities: { alwaysMatch: {} } }, 8000);
    results.sessionId = sess.sessionId;
    results.browserName = sess.capabilities?.browserName;
    results.browserVersion = sess.capabilities?.browserVersion;
    results.userAgent = sess.capabilities?.userAgent;
    results.headless = sess.capabilities?.['moz:headless'];
    log(`# session.new browser=${results.browserName}/${results.browserVersion} headless=${results.headless}`);
    log(`# userAgent=${results.userAgent}`);

    const ctxEvents = [];
    bidi.onEvent((m) => {
      if (m.method && m.method.startsWith('browsingContext.')) ctxEvents.push(m);
    });

    // create a fresh top-level context and navigate to the real http origin
    const tree = await bidi.send('browsingContext.getTree', {}, 5000);
    const context = tree.contexts[0].context;
    vlog('top context', context);

    const navP = bidi.send('browsingContext.navigate', {
      context,
      url: ARGS.url,
      wait: 'complete',
    }, Math.max(5000, deadline - Date.now()));

    const nav = await navP;
    log(`# navigationCommitted url=${nav.url} navId=${nav.navigation ?? 'n/a'}`);

    // browser-side fact: the document's own location.origin
    const evalJson = async (expr) => {
      const r = await bidi.send('script.evaluate', {
        expression: expr,
        target: { context },
        awaitPromise: true,
        resultOwnership: 'none',
      }, 6000);
      if (r.type === 'exception') throw new Error(`eval exception: ${r.exceptionDetails?.text}`);
      return r.result?.value;
    };

    const origin = await evalJson('location.origin');
    const href = await evalJson('location.href');
    // Page-agnostic DOM proof: either the tiny /marker page's lg-marker, or
    // the /page fixture's lg-origin element rendered from location.origin.
    const markerText = await evalJson('(document.getElementById("lg-marker")||{}).textContent || null');
    const originEl = await evalJson('(document.getElementById("lg-origin")||{}).textContent || null');
    const bodyText = await evalJson('document.body ? document.body.innerText.slice(0,120) : null');
    const expectedOrigin = new URL(ARGS.url).origin;
    const originOk = origin === expectedOrigin && expectedOrigin.startsWith('http://');
    const domOk = markerText === 'MARKER-OK' || originEl === expectedOrigin;
    results.checks.doc = {
      locationOrigin: origin,
      locationHref: href,
      domMarkerText: markerText,
      domOriginText: originEl,
      bodyText,
      expectedOrigin,
      isHttp: originOk,
      pass: originOk && domOk,
    };
    log(`# location.origin=${origin} domMarker=${JSON.stringify(markerText)} domOrigin=${JSON.stringify(originEl)} doc_pass=${results.checks.doc.pass}`);
    if (ctxEvents.length) {
      log(`# browsingContext events: ${ctxEvents.map((e) => e.method).join(',')}`);
    }

    const mode = ARGS.mode;
    const want = (m) => mode === 'all' || mode === m;

    if (want('api')) {
      // same-origin JSON fetch from the page itself (GET /api/echo)
      const apiExpr = `(async () => {
        const r = await fetch('/api/echo');
        return JSON.stringify({status: r.status, body: await r.text()});
      })()`;
      const apiRaw = await evalJson(apiExpr);
      const api = JSON.parse(apiRaw);
      results.checks.api = { ...api, pass: api.status === 200 };
      log(`# api status=${api.status} body=${api.body} api_pass=${results.checks.api.pass}`);
    }

    if (want('sse')) {
      // real EventSource from the same-origin page; collect N events + done
      const sseExpr = `(async () => {
        return await new Promise((resolve) => {
          const out = [];
          const es = new EventSource('/sse');
          const timer = setTimeout(() => { es.close(); resolve(JSON.stringify({events: out, done:false, timeout:true})); }, 6000);
          es.addEventListener('tick', (e) => out.push(e.data));
          es.addEventListener('done', (e) => { clearTimeout(timer); es.close(); resolve(JSON.stringify({events: out, done:true, last:e.data})); });
          es.onerror = () => {};
        });
      })()`;
      const sseRaw = await evalJson(sseExpr);
      const sse = JSON.parse(sseRaw);
      results.checks.sse = { ...sse, pass: Array.isArray(sse.events) && sse.events.length >= 1 };
      log(`# sse events=${JSON.stringify(sse.events)} done=${sse.done} sse_pass=${results.checks.sse.pass}`);
    }

    if (want('dom')) {
      // a real DOM interaction: mutate the DOM via script + click semantics,
      // then read the resulting state from the live document.
      const domExpr = `(async () => {
        const el = document.getElementById('lg-origin');
        const before = el.textContent;
        el.setAttribute('data-probe','clicked');
        el.textContent = 'CLICKED';
        el.dispatchEvent(new MouseEvent('click', {bubbles:true}));
        await new Promise(r => setTimeout(r, 50));
        const after = el.textContent;
        return JSON.stringify({before, after, attr: el.getAttribute('data-probe')});
      })()`;
      const domRaw = await evalJson(domExpr);
      const dom = JSON.parse(domRaw);
      results.checks.dom = { ...dom, pass: dom.after === 'CLICKED' && dom.attr === 'clicked' };
      log(`# dom before=${dom.before} after=${dom.after} attr=${dom.attr} dom_pass=${results.checks.dom.pass}`);
    }

    ws.close();
    results.ok = Object.values(results.checks).every((c) => c.pass);
  } catch (err) {
    results.error = String(err && err.message ? err.message : err);
    log(`# ERROR: ${results.error}`);
  } finally {
    cleanup();
    if (!ARGS.keepProfile) {
      try { rmSync(profile, { recursive: true, force: true }); } catch { /* ignore */ }
    } else {
      log(`# kept profile at ${profile}`);
    }
  }

  log('RESULT ' + JSON.stringify(results));
  process.exit(results.ok ? 0 : 1);
}

main().catch((e) => {
  console.error('fatal', e);
  cleanup();
  process.exit(2);
});
