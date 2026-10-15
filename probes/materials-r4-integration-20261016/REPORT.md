---
title: "Materials OCR R4 integration — REPORT (2026-10-16)"
doc_type: report
category: integration
status: "complete — R4 branch merged --no-ff into main; 22 focused tests + mypy exit 0; PM docs/task body updated; Z2 quality still FAIL, no status change"
updated: "2026-10-16"
---

# REPORT — materials-r4-integration-20261016

## 0. One-line result

`fix/materials-ocr-r4-20261016 @ 3cb68c6` (4 commits, base `db01cd6`, clean) was audited and merged
**`--no-ff`** into `main` as **`575f84a`** (parent `71a2041`). Only R4's own 8 product/doc/test files
plus `probes/materials-ocr-r4-20261016/**` entered; **no conflict**, **no product conflict**, **no
reset/clean/duplicate cherry-pick**, all raw/worktrees/dirty preserved. PM then updated PROGRESS top,
BACKLOG top, and the evidence BODY of LG-035 (status/assignee/frontmatter unchanged). Focused
integrated verification ran ONCE on `main`: **22 OCR tests passed**, **mypy 3 changed files clean**.
**Z2 table quality remains FAIL; LG-040/041 not unlocked; no full QA / no task-done claim.**

## 1. Starting state (verified, read-only)

- Repo root `/home/yhvh/code/lightgravity-bot`, branch `main`, **clean**, HEAD **`71a2041`**
  (ahead 246 of `origin/main`; not pushed).
- The four previously integrated evidence branches are confirmed **actual ancestors of `main`**:
  `test/materials-retry-20261016-r2`, `qa/lg040-gate-prep-20261016`,
  `test/materials-quality-20261016-r3`, `qa/materials-r3-audit-20261016` — all `ANCESTOR`.
- R4 branch worktree `/home/yhvh/code/lightgravity-bot-worktrees/materials-ocr-r4-20261016`
  clean, branch `fix/materials-ocr-r4-20261016 @ 3cb68c6`, base `db01cd6`, linear 4 commits:

| commit | message |
|---|---|
| `311c2d4` | freeze materials-ocr-r4 PLAN before POST |
| `8337e04` | product repair: expose optional `LIGHTGRAVITY_OCR_SCALE` through product path (default 2.0 unchanged, invalid rejected) |
| `e9fd5e5` | raster-grid correction + honest rescoring scripts |
| `3cb68c6` | R4 report + evidence (mechanism repair pass, Z2 table quality FAIL preserved, errata) |

> Note on `db01cd6..HEAD` deletion-look: comparing the R4 branch **to** `main` shows prior-probe files
> as "deleted" only because those files landed in `main` *after* `db01cd6` and are absent from the R4
> base. This is **not** an R4-owned deletion and was correctly not applied: the `--no-ff` merge kept
> every prior probe. R4's true owned diff vs its base is exactly the 22 files below.

## 2. Exact owned diff (R4 vs its base `db01cd6`)

Product / docs / tests (8 files, the only non-probe changes):

| file | change |
|---|---|
| `backend/lightgravity/sources/ocr/adapter.py` | `ENV_OCR_SCALE`, `MAX_OCR_SCALE=4.0`, `OcrScaleInvalid`, `parse_scale_env()` (finite, >0, ≤4; explicit diagnostic) |
| `backend/lightgravity/sources/processing.py` | `ProcessingConfig.from_env()` composes optional scale; default `2.0` |
| `backend/lightgravity/sources/service.py` | `build_source_service` passes `ProcessingConfig.from_env()` into real `ProcessingEngine` |
| `backend/lightgravity/sources/ocr/__init__.py` | export new names |
| `docs/08-interface-contract.md` | §6.6 implementation note, **no version bump** |
| `docs/09-source-intake-and-retrieval.md` | additive OCR render-scale note |
| `tests/sources/ocr/test_adapter.py` | env default/valid/NaN/inf/bounds/invalid tests |
| `tests/sources/ocr/test_processing.py` | actual-engine-receives-requested-scale tests |

Probes (new, `probes/materials-ocr-r4-20261016/**`, 14 files): `PLAN.md`, `REPORT.md`, `STATUS.md`,
`evidence/{health.json,ocr_post1_scale4.json,ocr_post_scale4.py,r3_ocr_post1_scale2_reused.json,raster_grid.json,raster_grid.py,score_r4.py,score_scale2_reused.json,score_scale4.json}`,
`private/{LG035-ZH-Z2.pdf,truth_z2_p2.txt}`. No frontend, no other features/tasks.

## 3. Merge

- `git merge --no-ff --no-edit fix/materials-ocr-r4-20261016` → **`575f84a`** (ort, no conflict).
- Tree proof: 22 files, +1704/−2; product/doc/test portion is exactly the 8 files in §2; probe portion
  is R4's own new dir. Distinguishes new product files from prior `probes/**`-only integration
  (`71a2041`), whose non-probe diff was empty.
- Post-merge ancestry re-verified: all five branches (four prior + R4) are `ANCESTOR` of `HEAD`.
- No genuine product conflict occurred; nothing was reset. Originals/worktrees preserved.

