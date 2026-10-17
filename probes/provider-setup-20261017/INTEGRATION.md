# LG-111 serial integration report (provider modal + backend)

Status: **stable integration candidate, not merged, not deployed, not accepted**.
Independent LG-112 Playwright/real-backend QA is still required. Root PM owns the
normative Markdown; this report is evidence only.

## Candidate identity

- Worktree: `/home/yhvh/code/lightgravity-bot-worktrees/provider-integrated-20261017`
- Branch: `integrate/provider-modal-20261017`
- Base: root `main` `85d009dbc0eecfc398d7f43a086cf20e1d90b63f` (verified
  unchanged before integration).
- **Final candidate product commit:**
  `a6c700eb0ee9058a4235871910a421b1be457ebc`
- **Product tree hash:** `52218c7aca7b0c94d2c0f40a8aae76ad847fc33f`
- This evidence commit (logs + this report) is a child of the product commit; its
  hash is reported in the final LG-111 message.

Root drift observed and deliberately not copied: the root worktree had 12
uncommitted files (`.gitignore`, `BACKLOG.md`, `PROGRESS.md`, `PROJECT.md`,
`README.md`, `agent.md`, `design.md`, `docs/01`, `docs/05`, `docs/06`, `docs/07`,
`docs/08`). Root `main` HEAD itself was unchanged. No root index/worktree file was
modified by this integration.

## Exact source commits integrated

Backend (`feat/provider-backend-20261017`):

| Commit | Content |
|---|---|
| `d158c57` | LG-108 tester budget fix (cherry-pick of native `3f8f8e6`; not duplicated) |
| `ea09a86` | LG-109 provider fields/capabilities/draft-test backend + tests |
| `28f89e9` | LG-109 delivery report and backend logs |

Frontend (`feat/provider-modal-20261017`):

| Commit | Content |
|---|---|
| `9c40e78` | LG-106 SDK provider preset UI candidate |
| `2637dd2` | LG-106 UI delivery notes |
| `b2caea9` | LG-110 compact list/New-Edit modal + draft Test -> Save frontend/tests |
| `27415df` | LG-110 delivery report, interface notes and logs |

Only owned product/tests/evidence files were cherry-picked. No unrelated branch
history, root PM Markdown, root dirty file or prior Codex fix commit was copied.

## LG-111 final feature binding

The frozen docs/08 §18.4 / MODAL-CONTRACT addendum is implemented in the product
commit above:

1. **`DELETE /api/v1/settings/connections/{id}`**
   - JSON body `{expected_revision:number}`; success `200 {deleted:true,id}`.
   - Missing row `404`; stale revision `409 revision_conflict`.
   - Admin/runtime-token/same-origin-or-loopback gates apply; anonymous is 401,
     member is 403.
   - Server-side default-role and Agent reference checks run while the store's
     connection entity lock is held; a referenced/default connection is refused
     with the existing `reference_invalid` envelope and safe references.
   - The secret-store value is **not** deleted (it may be shared); defaults,
     Agent references and other records are **not** rewritten.
2. **Additive `ConnectionView.last_test`**
   - `null` or exactly the saved-test summary projection:
     `{test_id?,overall,finished_at,connection_revision,credential_version}`.
   - Derived read-only from the existing saved-test diagnostic log; no second
     Connection state and no draft result. A revision/credential mismatch is for
     the UI to render as stale, not to rewrite.
3. **Actual host capability binding**
   - `openai-compat` alone no longer implies executable/default eligibility.
   - Public Settings capabilities/default checks require the existing authorized
     DeepSeek host (`api.deepseek.com`). Arbitrary custom hosts and saved loopback
     hosts are configurable/testable but `executable=false`,
     `vendor_verified=false`, and cannot become a new default.
   - Legacy records are read without migration and show honest unavailability;
     their stored base URL/reference/unknown fields are preserved.
   - The existing loopback constructor seam remains usable for local tests and
     the compiler path, but it is not public saved-host execution policy.

