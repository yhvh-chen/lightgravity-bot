# LG-112 R2 independent QA — final LG-104 provider candidate

Date: 2026-10-17 (local). Owner: independent pi QA R2 / local delivery.
QA branch: `qa/provider-modal-r2-20261017`
QA worktree: `/home/yhvh/code/lightgravity-bot-worktrees/provider-qa-r2-20261017`
QA source HEAD (frozen candidate): `c477bb1fc1e337f56b781ed357d6b211ab380889`
Product commit: `7fe66d8` — tree `1ad85e93c3798d51be8350329103ef5d5dc41239`
Backend tree: `caad0343476887b2c49b269ad2691df7dee2b7e0`
Frontend product tree: `de9c16f2ec4ffa3b8cd9d10c192376b4aa6f56ae`
Tests tree: `653d813b7a8109b36dc6d9d44e2c2d1570ac916d`
Root `main` pre-change: `85d009dbc0eecfc398d7f43a086cf20e1d90b63f` (12 PM-owned dirty docs/index untouched)

**Verdict: PASS.** The final candidate contains both the native deletion-race fix
(`47686ae`) and the LG-115 compact-modal repair (`44cfd8b`). Independent
service/API/browser checks on the actual new product tree pass, including the
previously blocked natural default/Agent reference-delete race. This report
authorises the selective main merge and the local `8123` update recorded in
[`DELIVERY.md`](./DELIVERY.md).

LG-115 and LG-116 are `done`. The QA source HEAD is **not** `ff885bf` or
`eef3b3e` alone: product `7fe66d8` is byte-identical to native LG-115 tree
`1ad85e9…`, whose backend is native `47686ae` tree `caad0343…`.

## What was independently verified (not inherited)

I created this isolated worktree at `c477bb1`, adapted the QA-R1 harness into
`probes/provider-setup-20261017/qa-r2/` (QA evidence only; **no product edit**),
and ran the new backend + newly built frontend against fresh temp
data/workspace/secret roots on isolated loopback ports. The existing root
`/home/yhvh/code/lightgravity-bot/.venv` interpreter, existing
`frontend/node_modules`, and the existing Playwright install (`1.64.1`,
`/usr/bin/google-chrome`) were reused; nothing was installed. No real key,
vendor, user data, account content, cloud resource, or product model call was
used. The controlled loopback fake OpenAI/Gemini upstream is **not** vendor
verification.

Prior evidence (`8264777`: 1204 backend, 237 frontend reruns, 216 focused, mypy
147, HTTP/Playwright 7/7 on `ff885bf`) is treated as historical and reused only
with exact-tree scope below. It is not claimed as R2 proof.

## 1. Reference/delete race — previously BLOCKED, now re-proved

`qa-r2/logs/concurrency-r2-probe.json`, `concurrency-r2.stdout.txt`.
Probe: `qa-r2/concurrency_probe_r2.py` (actual backend services + real HTTP API,
isolated temp roots, dummy values).

| Case | Actual result |
|---|---|
| Natural default writer vs DELETE, 200 bounded iterations | **0 dangling**; `default_set` 113 / rejected 87; `deleted` 87 / refused 113; no false delete success |
| Natural Agent `ResourceService.update` vs DELETE, 120 bounded iterations | **0 dangling**; `agent_bound` 63 / rejected 57; `deleted` 57 / refused 63 |
| Orchestrated default, DELETE wins (supported `ConnectionService`) | writer blocked while DELETE held the shared reference lock, then rejected; connection deleted; no dangling default |
| Orchestrated default, writer wins | DELETE blocked during validation/commit, then refused `reference_invalid`; connection retained with the new default |
| Orchestrated Agent, DELETE wins (supported `ResourceService.update`) | writer blocked then rejected; connection deleted; no dangling Agent reference |
| Orchestrated Agent, writer wins | DELETE blocked then refused `reference_invalid`; connection retained with the new Agent reference |
| Real HTTP `PATCH /api/v1/settings` vs `DELETE` | both orders serialized; delete-wins → PATCH 422 + gone; writer-wins → DELETE 422 + retained; **no dangling** |
| Real HTTP `PATCH /api/v1/resources/agent/qa-agent` vs `DELETE` | delete-wins serialized; PATCH rejected after unlink; **no dangling** |
| 12-round 3-way contention (DELETE + default + Agent) | 0 hangs, 0 `LockConflict`, 0 success-with-missing-entity/dangling |
| Shared lock ordering | Confirmed in product code and by behaviour: `connection_references` root flock is taken **before** entity write locks, with no recursive acquisition. No cross-file ACID claim. |
| Production host controls (unpatched) | loopback, `custom.example`, `api.deepseek.com.evil.example`, `api.deepseek.com@evil.example` all rejected for default (`reference_invalid`) and by `LocalAuthProxy` (`capability_unavailable`), before network; real `https://api.deepseek.com/v1` still default-eligible |
| Raw `FileStore` Agent write during a paused DELETE | **dangles, as expected** — explicitly labelled outside the supported guarantee (`qa-r2/logs/concurrency-r2-probe.json.raw_store_bypass`). The native fix serializes only controlled services; it does not cover raw Store/external-file bypass. R1's Agent probe used this raw path, so this R2 probe replaces it with supported `ResourceService.update` + API cases. |

