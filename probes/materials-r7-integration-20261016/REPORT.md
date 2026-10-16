---
title: "Materials R7 集成 REPORT（A/B/C/D/E 顺序 --no-ff；LG-035 置 done）"
doc_type: report
category: engineering
updated: "2026-10-16"
---

# Materials R7 集成 REPORT

* Role: main technical integration owner (sole PM only; no nested agents, no push/deploy/publish, no reset/clean, no network, no model calls).
* Date (UTC): 2026-10-16.
* Pre-merge main: `2d76c83` (clean, expected). No stash.
* Post-merge main: see `STATUS.md`.
* Package: `probes/materials-r7-integration-20261016/**` (only writer) + PM docs listed in §6.

## 1. Pre-flight (read-only, real)

* Project root `main@2d76c83` clean, expected base for all five source branches (`git merge-base` = `2d76c83`).
* Five source branches, all clean worktrees, exact tips:
  * A `test/materials-fixtures-r7-20261016@f21d6e3` (probes-only)
  * B `fix/materials-layout-r7-20261016@8182d36` (product 3 files + probes)
  * C `investigate/materials-endpoint-r7-20261016@1cfa417` (probes-only)
  * D `test/materials-ocr-cohort-r7-20261016@97c4f8f` (probes-only)
  * E `fix/materials-table-mode-r7-20261016@4917413` (BASE `8182d36`; **descends B**)