Frozen 1.17.0 interface checks: draft `TestResult` uses
`connection_id`/`connection_revision` (nullable for unsaved drafts; no
`connection_ref` alias), six layer names remain, and `config_parse` may include
static SDK construction. Gemini/Vertex native HTTP `base_url` was not opened;
only the constructor loopback test seam exists. Every explicit test still uses
one-request-per-click bounds and the persistent global counter; cap 0/corrupt
ledger still fails closed.

## Verification (commands and exit)

Raw logs: [integration-logs](integration-logs/). All runs use isolated pytest
`tmp_path`/local fake upstreams and dummy keys only; no real product key, vendor
call, user data, service restart or publication.

| Command | Result |
|---|---|
| `PYTHONPATH=backend python -m pytest -q <targeted provider/settings/API/adapter/proxy/version/startup files>` | **129 passed**, exit 0 (`backend-targeted.txt`) |
| `PYTHONPATH=backend python -m pytest -q` | **1204 passed, 5 skipped**, exit 0 (`backend-full-suite.txt`) |
| `PYTHONPATH=backend python -m mypy backend/lightgravity` | **Success, 147 files**, exit 0 (`backend-mypy.txt`) |
| `git diff --check` | exit 0 (`git-diff-check.txt`) |
| `npx vitest run tests/settings.test.tsx tests/provider-setup.test.tsx tests/settings-auth.test.ts tests/lg053-navigation-regression.test.tsx` | **38 passed**, exit 0 (`frontend-focused.txt`) |
| `npx vitest run` | **237 passed / 23 files**, exit 0 (`frontend-tests-full.txt`) |
| `npx tsc --noEmit` | exit 0 (`frontend-typecheck.txt`) |
| `npm run build` | exit 0; `frontend/dist` removed before commit (`frontend-build.txt`) |

Covered checks include draft no-write/no-secret persistence, saved-vs-draft
binding, per-click budget/repeat tests, provider/endpoint secret isolation,
saved revision/credential reuse restrictions, Pydantic error input redaction,
admin/member/anonymous and origin gates, member/unknown-target/legacy behavior,
HTTP route priority, last_test shape and staleness source, DELETE
404/409/reference/default gates with no secret/reference mutation, capability
host binding, and Settings -> Task entry/pinning regressions.

One intermediate full-suite run failed three existing loopback-only integration
tests because they used an unreachable loopback base URL as a default. That is
the local constructor test seam, not a product host. Those tests now opt into
that seam explicitly; public capability/default policy stayed strict. The
successful full-suite rerun above is the final state.

## Frontend integration

The LG-110 candidate is integrated unchanged in product behavior: compact
540px modal (near/full-screen at mobile widths), Provider/Name/auth/Model fields,
directly visible custom Base URL, separate Test draft and Save, inline failed-test
preservation, stale/late-result isolation, key clearing, focus trap/return,
in-window discard confirmation, list status from `last_test`, separate defaults,
Edit/Delete rows and honest permission/deeplink/miss behavior. Delete calls the
new body+revision endpoint, so no 405-only button is shipped.

## Remaining limits / not claimed

- No independent Playwright campaign, visual acceptance, real backend/browser
  run at 1440/1024/390, or LG-112 sign-off (owned by the independent QA task).
- No real Gemini/Vertex/DeepSeek vendor call and no real credential read/output.
  Product model calls made by this integration: **0**; cost unknown.
- No native Task execution/default expansion, custom-host allowlist expansion,
  cloud resource, package install, remote push, main merge, 8123/5173/18123
  service restart, `frontend/dist` publication, or user data action.
- Existing pinned SDK `google-antigravity==0.1.22` and root environment were
  reused; nothing was installed.
- DELETE checks server-side references under the connection write lock; this
  integration does not claim a cross-file ACID transaction across unrelated
  concurrent Settings/Agent writers.
- Root PM still owns any normative Markdown registration for these §18.4 details.
