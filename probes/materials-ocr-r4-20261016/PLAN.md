---
title: "Materials OCR R4 — FROZEN PLAN (pre-registered before any inference POST)"
doc_type: report
category: probe
status: "frozen — written before any implementation POST; no result may change it"
updated: "2026-10-16"
---

# FROZEN PLAN — materials-ocr-r4-20261016

Base `main @ db01cd6`. Branch `fix/materials-ocr-r4-20261016`. Worktree
`/home/yhvh/code/lightgravity-bot-worktrees/materials-ocr-r4-20261016`.

This plan is **frozen before any inference POST**. No result may change the
model, the input, the scales, the call count, the thresholds or the comparator.
Failed attempts are kept (`erratum`), never rewritten.

## 0. Context & prior facts (no new GET required unless noted)

Source-independent facts reused from R3 (`test/materials-quality-20261016-r3 @ 9e8ec8c`)
and the independent R3 audit (`qa/materials-r3-audit-20261016`, REPORT.md):

- Endpoint `http://192.168.8.12:11434` — llama.cpp router, OCR model `qwen3.8-27b`.
- Z2 PDF sha256 `da50c9f6963f70bc022db55a367b88fd4d6c5be36d899ae5a1d7392aada0eb5a`,
  page 2 only, 18 pages total (only page 2 rendered/OCR'd, **not** all 18).
- Human truth `TRUTH-PREP/truth/LG035-ZH-Z2.p2.txt`, sha256
  `8c6ad74b3b647dd85aacb1db665ceafd262da579a0c65aac7e879488665862b0`.
- Frozen scoring protocol: `TRUTH-PREP/protocol/SCORING-PROTOCOL.md`
  (NFKC + whitespace-strip, code-point Levenshtein; Z2 class threshold
  **segment/cell CER ≤ 0.25 AND structural pass**; Z1 printed page CER ≤ 0.15).
- R3 default-scale result (reused, NOT replayed): whole-page CER **0.2948**,
  fair windowed segment CER **0.3172** (> 0.25) ⇒ Z2 table FAIL at scale 2.0.
- R3 render grid was **mislabeled**: 408×689 is page **point** size;
  `page.render(scale=2.0)` bitmap ≈ **816×1379 px** (~144 DPI from 72-DPI PDF unit).
  Original embedded scan is **1701×2873 px @ 300 DPI**.
- R3 audit finding B3: `ProcessingConfig.scale` is hard-coded 2.0, **not
  env-configurable**, reaching the real product `PdfiumRasterizer` only through
  default composition. This is the repair target of this package.

## 1. DELIVER bound (this package)

### 1.1 Product repair — optional env `LIGHTGRAVITY_OCR_SCALE`

- Add an **optional** env var `LIGHTGRAVITY_OCR_SCALE`, parsed with the existing
  env-parsing style, composed into the **actual product processing path**
  (`build_source_service` → `ProcessingEngine(ProcessingConfig)`), so the value
  reaches the real `PdfiumRasterizer.render(scale=...)`.
- **Default behavior unchanged**: absent/empty ⇒ `2.0` (exactly today's value).
- Validation: finite, strictly positive, and ≤ a documented safe max. Invalid
  (NaN / infinite / ≤ 0 / > max / non-numeric) is **rejected with an explicit
  diagnostic**, never silently clamped into a pass. Existing memory/page/input
  bounds stay in force; scale does not raise `max_pages`.
- Document actual units (default 144 DPI ≈ "150 DPI" comment) and limits.
- Focused tests: env default / valid / NaN / infinite / out-of-bounds, plus a
  test that the **actual processing engine** receives the requested scale
  (not a mirror/stub test only).
- Contract: add-only optional env, **no API/schema/endpoint change**. Per
  docs/08 change control this is an implementation-note-level additive env
  (no version bump required); record the actual decision in docs (no
  mechanical version bump).

### 1.2 Independent scoring (new append-only scripts/report — do NOT edit R3)

- **whole CER** per protocol §1.
- **principled segmental alignment** per human row across machine wrap lines
  (windowed/global alignment, not best-single-line).
- **original protocol §4 strict row/col/cell token check** performed separately,
  recording each count. Any count that cannot be reliably inferred from plain
  OCR text is recorded **unverified**, never faked into a pass.
- Correct the raster grid using actual PNG metadata (IHDR width/height).

### 1.3 Bounded network retest (new phase)

| Item | Bound |
|---|---|
| inference POST total | **≤ 2** (planned exact 1 new scale retest) |
| concurrency | **1** (strictly serial) |
| retries | **0** — timeout/interruption ⇒ record unknown, no replay |
| per-call timeout | **120 s** |
| target | `http://192.168.8.12:11434` only, model `qwen3.8-27b` |
| input per POST | ≤ 2 MiB |
| output per POST | ≤ 2048 tokens |
| `/health` GET | ≤ 1, connect 3 s / total 8 s (only if needed) |
| ASR / embedding | **0** |
| other IP/provider/scans/TaskRun | none |

Frozen call decision **before** any POST:

- **Call #1 (preferred, sole planned new call):** one OCR POST at **scale 4.0**
  (≈288 DPI) on Z2 page 2, product `PdfiumRasterizer` + `OpenAICompatOcrBackend`
  path, model `qwen3.8-27b`, `temperature=0`, `stream=false`, `max_tokens=2000`,
  `cold=True`, timeout 120 s, retry 0. Truth **not** in the prompt.
- **Default-scale R3 record is REUSED**, not replayed (scale 2.0 already frozen
  in R3 `evidence/ocr_post1.json`).
- **Call #2 (allowed only if predeclared controlled comparator is necessary):**
  a single scale-2.0 replay POST, planned as **0**; it may be spent **only** if
  the scale-4.0 input bytes or a real defect make the reused R3 record
  non-comparable. This decision is made **before** the result is seen, never
  auto-retry of a timed-out write.

## 2. Pre-registered thresholds (frozen, do NOT relax)

- **Z2 table gate (original):** segment/cell CER ≤ **0.25** AND protocol §4
  structural pass. Z2 printed-page context threshold: 0.15.
- Mechanism repair is reported separately from table-quality pass: a config
  mechanism pass ≠ a table-quality pass. The Z2 quality result is reported
  honestly as pass/fail.
- No threshold relaxation. No forced pass.

## 3. Counters at PLAN freeze

- GET used **0 / 1** (planned) · POST used **0 / 2** (planned 1) · retries 0 ·
  ASR 0 · embedding 0.

## 4. Owner / file map (declared before edits)

| Path | Owner action |
|---|---|
| `backend/lightgravity/sources/ocr/adapter.py` | add `ENV_OCR_SCALE` const + safe parse helper (env style) |
| `backend/lightgravity/sources/processing.py` | `ProcessingConfig.scale` + validation / env wiring helper |
| `backend/lightgravity/sources/service.py` | `build_source_service` composes scale into `ProcessingConfig` |
| `backend/lightgravity/sources/ocr/pdf.py` | only if a documented max constant is needed (no behavior change) |
| `tests/sources/ocr/test_adapter.py` | env default/valid/NaN/inf/bounds tests |
| `tests/sources/ocr/test_processing.py` | actual-engine-receives-scale + invalid-env-diagnostic tests |
| `docs/07-settings-and-models.md` | additive env documentation (settings/model env notes) |
| `docs/08-interface-contract.md` | implementation-note decision (no mechanical version bump) |
| `probes/materials-ocr-r4-20261016/**` | scoring scripts, POST driver, evidence, report, errata |

No edits to other features, other tasks, frontend, or the R3/audit worktrees.

## 5. Non-goals

- No full-suite run unless a defect needs it.
- No default relevance-threshold tuning on the 7 R3 queries.
- No claim of full quality / task done.
- No image editing via python; rendering the PDF via the existing product
  rasterizer **is** allowed product execution (no image-gen tool required).
