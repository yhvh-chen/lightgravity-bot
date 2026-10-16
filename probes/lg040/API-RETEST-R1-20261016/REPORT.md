---
title: "LG-040 API-RETEST-R1-20261016 — independent API retest report"
doc_type: report
category: qa
status: "DONE — API slice PASS; flake classified test-timing (pre-existing, baseline==fix)"
updated: "2026-10-16"
---

# LG-040 API-RETEST-R1-20261016 — REPORT

## 0. Authority & independence

- Independent pi QA owner, **distinct from the revoke-fix implementer**
  (`pi-lg040-fix`) and from the original API QA owner. Root PM scope only.
- Worktree `/home/yhvh/code/lightgravity-bot-worktrees/lg040-api-retest-r1-20261016`,
  branch `qa/lg040-api-retest-r1-20261016`, HEAD `75c6048`.
- **Owner scope `probes/lg040/API-RETEST-R1-20261016/**` only.** No edits to old
  reports/harness/results, `main`, product (`backend/frontend/tests`) or docs. I did
  not run any old script that writes into an old raw dir; I wrote a fresh harness in
  my own path (the old ACL/real-TCP harnesses were read only as reference).
- No nested agents. No product writes. No push/deploy/publish/reset/clean.
- **Zero LAN/model calls**; `LIGHTGRAVITY_OCR_*` / `LIGHTGRAVITY_VECTOR_*` unset.
  Zero product inference. Retries 0.
- Separate free loopback TCP ports; **8123 not used** (it is occupied by the
  pre-existing `lightgravity-bot` main service; excluded). Server stopped in
  `finally`; port release asserted. No leftover QA servers/ports.
- Private Python env: `.venv` created in this worktree via `uv sync --frozen`
  (writes only into this worktree + shared uv cache; no other worktree touched).

## 1. Candidate under test

| Field | Value |
|---|---|
| HEAD | `75c6048` (branch `qa/lg040-api-retest-r1-20261016`) |
| Product tree (`backend frontend tests`) | `77685f0c64ba0403f6ba93823e7162d37be8e7bd` |
| Fix commit tree | `266945c` → same `77685f0c...` (byte-identical) |
| Baseline `2f277fa` product tree | `e1ec7b89...` |
| Worktree state | clean in the product/tests/main paths |

Re-verified independently:
`git ls-tree -r HEAD -- backend frontend tests | git hash-object --stdin`
→ `77685f0c64ba0403f6ba93823e7162d37be8e7bd`; same from `266945c`. The candidate
product tree equals the fix tree.

## 2. Real-TCP retest — 16/16 PASS (independent reproduction)

Fresh harness `owncases/harness_retest_tcp.py` (real uvicorn subprocess + real
`create_app` + real `FileStore`), every request over **real loopback TCP HTTP**
with `Cache-Control: no-store`. Marker `RETEST-MARKER-c4f19a`.

```
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$PWD/backend python \
  probes/lg040/API-RETEST-R1-20261016/owncases/harness_retest_tcp.py
  -> retest real-TCP: 16/16 PASS                             (exit 0)
```

| Case | Expected | Actual | Result |
|---|---|---|---|
| R1 BEFORE revoke content/download all kinds 200 + marker | all 200 and serve marker | all 6 kinds 200, marker served | PASS |
| R2 revoke 200 status=archived revoked=true | 200 archived revoked | 200 `status=archived`, `revoked=true` | PASS |
| R3 metadata remains diagnosable | 200 status archived | 200 `status=archived` | PASS |
| R4 search hits [] after revoke | 200 hits==[] | 200 `hits=[]` | PASS |
| R5 AFTER all kinds 404 not_found revoked + no bytes | all 404 `not_found` `revoked=true`, no marker | all 6 kinds 404 `not_found` `revoked=true`, no marker | PASS |
| R5b raw TCP body bytes no marker | all 404 and no marker | all 404 (`body_sha256=8102aeb0…`), no marker | PASS |
| R6 raw original/formal/machine preserved on disk | files present and byte-identical to pre-revoke served bytes | `original/doc.txt`, `derivative/machine.v1.md`, `formal/FORMAL.md` unchanged | PASS |
| R7 repeated revoke idempotent | 200 revoked, status still archived | 200 `revoked=true`, `status=archived` | PASS |
| R8 reprocess/formal cannot resurrect | both 404 not_found; status unchanged; views still 404 | 404/404, status archived, all views 404 | PASS |
| R9 archive keeps preview/search/download 200 | archive/content/download 200; hit present | 200/200/200; hit present | PASS |
| R10 unarchive restores openable | unarchive 200; status != archived; content 200 | 200; `received`; 200 | PASS |
| R11 global/task scopes preserved | task filter narrows, no cross-task leak | task_a sees a only; task_b excludes revoked; global listing has live sources | PASS |
| R12 forged/stale hit fail-closed | no forged hit; `source_stale` | no forged hit; `source_stale` (cached_v=999 vs current_v=1) | PASS |
| R13 unknown task_ref query | 200 hits==[] | 200 `hits=[]` | PASS |
| R14 missing source content | 404 not_found | 404 `not_found` | PASS |
| R15 cleanup server stopped / port released | port released | port released | PASS |

