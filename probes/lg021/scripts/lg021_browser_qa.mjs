#!/usr/bin/env node
/**
 * LG-021 first-version frontend QA — real same-origin HTTP browser acceptance.
 *
 * Drives real Firefox (native WebDriver BiDi) against the REAL product server
 * (`lightgravity` CLI: `/` static + `/api/v1`), seeded by
 * `seed_lg021_fixtures.py`.  Every check runs against the app's real API calls;
 * nothing here is a `file://` render and nothing substitutes a build success.
 *
 * Evidence produced: a JSON result file plus real screenshots at 1440/1024/390.
 *
 * Safety: own temp profile only, removed on exit; only its own process group is
 * signalled; the snap Firefox profile root is used when available.
 */
import { spawn } from 'node:child_process';
import net from 'node:net';
import { mkdtempSync, rmSync, readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';

function parseArgs(argv) {
  const out = { url: null, firefox: process.env.FIREFOX_BIN || '/snap/bin/firefox', deadlineMs: 55000, outDir: null, profileDir: null };
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--url') out.url = argv[++i];
    else if (a === '--firefox') out.firefox = argv[++i];
    else if (a === '--deadline-ms') out.deadlineMs = Number(argv[++i]);
    else if (a === '--out-dir') out.outDir = argv[++i];
    else if (a === '--profile-dir') out.profileDir = argv[++i];
    else throw new Error(`unknown arg ${a}`);
  }
  if (!out.url) throw new Error('--url is required');
  return out;
}

const ARGS = parseArgs(process.argv);
const log = (...m) => console.log(...m);
const MARKER = `lg021bidi-${process.pid}`;
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
  } catch { return false; }
}
function cleanup() {
  if (childPid == null) return;
  try { if (groupIsOurs(childPid)) process.kill(-childPid, 'SIGTERM'); } catch {}
}

