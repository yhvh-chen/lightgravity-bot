---
title: "LG-040 FINAL-CANDIDATE-20261016 — integration report (sequential --no-ff)"
doc_type: report
category: engineering
status: "candidate frozen — awaiting fresh independent QA; NO PASS/done claimed"
updated: "2026-10-16"
---

# LG-040 FINAL-CANDIDATE-20261016 — REPORT

## 0. Authority & nature

- Sole pi main **integration executor** for LG-040. Root PM scope only.
- This package **only** performs sequential `--no-ff` merges of the already-committed
  source branches, records this candidate, and prepares a fresh independent QA
  worktree. It does **not** run QA, does **not** start a QA worker (root dispatches
  after this package exits), does **not** review code, does **not** write product
  code/tests/docs beyond the merges, and makes **0** network/model calls.
- This document is **not a verdict**. **No whole-version PASS/done is claimed.**
  LG-040 remains **in-progress**.

## 1. Candidate

| Field | Value |
|---|---|
| Candidate commit | **`5d32b0414bab83d48be49be65f78331923f641c5`** |
| Candidate parents (final merge) | `74ee0990f26616de6eed6b26efb9509357f3bd26` + `6ad8e172580279abf23591ef8231b54831101f5e` |
| Base main (before this package) | `75c60487ad90c6712fa65c9f24ed235b45c06225` (clean, no stash, no other writer) |
| Prior runtime/integration base | `75c6048` (R1 integration candidate) |
| Product tree hash (`backend frontend tests`) @ candidate | `8c19ac6756caad5ab29547838628fdf1b7b519d7` |
| Product tree hash (`backend frontend tests`) @ `75c6048` | `77685f0c64ba0403f6ba93823e7162d37be8e7bd` |
| `backend/` tree hash @ candidate == @ `75c6048` | `a7c8cc73ecdf418e49e2e9ef4fe80e0a78a52b60` (**byte-identical**) |
| `frontend/` tree hash @ candidate | `a84dc87f64b387257dd4456df05d7068bffae7a6` |
| `tests/` tree hash @ candidate | `b443da19d6aaa03f251531f21ea34c0a80418a16` |

Exact product-side delta `75c6048..candidate` (`backend frontend tests`):

```
 frontend/src/views/files/files.css    | 35 ++++++++++++++++++++++++++++++++---
 tests/collaboration/test_claims.py   |  8 +++++++-
```

- **Backend runtime/API unchanged**: `git diff 75c6048 HEAD -- backend` is **empty**;
  `backend/lightgravity/sources/service.py` and `backend/lightgravity/api/` show **0** diff
  lines. The revoke fail-closed feature landed earlier in `266945c` and is carried
  unchanged.
- **Frontend-only Files delta**: only `frontend/src/views/files/files.css` changes
  (CSS only, no TSX/logic); byte-identical to Files owner tip `6ad8e17`.
- **Test-only race fix**: only `tests/collaboration/test_claims.py`; byte-identical to
  race owner tip `324de49`.
- `docs/` unchanged vs `75c6048` (`docs/08` byte-identical; contract stays `1.11.0`).

## 2. Sequential `--no-ff` merges (no cherry-pick; source receipts preserved)

Order and binding (second parent == source tip; all source tips are ancestors of candidate):

| # | Merge commit | Source branch @ tip | Content |
|---|---|---|---|
| 1 | `1494943` | `qa/lg040-quality-r1-20261016` @ `523d23a` | QUALITY R1 probes + METHOD-AUDIT (offline, 0 model calls) |
| 2 | `a774ba4` | `qa/lg040-api-retest-r1-20261016` @ `2e091f8` | API real-TCP retest (16/16 PASS) + race flake classification |
| 3 | `8222838` | `qa/lg040-browser-retest-r1-20261016` @ `59fe58e` | BROWSER retest (real UI search 2/2 PASS; revoke re-confirmed; narrow-390 observation) |
| 4 | `74ee099` | `fix/lg040-race-test-20261016` @ `324de49` | test-only single race-reason acceptance (no runtime edits) |
| 5 | `5d32b04` | `fix/lg040-files-narrow-20261016` @ `6ad8e17` | Files Materials narrow-width CSS fix |

- **No conflicts** in any merge; no manual resolution needed (only additive probe
  files + the two narrow product files). Source branches preserve their original
  tips (not moved, not rewritten).
- **All reports/raw preserved byte-identical**: `git diff <source tip> HEAD -- probes/lg040/<slice>/`
  is **empty** for QUALITY (incl. METHOD-AUDIT), API-RETEST, BROWSER-RETEST,
  RACE-TEST-FIX and FILES-NARROW-FIX slices.
- **No code changes beyond these five merges.** No unexpected product conflict.

Merge-parent evidence:

```
1494943: 75c60487… 523d23ac…      a774ba4: 1494943… 2e091f82…
8222838: a774ba4… 59fe58ea…       74ee099: 8222838… 324de491…
5d32b04: 74ee099… 6ad8e172…
```

## 3. Runtime/API + frontend + test-only facts

- **Runtime backend unchanged since `75c6048`/API retest.** `backend/` tree hash is
  identical to `75c6048`; the API-RETEST slice verified the candidate product tree
  `77685f0c…` (== fix `266945c`) over real loopback TCP, 16/16 PASS, on the same
  backend tree this candidate still carries.
