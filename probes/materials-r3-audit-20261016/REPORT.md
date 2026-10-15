---
title: "Materials R3 — independent technical DIAGNOSTIC (LG-040 gate readiness)"
doc_type: report
category: probe
status: "complete — offline independent audit; 2 real bugs + 1 invalid criterion + 1 config-vs-defect finding; no POST/status/product change"
updated: "2026-10-16"
---

# REPORT — materials-r3-audit-20261016

## 0. One-line result

Independent **offline** audit of R3 (`test/materials-quality-20261016-r3 @ 9e8ec8c`) against the
frozen TRUTH-PREP scoring protocol, LG-035/037/040 acceptance and docs/08 §4.3/§6.6 + docs/09 §7:
the R3 **CER failure is real and robust** (reproduced whole-page 0.2948 / corrected segment ≈0.317,
both > 0.25), but R3's **segment-CER method is buggy** (over-reports 0.3281 via single-line match),
its **Z2 "structure_pass" criterion is invented and stricter than protocol §4**, its **report mislabels
the render grid** (408×689 is the page's **point size**, not the raster grid — the PNG is ~816×1379,
~144 DPI), and the **negative-control "leakage" is an invented zero-hit requirement** not present in
the LG-037 acceptance or docs. One **real implementation gap** is identified (render `scale=2.0`
loses >half the 300-DPI source resolution and is **not env-configurable** despite being a quality
parameter). R3 remains valid evidence; it is **not** sufficient, by itself, to conclude product
defect from model limitation.

## 1. Authority & scope compliance

- Single pi executor, root PM only; **no nested agents**.
- **No live network / no inference POST**; offline recompute only (pure local string math).
- **No product changes, no task status, no push/deploy/publish/merge/reset/clean.**
- **No image edit, no python image editing, no external model upload.** The preserved Z2 scan was
  **not** opened/rendered by any image code here; conclusions use already-frozen textual evidence +
  `pdfinfo`/`pdfimages` metadata reads on the preserved private original (read-only, no network).
- Sole writes: `probes/materials-r3-audit-20261016/**`. R3 source/PI logs untouched; this is an
  **appended** audit, not an errata rewrite of R3.
- Branch `qa/materials-r3-audit-20261016`, base `main @ db01cd6` (worktree verified clean base).
- Original worktrees/dirty state preserved (no reset/clean).

## 2. What R3 claims, and the audit verdict per claim

| # | R3 claim | Verdict | Basis |
|---|---|---|---|
| C1 | Z2 p2 raster product 408×689 | **PARTIALLY WRONG (mislabel)** | `408×689` is `page.get_width()/get_height()` (**points**), not the bitmap; actual PNG grid ≈**816×1379 px** (`page.render(scale=2.0)`; `_bitmap_to_png` uses `bitmap.width/height`). See §4. |
| C2 | Segment CER 0.3281 > 0.25 FAIL | **FAIL is REAL, number is inflated** | Independent recompute: whole-page 0.2948, R3 method ≈0.3323, **layout-agnostic windowed segment ≈0.3172** — still > 0.25. See §3. |
| C3 | row/column collapse (structure_pass=false) | **FAIL real; criterion INVENTED** | Machine did drop dialect-prefix glyphs and merged some section pairs, but the R3 predicate (`machine_dialect_lines>=15 AND merged_columns==0`) is **not** protocol §4 (which requires row count == human rows, column count == human cols, cell tokens byte-exact). See §5. |
| C4 | Vector Recall@5=1 vs lexical 0.7 | **SUPPORTED (small sample)** | Real product `VectorSearchService.search` path; consistent with `retrieval_results.json`. 7 docs/7 queries is indicative only. |
| C5 | Negative queries return 5 each (leakage) | **TRUE observation, INVALID acceptance criterion** | Product has no threshold/abstention (by design); LG-037 acceptance asks only to **report** negative false-hits, docs/09 §7 says vector hits are candidates "受阈值与余量约束" (a **direction**, not a frozen gate). See §6. |
| C6 | image vector 768 finite | **SUPPORTED** | Real `EmbedInput.image` path; dim 768 finite. R3 correctly labels it **not** a cross-modal retrieval-quality result. |
| C7 | no product changes | **SUPPORTED** | R3 branch touches only `probes/materials-quality-20261016-r3/**`; `git diff db01cd6 -- backend/` empty on that branch (verified). |

## 3. Independent CER recomputation (offline, method-sensitivity)

Reproduced from R3's frozen `evidence/ocr_post1.json` + TRUTH-PREP `truth/LG035-ZH-Z2.p2.txt`
(`recompute_cer.py` / `recompute_cer.json`); protocol §1 normalization (NFKC + strip whitespace,
code-point Levenshtein).

| metric | value | threshold | note |
|---|---|---|---|
| whole-page CER | **0.2948** | (context) | matches R3 exactly |
| R3 "segment CER by best single line" | **0.3323** | 0.25 | R3 reported 0.3281 (rounding/line-set) |
| **layout-agnostic segment CER** (best window of 1–2 machine lines per human row) | **0.3172** | 0.25 | fairer; **still FAIL** |