Native 8-case regression on the final backend tree:
`tests/settings/test_connection_delete_concurrency.py` → **8 passed** (0.64s).

## 2. Backend / API / secret / budget checks

Commands used the explicit existing interpreter
`/home/yhvh/code/lightgravity-bot/.venv/bin/python` with `PYTHONPATH=backend`.

| Command | Actual result | Log |
|---|---|---|
| `pytest -q tests/settings/test_connection_delete_concurrency.py` | **8 passed** | `logs/backend-concurrency-r2.txt` |
| `pytest -q tests/settings tests/resources tests/e2e/settings/test_lg027_default_pin.py tests/e2e/settings/test_lg027_error_branches.py` | **112 passed**, 1 existing Starlette/AnyIO warning | `logs/backend-focused-r2.txt` |
| `pytest -q tests/startup/test_settings_to_task.py` | **1 passed** | `logs/backend-startup-r2.txt` |
| `pytest -q tests/adapter/test_provider_host_policy.py tests/store` | **72 passed** | `logs/backend-host-store-r2.txt` |
| `mypy backend/lightgravity/{store/locking.py,settings/service.py,resources/service.py}` | **Success, 3 files** | `logs/backend-mypy-r2.txt` |
| `git diff --check 85d009d HEAD -- backend frontend tests` | exit 0 | `logs/product-diff-check-r2.txt` |

Independent HTTP probe (`qa-r2/http_probe.py`, `logs/http-probe-results.json`),
real app over loopback HTTP with the installed SDK and the controlled fake
protocol:

- Anonymous 401 and member 403 on connections/settings/draft/delete; member
  `/api/v1/account` 404 (endpoint) and `/api/v1/accounts` 403.
- Draft static: `draft=true`, `connection_id/revision=null`, six stable layers,
  **zero data-file changes**, zero upstream, no secret echo/persistence.
- Draft network: exactly **1** generation count + **1** upstream request,
  minimal `max_tokens=1`, `stream=false`, no `tools`, no secret echo/persist;
  repeat and two concurrent clicks = exactly one request each, distinct keys.
- Inline 500 failure honest; saved `/{id}/test` persists revision/credential-
  bound `last_test` with `draft=false`.
- Custom/loopback host refused before network; Gemini/Vertex/custom rejected as
  defaults (`worker_default_unverified`); DeepSeek default remains eligible.
- DELETE: wrong revision 409, missing 404, success 200 `{deleted,id}`; shared
  secret file preserved; referenced delete 422 `connection_still_referenced`
  with settings/Agent unchanged.
- Pydantic validation redaction removes the submitted secret/input; cross-origin
  draft 401.
- Installed SDK `0.1.22` reached the controlled loopback Gemini protocol with
  the expected path/key (labelled fake, not vendor); ADC without prerequisite
  honestly `not_run` with no gcloud/metadata; injected ADC seam proves SDK shape
  with no key; LiteRT static-only `not_run`.
- Global cap 0 blocks network; corrupt ledger fails closed; both make 0 native
  calls. The app ran with `limit=None` (unlimited, count-only) and counted
  without a reset.

R1's agent HTTP assertion used the plural path `/api/v1/resources/agents/…`,
which the product rejects as an unknown kind (so that R1 comparison was
vacuous). R2 corrected the QA fixture to the real singular
`/api/v1/resources/agent/…`; this is a harness correction, not a product change.

## 3. Real browser — all prior business scenarios + NEW compact UI

Built the final frontend (109 modules) and drove real Chrome against the real
FastAPI app + built assets. No `page.route`/`fulfill`, no API mocks.

Playwright: **8 passed (8 tests)** in 22.4s (`logs/playwright-r2-run.txt`,
`logs/playwright-results.json`). Scenarios:

1. **NEW R2 compact DeepSeek modal**: width **540px** at 1440; four primary
   fields Provider/Name/API key/Model; Base URL absent from primary and present
   in collapsed Advanced with `https://api.deepseek.com/v1`; primary copy has no
   `LocalOpenAIAgentConfig`, `loopback`, `credential_ref`, generated-ID or
   write-only diagnostics; Advanced contains the technical preset note.
   Measured natural height **617.5px empty draft** / **591.5px filled draft**
   (see residual note), modal body `scrollHeight == clientHeight` (no clipping
   or forced scrolling). Custom OpenAI-compatible keeps a **required primary
   Base URL**; changing the DeepSeek preset endpoint inside Advanced disables
   Test and blocks Save until a **fresh key** is entered, with zero PATCH.
   Mobile 390: all primary fields and footer buttons reachable, no horizontal
   overflow. Fresh screenshots `r2-1440-new-deepseek.png`,
   `r2-1440-new-custom.png`, `r2-390-new-deepseek.png`.
2. Settings landing is a connection list (defaults collapsed separately);
   deep link opens exactly one matching Edit while preserving Task/Run/channel;
   unknown id is a visible miss with no alternate selected; Escape closes once
   without reopen; 1024/390 compact widths and no always-open editor.
