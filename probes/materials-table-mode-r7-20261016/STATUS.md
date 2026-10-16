# LG-035 R7 — Table-aware OCR mode — STATUS (finalization)

* Task: LG-035 (materials table-aware OCR mode, **OPTIONAL, default OFF**)
* Worktree: `/home/yhvh/code/lightgravity-bot-worktrees/materials-table-mode-r7-20261016`
* Branch: `fix/materials-table-mode-r7-20261016`
* Base: `8182d36` (LG-035 R7 layout candidate). Product commit: `8a0b9fd`. PLAN commit: `13fc993`.
* Date (UTC): 2026-10-16.
* Owner of this package: `probes/materials-table-mode-r7-20261016/**` only.

## State

`in-progress` — implementation delivered and **its own focused checks + 2 real calls PASS**; all
real/named acceptance is **LG-040** (independent QA milestone). **Not self-marked done.**
LG-040/041 not unlocked. No main/other-worktree/backlog/root-PM changes.

## What is delivered (product, minimal)

| File | Change |
|---|---|
| `backend/lightgravity/sources/ocr/layout.py` | `TableClassification`, `classify_table`, `classify_image_bytes` (pure, model-free, bounded) |
| `backend/lightgravity/sources/ocr/adapter.py` | `OCR_TABLE_PROMPT`, `OcrRequest.prompt` override, `ENV_OCR_TABLE_MODE`, `parse_table_mode_env`, `OcrTableModeInvalid` |
| `backend/lightgravity/sources/ocr/__init__.py` | re-export new symbols |
| `backend/lightgravity/sources/processing.py` | `ProcessingConfig.table_mode` (**default False**) via env; per-page classify + prompt selection; evidence `prompt_kind` / `prompt_sha256` / `table_classification` |
| `tests/sources/ocr/test_table_mode.py` | focused tests (env, gating, bounds, pipeline prompt selection, evidence) |
| `backend/lightgravity/sources/service.py` | **unchanged** (existing `ProcessingConfig.from_env()` wiring already carries the option) |

**Default OFF**: `LIGHTGRAVITY_OCR_TABLE_MODE` unset/empty ⇒ `table_mode=False`; every page uses the
unchanged `OCR_PROMPT`. Defaults are unchanged in every other respect.

## Evidence

* Real calls (already executed, **not replayed**): CALL1 real 8×3 grid table → rows 8/8, cols 3/3,
  cell CER **0.0**, symbol tokens **7/7** byte-exact, `structure_pass`/`table_gate_pass` PASS;
  CALL2 ordinary Chinese page with **default** prompt → page CER **0.04233** ≤ 0.15 PASS.
  Both through the real `SourceService/IntakeService → ProcessingEngine.process →
  OcrBackend.transcribe` path.
* Requests/raw/reservations persisted before scoring under `evidence/**` and `evidence/raw/**`;
  pre-forward `reservation` ledger records precede each `result`.
* Offline checks (already executed): `mypy` 138 files clean; `pytest tests/sources -q`
  147 passed/1 skipped; `test_table_mode.py` 8 passed; `test_layout.py` 20 passed; `offline_gate.py`
  ALL_OK. No full suite.

## Contract decision

New fields are **internal/opaque evidence extensions** written only into
`derivative/ocr_evidence.jsonl` and the pages `source_derivative` doc. The frozen `docs/08 §6.6`
`source` entity and `source.derivatives` entry shape are unchanged; no endpoint/error-code/enum/
transition/response change; the env var is optional+non-secret via the existing
`ProcessingConfig.from_env()` entry (same precedent as `LIGHTGRAVITY_OCR_SCALE`). ⇒ **No contract
version change**; contract stays `1.11.0`. No `docs/08`/`docs/09` edit was made.

## Non-claims / limits

* Single run (2 calls) — **not** statistical; no production-grade table-OCR claim.
* R3–R6 and R7-cohort historical FAILs remain FAIL as history; R7 cohort flatlist (`97c4f8f`)
  unchanged; mixed-page historical PASSes remain historical.
* Low-quality/rotated scans: behaviour unknown/degraded; **no invented low-quality CER gate**.
  Such results are REPORTED, not numerically required to pass.
* Product PNG-input bounds caveat: decoder caps dimensions before inflation (test-backed), but the
  accepted-PNG size limit was not swept to its empirical maximum; only a small PNG was live-tested.
* Fresh pi/DeepSeek cost: **unknown, not zero**. LAN cost: unknown.
* No independent QA yet — that is the named LG-040 milestone only.

## Finalization provenance

Previous bounded wrapper exited **143** (`token_budget_exceeded`, ~430 s) **after** the 2 real calls
and REPORT, before docs notes / final commit. Finalization done by one bounded executor with **no
model calls, no replay**; no competing live writer; all pre-existing owned dirty files preserved
(no reset/clean). Model calls **not** replayed. See `REPORT.md` §10.
