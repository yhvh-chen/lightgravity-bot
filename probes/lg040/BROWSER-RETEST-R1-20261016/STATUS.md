---
title: "LG-040 BROWSER RETEST R1-20261016 — STATUS"
doc_type: report
category: qa
status: "complete"
updated: "2026-10-16"
---

# LG-040 BROWSER RETEST R1 — STATUS

## Identity

| Field | Value |
|---|---|
| Role | Fresh independent pi BROWSER recheck (not product implementer) |
| Scope | Root PM only; owner writes `probes/lg040/BROWSER-RETEST-R1-20261016/**` only |
| Worktree | `/home/yhvh/code/lightgravity-bot-worktrees/lg040-browser-retest-r1-20261016` |
| Branch | `qa/lg040-browser-retest-r1-20261016` |
| HEAD | `75c6048` |
| Product base | fix `266945c` (byte-identical; `git diff 266945c HEAD -- backend frontend tests docs/08-interface-contract.md` empty) |
| Working tree | clean (only owned probe dir untracked; `.venv`/`frontend/dist` gitignored) |

## Objective

Close the two prior UNVERIFIED browser search cases on the **final repair
candidate** and capture a **single true end-state**, with **zero new model / LAN
requests**. Reuse prior real source data + Chat history from the prior live
BROWSER package as a **snapshot copy** into this owner's private dir.

## Frozen constraints (this owner)

- 0 new OCR / model / LAN requests. Browser original OCR budget already exhausted
  (2/2, NON-RENEWED). Whole-package total unknown beyond cited run (per-run ledger
  reset) — caveat retained, not washed to exactly 2.
- No new image/PDF uploads, no live OCR reprocess, no proxy reset / extra quota.
- Inference backend disabled or loopback DENY proxy; any attempt counted and
  refused BEFORE HTTP; never fall back to external env.
- No ASR / embedding / worker / DeepSeek product calls.
- No replay of old actions.
- Never write the original data / ledgers / reports; prior owner exited.

## Progress log

- [x] Read mandatory rules (`AGENTS.md`, `agent.md`, `design.md`), task `LG-040`,
      English-primary decision (`PROJECT.md` 2026-10-16), `RETEST-CANDIDATE.md`,
      prior BROWSER `REPORT.md` + driver results.
- [x] Verified HEAD `75c6048`, product tree byte-identical to fix `266945c`.
- [x] Snapshot-copied prior real data (`/tmp/lg040-browser-live/{data,ledger.json,
      app_ready.json,proxy_ready.json}`) into `evidence/snapshot/`; verified
      byte-identical + provenance (original matches frozen fixture hashes).
- [x] Verified prior owner exited; no other writer on the original data.
- [x] Own isolated venv (offline `uv sync`, no network) + reused real built
      frontend (`frontend/dist`, reproducible build of byte-identical
      `frontend/src`).
- [x] Pre-verified trusted-body search terms against the snapshot lexical index
      (only indexed trusted body = src1 `formal` with `correction`/`marker`).
- [x] Run new driver copy (corrected terms) on isolated free port, OCR backend
      DENY, single end-state capture.
- [x] Write REPORT.md.

## OUTCOME (2026-10-16)

- Startup blocker fixed: `orchestrate.py` `parents[5]` → `parents[4]` (+ heartbeat).
  The prior "orchestrator killed early" was a `FileNotFoundError` on a wrong
  venv path, not a product defect. See REPORT.md §2.
- Real harness ran on the candidate: **18/19 PASS, 0 UNVERIFIED**, deny ledger
  `attempts:0`. Both previously UNVERIFIED search cases now PASS
  (UI `correction` from the real trusted body; `rebuild_if_missing` `marker`
  with hash back-check). Revoke fail-closed fix re-confirmed.
- Single end-state + 5 screenshots captured once. Evidence: `evidence/run/`,
  `evidence/run-logs/`.
- Honest out-of-scope FAIL reported: narrow-390 Files Materials horizontal
  overflow (see REPORT.md §6).
- No leftover own processes; `:8123` and `/tmp/lg040-browser-live` untouched;
  prior run dir preserved (never wiped).

## R1 CONTINUATION (2026-10-16, root PM) — startup failure diagnosis

Prior retest wrapper exited 143 / max-rounds ~284 s, **no** REPORT and **no**
commit; last message: "run dir gone … orchestrator getting killed early …".
Diagnosis from EXISTING logs/scripts only (no full-orchestration replay, no
run-dir wipe):

- **ROOT CAUSE (verified, deterministic): off-by-one path bug in
  `scripts/orchestrate.py`.**
  - `ROOT = Path(__file__).resolve().parents[5]` resolves to
    `/home/yhvh/code/lightgravity-bot-worktrees` (the *parent of the worktree*),
    not the worktree root.
  - Therefore `VENV = ROOT/.venv/bin/python` = nonexistent
    `/home/yhvh/code/lightgravity-bot-worktrees/.venv/bin/python`.
  - `subprocess.Popen([VENV, …])` for the deny proxy raises
    `FileNotFoundError [Errno 2]` **immediately**, before any ready-file or log
    is written → wrapper sees no run dir content and reports "orchestrator
    killed early". Confirmed by direct reproduction (Popen raised) and by
    `/tmp/orch-trace.log` ending at `imported orchestrate`.
  - Correct value is `parents[4]` (cf. `launch_app.py` uses `parents[4]` ==
    worktree root, and `run_retest.sh` computes ROOT via `$PROBE/../../..`).
- **The real app/browser path itself WORKS.** Prior same-owner smoke
  (`/tmp/lg040-retest-sm2/smoke.out`, using the *correct* root): deny proxy up,
  app `http://127.0.0.1:55187` ready, `GET /api/v1/health` → **200**,
  `GET /api/v1/search?q=correction` → **200** with the expected trusted-body
  hit (`source_01M51N3TJT5QQGYGNB92V5C7MH`, basis `formal`, `verified:true`,
  snippet `LG040-FORMAL-EN Correction marker 2026-10-16`), `q=marker` → 200 hit,
  deny ledger `{"attempts": 0}`. So the blocker is harness wiring, **not** a
  product startup/runtime defect.
- **Not the cause:** missing parents dirs (RUN.mkdir is after the bad Popen),
  shell quoting, inherited ENV, SSE waits, or accidental self-pkill — all
  Popen happens *after* RUN.mkdir so the dir is created empty; no such kill was
  observed, and no product service on :8123 was touched.
- **Liveness check (this continuation):** no leftover retest/deny/launch/firefox/
  driver process owned by the prior run; the pre-existing :8123 service
  (`pid 3320745/3320750`, other worktree) is untouched and must be preserved.
  Prior run dir `/tmp/lg040-browser-retest-run` is empty except an empty
  `deny-proxy.log` — preserved (never wiped).

**Fix applied (owner scripts only):** `orchestrate.py` `parents[5]` →
`parents[4]` (worktree root). No product file touched.