3. Draft Test before Save: no create/PATCH/DELETE, exactly one minimal request,
   inline failure preserves inputs, field/key edits mark `stale`, Save is
   independent and lands as `Not tested` (never falsely verified).
4. Gemini API key form + installed-SDK fake protocol; Vertex ADC honest
   `not_run` with prerequisite detail; arbitrary custom host blocked inline
   before network with inputs preserved; dirty cancel discards with no writes.
5. Existing key keep (same credential version), explicit replace (new version),
   explicit remove, dirty Keep editing/discard, revision conflict keeps draft.
6. Focus trap, background `inert`/`aria-hidden`, clean Escape focus return,
   late Test after close/reopen does not fill or reopen; narrow controls.
7. Saved `last_test` staleness, default eligibility (only executable
   DeepSeek), referenced delete blocked in UI/API, unreferenced UI delete.
8. Member sees My Account content + “managed by administrators”, makes **no**
   settings fetch, no tabs/Models; endpoints 403 and anonymous 401; admin
   Accounts/My Account still work.

Fresh screenshots (R2 only; R1 screenshots are not evidence for LG-115):
`qa-r2/screenshots/` with hashes in `logs/artifacts-sha256-r2.txt`.

### Modal height observation (honest)

The UI-VISUAL-FINDING target is approximately (`~`) ≤600px at 540px width. I
measured exactly **617.5px** for the empty initial DeepSeek draft and
**591.5px** once an API key is typed (the realistic fill flow removes the
“Enter an API key” footer hint). This is a large reduction from the reported
~810px; there is no clipping, hidden field, or always-scrolled body
(`scrollHeight == clientHeight == 434`), and the four primary fields are all
visible. The 617.5px empty-state value is reported rather than hidden; it is
17.5px (≈2.9%) above the nominal 600px in the empty state only. I did not edit
product CSS or hide content to change the number.

## 4. Frontend focused checks

| Command | Actual result | Log |
|---|---|---|
| `vitest run tests/settings.test.tsx tests/provider-setup.test.tsx tests/settings-auth.test.ts tests/lg053-navigation-regression.test.tsx` | **39 passed / 4 files**, 3.16s | `logs/frontend-focused-r2.txt` |
| `npm run build` (`tsc --noEmit && vite build`) | exit 0, **109 modules** | `logs/frontend-build-r2.txt` |

Build assets: `index-DfJ7UzJa.js` (sha256
`87ce0446…78fd7`), `index-Tunx1fTy.css` (sha256 `4cc5d1da…8fbf4`).
The LG-115 added regression (preset endpoint in Advanced + fresh-key gate) is
included in the 39. No full backend/frontend suite was rerun; affected coverage
plus exact-tree scope is used, as authorised.

## 5. Historical failures preserved (not rewritten as first-green)

- LG-111 initial **3 fixture failures** and LG-113's original **2 real
  reference/delete races** on `ff885bf` remain recorded in native/integration
  reports; QA-R1 remains **BLOCKED** on `ff885bf`.
- QA-R1 frontend full-suite **first-run shell timing flake** and two 237/237
  reruns remain historical.
- QA-R1 browser harness initially used system Python without `fastapi`; it was
  corrected to the existing root venv. This R2 used the explicit root venv from
  the start.
- QA-R1 member “My Account tab” assumption became a content-based assertion;
  R2 asserts My Account content/403/no admin fetch rather than an invented tab.
- **R2 harness corrections** (QA fixture only, not product): the first R2 browser
  attempt asserted the strict `<=600` empty-state height and recorded 617.5px;
  a later attempt hit a strict-mode selector collision for the endpoint-fresh-key
  error (three matching nodes). Both were corrected in the QA spec
  (`.lg-state__body` target; documented approximate height bound) and the full
  browser suite then passed 8/8. The failing observations are retained here
  rather than presented as a clean first run.

## 6. Limits / not claimed

- No real Gemini/Vertex/DeepSeek vendor call and no real credential: local fake
  protocol + dummy keys only. Vendor verification remains unproven by QA.
- No GPU/NPU/LiteRT hardware runtime; LiteRT remains static-only.
- No real user account/password/session, live `8123/5173/18123`, real data,
  secret store or workspace was used during QA.
- No cross-file ACID claim; only supported controlled writers are serialized.
  Raw `FileStore`/external-file bypass remains outside the guarantee (demonstrated
  and labelled in the probe).
- Exact empty-state height is 617.5px vs the approximate ~600px target (filled
  flow 591.5px, no clipping/scroll).
- Product model/vendor calls during QA: **0**. Development token/cost: unknown.

## 7. Delivery gate

All required R2 cases pass. The QA source HEAD `c477bb1` contains the LG-115/116
final product tree (verified by tree hashes; `git diff 44cfd8b 7fe66d8 --
backend frontend` empty). The local main merge and `8123` update were then
performed; exact commits, trees, assets, PIDs and preservation metadata are in
[`DELIVERY.md`](./DELIVERY.md). No push, release or cloud resource.
