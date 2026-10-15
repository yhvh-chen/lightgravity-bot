---
title: "Materials OCR R4 — bounded OCR config repair + independent rescore"
doc_type: report
category: probe
status: "complete (within bound) — mechanism repair PASS; Z2 table quality still FAIL; no status/task change"
updated: "2026-10-16"
---

# REPORT — materials-ocr-r4-20261016

Base `main @ db01cd6`. Branch `fix/materials-ocr-r4-20261016`. Worktree
`/home/yhvh/code/lightgravity-bot-worktrees/materials-ocr-r4-20261016`.

Frozen PLAN: commit `311c2d4` (`probes/materials-ocr-r4-20261016/PLAN.md`),
written **before** any inference POST.

## 0. One-line result

The R3 audit's implementation gap **B3 is repaired**: an optional
`LIGHTGRAVITY_OCR_SCALE` (default `2.0` unchanged, invalid values rejected,
reaching the *actual* product `ProcessingEngine` → `PdfiumRasterizer`) now exists
and is exercised end-to-end. One bounded scale-4.0 retest **improved** the Z2
page-2 OCR (whole-page CER 0.2991 → **0.2508**; fair token-weighted segment CER
0.3172 → **0.2689**; exact row tokens 6 → 8/15) but the **Z2 table quality still
FAILS** every scoreable gate (> 0.25, structure unverified/fail). The mechanism
repair passing is **not** a table-quality pass. No task status was changed.

## 1. Authority & scope compliance

- Single pi executor; root PM only; **no nested agents**.
- Bounded network phase as frozen: target `http://192.168.8.12:11434` only,
  model `qwen3.8-27b`, concurrency 1, retry 0, per-call 120 s.
  **Counters used: GET 1/1 (health), POST 1/2 (planned 1), ASR 0, embedding 0.**
  No second POST (the predeclared comparator was not needed: the reused R3
  scale-2.0 record was directly comparable and the scale-4.0 bytes are frozen).
- No other IP/provider/scans/TaskRun. No push/deploy/publish/merge/reset/clean.
- Sole writes: `backend/lightgravity/sources/{processing,service}.py`,
  `backend/lightgravity/sources/ocr/{adapter,__init__}.py`,
  `tests/sources/ocr/{test_adapter,test_processing}.py`, docs 08/09 notes,
  `probes/materials-ocr-r4-20261016/**`. No frontend, no other features/tasks.
- R3 (`test/materials-quality-20261016-r3 @ 9e8ec8c`) and the independent audit
  (`qa/materials-r3-audit-20261016`, dirty OWNED reports only) are **unchanged**.
- `main` unchanged (`db01cd6`); other worktrees preserved.

## 2. Product repair (DELIVER 1)

### 2.1 Change

| File | Change |
|---|---|
| `backend/lightgravity/sources/ocr/adapter.py` | new `ENV_OCR_SCALE="LIGHTGRAVITY_OCR_SCALE"`, `MAX_OCR_SCALE=4.0`, `OcrScaleInvalid`, `parse_scale_env()` (finite, > 0, ≤ max; explicit diagnostic, no silent clamp) |
| `backend/lightgravity/sources/processing.py` | `ProcessingConfig.from_env()` composes the optional scale; default `2.0` unchanged |
| `backend/lightgravity/sources/service.py` | `build_source_service` passes `ProcessingConfig.from_env()` into the real `ProcessingEngine` |
| `backend/lightgravity/sources/ocr/__init__.py` | export the new names |

- Default/empty env ⇒ **2.0 exactly as before** (verified: `ProcessingConfig.from_env(env={}).scale == 2.0`).
- Invalid (`nan`/`inf`/`-inf`/`0`/`-1`/`4.1`/non-numeric) ⇒ **`OcrScaleInvalid` with explicit reason**, never a silent pass.
- Existing page/input/memory bounds unchanged; scale does **not** raise `max_pages`.
- Actual units: PDF user unit = 1/72", so default `2.0` ≈ **144 DPI** (historical "~150 DPI"); `4.0` ≈ 288 DPI; documented safe max `4.0`.

### 2.2 Evidence the env reaches the real product rasteriser

- `raster_grid.json`: product `PdfiumRasterizer` on the frozen Z2 PDF —
  scale 2.0 → PNG **817×1380 px** (164,473 B, sha `15ca6219…`); scale 4.0 →
  **1633×2759 px** (366,217 B). The scale-2.0 PNG sha/bytes **exactly reproduce
  R3's frozen PLAN values**, confirming deterministic product rendering.
- This corrects R3's mislabel (C1): `408×689` is the page **point** size, not
  the bitmap; the bitmap is 817×1380 px at scale 2.0 (~144 DPI) vs the source's
  1701×2873 px @ 300 DPI.
- `ocr_post_scale4.py` drove `ProcessingConfig.from_env(env={"LIGHTGRAVITY_OCR_SCALE":"4.0"})`
  into the real render, asserting `cfg.scale == 4.0` before the POST.

## 3. Bounded retest (DELIVER 1.3 + 3)

- Health GET 1/1: `{"status":"ok"}` 4 ms.
- **POST 1/1 (new):** scale **4.0**, Z2 page 2, product path, `qwen3.8-27b`,
  `temperature=0`, `stream=false`, `max_tokens=2000`, `cold=True`, timeout 120 s,
  retry 0. Input sha `2b8327bf…` (366,217 B ≤ 2 MiB), output `finish_reason=stop`,
  `completion_tokens=1183` ≤ 2048, latency 59.18 s. Truth not in prompt.
  Evidence: `evidence/ocr_post1_scale4.json`.
