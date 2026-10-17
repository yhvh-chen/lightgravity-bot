# LG-112 independent QA — LG-104 provider milestone

Date: 2026-10-17 (local)
QA branch: `qa/provider-modal-20261017`
QA worktree: `/home/yhvh/code/lightgravity-bot-worktrees/provider-qa-20261017`
Candidate HEAD: `ff885bf3b1025fd3d313ee4dc3c8b4a494ac1757`
Candidate product commit: `a6c700eb0ee9058a4235871910a421b1be457ebc`
Candidate product tree: `52218c7aca7b0c94d2c0f40a8aae76ad847fc33f`
Root `main` pre-change: `85d009dbc0eecfc398d7f43a086cf20e1d90b63f` (12 PM-owned dirty docs untouched)

**Verdict: BLOCKED / NOT DELIVERED.**

The frozen candidate has a real reference/delete race: a concurrent supported
default or Agent-reference write can commit after the DELETE guard read and
before the connection unlink, leaving a dangling reference. Native LG-113
reproduced the same defect and supplied fix `47686ae74f7a38250c2ec8c20e4af240d69964a3`, but that fix is **not in this QA HEAD**. Per the delivery gate I did
not merge, deploy, restart `8123`, publish `frontend/dist`, or push.

## Candidate integrity checked

- `provider-integrated-20261017` was clean at `ff885bf`; product tree for
  `a6c700e` matched `52218c7…`.
- My isolated QA worktree was created from `ff885bf` without editing product
  source. QA-only files live under `probes/provider-setup-20261017/qa/`.
- Root `main` remained `85d009d` with exactly the 12 pre-existing dirty
  Markdown/index-adjacent files; none were staged, reset or overwritten.
- Existing SDK `google-antigravity==0.1.22`, Python venv, Chrome and frontend
  modules were reused. Nothing was installed and no cloud/model/vendor call was
  made.

## Tests I actually ran (exact candidate)

| Command | Actual result | Log |
|---|---|---|
| Focused backend (settings/adapter/provider API/team draft gates/LG027/startup/contracts) | **216 passed**, 1 warning, exit 0 | `qa/logs/backend-focused.txt` |
| Full backend `pytest -q` | **1204 passed, 5 skipped**, 1 warning, 183.62s, exit 0 | `qa/logs/backend-full.txt` |
| `mypy backend/lightgravity` | **Success, 147 files**, exit 0 | `qa/logs/backend-mypy.txt` |
| Frontend first full `vitest run` | **1 failed / 236 passed**: `tests/shell.test.tsx` legacy deep-link race; the same test then passed alone and two full reruns were **237/237** | `qa/logs/frontend-full-first-run-failed.txt`, `frontend-full-rerun1.txt`, `frontend-full-rerun2.txt` |
| `tsc --noEmit` | exit 0 | `qa/logs/frontend-typecheck.txt` |
| `npm run build` | exit 0; `dist/index-DVXoACii.js`, `dist/index-Tunx1fTy.css` | `qa/logs/frontend-build.txt` |
| Independent Playwright, real HTTP + real built frontend, 1440/1024/390 | **7/7 passed**, 20.4s | `qa/logs/playwright-run.txt`, `qa/logs/playwright-results.json` |
| Independent HTTP/API/security/provider probe | all assertions passed | `qa/logs/http-probe-results.json` |
| Independent reference/delete concurrency probe | **race reproduced** | `qa/logs/concurrency-probe.json` |

The initial frontend full-suite failure was not a product behavior failure in
the browser, but it is recorded rather than rewritten as first-green. Two
subsequent full runs were 237/237.

`git diff --check 85d009d a6c700e` reports only new blank lines at EOF in three
evidence Markdown/log files, not product code.

## Real-browser evidence (fake protocol explicitly not a vendor)

The harness starts the real candidate app on isolated loopback ports with fresh
temp data/workspace/secret roots, fixed QA-only accounts, and a controlled
loopback fake OpenAI/Gemini upstream with dummy keys. No `page.route`/`fulfill`,
static mock server, real account, real key or vendor host is used. The fake
upstream is QA infrastructure only; it is **not** real-vendor verification.

Passed browser cases:

- Settings landing is a connection list, not an always-open editor; defaults are
  a separate collapsed section.
- New/Edit is one modal, 480–560px at 1440/1024, near-full width at 390 with no
  horizontal overflow and visible footer controls.
- New Custom OpenAI-compatible has required Base URL; Provider/Name/auth/Model
  order is preserved; Gemini/Vertex/DeepSeek/LiteRT presets are selectable.
- Draft Test before Save sends exactly one minimal request
  (`max_tokens=1`, `stream=false`, no tools), records no create/save/PATCH/DELETE,
  and does not persist connection/secret/default/diagnostic data.
- Editing any field/key immediately marks the draft result stale.
- Inline network failure (`HTTP 500` from the fake upstream) preserves inputs;
  Save is independently allowed, closes the modal, selects the new row, and the
  saved list status is `Not tested`, never falsely `verified`.
- Saved key reopens blank/`Configured`; empty keep preserves the credential
  version; explicit replacement changes it; explicit remove clears it.
