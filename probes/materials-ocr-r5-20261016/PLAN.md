---
title: "Materials OCR R5 — FROZEN PLAN (pre-registered before any inference POST)"
doc_type: report
category: probe
status: "frozen — written before any implementation POST; no result may change it"
updated: "2026-10-16"
---

# FROZEN PLAN — materials-ocr-r5-20261016

Base `main @ a2dc40a` (verified clean). Branch
`fix/materials-ocr-r5-20261016`. Worktree
`/home/yhvh/code/lightgravity-bot-worktrees/materials-ocr-r5-20261016`.

This plan is **frozen before any inference POST**. No result may change the
model, the input, the scale, the instruction, the call count, the thresholds,
the metrics or the comparator. Failed attempts are kept (errata), never
rewritten.

## 0. Problem statement (from R4, unchanged)

R4 left the Z2 page-2 table extraction **FAIL**: fair token-weighted segment
CER **0.268882 > 0.25** at scale 4.0 (threshold not relaxed), exact human row
tokens **8/15**, and protocol §4 **row/column structure absent** (machine
row/col counts unverified from plain text). Whole-page CER 0.250755 > 0.15.
The model produced **plain text**, merged adjacent table blocks (sections 2 & 3
of the human truth collapsed from 6 rows to 2 lines), and did not mark uncertain
characters explicitly.

Root cause considered: the product OCR instruction (R4 `OCR_PROMPT`) only says
"preserve line breaks and punctuation"; it never tells the model that a page can
have a **multi-column / table layout** whose rows and columns must be preserved,
nor how to represent it, nor that uncertain characters must be flagged rather
than guessed. This is a **generic instruction gap**, not a Z2-specific defect.

## 1. DELIVER — minimal candidate

### 1.1 Product change (generic, no Z2 geometry, no ground truth in prompt)

- Replace the single generic `OCR_PROMPT` with a **layout-aware but fully
  general** OCR instruction that:
  - preserves **headings** (and marks them as headings, not body rows);
  - detects **multi-column / tabular layout** and preserves it as a **Markdown
    table** with one row per real visual row and one column per real column cell;
  - for **non-tabular** pages, keeps ordinary reading-order plain text (retains
    ordinary text support; no regression to Z1-class pages);
  - marks **uncertain / illegible characters or cells** explicitly with the
    token `[unreadable]` instead of guessing or silently dropping them;
  - **forbids inference / completion / translation / summary / added content**,
    and forbids inventing rows, columns, cells or values not visibly present.
- The instruction must **not contain any Z2-specific geometry, cell values,
  dialect names, row/column counts, or the human truth**. It is a general
  layout-OCR instruction applicable to any page.
- No new API, no new dependency, no new endpoint, no platform change. The
  request path, model, temperature, `max_tokens`/timeouts, hashing and page
  back-reference are **unchanged**. Default render scale remains `2.0`.
- Keep the existing strict original-content gate and whitespace-only
  normalisation untouched.

### 1.2 Focused regression tests

- Adapter request-shape test updates to the new instruction (still typed
  `text` + `image_url`, `temperature=0`, `stream=False`, no ground truth).
- Assert the new instruction is **generic** (contains no Z2-specific literal)
  and contains the required layout/uncertainty guards.
- Assert ordinary text support is retained (the instruction still asks for
  plain reading-order transcription when there is no tabular layout).
- Assert default scale behaviour, page back-reference and input-hash
  preservation are unchanged (existing tests must still pass).

### 1.3 Independent scoring (append-only, does NOT edit R3/R4)