**Conclusion:** the Z2 table-class **quality FAIL is robust to the scoring method** — it is *not* an
artifact of the R3 segment matcher. The R3 segment matcher *does* over-count (it picks a single line,
and when the model emits a superset/merged line CER can exceed 1.0 per row, e.g. rows shown at
1.08); this is a **scoring bug** but it does not flip the verdict. No forced pass; no metric relaxed.

## 4. Render-resolution finding (config/parameter vs product defect)

Evidence from the preserved private original (read-only, no network):
`pdfinfo` → page 2 **MediaBox 408.24 × 689.52 pt**; `pdfimages -list` → embedded scan **1701×2873 px,
300 DPI**; product `PdfiumRasterizer._bitmap_to_png` encodes `bitmap.width/height`.

- Product renders at `ProcessingConfig.scale = 2.0` (`processing.py:74`) → **~144 DPI** (2.0 × 72).
- The source's native scan is **300 DPI**. The product therefore **discards >half the available
  resolution** before OCR of a dense 3-column dialect page.
- `scale` is **hard-coded default, NOT exposed via env** (no `LIGHTGRAVITY_OCR_SCALE`; `ENV_OCR_*`
  has base_url/model/token/timeout/max_tokens only). `DEFAULT_SCALE=2.0` comment says "~150 DPI".

**Verdict:** the low-resolution render is a **documented default parameter, not a defect by itself**
(the docstring states ~150 DPI). However it is a **quality-relevant parameter with no configuration
path**, and the source's 300-DPI availability means Z2's FAIL is **not provably a model-capability
limit**. This is a genuine **implementation gap to consider**, distinct from the OCR model's glyph
errors — and it is the single highest-value repair lever for the Z2 class.

## 5. "Is Z2 page 2 actually a table?" and the structural criterion

- The sample is `NLC416-14jh004627-68702 方言調查表格.pdf` page 2 → a **Multi-dialect survey table**:
  truth is a **5-section × 3-dialect side-by-side** page (15 `*`-prefixed dialect rows). **The class
  label "table/side-by-side" is protocol-consistent**, NOT invented (protocol §2 pre-registers the Z2
  class; TRUTH-PREP manifest and PREP package freeze it before execution).
