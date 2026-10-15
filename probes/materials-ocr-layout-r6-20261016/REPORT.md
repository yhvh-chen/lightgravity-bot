---
title: "Materials OCR Layout R6 — REPORT (offline program-side layout/column prototype)"
doc_type: report
category: probe
status: "Phase A complete — offline prototype + evidence; ordinary-path default untouched; no quality pass"
updated: "2026-10-16"
---

# REPORT — probes/materials-ocr-layout-r6-20261016

Sole pi technical owner; root PM only; no nested agents. This package implements
the **Phase A offline, program-side layout/column analysis prototype** for
LG-035 and audits the frozen "15x3" Z2 interpretation against the real page.

**No OCR / embedding / ASR / model HTTP / health call was made.** Network use is
0 (development only). No ground truth is used by the algorithm; the human truth
is read **only** to audit the frozen interpretation.

---

## 1. Provenance & scope

| Item | Value |
|---|---|
| Base `main` (verified clean) | **`7c27f18`** |
| Branch / worktree | `dev/materials-ocr-layout-r6-20261016` @ `/home/yhvh/code/lightgravity-bot-worktrees/materials-ocr-layout-r6-20261016` |
| Product commit (this package) | **`d996bef`** (+ evidence/report commits) |
| Real Z2 PDF | `probes/materials-ocr-r4-20261016/private/LG035-ZH-Z2.pdf` — PD, sha1 `fe5572520076aee2f3a252277e0fa648588a02bc`, sha256 `da50c9f6963f70bc022db55a367b88fd4d6c5be36d899ae5a1d7392aada0eb5a` |
| Human truth (audit only) | `probes/lg035/TRUTH-PREP/truth/LG035-ZH-Z2.p2.txt` |
| Non-table controls | `probes/lg035/fixtures/clear_real.pdf` (sha256 `89c6b422…`), `probes/lg035/fixtures/multipage_real.pdf` (sha256 `929fc2ac…`) |

**Owned files (declared before changes):**

| Path | Change |
|---|---|
| `backend/lightgravity/sources/ocr/layout.py` | NEW (offline analyser) |
| `backend/lightgravity/sources/ocr/__init__.py` | additive exports |
| `tests/sources/ocr/test_layout.py` | NEW (16 focused tests) |
| `probes/materials-ocr-layout-r6-20261016/**` | STATUS / REPORT / harness / evidence (private/ ignored) |

**Not touched:** `sources/ocr/{adapter,pdf}.py` (no change needed),
`sources/processing.py` (no integration made — see §7), vector / frontend /
docs08 / shared docs / backlog. No push / deploy / publish / reset / clean. All
worktrees and old raw evidence preserved.

---

## 2. What the algorithm does (generic, pixels + geometry only)

`layout.py` is a pure function of the raster (and optional PDF point geometry):

1. **Ink mask + projections** — per-column and per-row ink counts at a fixed
   luminance threshold (128).
2. **Content box** — the ink bounding box.
3. **Text lines** — horizontal bands between blank rows, with an ink floor so a
   stray dot cannot create a phantom line.
4. **Explicit ruling** — long straight dark runs (horizontal >= 60% width,
   vertical >= 40% height). Checked so a ruled form is never confused with text.
5. **Column gutters** — vertical whitespace runs that are >= 12 px wide **and**
   >= 90% empty over the analysed band, with a minimum accepted column width so
   a sliver is merged rather than reported as a column.
6. **Regions** — consecutive text lines grouped by section gaps; **column
   detection re-runs per region**, because one page can mix a full-width block
   with a genuine side-by-side block.

Result carries **deterministic integer coordinates**, an `input_sha256`
provenance (the exact bytes an OCR backend would see), optional PDF point
geometry, per-region and per-column **crop boxes**, and a coarse honest
`column_model` (`single_column` / `multi_column_local` / `multi_column` /
`blank` / `unanalysed`).

Bounds/honesty: over-size rasters (`>8000 px` side or `>24M` px) return
`status="too_large"` with **no fabricated structure**; blank pages return
`status="blank"`; short buffers and bad thresholds raise explicit errors.

No dependency beyond the standard library (`struct`, `zlib`, `hashlib`). PNG
decoding (gray and RGB, non-interlaced, 8-bit) is implemented in-module so the
analysis runs on the product rasteriser's exact output.

---

## 3. The frozen "15x3" interpretation vs. the actual page

### 3.1 What the frozen interpretation claims

The R4 protocol §4 structure check declares the truth as a **5-section x
3-dialect table = 15 rows, 3 columns**, and requires machine row count == 15,
machine column count == 3, and every cell token byte-exact. R4 recorded
`structure_pass=false` with machine row/column counts **"unverified"** because
"plain OCR text has no reliable row/column boundaries".

