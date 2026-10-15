---
title: "Materials OCR Layout R6 — STATUS"
doc_type: probe
category: engineering
status: "complete (Phase A) — offline prototype delivered; default pipeline untouched; no quality pass"
updated: "2026-10-16"
---

# STATUS — materials-ocr-layout-r6-20261016 (LG-035 layout-aware page analysis)

Sole pi technical owner, root PM only, no nested agents. Base verified: clean
`main` **`7c27f18`**; new branch `dev/materials-ocr-layout-r6-20261016`; worktree
`/home/yhvh/code/lightgravity-bot-worktrees/materials-ocr-layout-r6-20261016`.

## Prompt interpretation (fixed at start, not retro-edited)

- This is **Phase A**: a **concrete OFFLINE, program-side layout/column analysis
  prototype** with meaningful checks. **Not another prompt lottery.**
- **No OCR / embedding / ASR / model HTTP / health call** is authorized in this
  phase. Network use is 0 except pi development.
- No GT is used by the algorithm. Human truth is used only to *audit* the
  frozen 15x3 interpretation, never as algorithm input.
- PDF rendering / cropping is product rasterizer engineering (product
  `PdfiumRasterizer`), permitted. No manual imagegen/editimage; no
  generated/synthetic quality fixtures.

## Declared owned files (before changes)

| Path | Role |
|---|---|
| `backend/lightgravity/sources/ocr/layout.py` | NEW offline layout analysis (pixels + PDF geometry only) |
| `backend/lightgravity/sources/ocr/__init__.py` | additive exports for the new module |
| `backend/lightgravity/sources/ocr/pdf.py` | only if a raster grid/geometry accessor is needed |
| `backend/lightgravity/sources/processing.py` | only if a bounded optional integration is warranted |
| `tests/sources/ocr/test_layout.py` | NEW focused tests (geometry boundary/overflow/non-table) |
| `probes/materials-ocr-layout-r6-20261016/**` | STATUS / REPORT / evidence |

No adapter-prompt / vector / frontend / docs08 / shared-doc / backlog edits.

## Round log

- **R1**: read AGENTS/agent.md/PROJECT/README/LG-035/R5-close/SCORING-PROTOCOL;
  located implementation (`sources/ocr/{adapter,pdf}.py`, `sources/processing.py`,
  `sources/content.py`, `tests/sources/ocr/**`); verified base clean `7c27f18`;
  created branch + worktree. Began pixel/geometry inspection of the real Z2
  page-2 scan (`probes/materials-ocr-r4-20261016/private/LG035-ZH-Z2.pdf`,
  public domain, sha1 `fe5572520076aee2f3a252277e0fa648588a02bc`).
- **R2**: pixel projection + ASCII-art analysis of Z2 page 2 established the
  actual geometry (see REPORT §2): content band x=109..703, **no ruled lines**,
  no 3-column vertical gutters; text is label-column + full-width or 2-column
  sections. Frozen "15 rows x 3 columns" is a **semantic dialect mapping**, not
  page geometry.
- **R3**: implemented `layout.py` (projection/segmentation + per-region column
  model), 16 focused tests, and the probe harness.
- **R4**: froze real evidence through the product rasteriser (Z2 p2 @2./4.0 +
  two English controls); audited the frozen "15x3" interpretation vs. measured
  geometry; confirmed provenance hashes match the real OCR inputs.
- **R5**: wrote REPORT; finalised scope; no default-pipeline change.

## Result (summary)

* Real Z2 page 2: **no ruling**, region column counts **[3,2,1,2]**,
  `multi_column_local`; the "15x3" claim is a **semantic dialect mapping, not a
  table geometry** (flagged for PM, history unchanged).
* English scanned controls: `single_column` (no spurious tabular claim).
* Deterministic; input-hash provenance matches the real OCR inputs
  (`2b8327bf…` @4.0).
* Default OCR pipeline unchanged; **no integration**.

## Invariants

- LG-035 stays `in-progress`; **no** quality-pass claim; **no** LG-040/041 unlock.
- Contract `1.11.0` and SDK `0.1.22` unchanged. No default pipeline change unless
  the algorithm is reliable (see REPORT verdict).
- No push / deploy / publish / reset / clean. All worktrees and old raw evidence
  preserved.

## Counters

| counter | value |
|---|---|
| product OCR / embedding / ASR / model calls | **0** |
| network calls | **0** (development only) |
| GT used by the algorithm | **0** |
| new heavy dependencies | **0** |
| push / deploy / publish / reset / clean | **none** |

pi/DeepSeek cost: unknown, not zero.