**Assertion detail (expected→actual), the repaired MAJOR:** before revoke
`GET /sources/{src_b}/content` and `/download` (all 6 kinds) = **200** serving
the marker; after `revoke` (200, `status=archived`, `revoked=true`) the same 6
kinds = **404 `not_found` `details.revoked=true`** and a raw byte scan of every
response body contains **no marker**. This is exactly the fix's expected status
and closes the original ACL-ADDENDUM FAIL (which had post-revoke content 200 /
download 200 with bytes served).

Machine-readable: `raw/retest_tcp_cases.json`.

## 3. Affected suites + focused + mypy (matched receipts)

```
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$PWD/backend python -m pytest tests/sources tests/api -q
  -> 219 passed, 1 skipped    (exit 0)          # matches fix receipt
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$PWD/backend python -m pytest \
  tests/sources/test_lg040_revoke_availability.py -q
  -> 8 passed                 (exit 0)
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$PWD/backend python -m mypy
  -> Success: no issues found in 138 source files  (exit 0)
```

All pytest caches/temp were forced inside my own path
(`-p no:cacheprovider --basetemp=/tmp/lg040-retest-pytmp/...`).

## 4. Flake classification — REQUIRED

Claim under review (fix owner's FULL-RUN single failure):
`tests/collaboration/test_claims.py::test_two_owner_race_on_real_store_only_one_wins`
was reported as "pre-existing timing/flaky … unrelated … passes in isolation".

### 4.1 Evidence inspected

- The fix owner's `REVOKE-FIX-R1-20261016` evidence contains **only a prose
  summary** of the failure — **no raw traceback / no captured assertion output**
  is stored (`STATUS.md` line 29, `REPORT.md` line 86). Gap noted honestly below.
- Product/test hashes: `tests/collaboration/test_claims.py` and the whole
  `backend/lightgravity/collaboration` tree are **byte-identical** between
  baseline `2f277fa` and fix `HEAD`:
  - `test_claims.py` blob `8c10321abb37e0b2462ce5770c31718ceb5baac2` at both.
  - collaboration tree `8fbfaa35feabe65b1a7969457c2ced6e35f9902b` at both.
  So any behavior of this test is **unchanged by the LG-040 fix**.

### 4.2 Targeted repeats (≤3 each; baseline read-only)

Baseline = `/home/yhvh/code/lightgravity-bot-worktrees/lg040-quality-r1-20261016`
product tree `e1ec7b89` (owner exited; invoked read-only from my cwd with
`PYTHONDONTWRITEBYTECODE=1`, pytest cache/basetemp inside my own `/tmp` path).
Baseline worktree `git status` stayed empty (0 changes).

| Context | Runs | Result |
|---|---|---|
| fix product, isolated | 3 | 3 passed |
| baseline product, isolated | 3 | 3 passed |

Isolated runs pass on **both** — consistent with the fix owner's "passes in
isolation" claim. Isolation alone is not the classification.

### 4.3 Forced-contention stress (decisive)

`owncases/race_probe.py` reproduces the identical two-owner race 300× against the
real store/service and records outcomes.

| Product | Iterations | Pass | Fail | **Double/zero grant** | Fail reason |
|---|---|---|---|---|---|
| fix `77685f0c` | 300 | 282 | 18 | **0** | all `not_discoverable` |
| baseline `e1ec7b89` (read-only) | 300 | 276 | 24 | **0** | all `not_discoverable` |

Machine-readable: `raw/race_probe_results_fix.json`,
`raw/race_probe_results_baseline.json`.

### 4.4 Root cause of the flake (actual mechanism, not a guess)

`CollaborationService.request_claim` (`backend/lightgravity/collaboration/service.py`
L244) computes `is_discoverable = request.subtask_id in visible` from a discovery
snapshot **taken before** the lease decision. `DiscoveryService.discover`
(`discovery.py` L167–L169) excludes a subtask once it is `running` with a live
lease (`state_not_claimable`). `LeaseManager.request_claim` (`lease.py` L197–L210)
tests `is_discoverable is False` **before** the `held_by_other` branch.

- If the loser's discovery snapshot is taken **before** the winner's committed
  write → loser sees it claimable and is refused `held_by_other`.
- If taken **after** the winner's commit → loser is refused `not_discoverable`.

Both are **fail-closed, single-winner** refusals. The test asserts the exact
reason `held_by_other`, so it races the discovery snapshot against the winner's
commit. That is a **test timing assumption**, not a product defect.

Atomicity is genuinely protected: `FileStore.write` takes a per-entity
`fcntl.flock` (`store/locking.py`) around read-revision → compare
`expected_revision` → atomic commit (`store/store.py` L241–L256); a loser gets
`RevisionConflict` and re-decides. Result: **0 double-grants and 0 zero-grants in
600 forced-contention iterations across baseline+fix.**

### 4.5 Classification verdict

**Pre-existing test timing flake — NOT a product atomicity defect and NOT an
LG-040 regression.** Basis: (a) collaboration product+test byte-identical
baseline vs fix; (b) identical flake rate/mechanism on baseline and fix (0
double/zero grants on both); (c) mechanism identified at source lines above.
Not labeled "pre-existing" from an isolated pass alone — it is labeled from the
baseline reproduction with forced contention. No product fix made; the test
itself is pre-existing and out of this task's scope.

## 5. Slice verdict & honesty

- **API slice: PASS.** The repaired MAJOR is independently reproduced as closed
  over real TCP: post-revoke preview/download (all kinds) = 404 `not_found`
  `details.revoked=true` with **no source bytes**, metadata still diagnosable,
  raw files preserved, search hits `[]`, idempotent revoke, no
  resurrection via reprocess/formal, reversible archive/unarchive still
  200/openable/searchable, normal/global/task scopes preserved, forged/stale and
  query-scope fail-closed.
- This is the **API slice only**. Whole-version verdict is **not mine alone**
  (BROWSER/QUALITY slices are separate contexts). The flake classification above
  is likewise a separate finding from the slice verdict.
- **Documentation gap:** the fix owner stored no raw traceback for its single
  full-run failure; I reconstructed the mechanism myself. The fix owner's
  "pre-existing flaky" conclusion is **correct**, but was under-evidenced at
  receipt time.

## 6. Counters & stop

- Real TCP: 1 loopback server for the retest (ephemeral port this run; released),
  plus per-iteration temp servers in the race probe (all stopped). **8123 not
  used.**
- External network / LAN / model calls: **0** · product inference: **0** ·
  retries: **0** · non-cache tokens: 0.
- Product/tests/main/docs writes: **0**. Files owned: `probes/lg040/API-RETEST-R1-20261016/**`.
- Baseline worktree invoked read-only; `git status` empty after use.
- No production thread/service touched outside my own server. No leftover
  QA server or listening port.
- Cost: pi unknown, **not 0**.

## 7. Raw evidence index

- `raw/retest_tcp_cases.json` — 16 real-TCP cases (expected/actual), 0 failures.
- `raw/race_probe_results_fix.json` — 300-iteration fix stress, 0 double-grants.
- `raw/race_probe_results_baseline.json` — 300-iteration baseline stress, 0 double-grants.
- `owncases/harness_retest_tcp.py`, `owncases/race_probe.py` — harness source.