### 3.2 What the page actually is (measured, deterministic)

From `evidence/z2_page2_scale2.json` (product rasteriser, scale 2.0, PNG hash
`15ca6219…` — **matches R4's recorded scale-2.0 raster**):

| Fact | Measurement |
|---|---|
| Content box (px) | x **109..704**, y **319..1039** |
| Horizontal ruled lines | **none** |
| Vertical ruled lines | **none** |
| Text lines | 12 (after speck filtering) |
| **Region column counts** | **[3, 2, 1, 2]** |
| Column model | `multi_column_local` |

The truth text is **5 sections x 3 dialect-labelled lines** (prefixes
`國/蘇/廣…`), i.e. 15 content lines. The "3" is the **number of dialect
variants per section**, expressed as a *label prefix on separate lines* — it is
not a repeated per-row cell grid, and the page has **no ruling** and **no
uniform 3-column geometry**. The measured layout is mixed: most regions are
full-width, one region is a real side-by-side pair.

**Conclusion:** the frozen "15 rows x 3 columns" is a **semantic dialect
mapping, not a geometric table**. Applying the protocol §4 geometric structure
check (row count == 15 AND column count == 3) to this page is comparing a
**label taxonomy** against **page geometry**; it cannot be satisfied by any
faithful transcription. This is flagged as a **possible protocol bug for PM
decision** — see §8. No threshold was lowered and the historical R3/R4/R5
numbers are unchanged.

### 3.3 The precise row/column disagreement (diagnosed)

The machine outputs (frozen R4/R5 evidence) have **15 and 14 text lines**
respectively — i.e. a line count close to the truth's 15. The disagreement is
**reading order**, not missing rows:

* the page places two dialect blocks **side by side** in the section-2 region
  (measured gutter x 359..402 at scale 2.0);
* plain OCR reads left-block + right-block onto **one line**
  (`北風說，我的本事大極了。 世界上的東西沒有不怕我的。`);
* the human truth **flattens** reading order: it lists all left-column lines,
  then all right-column lines, as separate lines.

So a "row token byte-exact" test penalises a transcription that is *more*
faithful to the page's 2-D layout than the truth's linearised form. Reproduced
offline: R4 exact full-line present **8/15**, R5 **6/15** (matches frozen
numbers). A region/column-aware emitter could reconcile the two orders, but that
is downstream of this Phase A module and out of scope here.

---

## 4. Observable deliverables (real evidence)

`evidence/summary.json` (frozen, product rasteriser, offline):

| page | status | lines | global cols | max region cols | model | ruling | input_sha256 |
|---|---|---|---|---|---|---|---|
| Z2 p2 @2.0 | ok | 12 | 3 | 3 | `multi_column_local` | **no** | `15ca6219…` |
| Z2 p2 @4.0 | ok | 14 | 6 | 5 | `multi_column` | **no** | `2b8327bf…` |
| clear_real p1 @2.0 | ok | 8 | 1 | 1 | `single_column` | yes | `1aebdc63…` |
| multipage_real p1 @2.0 | ok | 8 | 1 | 1 | `single_column` | yes | `1aebdc63…` |

**Real Z2 column detection is a deterministic coordinate proof:** at scale 2.0
the section-2 region is split at gutter x=359..402 into columns
`[116..358]` and `[403..675]` (`evidence/z2_page2_scale2.json`, `regions[1]`).

**Ordinary non-table pages are NOT spuriously tabular:** both English scanned
controls report `single_column`, `max_region_columns=1`.

**Provenance cross-check:** the scale-4 analyser input hash `2b8327bf…` is
**identical** to the `input_sha256` the real OCR model saw in R4/R5
(`probes/materials-ocr-r5-20261016/evidence/ocr_call1_z2_scale4.json`), so the
analysed pixels are the exact OCR input — no re-render drift.

**Determinism:** two independent runs produced byte-identical analysis JSON.

---

## 5. What generic layout CAN and CANNOT reconstruct

**Can (measured):**
* content bounding box, margins, text-line bands (y-coordinates);
* vertical whitespace gutters and **per-region side-by-side column splits**;
* explicit horizontal/vertical ruling presence;
* per-region and per-column **crop coordinates** with page + input-hash
  provenance.

**Cannot (honest limits):**
* it does **not** read text (no OCR) and cannot by itself emit cells/rows;
* it cannot decide *semantic* dialect membership — "3 dialects" is a
  human/semantic fact, not present as geometry;
* the pixel gutter model is **scale-sensitive**: at 4.0 the CJK character
  spacing creates extra near-empty columns and the region/column count changes
  (5-6 cols). A production step must pin the render scale or use a
  scale-normalised gutter width;
* it does not resolve the **reading-order** mismatch by itself; a later stage
  must emit left-column/right-column text and merge with line order.

**One page cannot establish generality.** This prototype is exercised on one
real 3-dialect form plus two English controls; it does **not** prove general
multi-column reliability, and the LG-035 real table **quality gate remains
unmet** (no cell CER improvement is claimed — cell OCR quality is **untested**
this phase).

---

## 6. Why this is NOT a prompt lottery

R5 (merge `767f1ea`) already showed a generic layout-aware **prompt** did not
induce table structure (Z2 machine rows 0, fair segment CER regressed). This
package moves the work to the **program side** and produces a deterministic,
testable structural signal (gutters/regions/ruling) as the first building block
of a rule/segmentation pipeline — not another instruction variant.

---

## 7. Integration decision (default pipeline unchanged)

`processing.py` and `pdf.py` were **not modified**. Rationale (per the brief):
integration is **premature** before the algorithm is shown reliable and before
a downstream cell/column emitter exists. Instead:

* the prototype ships as an **optional internal module** (`sources/ocr/layout.py`)
  with a stable, side-effect-free API and honest bounds;
* **no HTTP / schema / enum / endpoint change**; **no default behaviour change**;
* the probe harness proves the real-pipeline bridge works
  (`analyse_rendered_page` consumes a product `RenderedPage`) **if/when** PM
  authorises integration.

**Exact gap to integration:** (a) a stage that crops each region/column and
routes crops to the OCR backend; (b) reading-order reconciliation between the
truth's linear form and the page's column form; (c) a scale-pinned render so the
gutter model is stable; (d) a decision on how the `page_map` schema carries
column/region provenance (docs08 owner).

---

## 8. 🚩 Flagged for PM (no retroactive change to history)

* **Possible protocol §4 bug:** applying a *geometric* "row count == 15 AND
  column count == 3" check to a page whose "3 columns" are a **dialect label**
  (no ruling, non-uniform geometry) cannot be passed by a faithful transcript.
  PM should decide whether §4 should be re-scoped to a **semantic** structure
  (per-section dialect grouping) or to a **ruled-table** class only. **No
  historical score, threshold, or report byte is modified here.**

---

## 9. Checks run (commands + exit)

Env: `.venv` (Python 3.12.13), product code from this worktree.

```
.venv/bin/python -m pytest tests/sources/ocr/test_layout.py -q      # exit 0 — 16 passed
.venv/bin/python -m pytest tests/sources/ocr -q                     # exit 0 — 44 passed
.venv/bin/python -m mypy --config-file pyproject.toml \
    backend/lightgravity/sources/ocr/layout.py \
    backend/lightgravity/sources/ocr/__init__.py                    # exit 0 — Success (2 files)
```

Focused only; no full-suite run (no new failures expected). No full frontend
build (no frontend change).

---

## 10. Counters (this package)

| counter | value |
|---|---|
| product OCR / embedding / ASR / model calls | **0** |
| network calls | **0** (development only) |
| GT used by algorithm | **0** |
| new heavy dependencies | **0** (stdlib only) |
| generated/synthetic quality fixtures | **0** (geometry test vectors are unit fixtures, not quality samples) |
| push / deploy / publish / reset / clean | **none** |

pi/DeepSeek execution cost: **unknown, not zero**.

---

## 11. Status & next step (DO NOT execute without PM binding)

* LG-035 stays **`in-progress`**; **no quality-pass**; **no LG-040/041 unlock**.
  Contract `1.11.0`, SDK `0.1.22` unchanged.
* **Proposed NEXT fixed-model test (`<= 6` POST = max 3 column + printed
  regression controls) — NOT executed here:**

  1. **POST Z2 page 2, scale 4.0, per-column crops** from
     `regions[1].column_crops` (2 POST: left col, right col) — measure whether
     per-column transcription improves fair segment/cell CER vs the frozen
     whole-page R4/R5 result, and whether the reading-order merge reconstructs
     the 15-line truth.
  2. **POST a left/right column-pair crop** for the section-2 region
     (1 POST).
  3. **Printed regression controls** (max 3 POST): Z1 page 10 and one ordinary
     English control page, to confirm the layout step does **not** regress the
     currently-passing printed path.

  Total <= 6 POST, serial, retry 0, same endpoint/model as R4/R5. **This plan is
  a proposal only; it is not authorised by this package and must not be run
  until the PM binds it.**