## 4. Integrated verification (ONCE, on `main`, existing env)

Run from `/home/yhvh/code/lightgravity-bot` with the existing project venv and `PYTHONPATH=backend`
(product code from this merge); **no dependency install, no network inference**:

- `PYTHONPATH=backend .venv/bin/python -m pytest tests/sources/ocr/test_adapter.py tests/sources/ocr/test_processing.py -q`
  → **22 passed** (exit 0).
- `PYTHONPATH=backend .venv/bin/python -m mypy --config-file pyproject.toml backend/lightgravity/sources/ocr/adapter.py backend/lightgravity/sources/processing.py backend/lightgravity/sources/service.py`
  → **Success: no issues found in 3 source files** (exit 0).

This is a local integrated smoke of the merged product path only. **No broad/full suite** was run
(focused scope; broadening not needed since no failure). Exact CLI output is the two lines above.

## 5. Quality verdict (unchanged, honest)

- **Mechanism repair PASS**: optional `LIGHTGRAVITY_OCR_SCALE` (default `2.0` unchanged, invalid
  rejected, reaches the real product `ProcessingEngine` → `PdfiumRasterizer`).
- **Z2 table quality FAIL preserved**: one bounded scale-4.0 retest improved Z2 page-2 OCR
  (whole-page CER 0.2991 → **0.2508**; fair token-weighted segment CER 0.3172 → **0.2689**) yet
  **stays > 0.25**; protocol §4 structure **unverified/fail**. Printed-page Z1 prior CER **0.0423**
  remains the only passing real page.
- **CER comparability**: the R4 fair token-weighted segment method **exactly reproduces the R3
  audit's 0.3172**, confirming the scoring methods are comparable. The R4 whole-page CER (0.2991/0.2508)
  is on the same normalization as the audit's 0.2948 — differences are the R4 rescale + method bug fix
  and are explained in the R4 REPORT §4. Therefore **no errata file is required** for a CER mismatch,
  and the frozen R4 REPORT was **not** edited.
- One stale-but-not-CER wording in the frozen R4 REPORT ("`main` unchanged (db01cd6)"): true at branch
  creation; actual `main` was `71a2041` pre-merge and is `575f84a` post-merge. This is an
  ancestry/timestamp fact, not a score/baseline CER mismatch, so it is recorded **here** rather than by
  appending an errata file to the R4 probe (raw REPORT left byte-unchanged).
- **No full QA, no task-done claim, no status change.** 3172 baseline reasoning not used as a pass.

## 6. PM docs & task body

- `PROGRESS.md` top: added R4 integration checkpoint (merge `575f84a`, focused verification result,
  honest Z2 FAIL, no status change).
- `BACKLOG.md` top: added R4 evidence line + crosslink; counts/statuses unchanged.
- `backlog/tasks/LG-035.md`: appended R4 evidence to the **验证记录 body only**; frontmatter
  `status: in-progress`, assignee, deps **unchanged**. Recorded latest repair commit `8337e04`,
  merge `575f84a`, quality FAIL reason (Z2 table/mixed + crossmodal + ASR blocks).
- LG-040/041 remain `todo`/unlocked; LG-040 QA **preparation exists, but is not a full gate and not
  passed**. No "new authorization required" wording — ordinary task work continues under the existing
  active authorization.
- New crosslinks added; new relative links from `backlog/tasks/LG-035.md` resolve to
  `../../probes/materials-ocr-r4-20261016/...` (two levels up) and from `BACKLOG.md` to
  `probes/materials-ocr-r4-20261016/...`.

## 7. Git / status

- Merge commit `575f84a` on `main`; R4 tip `3cb68c6` now an ancestor of `main`.
- `main` clean after commit; **not pushed / deployed / published**.
- No other worktrees, branches or raw evidence removed or modified.

## 8. Costs & limits

- **Product-LAN calls by THIS integration phase: 0** (no GET, no OCR POST, no ASR, no embedding);
  no new quality POST. The R4 branch's own counted calls (GET 1/1, POST 1/2, ASR 0, embedding 0) are
  historical and unchanged.
- **pi/DeepSeek executor cost: unknown, not zero** — not a zero-cost claim.
- **Not claimed**: full quality, task done, LG-035/037/040 closure, ASR, retrieval threshold tuning.
- **Remaining blocks**: Z2 table / mixed born-digital+scan / crossmodal retrieval quality; ASR quality
  gate (LG-041). Next step is the **already-named LG-040 concentrated version QA** on the integrated
  candidate. No independent tiny gate was added.

## 9. Crosslinks

- R4 probe: [REPORT](../materials-ocr-r4-20261016/REPORT.md), [PLAN](../materials-ocr-r4-20261016/PLAN.md),
  [STATUS](../materials-ocr-r4-20261016/STATUS.md).
- Prior integration: [materials-test-integration-20261016 REPORT](../materials-test-integration-20261016/REPORT.md).
- Task body: [LG-035](../../backlog/tasks/LG-035.md).
