---
title: "Materials OCR R5 — generic layout-preserving OCR instruction + Z2/Z1 bound retest"
doc_type: report
category: probe
status: "complete (within bound) — instruction improvement delivered; Z1 regression PASS; Z2 table quality still FAIL; no status/task change"
updated: "2026-10-16"
---

# REPORT — materials-ocr-r5-20261016

Base `main @ a2dc40a` (verified clean). Branch `fix/materials-ocr-r5-20261016`.
Worktree `/home/yhvh/code/lightgravity-bot-worktrees/materials-ocr-r5-20261016`.

Frozen PLAN: commit `7afe8eb` (`probes/materials-ocr-r5-20261016/PLAN.md`),
written **before** any inference POST. Exactly **2 planned POST** were sent.

## 0. One-line result

The product OCR instruction was replaced by a **generic, layout-aware** one
(preserve headings, emit a Markdown table for real tabular/multi-column regions,
flag uncertain characters `[unreadable]`, forbid inference) and exercised through
the **real product** `PdfiumRasterizer` + `OpenAICompatOcrBackend`. Z1 ordinary
printed text **still PASSES** (whole-page CER **0.10582 ≤ 0.15**), so ordinary
text support is retained. **Z2 table quality still FAILS**: the model emitted
**no Markdown table** (machine rows = 0 ⇒ protocol §4 FAIL) and the fair
token-weighted segment CER is **0.277946 > 0.25**. Whole-page CER improved to
**0.241692** but that is not the Z2 gate. No threshold was relaxed and no
adaptive extra call was made.

## 1. Authority & scope compliance

- Single pi executor; root PM only; **no nested agents**.
- Bounded phase exactly as frozen: target `http://192.168.8.12:11434` only,
  model `qwen3.8-27b`, **POST 2/2** (both planned, no adaptive extra),
  concurrency 1, retry 0, per-call 120 s total / 5 s connect, `temperature=0`,
  `stream=false`, `max_tokens=4096`, input ≤ 2 MiB, **GET 1/1** (health, HTTP
  200), **ASR 0, embedding 0**. No other IP/provider/scans/TaskRun/model install.
- No push/deploy/publish/reset/clean. Prior evidence (R3, audit, R4, vector)
  **unchanged**.
- Sole product writes: `backend/lightgravity/sources/ocr/{adapter,__init__}.py`,
  `tests/sources/ocr/test_adapter.py`, narrow additive note in docs/09. No
  frontend, no other features/tasks, no LG-035 frontmatter, no PM root docs.
- Input truth never placed in the prompt (verified: `OCR_PROMPT` contains no
  dialect names, cell values or counts).

## 2. Product change (DELIVER 1.1)

| File | Change |
|---|---|
| `backend/lightgravity/sources/ocr/adapter.py` | replaces the single generic `OCR_PROMPT` with a **generic layout-aware** instruction: preserve headings; if a table/multi-column layout is present, emit a **Markdown table** with the real rows/columns (no merge/split/reorder/omit, empty cell instead of invention); otherwise plain reading-order text; mark genuinely illegible characters `[unreadable]`; forbid inference/completion/translation/summary/commentary and any content not visibly present |
| `backend/lightgravity/sources/ocr/__init__.py` | export `OCR_PROMPT` |
| `tests/sources/ocr/test_adapter.py` | `test_ocr_prompt_is_layout_aware_and_generic`: asserts table/Markdown/row/column/heading/`[unreadable]`/no-inference requirements **and** that the prompt contains **no** page-specific truth (`北風`, `國`, `15`, `z2`, …) |
| `docs/09-source-intake-and-retrieval.md` | additive narrow note: generic layout-preserving OCR instruction; no table API/dependency/endpoint added |

- **No** request-shape change: still typed `text` + `image_url`,
  `temperature=0`, `stream=False`; model, `max_tokens`, timeouts, input hashing
  and page back-reference are unchanged. Default render scale remains **2.0**.
  The existing strict original-content gate and whitespace-only normalisation
  are untouched.

## 3. Bounded retest (DELIVER 1.3 + 3)

- Health GET 1/1: `{"status":"ok"}` HTTP 200.
- **Call #1 (Z2):** page 2, scale **4.0** through real product
  `PdfiumRasterizer`, real `OpenAICompatOcrBackend`, new instruction.
  Input sha `2b8327bf…` (366,217 B ≤ 2 MiB) — **byte-identical to R4's scale-4
  render**, confirming deterministic product rendering. `finish_reason=stop`,
  `completion_tokens=1262`, latency 62.71 s, retry 0, truth not in prompt.
  Evidence `evidence/ocr_call1_z2_scale4.json`.
- **Call #2 (Z1):** `lg035_truth_zh_laojielao_p10.jpg` sha `5c73b9d0…`,
  same instruction, `scale=2.0` (image path, no raster), `finish_reason=stop`,
  `completion_tokens=733`, latency 33.09 s, retry 0. Evidence
  `evidence/ocr_call2_z1_regression.json`.
- Reservations persisted **before each POST** in `evidence/reservations.jsonl`
  (input sha, instruction sha `b89052d3…`, scale, thresholds, model).
- No adaptive third call. The endpoint stayed reachable throughout.

## 4. Independent rescoring (DELIVER 1.2)

