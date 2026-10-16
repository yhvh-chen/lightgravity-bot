---
title: "LG-040 API-RETEST-R1-20261016 — plan (independent QA, distinct from implementer)"
doc_type: plan
category: qa
status: "in-progress"
updated: "2026-10-16"
---

# LG-040 API-RETEST-R1-20261016 — PLAN

## 0. Authority & isolation

- Independent pi QA owner, distinct from the revoke-fix implementer
  (`pi-lg040-fix`) and from the original API QA owner. Root PM scope only.
- Worktree `/home/yhvh/code/lightgravity-bot-worktrees/lg040-api-retest-r1-20261016`,
  branch `qa/lg040-api-retest-r1-20261016`, HEAD `75c6048`.
- Candidate product tree (`backend frontend tests`) = `77685f0c64ba0403f6ba93823e7162d37be8e7bd`
  = fix tree `266945c` (independently re-verified by `git ls-tree -r | git hash-object`).
- **Owner scope: `probes/lg040/API-RETEST-R1-20261016/**` only.** No edits to old
  reports/harness/results/main/product/tests. New QA cases may copy old harness
  into my own path (adapted; expected now fixed 404). I do **not** run the old
  harness/scripts writing to the old raw dirs.
- No nested pi/agents. No product writes. No push/deploy/publish/reset/clean.
- Zero LAN/model calls; `LIGHTGRAVITY_OCR_*` / `LIGHTGRAVITY_VECTOR_*` unset.
- Separate free local TCP ports; never 8123. Server stopped in `finally` with
  port-release assertion.
- Python: private `.venv` created in this worktree via `uv sync --frozen`
  (no writes to other worktrees/caches/sources).

## 1. Required retest content (independently reproduce)

1. BEFORE → revoke → AFTER over **real loopback TCP** (uvicorn + create_app +
   real FileStore), source original/formal/machine preview (`content`) and
   download, all kinds.
2. All AFTER preview/download = **404 `not_found`** with `details.revoked=true`,
   with **NO source bytes served** (raw body byte-check for the marker).
3. Metadata remains diagnosable (`GET /sources/{id}` → status archived).
4. Raw files (original/formal/machine) preserved on disk.
5. Search `hits=[]` after revoke.
6. Repeated revoke idempotent.
7. reprocess / formal cannot resurrect.
8. Reversible archive/unarchive still preview/search/download 200.
9. normal user / global / task scopes preserved.
10. Forged/stale hit + query scope fail-closed.

## 2. Flaky-race classification (required)

- Classify the fix owner's FULL-RUN single failure
  `tests/collaboration/test_claims.py::test_two_owner_race_on_real_store_only_one_wins`
  as pre-existing / timing-assumption vs genuine product atomicity defect.
- Evidence: raw traceback (owner's own report + targeted repeat), product/test
  hashes baseline `2f277fa` (product `e1ec7b89`) vs fix `HEAD` (`77685f0c`).
- Baseline read-only at `/home/yhvh/code/lightgravity-bot-worktrees/lg040-quality-r1-20261016`
  (product == `e1ec7b89`, owner exited). Invoke its backend/tests READ-ONLY from my
  cwd with `PYTHONDONTWRITEBYTECODE=1` and pytest cache/temp inside my own path.
- Targeted repeat ≤3 runs each baseline and fix if needed.
- Do **not** label "pre-existing" merely from an isolated pass; do **not** waive a
  real concurrency defect. If genuine/important → report UNRESOLVED (no product fix).

## 3. Deliverables

- `REPORT.md` (main QA verdict, raw commands/exits, real-TCP counts, candidate
  hash, assertion expected/actual, process stop, no-inference) + `STATUS.md`.
- `raw/` machine-readable evidence; `owncases/` copied/adapted harness.

## 4. Budget

- 420s / 65 rounds / 115000 tokens bound (non-cache 0, retries 0).
- Report by round 25; commit by round 45. Cost pi unknown, not 0.