- **R3's `structure_pass` predicate** (`machine_dialect_lines >= human_rows AND machine_sections >=
  human_sections AND merged_columns == 0`) is **invented** and does not implement protocol §4
  (`row count == human row count` AND `column count == human column count` AND `cell tokens
  byte-exact`). R3's rule is both **not verifiable from its recorded artifacts** (the counts
  `machine_dialect_lines`/`merged_columns` come from fragile substring heuristics, not real row/col
  detection) and **stricter than §4 in one direction while laxer in another** (it never actually
  counts columns). So the **structure FAIL is directionally supported** (the model did merge section-2/3
  dialect pairs onto single lines and drop 末/格/的 prefixes) but the **criterion must be replaced by
  the protocol's explicit row/col/cell check** before any gate uses it.

## 6. Query labels, relevance leakage, and the negative-control criterion

- **Harness reality:** R3's `retrieval_harness.py` calls the **real product** `VectorSearchService`
  (`index_source` + `search`) and the real `LexicalSearchService` — **not** a bypass, not a mock.
  Corpus is built as trusted **formal text** sources; the media image is embedded **separately as
  media** (`EmbedInput.image`), never fabricated into text. This matches docs/09 §7 and docs/08 §6.6.
- **Cross-modal:** the media vector is embedded but there is **no text↔image relevance comparison**
  in the product (single ranked list). R3 **correctly** states this does **not** close multimodal
  acceptance. **SUPPORTED.**
- **Negative control:** product `vector/index.py:search` returns **top-k cosine neighbours sorted,
  no score threshold, no abstention**; `service.search` returns them after authorization+回源. LG-037
  acceptance requires "报告负向误命中" (**report** negative false-hits) and docs/09 §7 describes vector
  hits as **candidates** subject to threshold+margin **as a design direction** (docs/09 is "接口未冻结";
  docs/08 froze no threshold field/behavior). Therefore **"negative queries must return 0" is an
  invented requirement**, not a contract violation — the 5/5 result is the **expected behaviour of a
  pure top-k NN retriever**, not "permission/relevance leakage". There is **no access-control leakage
  proof** in R3, and none is inferable from semantic rank (authorization is enforced separately by
  `authorize_and_verify` + 回源核对, exercised by LG-037 tests). **Claim C5's framing as failure is
  UNSUPPORTED as an acceptance failure.**
- **Label quality:** the 5 positive + 2 negative labels are **executor-authored** (declared). On a
  **7-doc corpus**, deep lexical overlap with the source fragments makes positive labels easy
  (a query like `北風 太陽 爭論 本事` shares characters with D4). This is acceptable for *indicative*
  evidence but **cannot justify a default threshold**: with 7 docs any threshold would be tuned and
  "validated" on the **same** queries — R3 correctly does **not** do this, and this audit does **not**
  tune or validate.

## 7. Concrete bugs found (product / harness), minimal repair plan

### B1 — Harness: segment-CER single-line matcher over-reports (R3-owned, not product)
- **Owner/file:** `probes/materials-quality-20261016-r3/evidence/ocr_score_z2.py` (harness only).
- **Impact:** inflates segment CER (rows can exceed 1.0); does not flip verdict. **No product change.**
- **Repair:** replace best-single-line with a windowed/global alignment (or per-human-row vs the
  machine concatenation), per §3 corrected method. Deps: none. Contract impact: none. Test: re-run
  offline on frozen `ocr_post1.json`.

### B2 — Product: Z2 structural gate uses an invented predicate instead of protocol §4 (evidence/QA only)
- **Owner/file:** the gate/QA harness (future LG-040 QA), **not** product source.
- **Impact:** structure verdict not reproducible from declared row/col counts.
- **Repair:** implement protocol §4 explicitly (explicit human row count, explicit dialect-column
  count, byte-exact cell tokens) and record each count. Deps: none for scoring; product unchanged.

### B3 — Product: PDF render resolution fixed at `scale=2.0` (~144 DPI), not configurable
- **Owner/file:** `backend/lightgravity/sources/processing.py` (`ProcessingConfig.scale`),
  `backend/lightgravity/sources/ocr/pdf.py` (`DEFAULT_SCALE`). **Product code change** — needs a
  normal engineering task, not a gate waiver.
- **Impact:** dense 300-DPI table scans are OCR'd at <half resolution → plausible contributor to the
  Z2 FAIL. This is the strongest candidate "real implementation gap vs quality limitation".
- **Minimal repair:** expose render scale via env (e.g. `LIGHTGRAVITY_OCR_SCALE`) with default
  unchanged (2.0), clamp to a sane max, document; single owner = the OCR/processing file owner.
  Deps: none beyond docs/08 config note (加性 env, no endpoint/schema change). Test: unit test that
  `scale=4.0` yields ~2× pixels and OCR request carries the larger PNG; plus one bounded POST retest.

### B3 retest budget (proposed, bounded, NOT executed here)
- 1 raster (offline, 0 POST) at `scale=2.0` vs `scale=4.0` to confirm pixel count and PNG size.
- **2 OCR POST max** on Z2 p2 (one per scale), serial, timeout 120 s, retry 0, concurrency 1.
- Re-score offline with the §3 corrected scorer + §4 protocol structure check.
- **Cost: unknown until run** (prior Z2 p2 OCR latency 37.8 s/call; tokens unknown-not-counted here).

## 8. Is R3 technically valid acceptance evidence for LG-040 gate readiness?

- **Valid as:** real-path, real-sample, license-clear, pre-registered-threshold evidence; genuinely
  measures OCR Z2 FAIL and vector-vs-lexical recall on a small set; product unmodified.
- **NOT sufficient to:** (a) declare a product **defect** for Z2 (render-resolution confound B3);
  (b) treat negative-control zero-hit as a pass gate (invented requirement, §6); (c) close LG-037
  cross-modal (product path absent — correctly stated); (d) justify a default threshold (7 docs).
- **LG-040 gate readiness:** **partially ready** — the retrieval harness, provenance, budget and
  scoring infrastructure are reusable; the **Z2 verdict needs one bounded retest** (§7 B3) plus the
  protocol-§4 structure check (B2) before it can attribute the FAIL to product vs resolution.

## 9. No user-decision blockers for ordinary implementation

B1/B2 are ordinary harness/scoring fixes; B3 is an ordinary additive config + bounded retest. **None
require a user decision.** The only genuinely external dependencies remain the same as R3 recorded:
a licensed non-NC mixed-page sample (coverage class) — but that is a **coverage gap**, not a blocker
for the Z2 retest above. **LG-041 stays locked**; ASR not touched; task statuses not changed.

## 10. Cost & git

- **Cost this audit:** 0 network, 0 POST, 0 model calls. CPU-only offline recompute. Remote token/$
  cost = **unknown / not applicable** (no inference). Round/time budget respected.
- **Commit:** this package is committed on `qa/materials-r3-audit-20261016`; **`main` unchanged**
  (`db01cd6`). No merge/push/deploy. Original worktrees and dirty state preserved.

## 11. Evidence index (this package)

- `STATUS.md`, this `REPORT.md`
- `recompute_cer.py`, `recompute_cer.json` (independent CER + method sensitivity)
- `score_sep.py` (score-availability / negative-control data-only check)
- Base `main @ db01cd6`; worktree
  `/home/yhvh/code/lightgravity-bot-worktrees/materials-r3-audit-20261016`.
