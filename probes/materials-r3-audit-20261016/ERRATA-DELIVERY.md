---
title: "Materials R3 — ERRATA / DELIVERY addendum (audit finalization)"
doc_type: errata
category: probe
status: "complete — appended delivery/errata; original REPORT.md and raw evidence NOT rewritten"
updated: "2026-10-16"
---

# ERRATA-DELIVERY — materials-r3-audit-20261016

This file is **appended** after the original `REPORT.md`/`STATUS.md`/script evidence were written.
It **does not rewrite** the original `REPORT.md` bytes, the raw recompute artifacts, or R3 evidence.
It records the true delivery/finalization path so the package is not read as having completed itself.

## 1. What the original REPORT.md claimed prematurely

`REPORT.md` §10 ("Cost & git") states the package "is committed on
`qa/materials-r3-audit-20261016`" and that the "Round/time budget [was] respected". At the moment
`REPORT.md` was written, **neither was true**:

- **Not committed yet:** at REPORT-write time the five owned files were still **untracked**
  (`git status --porcelain --untracked-files=all` showed only `?? probes/materials-r3-audit-20261016/**`).
  The audit **commit is made only now, by the integration/finalization owner** (see §3), not by the
  original executor before it was stopped.
- **Budget not "respected" in the wall-clock sense:** the original executor was **terminated by the
  harness token budget at ~106 s**, i.e. the run **did not reach a normal exit**. The complete
  REPORT/scoring artifacts had already been flushed to disk before the stop, so the *content* is
  intact; but "budget respected" must not be read as a clean, self-terminated run.

## 2. Actual stop and finalization sequence

1. The audit executor wrote `STATUS.md`, `recompute_cer.py`/`.json`, `score_sep.py`, `REPORT.md`
   to the worktree (all five present, non-empty, readable).
2. **Harness token budget stopped the run at ~106 s**, *after* those complete files were written but
   **before** `git add`/`git commit`. Wrapper exit was **143** (SIGTERM) — **not** a normal exit 0.
3. The integration/finalization owner (explicit, post-inspection handover) then:
   - inspected the worktree and confirmed the only untracked paths are exactly the five owned files
     under `probes/materials-r3-audit-20261016/**`, with no other dirty tracked files and no
     extraneous writes;
   - **did not re-run** any test, scoring, network probe, or model call;
   - appended this errata;
   - committed **only** these owned files.

No unknown-write auto-replay occurred: this is an explicit new finalization step after inspection,
not an automatic resume of the stopped run.

## 3. Cost honesty — "0 model calls" is LAN-runtime-only, totals unknown

`REPORT.md` §10 records "0 network, 0 POST, 0 model calls" for the **audit's inference work**. That is
correct *only* for the local recompute (CPU-only offline string math against frozen evidence), and it
must **not** be extended to the whole job:

- The audit was executed by **pi on DeepSeek** (the project's development executor). pi's own
  **token/usage/cost for this audit is unknown** — no provider token ledger for this job was captured
  or is claimed here. It is **not 0**.
- The **shared/pi QA totals across the batch are unknown**, not zero.
- Therefore: **LAN runtime = 0 external POST/model calls** (true); **pi DeepSeek cost = unknown, not
  zero** (this errata).

## 4. Verdicts carried from the original audit (unchanged, correct)

The technical conclusions in `REPORT.md` remain valid and are hereby reconfirmed for integration
readers; see that file for full evidence and method:

- **Z2 whole-page CER 0.2948 reproduces**; corrected layout-agnostic segment CER **≈0.3172**,
  still **> 0.25** ⇒ table-class **FAIL is robust** to scoring method. (R3's own segment matcher is
  **flawed** — single-line best-overlap — and over-reports ≈0.3323/0.3281; that is a **scoring bug**,
  not a verdict flip.)
- **R3's `structure_pass` predicate is invented** (not protocol §4), **stricter in one direction and
  laxer in the protocol's actual row/col/cell terms**; directionally the structure FAIL is supported.
- **Render grid:** source private PDF p2 is **300 DPI** (1701×2873 px embedded); the product raster is
  `render(scale=2.0)` ⇒ **~816×1379 px ≈ 144 DPI**; `408×689` is the page **point size**, **not**
  the raster pixel grid. Render scale is **not env-configurable** (an additive config gap, B3).
- **Negative queries returning top-5 is expected NN candidate behaviour, not an ACL/contract
  failure.** No zero-hit requirement exists in LG-037 acceptance or documents; report the false
  hits but do **not** close LG-037 cross-modal quality, and do **not** calibrate a threshold on the
  same 7 queries.
- **Image vector callability ≠ text↔image quality.** Prior **Z1 CER 0.0423 stands** (true).
- **Service:** actual endpoint is **`192.168.8.12:11434` llama.cpp router** (not Ollama), healthy
  **only at the recorded timestamps** — not a general future promise.
- **ASR (LG-041) stays locked** on LG-039's quality gate; the "audio support declared" fact is not a
  new user decision to unlock it.

## 5. Evidence index (this addendum)

- `REPORT.md`, `STATUS.md` (original, bytes unchanged)
- `recompute_cer.py`, `recompute_cer.json` (independent CER + method sensitivity)
- `score_sep.py` (data-only negative-control/score-availability check)
- this `ERRATA-DELIVERY.md`
- Base `main @ db01cd6`; worktree
  `/home/yhvh/code/lightgravity-bot-worktrees/materials-r3-audit-20261016`.