- **Frontend-only Files delta** (`files.css`), verified by the Files owner with a
  real built `frontend/dist`, real Firefox WebDriver BiDi, 13/13 PASS on
  390/1024/1440 (ledger `{"attempts":0,"events":[]}`). Not re-run here.
- **Test-only race fix** (`test_claims.py` set-membership assertion); runtime code
  untouched. Full completed evidence below.

## 4. Full pytest evidence (race-test report; one complete run)

From `probes/lg040/RACE-TEST-FIX-20261016/REPORT.md` §Evidence (raw archived in
`raw/full_backend_pytest_completed_stdout.txt`):

```
863 passed, 5 skipped, 1 warning in 104.35s (0:01:44)
PYTEST_EXIT=0
```

- Command: `python -m pytest backend tests -q -p no:cacheprovider --basetemp=/tmp/lg040-racefix-fullpytmp`
- HEAD at run time: `75c6048`; env: quality-gate/external-call vars unset; external calls 0.
- The **partial second run** captured at `raw/full_backend_pytest_PARTIAL_killed_secondrun.txt`
  was killed at ~66% (wrapper exit143) and is explicitly **NOT valid** as a passing or
  failing result; it is retained for provenance only and is superseded by the
  independent `863 passed / exit 0` run above.
- **No full-suite rerun performed by this integration package** (integration-only;
  backend byte-identical, so the prior completed run binds).

## 5. Honest quality/coverage limits (do NOT over-claim)

- **Quality G2 top-1 experiment remains FAIL** (frozen result): image Q3′ ranked
  **2** (D2 text duplicate rank 1, margin 0.0448). The METHOD-AUDIT classifies this
  as a **same-content cross-modal ordering KNOWN_LIMIT**, but **the original result
  stays FAIL — it is not turned into PASS.**
- **OCR page-1**: the frozen slice scored CER **2.79** against a **600-char subset**
  reference; METHOD-AUDIT identifies F1 as a **BENCHMARK_DEFECT** (full-page native
  truth ⇒ CER **0.0026**, matching prior R7 0.0295 PASS). The frozen case stays
  **FAIL/INVALID_REFERENCE (historical)**; no retroactive gate change. Page-2 real
  scan CER **0.00**.
- **Quality durable counters**: **2 OCR POST** + **17 embedding POST**
  (embedding quota 17/18, **1 spare UNSPENT**), inference 19/≤20; **0** new calls in
  this integration package.
- **Browser original global OCR package count is UNKNOWN (≥2 confirmed)** because
  the per-run ledger resets each run; cap reached and **NON-RENEWED**. Not normalized
  to a clean number; **no new OCR calls here**.
- **Budget**: this package makes **0** network/model calls. **Do not claim all budget
  verified. Do not claim cost 0.** pi cost is **unknown, not 0**.
- LG-040 remains **in-progress**; this is **not** a PASS/done and not a whole-version
  verdict. Original R1 results/safety gates unchanged.

## 6. Fresh independent QA worktree (prepared, NOT started)

| Field | Value |
|---|---|
| Path | `/home/yhvh/code/lightgravity-bot-worktrees/lg040-final-qa-20261016` |
| Branch | `qa/lg040-final-20261016` |
| Base | exact frozen candidate **`5d32b0414bab83d48be49be65f78331923f641c5`** |
| Owner scope (root to define at dispatch) | `probes/lg040/FINAL-QA-20261016/**` (suggested) |

- Worktree created via `git worktree add -b qa/lg040-final-20261016 <path> 5d32b04`.
- **No QA run by this package; no QA worker started.** Root dispatches a fresh pi
  afterward. Before dispatch, confirm the QA worktree base equals the candidate.

## 7. CLI validation & process/state

- Node CLI `tasks validate backlog`: **OK — 41 tasks, no diagnostics.**
- Node CLI `tasks digest backlog`: **41 tasks: 1 todo, 1 in progress, 39 done**;
  LG-040 `agent:pi-lg040`, **in-progress**.
- **Source owners stopped**: all five source worktrees inspected clean/committed;
  tips `523d23a`/`2e091f8`/`59fe58e`/`324de49`/`6ad8e17` unchanged. Untracked
  `frontend/node_modules` in the Files worktree is an **owned symlink and was NOT
  staged/copied** (0 tracked node_modules in candidate).
- **`main` had no external writer** beyond this package (only its own bounded
  wrapper live). Working tree clean at candidate.
- The pre-existing product service on **:8123 was not touched**; no service
  restarts, no destructive cleanup, all historical artifacts/worktrees preserved.

## 8. Counters (this integration package)

- Network **0** · POST **0** · model calls **0** · product inference **0** · retries **0**.
- Product source edits by this package **0** (the only product delta is the merged
  Files CSS + test-only race fix).
- New backlog Task/Run **0** · SDK/default-model changes **0** · push/deploy/publish **0**.
- pi cost: **unknown, not 0**.

## 9. Status

- Candidate **frozen at `5d32b04`**, awaiting fresh independent QA.
- LG-040 **in-progress** — no PASS/done, no decision required here.
