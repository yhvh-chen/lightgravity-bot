# LG-116 — final integration: compact modal + deletion-race repair + QA evidence

Date: 2026-10-17 (local). Owner: pi serial integration LG-116.
Status: **frozen candidate for independent LG-112 R2. Not merged, not deployed,
not accepted.** Root PM owns task status and normative documents.

## Gate and identity

| Item | Value |
|---|---|
| LG-114 candidate base | `eef3b3e83da269202f97b06f48644149c07496d8` |
| LG-114 product commit | `345f71f634e7ebf7e2455f6daf63bca639dee32f` (native `47686ae` tree) |
| Native race fix | `47686ae74f7a38250c2ec8c20e4af240d69964a3` |
| LG-115 native polish source | `44cfd8b91854448bd6255f22fd6c00ebd41945a2` (based on `eef3b3e`) |
| Native polish product tree | `1ad85e93c3798d51be8350329103ef5d5dc41239` |
| Integration worktree | `/home/yhvh/code/lightgravity-bot-worktrees/provider-final-20261017` |
| Integration branch | `integrate/provider-modal-final-20261017` |
| Final product commit | `7fe66d8` — tree `1ad85e93c3798d51be8350329103ef5d5dc41239` |
| Final candidate / evidence HEAD | `94ab246076e46434e217e037b13d19f247ca9813` |
| Candidate full tree (product + QA evidence) | `56082df79ddf46c2b0c9065ea048941db8def727` |
| Backend tree | `caad0343476887b2c49b269ad2691df7dee2b7e0` |
| Frontend product tree | `de9c16f2ec4ffa3b8cd9d10c192376b4aa6f56ae` |
| QA evidence source | `82647777181d78d24c064efd7f16420e34c92847` |
| QA evidence cherry-pick | `94ab246` (same commit as final candidate HEAD) |

Only `44cfd8b` and the evidence-only `8264777` were replayed onto the `eef3b3e`
base. Neither cherry-pick conflicted. No backend fix was duplicated.

### Integration commands

```text
git worktree add -b integrate/provider-modal-final-20261017 \
  /home/yhvh/code/lightgravity-bot-worktrees/provider-final-20261017 eef3b3e
git cherry-pick 44cfd8b   -> 7fe66d8
git cherry-pick 8264777   -> 94ab246
```

## Exact product identity

The final product tree is byte-identical to native LG-115 `44cfd8b`:

```text
7fe66d8 tree       1ad85e93c3798d51be8350329103ef5d5dc41239
44cfd8b tree       1ad85e93c3798d51be8350329103ef5d5dc41239
git diff 44cfd8b 7fe66d8 -- backend frontend  -> empty
```

Backend is unchanged from LG-114/native `47686ae`:

```text
HEAD backend       caad0343476887b2c49b269ad2691df7dee2b7e0
eef3b3e backend    caad0343476887b2c49b269ad2691df7dee2b7e0
47686ae backend    caad0343476887b2c49b269ad2691df7dee2b7e0
```

Frontend is exactly the native polish tree:

```text
HEAD frontend      de9c16f2ec4ffa3b8cd9d10c192376b4aa6f56ae
44cfd8b frontend   de9c16f2ec4ffa3b8cd9d10c192376b4aa6f56ae
eef3b3e frontend   a3532347a41e3abd49a65b09c8c6e18fd30d7bef
```

The QA cherry-pick adds **only** files under
`probes/provider-setup-20261017/qa/`. Non-QA changed files: **0**. Product diff
from `7fe66d8` to final HEAD: **empty**. QA scripts, logs, screenshots and the
blocked report were preserved verbatim; no product file was taken from QA.

## Reused evidence and checks run here

The product trees match the source commits above, so focused evidence is reused
with exact tree hashes instead of rerunning full suites.

### Backend — reused LG-114/native exact-tree evidence

Backend tree `caad0343…` is unchanged from native `47686ae` and LG-114
`eef3b3e`. Valid evidence includes: native concurrency regression **8 passed**,
settings/resources/LG-027 focused **112 passed**, startup node **1 passed**,
host policy + store **72 passed**, and mypy on the three changed product files.
The original **2 failed** concurrency reproductions on `ff885bf` remain recorded
as the pre-repair failure, not rewritten.

Run here as a minimal binding check on the final candidate:

| Command | Actual result | Log |
|---|---|---|
| `pytest -q tests/settings/test_connection_delete_concurrency.py` | **8 passed**, 0.73s, exit 0 | `integration-final-logs/backend-concurrency.txt` |