Reuse R4's `score_r4.py` **only where the metric is identical**; report any
difference against the **original protocol** and report whole-page CER and
segment CER separately. Add a machine Markdown **table parse** so that when the
model emits a Markdown table, machine row/column counts are actually parsed
(not merely called "unverified"); if **no** table structure is emitted,
`machine_rows = 0` ⇒ structure **FAIL** per protocol §4 (never "not
applicable").

## 2. Frozen human structure truth (reconciled BEFORE calls)

Reconciled directly from `private/LG035-ZH-Z2.p2.txt` (human ProofreadPage
level 3, sha256 `8c6ad74b3b647dd85aacb1db665ceafd262da579a0c65aac7e879488665862b0`):

- 5 blank-line-separated sections.
- Each section has **3** dialect rows (國 / 蘇 / 廣 style), i.e. **3 columns**.
- **15 human data rows**, **3 human columns**, heading line
  `語助詞北風跟太陽` above them.

The manual truth **does support** 15 rows × 3 columns; the manifest does **not**
mandate a different shape. No `15×3` is invented beyond what the manual truth
contains.

## 3. Bounded network phase (authorized exactly 2 planned POST)

| Item | Bound |
|---|---|
| inference POST total | **exactly 2** (both predeclared below; no adaptive extra) |
| concurrency | **1** (strictly serial) |
| retries | **0** — timeout/interruption ⇒ record unknown, no replay |
| per-call timeout | **120 s** total, **5 s** connect |
| target | `http://192.168.8.12:11434` only, model `qwen3.8-27b` |
| input per POST | ≤ 2 MiB |
| output per POST | `max_tokens=4096` |
| temperature / stream | `0` / `false` (deterministic) |
| `/health` GET | **≤ 1**, 8 s (already spent: 1/1, HTTP 200) |
| ASR / embedding | **0** |
| other IP/provider/scans/TaskRun/model install | none |

Frozen call decision **before** any POST:

- **Call #1 (planned):** Z2 page 2 at render **scale 4.0**, rendered through the
  real product `PdfiumRasterizer` (`LIGHTGRAVITY_OCR_SCALE=4.0`), OCR'd through
  the real product `OpenAICompatOcrBackend` with the **new general layout
  instruction**, model `qwen3.8-27b`, `temperature=0`, `stream=false`,
  `max_tokens=4096`, timeout 120 s, retry 0, `cold=True`. Original truth is
  **not** in the prompt.
- **Call #2 (planned):** Z1 printed page (`lg035_truth_zh_laojielao_p10.jpg`,
  sha256 `5c73b9d0…d0e64f`) through the **same new general instruction**, same
  deterministic parameters, as the ordinary-text **regression** check. Truth not
  in prompt.
- No adaptive third call. If call #1 fails to produce the table, the gate is
  **not** relaxed, no extra attempt is made, and the Z2 FAIL is reported.
- If the endpoint becomes unavailable mid-phase, **stop network**, do not retry,
  and report the truthful partial state.

### 3.1 Persistence before each POST

Before each POST the reservation is persisted to
`evidence/reservations.jsonl` (append-only) containing: plan id, call index,
kind, endpoint, model, scale, input sha256/bytes, `max_tokens`, timeout,
temperature, instruction name+sha256, and the frozen thresholds. The raw
(redacted) response is persisted after each call.

## 4. Pre-registered thresholds (frozen, DO NOT relax)

Original TRUTH-PREP protocol:

- **Z1 printed page:** page CER ≤ **0.15**.
- **Z2 table page:** cell/segment CER ≤ **0.25** AND protocol §4 structural pass
  (machine rows == human rows AND machine cols == human cols AND every human
  cell/segment token byte-exact after NFKC).
- Whole-page CER reported separately (context only, not the Z2 pass gate).

No threshold relaxation. No forced pass. A mechanism/instruction change is
reported **separately** from a table-quality pass.

## 5. Counters at PLAN freeze

- GET used **1 / 1** (health, HTTP 200) · POST used **0 / 2** · retries 0 ·
  ASR 0 · embedding 0.

## 6. Owner / file map (declared before edits)

| Path | Owner action |
|---|---|
| `backend/lightgravity/sources/ocr/adapter.py` | new generic layout-aware `OCR_PROMPT` (no request-shape change) |
| `tests/sources/ocr/test_adapter.py` | prompt-shape/generic-guard regression tests |
| `tests/sources/ocr/test_processing.py` | only if an existing assertion references the old prompt |
| `probes/materials-ocr-r5-20261016/**` | PLAN, scoring scripts, POST drivers, evidence, report, errata |
| `docs/09-source-intake-and-retrieval.md` | additive narrow implementation note (single owner) |
| `docs/08-interface-contract.md` | narrow implementation note only if necessary; **no contract bump** |

No edits to frontend, no other features/tasks, no LG-035 frontmatter, no PM root
docs, no prior evidence.

## 7. Non-goals

- No full-suite run unless a real defect needs it.
- No new table API / dependency / platform.
- No claim of full quality / task done / LG-040 unlock.
- No image editing/generation/cropping; only the existing whole-page product
  rasteriser at scale 4.0.