- Dirty Cancel/close asks in-window; Keep editing preserves fields; discard
  writes nothing. Revision 409 keeps the draft fields and shows the conflict.
- Focus is trapped, background receives `inert`/`aria-hidden`, clean Escape
  returns focus to the trigger, and a late Test after close/reopen does not fill
  the new draft or reopen the modal.
- Deep link opens the correct Edit once; unknown id shows a miss and selects no
  alternate; Task/Run/channel query context survives close with no reopen loop.
- Members see only My Account plus the “managed by administrators” notice, make
  no settings/connection fetch, and get real HTTP 403 on settings/test-draft/DELETE
  and 403 on account admin; anonymous gets 401. Admin Accounts/My Account still
  load.

Screenshots: `qa/screenshots/` (hashes in `qa/logs/artifacts-sha256.txt`).

## API/security/provider evidence

HTTP probe (`qa/logs/http-probe-results.json`):

- Draft static/no-network: `draft=true`, `connection_id=null`,
  `connection_revision=null`, six stable layer names, cannotary in response or
  data-directory scan, zero data-file changes, zero upstream requests.
- Draft network through the QA-injected loopback fake: 1 generation reservation,
  1 upstream request, one minimal envelope, dummy key only in memory/request,
  no connection/secret/diagnostic write.
- Repeated and two concurrent tests each made exactly one request with distinct
  credentials; no process-lifetime cap regression.
- Saved `/{id}/test` still persists a safe revision/credential-bound `last_test`.
- Arbitrary custom host is blocked before network (`CapabilityUnavailable:
  upstream host ... is not authorized`); the UI surfaces this inline and keeps
  inputs. It is an honest error path, not a layered passed result.
- Gemini/Vertex defaults are rejected with `reference_invalid` /
  `worker_default_unverified`; custom/loopback hosts are not default-eligible.
- DELETE wrong revision **409 revision_conflict**, missing **404**, success
  **200 `{deleted:true,id}`**; the shared secret file remains after connection
  deletion. Non-concurrent referenced delete **422 `reference_invalid`** with
  safe default/Agent refs and no settings/Agent mutation.
- Pydantic validation redaction removes the submitted secret and input.
  Cross-origin draft is 401.
- Installed SDK 0.1.22 reached a controlled loopback fake Gemini protocol with
  the expected path/key; ADC without a real prerequisite is honestly `not_run`
  and makes no gcloud/metadata request; the injected ADC seam separately proves
  the SDK shape with no key. LiteRT stayed static-only with package absent and
  model file present; it did not claim a pass.
- Global cap 0 blocks network; corrupt ledger fails closed; both made zero
  native calls.

## BLOCKER R1 — reference/delete concurrent ordering

Owner: native Codex LG-113 / pi integrator LG-114. File evidence:
`qa/logs/concurrency-probe.json`.

Steps (same product service methods the HTTP routers call, isolated temp data):

1. Create an executable DeepSeek connection, clear the worker default.
2. Run DELETE and `PATCH /settings` (set worker default) concurrently.
3. Also repeat with an Agent-reference write paused after the DELETE guard read.

Expected: one writer fails cleanly or DELETE is refused; no settings or Agent
reference may point at a removed connection.

Actual on `ff885bf`:

- Natural schedule reproduced on the first iteration: both `default_set` and
  `deleted` succeeded. Settings retained `default_worker_connection_ref =
  "race-natural"` while the connection was gone; resolving the default raised
  `EntityNotFound`.
- Orchestrated Agent schedule similarly left `agent_refs=["race-agent-ref"]`
  after the connection was deleted.
- This confirms the guard is only serialized against the connection entity lock;
  default/Agent writers use different locks.

Native fix `47686ae` (shared data-root reference lock acquired before entity
locks) and its 8-case regression are **not integrated into QA HEAD**, so this
candidate cannot be published. PM should arrange LG-114 pi integration of
`47686ae` into a new frozen candidate, then request independent LG-112 retest of
the exact new tree (including this concurrency probe and the browser suite).

## Remaining declared limits

- No real Gemini/Vertex/DeepSeek vendor call; local fake protocol and dummy keys
  only. Vendor verification remains unproven by this QA.
- No GPU/NPU/LiteRT hardware runtime; static checks only.
- No real user account/password/session, live `8123/5173/18123` service, root
  data, secret key, or user workspace was used.
- No cross-file ACID claim; the native fix only serializes supported controlled
  writers, not raw Store/foreign-file bypasses.
- Frontend full-suite first-run flake recorded above; it did not reproduce in
  the browser or in two later full runs.
- Minor type hygiene: the frontend draft result type carries unused
  `connection_ref`/`revision` aliases and a non-null `connection_id` even though
  the wire draft returns null. No wire/behavior impact observed.

## Delivery state

Nothing was merged to `main`, no `frontend/dist` was published, no service was
restarted, and nothing was pushed. Root PM owns the final task state and
`DELIVERY.md`; this report is QA evidence only.

Pending: integrate native `47686ae` into a new candidate and independently
retest before the authorized `8123` update.