No full backend suite was rerun; the backend tree is exactly the independently
verified LG-114/native tree.

### Frontend — LG-115 evidence reused, focused checks repeated

Native LG-115 evidence on frontend tree `de9c16f2…` is applicable unchanged:
39 focused tests, `tsc --noEmit`, production build, and `git diff --check`.
The native report also preserves its initial added-test selector failure (exact
label lookup did not include the inline hint) and the correction to the existing
prefix-regex convention; this was a test-selector fix, not a product repair.

Run here on the exact final candidate, using the existing root
`frontend/node_modules` through a temporary worktree-only symlink (no install):

| Command | Actual result | Log |
|---|---|---|
| `vitest run tests/settings.test.tsx tests/provider-setup.test.tsx tests/settings-auth.test.ts tests/lg053-navigation-regression.test.tsx` | **39 passed / 4 files**, 2.91s, exit 0 | `integration-final-logs/frontend-focused.txt` |
| `npm run build` (`tsc --noEmit && vite build`) | exit 0, **109 modules**, dist removed afterward and not published | `integration-final-logs/frontend-build.txt` |
| `git diff --check eef3b3e HEAD -- backend frontend` | exit 0 | `integration-final-logs/diff-check-product.txt` |

No full frontend rerun is claimed for the new frontend tree. The prior **237**
full-suite passes and the first-run shell timing flake belong to the earlier
`a3532347…` frontend tree and remain historical QA evidence only.

Tree identity and QA-only checks are logged in
`integration-final-logs/tree-identity.txt` and
`integration-final-logs/qa-cherry-pick-files.txt`.

## Preserved failure history

- LG-111's original **3 fixture failures** remain in
  `INTEGRATION-FIRST-FAILURES.md`; they are not rewritten as first-green.
- The **2 real default/Agent reference-delete race failures** reproduced on
  `ff885bf` remain in native/QA evidence. Fix `47686ae` is included in this
  candidate and its concurrency regression passes.
- LG-112 R1 remains **BLOCKED / NOT DELIVERED** in `qa/QA-R1.md`. Its 7/7
  browser/API passes were on the old `ff885bf` candidate and do **not** transfer
  to this final tree.
- The frontend first-run full-suite flake and two subsequent 237/237 reruns
  remain explicitly recorded.
- `git diff --check eef3b3e HEAD` exits 2 only because three preserved QA log
  files contain new blank lines at EOF. Product-only diff check is clean; the QA
  evidence was not edited to manufacture a clean check.

## Limits / not claimed

- No new independent browser/visual acceptance. Native LG-115 did not measure
  the repaired desktop height or mobile screenshot; fresh LG-112 R2 must capture
  new 1440/1024/390 screenshots and verify the compact ~<=600px target and usable
  mobile form/buttons. Old LG-112 screenshots are not evidence for LG-115.
- No real vendor/model call, real credential read, package installation, cloud
  resource, GPU/NPU/LiteRT runtime, or user-data action. Product model calls:
  **0**. Development cost/token usage: unknown.
- QA probe selectors/expectations were not adjusted in product code. Fresh
  independent QA owns any necessary harness/selector adaptation.
- APIS/provider/capability/security behavior is unchanged from `eef3b3e` /
  native `47686ae`; no additional feature or custom-host expansion.
- No cross-file ACID claim; only supported controlled writers are serialized.
- No main merge, no `frontend/dist` publication, no service restart, no push.
  Root `main` remains `85d009d`, with the same 12 pre-existing PM-owned dirty
  docs/index-adjacent files. Protected services `2516844`, `2332542`, `1597462`
  and data/secret stores were untouched.
- No full backend or full frontend suite was rerun in this integration; exact
  tree-hash identity and the focused checks above are the basis.

## Freeze

Independent LG-112 R2 must check the exact candidate HEAD
`94ab246076e46434e217e037b13d19f247ca9813` (product commit `7fe66d8`, tree
`1ad85e93c3798d51be8350329103ef5d5dc41239`; backend
`caad0343476887b2c49b269ad2691df7dee2b7e0`, frontend
`de9c16f2ec4ffa3b8cd9d10c192376b4aa6f56ae`) before any main merge or local
`8123` delivery. Do not deploy `ff885bf` or `eef3b3e` alone.

The report/evidence commit containing this file is a child of `94ab246`; it
changes only this report and `integration-final-logs/`, leaving the product and
QA evidence trees above unchanged. Its exact branch HEAD hash is reported in the
LG-116 handoff.