- **Scale 2.0 reused, not replayed** (R3 `ocr_post1.json`, sha `d0e9915e…`).
- The predeclared comparator POST #2 (scale-2.0 replay) was **not needed/spent**.

## 4. Independent rescoring (DELIVER 1.2)

`evidence/score_r4.py` (append-only; does NOT edit R3). Normalisation per
protocol §1. Metrics reported separately:

| metric | scale 2.0 (R3 reuse) | scale 4.0 (new) | threshold |
|---|---|---|---|
| whole-page CER | 0.299094 | **0.250755** | (Z2 context) |
| segment CER, monotonic DP mean | 0.634136 | 0.790741 | — |
| segment CER, independent line-window mean | 0.458564 | 0.419953 | — |
| **segment CER, independent line-window token-weighted** | **0.317221** | **0.268882** | ≤ 0.25 |
| exact human row tokens | 6 / 15 | 8 / 15 | 15 / 15 |
| protocol §4 structure pass | fail/unverified | fail/unverified | pass |

- The token-weighted independent line-window value **0.317221 reproduces the
  independent audit's fair 0.3172** exactly, confirming method comparability.
- **All scoreable gates remain FAIL at both scales.** No metric was relaxed; the
  audit's rejected "0 negative hits" gate was not reintroduced.
- Scoring-method bug B1 (single-line matcher over-count, rows > 1.0) is replaced
  by capped DP + independent window + token-weighted reporting.

### 4.1 Protocol §4 structure — honestly unverified

`structure_pass=false` with explicit reasons:
- human row count **15**, column count **3** (5 sections × 3 dialects).
- machine row/column counts recorded **`unverified`** — plain OCR text has **no
  reliable row/column boundaries**, so a true machine table row/col count cannot
  be inferred without layout analysis (not available). Per the brief, these are
  **not faked** and the gate is **not** claimed as pass.
- The reliably checkable part (byte-exact human row tokens) is 8/15 at scale 4.0;
  merged section pairs and dropped prefixes remain.

## 5. Quality verdict (honest)

- **Mechanism-repair PASS:** the env var exists, is validated, and reaches the
  real product rasteriser/OCR path; scale 4.0 genuinely renders ~2× pixels and
  the OCR request carried the larger PNG.
- **Z2 table-quality FAIL preserved:** whole CER 0.2508 > 0.15; fair segment CER
  0.2689 > 0.25; structure fail/unverified. **This is not a full-quality or
  task-done claim**, and **not** a claim that the remaining gap is purely model
  limitation — the resolution lever helped but did not close the gap.
- The remaining gap is consistent with the page's 3-dialect side-by-side layout
  (the model merges column-pairs onto single lines) plus dialect glyph errors.

## 6. Errata (append-only, new owner path)

- **Erratum E1 — audit cost phrasing.** The independent audit's REPORT §10 states
  "Cost this audit: 0 network, 0 POST, 0 model calls … Remote token/$ cost =
  unknown / not applicable". That is accurate **only for the audit's own offline
  recompute (LAN-free)**. The surrounding R3/A4 package and this repo's pi
  executor work incur **product-LAN (unknown $) and pi/DeepSeek (non-zero)**
  costs. The phrase must be read as "0 model calls **in the offline audit step
  only**", not as a package-wide zero-cost claim.
- **Erratum E2 — R3 raster-grid mislabel.** Confirmed and corrected: R3's
  "408×689" is the page point size; actual PNG is 817×1380 px at scale 2.0.

## 7. Tests & type checks (commands + exit)

Run with the existing env venv + `PYTHONPATH=backend` (product code from this worktree):

- `python -m pytest tests/sources/ocr/test_adapter.py tests/sources/ocr/test_processing.py -q`
  → **22 passed** (exit 0). Includes: env default/valid/NaN/inf/out-of-bounds,
  invalid-env explicit diagnostic, and **actual-engine-receives-requested-scale**
  (recording rasterizer through `ProcessingEngine`, both 4.0 and default 2.0).
- `python -m mypy --config-file pyproject.toml backend/lightgravity/sources/ocr/adapter.py
  backend/lightgravity/sources/processing.py backend/lightgravity/sources/service.py`
  → **Success: no issues found in 3 source files** (exit 0).

No broad full-suite run (not needed; focused scope only).

## 8. Docs / contract decision

- docs/09 §6: additive note on the optional OCR render scale (units, default,
  validation, bounds).
- docs/08 §6.6: **implementation note, no version bump** — added optional,
  non-secret env; **no endpoint/error-code/entity/enum/migration/request-response
  change**. Kept contract version `1.11.0` (no mechanical bump), recorded as the
  actual change-control decision.

## 9. Git

- `311c2d4` PLAN (frozen before POST).
- `8337e04` product repair (env scale) + focused tests + docs notes.
- `e9fd5e5` raster-grid + rescoring scripts.
- Final commit: this report + evidence + errata.
- `main` unchanged; R3 and audit worktrees untouched.

## 10. Limits & next concrete block

- **Not claimed:** full quality, task done, LG-035/037/040 closure, ASR (0 POST),
  retrieval-threshold tuning (none on the 7 R3 queries).
- **Next concrete block:** product worktree candidate awaits the **named LG-040
  version QA**; small repairs should be limited to necessary local tests, not a
  new independent tiny gate. If further Z2 quality work is wanted, the same
  bounded method can compare a layout-aware extraction step, but that is a new,
  separately-authorized scope.