* **No previous bounded wrapper running except self**: the only `lightgravity-pi-bounded.py` process was this integration task itself (argv `materials-r7-integrate-20261016.txt`, its `pi` child is this shell's parent). All five source owner wrappers had already exited (not killed). No external `main` writer (HEAD/status matched expectation before merge). The long-running `uvicorn` on 8123 is an unrelated pre-existing service, untouched.

## 2. Merge order and results (sequential `--no-ff`, no duplicate pick)

| Step | Merge | Merge commit | Notes |
|---|---|---|---|
| 1 | A `test/materials-fixtures-r7-20261016` | `89b0cc1` | probes-only; no conflict |
| 2 | B `fix/materials-layout-r7-20261016` | `7eb88fe` | product `layout.py` + `__init__.py` export + `test_layout.py`; no conflict |
| 3 | C `investigate/materials-endpoint-r7-20261016` | `e8a8e40` | probes-only; no conflict |
| 4 | D `test/materials-ocr-cohort-r7-20261016` | `95b66bf` | probes-only; no conflict |
| 5 | E `fix/materials-table-mode-r7-20261016` | `5f84503` | E descends B ⇒ only E's own delta applied, no duplicate pick; no conflict |

* All merges clean; **all owned legitimate product changes merged, no snapshots, no drops**.
* Final merged product tree for the owned files is **byte-identical to E `4917413`**:
  `git diff 4917413 HEAD -- backend/lightgravity/sources/ocr/ backend/lightgravity/sources/processing.py tests/sources/ocr/` is **empty**.
* Source branch tips unchanged (`f21d6e3`/`8182d36`/`1cfa417`/`97c4f8f`/`4917413`); all five source worktrees remain clean; all other historical worktrees/dirty preserved (not touched).

## 3. Product change summary (merged, scope/security receipts)

Product delta vs pre-merge `2d76c83`:

| File | Change |
|---|---|
| `backend/lightgravity/sources/ocr/__init__.py` | re-export layout + table-mode symbols |
| `backend/lightgravity/sources/ocr/layout.py` | NEW: bounded, model-free layout analysis + ruled-grid `TableClassification`/`classify_table`/`classify_image_bytes` |
| `backend/lightgravity/sources/ocr/adapter.py` | `OCR_TABLE_PROMPT` (generic structure only), `OcrRequest.prompt` override, `ENV_OCR_TABLE_MODE` + `parse_table_mode_env` + `OcrTableModeInvalid` |
| `backend/lightgravity/sources/processing.py` | `ProcessingConfig.table_mode` (**default False**) via env; per-page classify + prompt selection; evidence `prompt_kind`/`prompt_sha256`/`table_classification` |
| `tests/sources/ocr/test_layout.py` | NEW cross-scale/bounds tests |
| `tests/sources/ocr/test_table_mode.py` | NEW table-mode env/gating/pipeline tests |

* **Default pipeline unchanged**: `LIGHTGRAVITY_OCR_TABLE_MODE` unset/empty ⇒ `table_mode=False`; every page uses the unchanged `OCR_PROMPT` (proven live by E CALL2 request prompt hash == default hash `7cb03181…`).
* **Scope**: no endpoint/error code/entity schema/enum/transition/response-field change. New evidence fields written **only** into the opaque local derivative `derivative/ocr_evidence.jsonl` and the pages `source_derivative` doc. `api/`, `service.py`, `content.py`, `models.py` **byte-unchanged** vs pre-merge.
* **Security**: layout PNG decoder caps geometry (`MAX_PAGE_SIDE`/`MAX_PAGE_PIXELS`) **before** IDAT inflation (fixes a prior unbounded `zlib.decompress`); the classifier is bounded/model-free and never reads filename/fixture-hash/page-number/ground-truth. **No untrusted unbounded PNG inflation**; **no new public schema**.
* **No runtime absolute reference paths**: `grep -nE '/home/|/tmp/|/Users/'` over the four changed product files returns none; the only `probes/` mention is a docstring comment, not a runtime dependency. `ProcessingConfig.from_env()` env wiring preserved (via existing `service.py` path). Existing worker/SDK/token/connection-pin/lease/recovery untouched. Source API unchanged.

## 4. Necessary integration checks (real exits, on the final merged candidate)

Recorded raw in `evidence.txt`; run once on the merged candidate, no broad full suite, no new model probes.

| Command | Exit | Result |
|---|---|---|
| `pytest tests/sources -q` | 0 | **147 passed, 1 skipped** |
| `pytest tests/sources/ocr/test_layout.py tests/sources/ocr/test_table_mode.py -q` | 0 | **28 passed** |
| `mypy` (repo config) | 0 | **Success: no issues found in 138 source files** |
| `python probes/materials-table-mode-r7-20261016/offline_gate.py` | 0 | **ALL_OK** (T1 fires; NIST/MIX/Z1 do not) |

* Regenerating `offline_gate.json` produced output **byte-identical** to E's committed file (deterministic; `git diff` empty) — no snapshot drift.
* Board CLI (absolute root `/home/yhvh/code/olav-tasks/dist/cli.js`, backlog root `/home/yhvh/code/lightgravity-bot/backlog`):
  * `validate` → `41 tasks / 0 diagnostics` (before and after);
  * `digest` **after** LG-035 status change → `38 done / 1 in-progress / 2 todo`, complete=true, **0 diagnostics**, `ready=[]`;
  * `ready` → `[]` (LG-035 done, LG-037 still in-progress blocks LG-040).

## 5. Coverage vs the original LG-035 acceptance conditions

| Original class | Receipt | Result |
|---|---|---|
| authorized backend + real product env | D/E real `OpenAICompatOcrBackend` (`qwen3.8-27b`) via `IntakeService → ProcessingEngine.process → OcrBackend.transcribe` | ✔ |
| real clear page | baseline CER **0.0000** | PASS |
| multipage PDF | baseline real 2-page p1 0.0000 / p2 0.0763 | PASS |
| mixed text+scan one file | D R7 MIX p1 **0.0295** / p2 **0.0000** | PASS |
| table (real grid + human truth + optional table mode) | E R7 T1 real NIST 8×3 grid, human truth from PDF text layer → rows 8==8, cols 3==3, cell CER **0.0**, symbols 7/7 byte-exact | PASS |
| Chinese printed | Z1 CER **0.0423** (default prompt hash unchanged) | PASS |
| low-quality/rotated | baseline recorded-only, honest degradation, no invented numeric gate | honest degradation |
| machine-derived vs human formal separation, reprocess not overwrite | baseline delivered | PASS |

All original acceptance classes are covered by **real receipts** ⇒ per the PM authorization, **LG-035 set `done` (待 LG-040 集中版本 QA)**.

## 6. Limits / non-claims

* E's table PASS is a **single run, single born-digital grid sample** — not a statistical or production-grade table-OCR claim.
* D's **default pipeline** (table mode OFF) on the same real grid input still **FAILs** (`parse_method=none`, rows/cols 0, cell CER 1.0); historical R3/R4/R5/R6 and R7-cohort table FAILs remain FAIL and are preserved unchanged.
* Z2 multi-column/reading-order is not part of the original LG-035 classes and is left to LG-040.
* Layout cross-scale receipt is scoped to Z2 page-2 topology + controls, not all pages.
* Contract determination: `prompt_kind`/`prompt_sha256`/`table_classification` are opaque derivative evidence only ⇒ **no version bump; contract stays `1.11.0`** (docs/08 §6.6 / §13 precedent = `LIGHTGRAVITY_OCR_SCALE` implementation note). No fake "changed" claims.
* LG-040/041 **remain locked**; LG-037 stays `in-progress`.

## 7. Cost (summed separately, unknown ≠ 0)

Source history (not double-counted with acquisition/protocol overlaps): C embedding **2 POST + 2 GET** (health + `/v1/models`), D OCR **3 POST + 1 health GET**, E OCR **2 POST + 1 health GET**; acquisition (A) **7 GET + 1 download** (incl. 3 redundant size checks, recorded honestly). **Current integration phase product LAN calls = 0** (no new POST/GET/ASR/embedding, no new tests to network, no model probes). pi/DeepSeek execution cost: **unknown, not zero**. LAN/endpoint price: unknown. No audio.

## 8. Preservation

No push/deploy/publish. No reset/clean/overwrite. No `.env` copied. All historical worktrees, dirty trees, branches, raw evidence preserved untouched. Only the five `--no-ff` merges, the PM docs in §6, and this report/STATUS were written.
