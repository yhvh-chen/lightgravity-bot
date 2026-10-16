# LG-055 Playwright acceptance harness

Repeatable, real-browser acceptance harness for LightGravity Bot. It is
**isolated** from the repository's root frontend/backend dependencies and from
the developer's live 8123/5173 services:

* `e2e/node_modules` holds its own `@playwright/test` install (never the root
  `frontend/node_modules`);
* each run starts fresh temp data/workspace/secret roots and two real backends
  (team mode + single mode) on loopback ports 8791/8792 (override with
  `LG_E2E_TEAM_PORT`/`LG_E2E_SINGLE_PORT`);
* the Python fixture injects a deterministic direct-answer responder and sets
  `LIGHTGRAVITY_MAX_GENERATION_CALLS=0`, so **no product model/OCR/embedding
  call** is ever made and no credentials are required;
* the real built frontend (`frontend/dist`) is served by the same origin as the
  API. Tests never use `page.route`/`fulfill`: every request hits real routes
  and real file/JSONL persistence;
* traces, screenshots and videos are written to `/tmp/lg051-playwright-artifacts`
  on failure; reports go to `/tmp/lg051-playwright-report` and
  `/tmp/lg051-playwright-results.json`.

Test-only accounts (fake, created at fixture startup): `admin`/`lg-admin-test-pw`,
`alice`/`lg-alice-test-pw`, `bob`/`lg-bob-test-pw`.

## Install

```bash
cd e2e
npm install
```

Playwright is configured to use the machine's real Google Chrome
(`/usr/bin/google-chrome`, override with `CHROME_BIN`) so no browser download is
needed. For the optional Firefox project run `npx playwright install firefox`
and set `LG_E2E_FIREFOX=1`.

## Run

```bash
cd e2e
npm run typecheck          # tsc --noEmit over the harness
npm run test:list          # list specs without running/browsers
npm run api:smoke          # real HTTP, no browser (health/privacy/isolation)
npm test                   # full real-browser acceptance
```

The harness reuses the repository `.venv` Python (override with `PYTHON_BIN`
or `LG_E2E_PYTHON`). If this is a linked worktree without
`frontend/node_modules`, the harness creates a temporary symlink to the main
worktree's installed deps (read-only; the root install is never modified).
Set `LG_E2E_SKIP_BUILD=1` to reuse an already-built `frontend/dist`.

## Coverage

| Spec | Covers |
|---|---|
| `00-api-smoke` | contract 1.14.0, `personal_chat`, anonymous 401, per-identity private isolation, chat-only delivery |
| `01-meta-and-navigation` | seven resource categories in one rail, no second context/Scope/Run, all pages no fatal console/5xx/404, task_ref preservation, 1440/1024/390, drawer Escape/focus |
| `02-chat-composer` | simple composer + attachment menu, three-source cap, failure draft, Personal hides shared tools |
| `03-files-search` | top material search -> Files backlink + empty state, Files Task -> exact Chat scope + refresh/back |
| `04-personal-team-privacy` | two browser contexts, admin cannot read a member's private history, polling isolation, shared Task/source stay shared |
| `05-single-mode` | Team disabled with truthful note, outdated backend explicit failure state |

This harness is implemented by pi as LG-055 test setup; the version QA verdict
and user acceptance remain with the independent pi executor and the user.