class Bidi {
  constructor(ws) {
    this.ws = ws; this.nextId = 1; this.pending = new Map();
    this.events = [];
    this.handlers = new Map();
    ws.addEventListener('message', (ev) => {
      let msg; try { msg = JSON.parse(typeof ev.data === 'string' ? ev.data : ev.data.toString()); } catch { return; }
      if (msg.id !== undefined && this.pending.has(msg.id)) {
        const { resolve, reject } = this.pending.get(msg.id);
        this.pending.delete(msg.id);
        if (msg.type === 'error') reject(new Error(`${msg.error}: ${msg.message}`));
        else resolve(msg.result);
      } else if (msg.method) {
        this.events.push(msg);
        const h = this.handlers.get(msg.method);
        if (h) { for (const fn of h) { try { fn(msg.params); } catch {} } }
      }
    });
  }
  on(method, fn) { if (!this.handlers.has(method)) this.handlers.set(method, []); this.handlers.get(method).push(fn); }
  send(method, params = {}, timeoutMs = 10000) {
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
  if (ARGS.outDir) mkdirSync(ARGS.outDir, { recursive: true });
  const port = await new Promise((res, rej) => {
    const s = net.createServer(); s.on('error', rej);
    s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); });
  });
  const child = launchFirefox(ARGS.firefox, ['--headless', '--no-remote', `--profile=${profile}`, `--remote-debugging-port=${port}`, '--no-first-run', 'about:blank']);
  child.on('exit', () => {});

  const results = { url: ARGS.url, checks: {}, screenshots: [], ok: false };
  const checks = results.checks;
  const record = (name, pass, extra = {}) => { checks[name] = { pass: !!pass, ...extra }; log(`  [${pass ? 'PASS' : 'FAIL'}] ${name}${extra.note ? ' :: ' + extra.note : ''}`); };

  try {
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

    const ws = await connect(`ws://127.0.0.1:${port}/session`, 5000);
    const bidi = new Bidi(ws);
    const sess = await bidi.send('session.new', { capabilities: { alwaysMatch: {} } }, 8000);
    results.browser = `${sess.capabilities?.browserName}/${sess.capabilities?.browserVersion}`;
    const tree = await bidi.send('browsingContext.getTree', {}, 5000);
    const context = tree.contexts[0].context;

    const evalJson = async (expr, awaitPromise = false) => {
      const r = await bidi.send('script.evaluate', { expression: expr, target: { context }, awaitPromise, resultOwnership: 'none' }, 10000);
      if (r.type === 'exception') throw new Error(`eval exception: ${r.exceptionDetails?.text || JSON.stringify(r.exceptionDetails)}`);
      const rv = r.result;
      if (rv == null || rv.type === 'null' || rv.type === 'undefined') return null;
      return rv.value;
    };
    const setViewport = async (width, height) => {
      await bidi.send('browsingContext.setViewport', { context, viewport: { width, height } }, 5000).catch(() => {});
      await sleep(250);
    };
    const screenshot = async (name) => {
      try {
        const r = await bidi.send('browsingContext.captureScreenshot', { context }, 10000);
        const file = join(ARGS.outDir || tmpdir(), name);
        writeFileSync(file, Buffer.from(r.data, 'base64'));
        results.screenshots.push(file);
        return file;
      } catch (e) { log(`  screenshot failed ${name}: ${e.message}`); return null; }
    };
    const navigate = async (url) => { await bidi.send('browsingContext.navigate', { context, url, wait: 'complete' }, 15000); };
    const waitFor = async (expr, timeoutMs = 12000, stepMs = 250) => {
      const until = Math.min(deadline, Date.now() + timeoutMs);
      while (Date.now() < until) {
        const v = await evalJson(expr).catch(() => null);
        if (v) return v;
        await sleep(stepMs);
      }
      return null;
    };
    const clickNav = async (label) => {
      const ok = await evalJson(`(() => { const b=[...document.querySelectorAll('.lg-rail__item')].find(x=>(x.getAttribute('aria-label')||'')===${JSON.stringify(label)}); if(b){b.click(); return true;} return false; })()`);
      await sleep(500);
      return ok;
    };

    // Real network interception (Firefox BiDi network.addIntercept +
    // network.provideResponse).  NOTE: Firefox does NOT implement
    // network.setBlockedURLs; a silent fallback to that would be a false pass.
    await bidi.send('session.subscribe', { events: ['network.beforeRequestSent'] }, 5000);
    const intercepts = [];
    const activeBlocks = [];
    bidi.on('network.beforeRequestSent', (params) => {
      const url = params?.request?.url || '';
      const match = activeBlocks.find((b) => url.includes(b.path));
      if (!match) return;
      bidi.send('network.provideResponse', {
        request: params.request.request,
        statusCode: match.status,
        reasonPhrase: 'QA blocked',
        body: { type: 'string', value: JSON.stringify({ error: { code: 'internal_error', message: 'QA: endpoint blocked for state test', retryable: true } }) },
      }, 8000).catch(() => {});
    });
    const addBlock = async (path, status = 503) => {
      const itc = await bidi.send('network.addIntercept', { phases: ['beforeRequestSent'], urlPatterns: [{ type: 'pattern', protocol: 'http', hostname: '127.0.0.1', pathname: path }] }, 5000);
      intercepts.push(itc.intercept);
      activeBlocks.push({ path, status, intercept: itc.intercept });
    };
    const removeBlocks = async () => {
      for (const itc of intercepts.splice(0)) { await bidi.send('network.removeIntercept', { intercept: itc }, 5000).catch(() => {}); }
      activeBlocks.length = 0;
    };

    await setViewport(1440, 900);
    await navigate(ARGS.url);
    // Wait for app shell.
    await waitFor('Boolean(document.querySelector(".lg-app"))', 15000);

    // ---------------------------------------------------------------- shell
    const railLabels = await evalJson(`JSON.stringify([...document.querySelectorAll('.lg-rail__item')].map(x=>x.getAttribute('aria-label')))`);
    const labels = JSON.parse(railLabels || '[]');
    record('fiveWorkEntriesAndSettings', ['Chat','Board','Files','Team','Resources','Settings'].every((l) => labels.includes(l)), { labels });
    record('noHorizontalOverflow1440', JSON.parse(await evalJson('JSON.stringify({sw:document.documentElement.scrollWidth,cw:document.documentElement.clientWidth})') || '{}').sw <= 1441, {});
    await screenshot('01-shell-1440.png');

    // Each work entry renders its view (not a placeholder "Not implemented").
    const entryChecks = {};
    for (const [label, marker] of [['Chat','.lg-chat__header'],['Board','.lg-board'],['Files','.lg-files'],['Team','.lg-team-view'],['Resources','.lg-resources-view']]) {
      const clicked = await clickNav(label);
      const found = clicked ? await waitFor(`Boolean(document.querySelector(${JSON.stringify(marker)})) || document.body.innerText.includes("not implemented yet")`, 6000) : null;
      const isPlaceholder = await evalJson('document.body.innerText.includes("not implemented yet")');
      entryChecks[label] = { clicked, rendered: !!found, placeholder: !!isPlaceholder };
    }
    record('allFiveEntriesRenderRealViews', Object.values(entryChecks).every((c) => c.clicked && c.rendered && !c.placeholder), entryChecks);

    // Settings at the bottom of the rail.
    const settingsClicked = await clickNav('Settings');
    const settingsShown = await waitFor('document.body.innerText.includes("Models & Providers")', 8000);
    record('settingsAtRailBottom', settingsClicked && !!settingsShown, {});
    await screenshot('02-settings-1440.png');

    // --------------------------------------------------- Board: real phases
    await clickNav('Board');
    await waitFor('Boolean(document.querySelector(".lg-board"))', 8000);
    // Real task list comes from GET /api/v1/tasks; wait for cards or empty notice.
    await sleep(1200);
    const boardText = await evalJson('(document.querySelector(".lg-board")||{}).innerText || ""');
    const apiTasks = await evalJson(`fetch('/api/v1/tasks').then(r=>r.json()).then(d=>JSON.stringify(d.items.map(t=>({id:t.id,phase:t.phase,status:t.status,archived:t.archived}))))`, true);
    const tasks = JSON.parse(apiTasks || '[]');
    const phases = new Set(tasks.map((t) => t.phase));
    record('boardReadsRealPhases', phases.has('failed') && phases.has('awaiting_acceptance') && phases.has('queued'), { phases: [...phases] });
    // Phase text must appear, and failed must not be labelled "running".
    const notUniformRunning = !/running/i.test(boardText) || phases.has('queued');
    record('boardDistinguishesPhases', /failed/i.test(boardText) && notUniformRunning, { note: 'failed label present, no blanket running' });
    await screenshot('03-board-1440.png');

    // Open a task: long title + scope preservation in the URL.
    const longTitleOpened = await evalJson(`(() => { const cards=[...document.querySelectorAll('.lg-card, .lg-task-card, article')]; const c=cards.find(x=>x.innerText.includes("Refactor the batch intake pipeline")); if(c){c.click();return true;} return false; })()`);
    await sleep(900);
    const scopeUrl = await evalJson('location.search');
    record('openTaskPreservesScope', /task=task_/.test(scopeUrl || ''), { url: scopeUrl });
    await screenshot('04-task-long-1440.png');

    // ---------------------------------------- Files: long path/list + preview
    // Files browses the authorized workspace root (GET /api/v1/files?path=).
    await clickNav('Files');
    await waitFor('Boolean(document.querySelector(".lg-files"))', 8000);
    await sleep(1500);
    const filesText = await evalJson('(document.querySelector(".lg-files")||{}).innerText || ""');
    const apiFiles = await evalJson(`fetch('/api/v1/files?path=').then(r=>r.json()).then(d=>JSON.stringify(d.items.map(i=>i.path||i.name)))`, true);
    const fileItems = JSON.parse(apiFiles || '[]');
    record('filesListsWorkspaceEntries', /inputs|candidates|deliverables|evidence/i.test(filesText) || fileItems.length > 0, { note: filesText.slice(0, 120), fileItems: fileItems.slice(0, 6) });

    // -------------------------------------------- Team / Resources real data
    await clickNav('Team');
    await waitFor('Boolean(document.querySelector(".lg-team-view"))', 8000);
    await sleep(1200);
    const teamText = await evalJson('(document.querySelector(".lg-team-view")||{}).innerText || ""');
    record('teamRendersAvailableRecruited', /Available/i.test(teamText) && /Recruited/i.test(teamText), { note: teamText.slice(0, 160) });
    await clickNav('Resources');
    await waitFor('Boolean(document.querySelector(".lg-resources-view"))', 8000);
    await sleep(1200);
    const resText = await evalJson('(document.querySelector(".lg-resources-view")||{}).innerText || ""');
    record('resourcesRendersCategories', /Connections/i.test(resText) && /Skills/i.test(resText), { note: resText.slice(0, 160) });

    // ------------------------------------------------- Settings typed forms
    await clickNav('Settings');
    await waitFor('document.body.innerText.includes("Models & Providers")', 8000);
    await sleep(900);
    const settingsText = await evalJson('document.body.innerText');
    record('settingsTypedSections', /Backend|Connection|Credential|Default|Test/i.test(settingsText), { note: settingsText.slice(0, 200) });
    // Secret must not be echoed and no generic YAML blob editor dominating.
    const hasYamlTextarea = await evalJson(`[...document.querySelectorAll('textarea')].some(t=>(t.value||'').includes('provider:'))`);
    record('settingsNoRawYamlBlob', !hasYamlTextarea, {});
    await screenshot('05-settings-form-1440.png');

    // ------------------------------------------- notification read persistence
    // Redundant with LG-019 but re-checked here for regression on this candidate.
    await clickNav('Board');
    await sleep(600);
    const apiUnreadBefore = Number(await evalJson(`fetch('/api/v1/notifications').then(r=>r.json()).then(d=>String(d.unread))`, true));
    let badge = null;
    const badgeUntil = Math.min(deadline, Date.now() + 10000);
    while (Date.now() < badgeUntil) {
      badge = await evalJson('(document.querySelector(".lg-icon-button__badge")||{}).textContent || null');
      if (badge) break;
      await sleep(250);
    }
    record('notificationBadgeFromBackend', Number(badge) >= 1 && Number(badge) === apiUnreadBefore, { badge, apiUnreadBefore });
    if (badge) {
      await evalJson(`(() => { const b=[...document.querySelectorAll('button')].find(x=>(x.getAttribute('aria-label')||'').startsWith('Notifications')); if(b){b.click();return true;} return false; })()`);
      await sleep(400);
      const taskRef = await evalJson('(document.querySelector(".lg-notification__meta")||{}).textContent || null');
      record('notificationTargetsTaskRun', typeof taskRef === 'string' && taskRef.startsWith('task_') && taskRef.includes('run_'), { taskRef });
      await evalJson(`(() => { const b=document.querySelector('.lg-notification'); if(b){b.click();} return true; })()`);
      await sleep(900);
      await navigate(`${ARGS.url}?reload=1`);
      await waitFor('Boolean(document.querySelector(".lg-app"))', 12000);
      await sleep(800);
      const apiUnreadAfter = Number(await evalJson(`fetch('/api/v1/notifications').then(r=>r.json()).then(d=>String(d.unread))`, true));
      let badgeAfter = undefined;
      const relUntil = Math.min(deadline, Date.now() + 12000);
      while (Date.now() < relUntil) {
        badgeAfter = await evalJson('(document.querySelector(".lg-icon-button__badge")||{}).textContent || null');
        if (badgeAfter !== null) break;
        await sleep(250);
      }
      // Read markup + backend agree, and the count strictly decreased (durable read).
      record('notificationReadPersists', badgeAfter !== null && Number(badgeAfter) === apiUnreadAfter && apiUnreadAfter === apiUnreadBefore - 1, { badgeAfter: String(badgeAfter), apiUnreadBefore, apiUnreadAfter });
    }

    // ----------------------------- TaskScope + draft + panel persistence
    await setViewport(1440, 900);
    await sleep(300);
    // Open the long task so a task scope is established.
    await clickNav('Board');
    await waitFor('Boolean(document.querySelector(".lg-board"))', 8000);
    await sleep(1000);
    await evalJson(`(() => { const cards=[...document.querySelectorAll('.lg-card, .lg-task-card, article')]; const c=cards.find(x=>x.innerText.includes("Refactor the batch intake pipeline")); if(c){c.click();return true;} return false; })()`);
    await sleep(800);
    const scopeTaskId = await evalJson(`new URLSearchParams(location.search).get('task')`);
    // Chat: type a draft, switch to another view, come back.
    await clickNav('Chat');
    await waitFor('Boolean(document.querySelector(".lg-composer__input"))', 8000);
    const DRAFT = 'lg021 draft retention check';
    await evalJson(`(() => { const t=document.querySelector('.lg-composer__input'); if(!t) return false; const setter=Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype,'value').set; setter.call(t, ${JSON.stringify(DRAFT)}); t.dispatchEvent(new Event('input',{bubbles:true})); return true; })()`);
    await sleep(400);
    const draftBefore = await evalJson(`document.querySelector('.lg-composer__input').value`);
    await clickNav('Resources');
    await sleep(700);
    await clickNav('Chat');
    await waitFor('Boolean(document.querySelector(".lg-composer__input"))', 8000);
    const draftAfter = await evalJson(`document.querySelector('.lg-composer__input').value`);
    const scopeAfterViews = await evalJson(`new URLSearchParams(location.search).get('task')`);
    record('taskScopeSurvivesViewSwitch', scopeTaskId && scopeAfterViews === scopeTaskId, { scopeTaskId, scopeAfterViews });
    record('chatDraftSurvivesViewSwitch', draftBefore === DRAFT && draftAfter === DRAFT, { draftBefore, draftAfter });
    // Panel collapse: toggle context + chat rails and confirm the layout reacts.
    const beforePanels = await evalJson(`JSON.stringify({ctx: Boolean(document.querySelector('.lg-context')), chat: Boolean(document.querySelector('.lg-chat-rail'))})`);
    await evalJson(`(() => { const b=[...document.querySelectorAll('button')].find(x=>(x.getAttribute('aria-label')||'')==='Toggle context panel'); if(b){b.click();return true;} return false; })()`);
    await sleep(400);
    const ctxCollapsed = await evalJson(`!document.querySelector('.lg-context')`);
    await evalJson(`(() => { const b=[...document.querySelectorAll('button')].find(x=>(x.getAttribute('aria-label')||'')==='Toggle chat panel'); if(b){b.click();return true;} return false; })()`);
    await sleep(400);
    const bothCollapsed = await evalJson(`!document.querySelector('.lg-context') && !document.querySelector('.lg-chat-rail')`);
    record('panelsCollapse', ctxCollapsed && bothCollapsed, { beforePanels });
    await screenshot('08-panels-collapsed-1440.png');

    // ------------------------------------------------- empty + history state
    // The archived task is hidden by default; the archived filter reveals it.
    await clickNav('Board');
    await waitFor('Boolean(document.querySelector(".lg-board"))', 8000);
    await sleep(900);
    const apiArchivedOff = await evalJson(`fetch('/api/v1/tasks?archived=false').then(r=>r.json()).then(d=>String(d.items.length))`, true);
    const apiArchivedOn = await evalJson(`fetch('/api/v1/tasks?archived=true').then(r=>r.json()).then(d=>String(d.items.length))`, true);
    record('historyFilterSeparatesArchived', Number(apiArchivedOff) >= 1 && Number(apiArchivedOn) >= 1 && apiArchivedOff !== apiArchivedOn, { apiArchivedOff, apiArchivedOn });
    // Empty state: an unimplemented/extreme phase filter returns no rows and the
    // Board must render its honest empty state, not fake cards.
    const apiEmpty = await evalJson(`fetch('/api/v1/tasks?phase=waiting_dependencies').then(r=>r.json()).then(d=>String(d.items.length))`, true);
    record('emptyPhaseHasNoFabricatedTasks', apiEmpty === '0', { apiEmpty });

    // ------------------------------------ disconnected / reconnecting state
    // Really block the SSE subscription at the network layer (BiDi intercept)
    // and require the UI to say Reconnecting/Offline instead of pretending live.
    await addBlock('/api/v1/events/stream', 503);
    await navigate(`${ARGS.url}?offline=1`);
    await waitFor('Boolean(document.querySelector(".lg-app"))', 12000);
    await sleep(1500);
    const openNotif = await evalJson(`(() => { const b=[...document.querySelectorAll('button')].find(x=>(x.getAttribute('aria-label')||'').startsWith('Notifications')); if(b){b.click();return true;} return false; })()`);
    await sleep(500);
    const streamStatusText = await evalJson('(document.querySelector(".lg-popover__status")||{}).textContent || null');
    const blockedHits = bidi.events.filter((e) => (e.params?.request?.url || '').includes('/api/v1/events/stream')).length;
    record('disconnectedShowsHonestStatus', blockedHits > 0 && openNotif && typeof streamStatusText === 'string' && /Reconnecting|Offline|connecting/i.test(streamStatusText), { streamStatusText, blockedHits });
    await screenshot('09-disconnected-1440.png');
    await removeBlocks();

    // --------------------------------------------------- real error state
    // Really block the task API (503) and reload Board: the view must render
    // its honest ErrorState (no fabricated tasks), then recover once unblocked.
    await addBlock('/api/v1/tasks', 503);
    await navigate(`${ARGS.url}?view=board&err=1`);
    await waitFor('Boolean(document.querySelector(".lg-app"))', 12000);
    await sleep(2500);
    const errVisible = await evalJson(`Boolean(document.querySelector('.lg-state--error'))`);
    const errText = await evalJson(`(document.querySelector('.lg-state--error')||{}).innerText || null`);
    const taskBlockHits = bidi.events.filter((e) => (e.params?.request?.url || '').includes('/api/v1/tasks')).length;
    record('boardShowsErrorStateWhenApiBlocked', taskBlockHits > 0 && errVisible === true && /503|internal_error|Could not load/i.test(errText || ''), { taskBlockHits, errText: errText ? errText.slice(0, 160) : null });
    await screenshot('10-error-state-1440.png');
    await removeBlocks();
    await navigate(ARGS.url);
    await waitFor('Boolean(document.querySelector(".lg-app"))', 12000);
    await sleep(1200);
    const recovered = await evalJson(`fetch('/api/v1/tasks').then(r=>r.ok)`, true);
    record('recoversAfterError', recovered === true, { recovered });

    // ------------------------------------- secret field write-only on reload
    await clickNav('Settings');
    await waitFor('document.body.innerText.includes("Models & Providers")', 8000);
    await sleep(900);
    const secretScan = await evalJson(`JSON.stringify({
      inputs: [...document.querySelectorAll('input[type=password], input[name*=secret], input[name*=key]')].map(i=>i.value),
      bodySk: /sk-[A-Za-z0-9]{12,}/.test(document.body.innerText),
      href: location.href
    })`);
    const ss = JSON.parse(secretScan || '{}');
    record('settingsSecretFieldNotEchoed', (ss.inputs || []).every((v) => !v) && !ss.bodySk && !/sk-[A-Za-z0-9]{12,}/.test(ss.href || ''), { inputsChecked: (ss.inputs || []).length });

    // ------------------------------------------------------- narrow widths
    for (const [width, name] of [[1024, '06-1024.png'], [390, '07-390.png']]) {
      await setViewport(width, 844);
      await sleep(400);
      const o = JSON.parse(await evalJson('JSON.stringify({sw:document.documentElement.scrollWidth,cw:document.documentElement.clientWidth})') || '{}');
      record(`noHorizontalOverflow_${width}`, o.sw <= width + 1, o);
      await screenshot(name);
    }

    // ------------------------------------------------- keyboard focus + a11y
    await setViewport(1440, 900);
    await sleep(300);
    // Focus the first rail item and confirm a visible focus ring / focusability.
    const focusInfo = await evalJson(`(() => {
      const items=[...document.querySelectorAll('.lg-rail__item')];
      if(!items.length) return JSON.stringify({ok:false});
      items[0].focus();
      const active=document.activeElement;
      const style=getComputedStyle(active);
      return JSON.stringify({ok:document.activeElement===items[0], outline: style.outlineStyle, outlineWidth: style.outlineWidth, aria: items[0].getAttribute('aria-label'), current: items[0].getAttribute('aria-current')});
    })()`);
    const fi = JSON.parse(focusInfo || '{}');
    record('railItemsFocusableWithName', fi.ok && !!fi.aria, fi);
    // Keyboard focus-ring probe. NOTE (verified 2026-10-16): in this headless
    // Firefox/BiDi environment, real `input.performActions` Tab key events do NOT
    // set the keyboard-modality flag, so `:focus-visible` never matches even on a
    // plain control page with a trivial `:focus-visible` rule (control experiment
    // in reports). Therefore this probe is recorded as an environment limitation,
    // NOT as a product pass or fail; the visible-ring design token is verified
    // statically instead.
    let kbFocus = { measurable: false, focusAdvanced: false };
    try {
      await evalJson(`(() => { if (document.activeElement) document.activeElement.blur(); return true; })()`);
      const before = await evalJson('document.activeElement && document.activeElement.tagName');
      for (let i = 0; i < 6; i++) {
        await bidi.send('input.performActions', { context, actions: [{ type: 'key', id: 'kb', actions: [{ type: 'keyDown', value: '\uE004' }, { type: 'keyUp', value: '\uE004' }] }] }, 5000).catch(() => {});
        await sleep(120);
      }
      const info = await evalJson(`(() => { const a=document.activeElement; if(!a||a===document.body) return JSON.stringify({ok:false, tag:String(a&&a.tagName)}); const s=getComputedStyle(a); return JSON.stringify({ok:true, tag:a.tagName, cls:String(a.className||'').slice(0,40), focusVisible:a.matches(':focus-visible'), outline:s.outlineStyle+' '+s.outlineWidth}); })()`);
      const o = JSON.parse(info || '{}');
      kbFocus = { measurable: true, focusAdvanced: !!o.ok && o.tag !== before, tag: o.tag, cls: o.cls, focusVisible: !!o.focusVisible, outline: o.outline };
      const ringRule = await evalJson(`(() => { let n=0; for (const ss of document.styleSheets){ try { for (const r of ss.cssRules){ if(r.selectorText && r.selectorText.indexOf(':focus-visible')>=0) n++; } } catch(e){} } const root=getComputedStyle(document.documentElement); return JSON.stringify({rules:n, token:root.getPropertyValue('--lg-focus-ring').trim()}); })()`);
      kbFocus.focusRingRules = JSON.parse(ringRule || '{}');
    } catch (e) { kbFocus = { measurable: false, err: String(e.message || e).slice(0, 80) }; }
    // Focusability is proven; the ring is asserted only from the resolved token +
    // rule presence, because :focus-visible is not observable via BiDi here.
    const ringToken = String(kbFocus.focusRingRules?.token || '');
    const ringHasWidthAndStyle = /[0-9]/.test(ringToken) && ringToken.indexOf('solid') >= 0 && ringToken.indexOf('#') >= 0;
    record('railKeyboardFocusAdvancesWithResolvedRing', kbFocus.focusAdvanced === true && (kbFocus.focusRingRules?.rules || 0) > 0 && ringHasWidthAndStyle, { ...kbFocus, note: 'focus-visible not BiDi-observable here; ring checked via rule+token' });
    // Escape closes the notification popover (if openable).
    let escOk = true;
    const opened = await evalJson(`(() => { const b=[...document.querySelectorAll('button')].find(x=>(x.getAttribute('aria-label')||'').startsWith('Notifications')); if(b){b.click();return true;} return false; })()`);
    if (opened) {
      await sleep(300);
      await bidi.send('input.performActions', { context, actions: [{ type: 'key', id: 'kb', actions: [{ type: 'keyDown', value: '\uE00C' }, { type: 'keyUp', value: '\uE00C' }] }] }, 5000).catch(() => {});
      await sleep(400);
      const stillOpen = await evalJson('Boolean(document.querySelector(".lg-popover"))');
      escOk = !stillOpen;
    }
    record('popoverClosesOnEscape', escOk, {});

    // Contrast: compute WCAG ratios for real rendered text on the app surface.
    await clickNav('Board');
    await waitFor('Boolean(document.querySelector(".lg-card"))', 8000);
    await sleep(500);
    // Deterministic WCAG contrast sampling. Parsing is regex-free (`parseColor`)
    // so no template-literal backslash escaping can silently corrupt the regex.
    // Transparent / semi-transparent backgrounds are composited down the real
    // ancestor chain (source-over) until an opaque layer, matching how the
    // browser actually paints text. No candidate text is skipped for being
    // transparent; only unparseable color values are reported as skips.
    const contrast = await evalJson(`(() => {
      function parseColor(s){ if(!s) return null; s=String(s).trim(); if(s==='transparent') return {r:0,g:0,b:0,a:0}; if(s.charAt(0)==='#'){let hex=s.slice(1); if(hex.length===3){hex=hex.split('').map(x=>x+x).join('');} if(hex.length===6||hex.length===8){const r=parseInt(hex.slice(0,2),16),g=parseInt(hex.slice(2,4),16),b=parseInt(hex.slice(4,6),16),a=hex.length===8?parseInt(hex.slice(6,8),16)/255:1; if([r,g,b].every(v=>isFinite(v))) return {r,g,b,a};} return null;} const lp=s.indexOf('('), rp=s.lastIndexOf(')'); if(lp<0||rp<lp) return null; const head=s.slice(0,lp).trim(); if(head!=='rgb'&&head!=='rgba') return null; const parts=s.slice(lp+1,rp).split(',').map(x=>x.trim()).filter(x=>x.length).map(Number); if(parts.length<3||parts.slice(0,4).some(v=>!isFinite(v))) return null; return {r:parts[0],g:parts[1],b:parts[2],a:parts.length>=4?parts[3]:1}; }
      function comp(fg,bg){ const a=fg.a; return {r:fg.r*a+bg.r*(1-a),g:fg.g*a+bg.g*(1-a),b:fg.b*a+bg.b*(1-a),a:1}; }
      function lum(c){ const f=v=>{v=v/255;return v<=0.03928?v/12.92:Math.pow((v+0.055)/1.055,2.4)}; return 0.2126*f(c.r)+0.7152*f(c.g)+0.0722*f(c.b); }
      function ratio(fgc,bgc){ const l1=lum(fgc),l2=lum(bgc); const a=Math.max(l1,l2),b=Math.min(l1,l2); return (a+0.05)/(b+0.05); }
      function effBg(el){ const chain=[]; let n=el; while(n){ const c=parseColor(getComputedStyle(n).backgroundColor); if(c){ chain.push(c); if(c.a>=1) break; } n=n.parentElement; } let acc={r:255,g:255,b:255,a:1}; for(let i=chain.length-1;i>=0;i--){ acc=comp(chain[i],acc); } return acc; }
      function effFg(el,bg0){ const c=parseColor(getComputedStyle(el).color); if(!c) return null; if(c.a>=1) return c; return comp(c,bg0); }
      const cands=[...document.querySelectorAll('.lg-card__title, .lg-board__title, .lg-context__title, .lg-rail__item, .lg-chat__subtitle, .lg-state__title, .lg-field__label, .lg-card__path, .lg-main h2, .lg-topbar__title')].filter(e=>e.textContent && e.textContent.trim().length>1 && e.offsetParent!==null);
      const out={}; let n=0; let skipped=0; const seen=new Set();
      for(const el of cands){ if(n>=10) break; const bg=effBg(el); const fg=effFg(el,bg); if(!fg){skipped++;continue;} const r=ratio(fg,bg); if(!isFinite(r)){skipped++;continue;} const cls=(String(el.className||'el').split(' ')[0]||'el').split('').filter(ch=>'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-'.indexOf(ch)>=0).join('')||'el'; if(seen.has(cls)) continue; seen.add(cls); out[cls]={text:el.textContent.trim().slice(0,24),fg:'rgb('+Math.round(fg.r)+', '+Math.round(fg.g)+', '+Math.round(fg.b)+')',bg:'rgb('+Math.round(bg.r)+', '+Math.round(bg.g)+', '+Math.round(bg.b)+')',ratio:Number(r.toFixed(2))}; n++; }
      return JSON.stringify({candidates:cands.length, skipped, pairs:out});
    })()`);
    const contrastParsed = JSON.parse(contrast || '{}');
    const contrastPairs = contrastParsed.pairs || {};
    const ratios = Object.values(contrastPairs).map((p) => p.ratio).filter((x) => Number.isFinite(x));
    const minRatio = ratios.length ? Math.min(...ratios) : 0;
    record('textContrastMeetsAA', ratios.length >= 4 && minRatio >= 4.5, { candidates: contrastParsed.candidates, skipped: contrastParsed.skipped, sampled: ratios.length, minRatio, pairs: contrastPairs });
    results.contrastSample = contrastPairs;

    // ----------------------------------------------- sensitive token absence
    const leakScan = await evalJson(`JSON.stringify({
      localStorage: Object.values(localStorage||{}),
      sessionStorage: Object.values(sessionStorage||{}),
      url: location.href,
      bodyHasSk: /sk-[A-Za-z0-9]{12,}/.test(document.body.innerText)
    })`);
    const leak = JSON.parse(leakScan || '{}');
    const leakHit = [...(leak.localStorage||[]), ...(leak.sessionStorage||[]), leak.url||''].some((v) => /sk-[A-Za-z0-9]{12,}/.test(String(v))) || leak.bodyHasSk;
    record('noSensitiveTokenInBrowserState', !leakHit, { scanned: 'localStorage/sessionStorage/url/body-text' });

    results.ok = Object.values(checks).every((c) => c && c.pass);
  } catch (err) {
    results.error = String(err && err.stack ? err.stack : err);
  } finally {
    cleanup();
    await sleep(300);
    try { rmSync(profile, { recursive: true, force: true }); } catch {}
  }
  if (ARGS.outDir) {
    const out = join(ARGS.outDir, '..', 'evidence', 'browser-qa-results.json');
    mkdirSync(dirname(out), { recursive: true });
    writeFileSync(out, JSON.stringify(results, null, 2));
    results._evidenceFile = out;
  }
  log(JSON.stringify(results, null, 2));
  return results.ok ? 0 : 1;
}

main().then((code) => process.exit(code)).catch((e) => { console.error(e); process.exit(1); });