`evidence/score_r5.py` (append-only; does NOT edit R3/R4). Normalisation per
protocol §1 (NFKC + whitespace-strip, code-point Levenshtein).

**Method comparability check (0 POST):** scoring R4's frozen scale-4 raw output
with the R5 script reproduces R4 **exactly** — whole-page CER **0.250755** and
fair token-weighted segment CER **0.268882**. The R5 structure check improves on
R4 by **actually parsing Markdown tables**; for a plain-text response it records
`machine_rows = 0` (structural **FAIL**), never "unverified".

| metric | R4 scale 4.0 (reused) | **R5 scale 4.0 (new instruction)** | threshold |
|---|---|---|---|
| Z1 whole-page CER | 0.0423 (R4/R3, plain text) | **0.10582** | ≤ 0.15 → **PASS** |
| Z2 whole-page CER | 0.250755 | **0.241692** | (context only) |
| Z2 fair token-weighted segment CER | 0.268882 | **0.277946** | ≤ 0.25 → **FAIL** |
| Z2 exact human row tokens | 8 / 15 | **6 / 15** | 15 / 15 → FAIL |
| Z2 machine table rows | 0 (no table) | **0 (no table)** | == 15 → FAIL |
| Z2 machine table cols | 0 (no table) | **0 (no table)** | == 3 → FAIL |
| Z2 protocol §4 structure | fail | **fail** | pass → FAIL |
| Z2 table quality | fail | **fail** | **FAIL** |

- Z1 printed-page gate **PASSES** ⇒ ordinary text support retained (the
  regression check is meaningful, not skipped).
- Z2 gate **FAILS** on both the CER gate and the structural gate. Thresholds
  were not relaxed.
- Reporting differences: R4 reported the fair metric as
  "independent line-window token-weighted" and recorded `structure_pass=false`
  because machine rows/cols were "unverified". R5 uses the **same** fair metric
  (reproduced exactly) and, in addition, **parses** any Markdown table; when none
  is emitted it records `machine_rows = 0` and marks the structural gate failed
  per protocol §4 (never "not applicable") — this is the protocol-faithful
  difference and is reported separately from the CER numbers.

## 5. Quality verdict (honest)

- **Instruction improvement delivered and exercised** through the actual
  product adapter: it is generic, retains ordinary text (Z1 PASS), explicitly
  marks uncertainty, and asks for Markdown tables.
- **The Z2 table gate is still UNMET.** The model, even with the new
  layout-aware instruction, chose plain text and still merged human sections
  2 & 3 onto shared lines, so `machine_rows = 0` and the fair segment CER
  regressed slightly (0.277946 > 0.25). This is **not** a full-quality or
  task-done claim and **not** a claim that the remaining gap is a model
  limitation; an instruction alone did not induce table structure for this page.
- **Remaining exact gap:** the Z2 class requires (a) a real machine
  row/column structure matching 15×3 and (b) fair segment/cell CER ≤ 0.25. Both
  are unmet. A viable next step (new, separately-authorized scope) is a
  program-side layout-analysis / column-segmentation step **before or alongside**
  OCR (e.g. detecting ruled/column boundaries and assembling the table from
  per-column cell transcriptions), since a purely text instruction does not make
  this model emit a table. No such step is implemented here.

## 6. Tests & type checks (commands + exit)

Run with the existing env venv + `PYTHONPATH=backend`:

- `python -m pytest tests/sources/ocr/test_adapter.py tests/sources/ocr/test_processing.py -q`
  → **23 passed** (exit 0). Includes the new generic-instruction guard and the
  unchanged adapter/processing/scale behaviour.
- `python -m mypy --config-file pyproject.toml backend/lightgravity/sources/ocr/adapter.py backend/lightgravity/sources/ocr/__init__.py`
  → **Success: no issues found in 2 source files** (exit 0).

No broad full-suite run (not needed; focused scope only).

## 7. Docs / contract decision

- docs/09 §6: additive narrow note on the generic layout-preserving OCR
  instruction (no new table API/dependency/endpoint).
- docs/08: **not modified** — no endpoint/error-code/entity/enum/migration or
  request/response field change. Contract stays **1.11.0** (no mechanical bump).

## 8. Counters

| counter | used / cap |
|---|---|
| health GET | **1 / 1** |
| inference POST | **2 / 2** (both planned) |
| retries | **0** |
| ASR | **0** |
| embedding | **0** |
| connect / total timeout | 5 s / 120 s per call |

pi/DeepSeek executor cost is **unknown but non-zero** (pi harness counters not
exposed to this executor); the model reports `prompt`/`completion` tokens per
call (call 1: `completion_tokens=1262`; call 2: `completion_tokens=733`).

## 9. Git

- `7afe8eb` PLAN + health GET (frozen before POST).
- `06fabd3` product instruction + focused tests + docs/09 note.
- Final commit: this report + STATUS + scoring/POST drivers + raw responses +
  scores + reservations.
- `main` unchanged; R3/audit/R4/vector worktrees untouched.

## 10. Limits & next concrete block

- **Not claimed:** full quality, task done, LG-035/037/040 closure, ASR (0 POST).
- Local checks are **not** version QA; the candidate awaits the named **LG-040**
  version QA. Mixed born-digital/scanned acceptance remains unmet (no such sample
  used here). No push/deploy/publish.
