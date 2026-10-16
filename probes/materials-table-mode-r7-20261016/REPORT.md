# LG-035 R7 — Table-aware OCR mode (OPTIONAL, default OFF) — REPORT

* Package: `probes/materials-table-mode-r7-20261016/**` (only writer).
* Worktree: `/home/yhvh/code/lightgravity-bot-worktrees/materials-table-mode-r7-20261016`
* Branch: `fix/materials-table-mode-r7-20261016`
* Base HEAD: `fix/materials-layout-r7-20261016` @ `8182d36` (explicit candidate dependency;
  **NOT** current `main@2d76c83` — root integrates `8182` first).
* Date (UTC): 2026-10-16. **PLAN frozen in commit `13fc993` BEFORE any POST.**
* Endpoint `http://192.168.8.12:11434`, model `qwen3.8-27b`. Both calls drove the **actual**
  `SourceService/IntakeService → ProcessingEngine.process → OcrBackend.transcribe` path.

## 1. Headline

| Call | Sample | Prompt chosen | Gate | Value | Threshold | Result |
|---|---|---|---|---|---|---|
| 1 | `LG035-R7-T1` real grid table | **table** (explicit Markdown) | rows incl. header | **8 == 8** | exact | **PASS** |
| | | | columns | **3 == 3** | exact | **PASS** |
| | | | table cell CER | **0.0** | ≤ 0.25 | **PASS** |
| | | | symbol tokens byte-exact | **7/7** | all | **PASS** |
| 2 | `LG035-ZH-Z1` ordinary Chinese page | **default** (unchanged) | page CER | **0.04233** | ≤ 0.15 | **PASS** |

**Overall: table hardgate PASS; ordinary-page gate PASS with the default prompt unchanged.**

**Honest scope:** this is a **single run** (2 calls), not a statistical or multi-sample battery.
The table gate passing once is real but does **not** by itself claim production-grade table OCR
across arbitrary tables. R3/R4/R5/R6/R7-cohort historical FAILs remain FAIL as history; the R7
cohort flatlist (`97c4f8f`) is unchanged. LG-035 stays **in-progress**; LG-040/041 not unlocked;
**no self-marked done**.

## 2. What changed (product, minimal)

Files owned and changed (no vector/frontend/coordinator/settings/store/backlog/root-PM docs):

| File | Change |
|---|---|
| `backend/lightgravity/sources/ocr/layout.py` | added `TableClassification`, `classify_table`, `classify_image_bytes` (pure, model-free, bounded) |
| `backend/lightgravity/sources/ocr/adapter.py` | added `OCR_TABLE_PROMPT` (generic structure only), `OcrRequest.prompt` override, `ENV_OCR_TABLE_MODE` + `parse_table_mode_env` + `OcrTableModeInvalid` |
| `backend/lightgravity/sources/ocr/__init__.py` | re-export the new symbols |
| `backend/lightgravity/sources/processing.py` | `ProcessingConfig.table_mode` (default **False**) via env; per-page classify + prompt selection; evidence records `prompt_kind`/`prompt_sha256`/`table_classification` |
| `backend/lightgravity/sources/service.py` | **unchanged** (existing `ProcessingConfig.from_env()` wiring already carries the option through the normal service path) |
| `tests/sources/ocr/test_table_mode.py` | focused tests (env, classifier gating, bounds, pipeline prompt selection, evidence) |

> **Correction (finalization R7-close, 2026-10-16):** an earlier draft of this report listed
> `docs/08`, `docs/09` as changed. **They are NOT changed.** `git diff HEAD -- docs/` is empty and
> the product commit `8a0b9fd` contains no `docs/**` path. No `docs/08`/`docs/09` edit was made;
> the contract determination in §9 stands on the existing `docs/08 §6.6` precedent alone.

**Default OFF**: with `LIGHTGRAVITY_OCR_TABLE_MODE` unset/empty, `ProcessingConfig.table_mode=False`
and every page uses the unchanged `OCR_PROMPT`. Verified offline + by CALL2 (request prompt hash
equals the default prompt hash exactly).

### Classifier signal (real, bounded, not decorative)

A page is a table candidate only when **all** hold: a single **dominant** region owns ≥ 0.75 of
the page's text lines; it has ≥ 2 columns; ≥ 2 full-width horizontal rules fall inside its y-span;
and ≥ 60% of its lines confirm the region's columns (per-line column occupancy). Constants are
documented ratios; inputs are pixels + normalised gutters only — **no filename / fixture hash /
page number / GT / known SI answers**.

**Offline gating evidence** (`evidence/offline_gate.json`, command `offline_gate.py`): fires on
the real T1 grid; does **not** fire on the NIST p16 full born-digital prose page, MIX p1 prose,
MIX p2 scan, or Z1 Chinese printed JPEG.

## 3. Calls (exact inputs / hashes / provenance)

| Call | Sample | input sha256 | bytes | media | classifier | prompt | latency |
|---|---|---|---|---|---|---|---|
| 1 | LG035-R7-T1 | `39138a97…` | 33716 | image/png | `is_table=True` (3 cols, 4 rules, lf 1.0, cons 0.92) | table | 36.404 s |
| 2 | LG035-ZH-Z1 | `5c73b9d0…` | 333996 | image/jpeg | `is_table=False` (unsupported format) | **default** | 28.325 s |

CALL1 provenance: NIST SP 811 (2008) p.16 Table 1 grid crop, PDF pts `(90.0,517.0,524.6,627.5)`
scale 4.0; source PDF sha256 `788dd8f0…` (public domain, US Gov work).
CALL2 provenance: Wikimedia Commons `File:10-13老解老.pdf` p.10 (Public domain); human truth
`9043c2b7…`. Truth was **never** placed in a prompt.

Per-call request facts recorded by the product evidence:

* CALL1: `prompt_kind=table`; `prompt_sha256=4c7d8ec4…` (≠ default `7cb03181…`); usage 954/634; `finish_reason=stop`.
* CALL2: `prompt_kind=default`; `prompt_sha256 == default_prompt_sha256 == 7cb03181…`; usage 1262/472; `finish_reason=stop`.

Raw machine derivatives persisted **before** scoring under `evidence/raw/`.

## 4. Results detail

* **CALL1 machine output = a real Markdown pipe table** (3 columns × 8 rows incl. header), parsed
  as `markdown_pipe`. Scored with the **frozen, unchanged** R7 cohort parser/scorer: rows 8/8,
  cols 3/3, cell CER **0.0**, all symbol tokens `m,kg,s,A,K,mol,cd` byte-exact ⇒
  `structure_pass=true`, `table_gate_pass=true`. **No truth was used to reconstruct a grid.**
* **CALL2**: default prompt → page CER **0.04233** ≤ 0.15 PASS; request prompt hash proves the
  default request is unchanged for an ordinary page.

## 5. Necessary checks (all offline)

| Check | Result | Evidence |
|---|---|---|
| optional feature default OFF | PASS | `ProcessingConfig().table_mode is False`; CALL2 request uses default prompt |
| env validity (invalid → explicit error) | PASS | `test_table_mode_env_invalid_is_rejected_not_silently_off` |
| true candidate gating vs ordinary/not-a-table | PASS | `offline_gate.py` ALL_OK; pipeline test |
| pipeline wire (actual request + table format + provenance) | PASS | LIVE CALL1 via `ProcessingEngine.process`; evidence `prompt_kind/provenance` |
| unsafe input bounds (over-size/bomb PNG refused) | PASS | `test_classifier_is_bounded_…`; layout decoder caps before inflation |
| old layout cross-scale checks preserved | PASS | `test_layout.py` 20 passed (R7 layout candidate unaffected) |

## 6. Check commands / exits

| Command | Exit | Result |
|---|---|---|
| `mypy` (repo config, `backend/lightgravity`) | 0 | **138 source files clean** |
| `pytest tests/sources/ocr/test_table_mode.py -q` | 0 | **8 passed** |
| `pytest tests/sources/ocr/test_layout.py -q` | 0 | **20 passed** (layout cross-scale preserved) |
| `pytest tests/sources -q` | 0 | **147 passed, 1 skipped** |
| `python probes/.../offline_gate.py` | 0 | **ALL_OK** |

No full-suite run was performed (per instruction: affected OCR/source tests + mypy only).

## 7. Counters / budget

| counter | used / cap |
|---|---|
| OCR POST | **2 / 2** |
| health GET | 1 / 1 (200, 5 ms) |
| retries | **0** |
| concurrency | 1 |
| audio / embedding / ASR / worker | 0 / 0 / 0 / 0 |
| per-call timeout (connect/total) | 5 s / 120 s |
| max output tokens | 4096 |
| input per call / total | 33716 / 333996 / 367712 B ≤ 4 MiB (each ≤ 2 MiB) |

Reservation written before each forward (2 `reservation` ledger records); raw persisted before
scoring. No auto-retry; no timeout occurred so no call was skipped. pi/DeepSeek cost: **unknown,
not zero**. LAN cost: unknown.

## 8. Pipeline exact path (no harness-only injection)

Both calls used the **real product pipeline**: `IntakeService.receive` persisted the original,
then `ProcessingEngine.process` read the file SoT, classified the rendered page, selected the
prompt, and called the real `OpenAICompatOcrBackend.transcribe` over HTTP. A thin recording wrapper
around the real backend captured the **actual** request without altering it. No handcrafted answer
or harness-only instruction injection was used. The derivative was written to the file SoT and the
layout decision recorded in `ocr_evidence.jsonl`.

**Disclosed gap:** the probe wires the engine directly (with a real HTTP backend) rather than
through the full HTTP API `create_app`; the option itself flows through the same
`ProcessingConfig.from_env()` path that `build_source_service()` uses, so the service/API wiring
is exercised by construction, but the HTTP round-trip is not re-run here.

## 9. Boundaries / non-claims

* No quality-pass claim beyond the single table sample + single ordinary sample; not statistical.
* R3/R4/R5/R6/R7-cohort historical FAIL results remain unchanged; Z2 FAIL unaffected.
* The T1 input is **born-digital** (not a historical scan), as disclosed by the fixture package.
* Low-quality/rotated pages: behaviour unknown/degraded; **no invented low-quality CER gate**.
* No push / deploy / publish / reset / clean. All prior worktrees/branches/raw preserved.
* No new dependency, no new provider/model install.

### 9.1 Contract-impact determination (actual declared schema, not assumed)

The new evidence fields are written **only** into the OCR evidence sidecar artifact
`derivative/ocr_evidence.jsonl` (declared **internally** in
`backend/lightgravity/sources/content.py` as `DERIVATIVE_EVIDENCE = "ocr_evidence"`; `kinds`
`ocr_evidence` / `pages` machine derivatives) and the per-version `source_derivative` pages doc.
Both are **opaque local derivative artifacts**, not part of the frozen public entity/API surface:

* `docs/08` §6.6 freezes the `source` entity with `derivatives: []  # {kind, path, source_version,
  content_hash, model_version}`. The added fields live **inside the artifact**, not inside any
  `source.derivatives` entry and not in any `source` top-level field. `grep` over `docs/` finds
  **zero** references to `ocr_evidence`, `pages.json`, `prompt_kind`, `prompt_sha256` or
  `table_classification` — none is a declared, frozen public entity/schema field.
* The new HTTP surface is **unchanged**: no endpoint, error code, response field, enum or state
  transition was added or altered. `LIGHTGRAVITY_OCR_TABLE_MODE` is a new **optional, non-secret**
  env var parsed through the existing `ProcessingConfig.from_env()` entry, exactly mirroring the
  documented `LIGHTGRAVITY_OCR_SCALE` precedent.

**Decision:** this is an **internal/opaque evidence extension** under `docs/08` §13's
"实现说明增补（无版本变化）" rule (the same rule cited by the `LIGHTGRAVITY_OCR_SCALE` note in
§6.6). **No contract version change is required and none was made** — the contract version stays
`1.11.0`, and the schema namespace `lightgravity.bot/v1` is untouched. No version constant, test or
`docs/` entry edit is needed. (If a future integration owner instead promotes these into a frozen
public entity/API field, that becomes a conservative **MINOR** under §13; that promotion is **not**
part of this change and is left to the integration owner.)
* LG-035 stays `in-progress`; all real acceptance is LG-040 (named independent QA milestone only).

## 10. Finalization provenance (R7-close)

This section records how the report/commit was finished after a prior executor was cut off.

* A **previous wrapper exited `143`** (`token_budget_exceeded`, ~430 s) **after** the 2 successful
  REAL calls and after `REPORT.md` was written, but **before** the docs notes and final commit.
  Finalization was done by a single bounded executor; **the 2 model calls were NOT replayed**.
* **No live competing writer**: the only `pi`/wrapper process in the worktree at finalization
  (`lightgravity-pi-bounded-*`) was this executor's own session tree
  (`wrapper → pi → shell`, same PID lineage). No other writer touched the tree; all existing owned
  dirty files (`probes/materials-table-mode-r7-20261016/**`) were preserved, not reset/cleaned.
* **Non-replay:** CALL1/CALL2 raw responses, requests, reservations and scores are the persisted
  artifacts under `evidence/**` and `evidence/raw/**` produced by the earlier run; they were read
  from disk, not regenerated. Live ledger has the pre-forward `reservation` records before each
  `result` record, confirming no replay.
* **Offline checks were already executed** (evidence/log, not re-run): `mypy` → 138 source files
  clean; `pytest tests/sources -q` → 147 passed, 1 skipped; `test_table_mode.py` → 8 passed;
  `test_layout.py` → 20 passed; `offline_gate.py` → ALL_OK. No full suite was run.
* **Product PNG input bounds caveat (honest):** the bounded-decoder guard caps pixel dimensions
  *before* inflation, but the accepted/live PNG sample (33 716 B) is small; the exact upper bound
  of *accepted* PNG input that still decodes under the guard was **not** empirically swept to its
  limit. "Over-size/bomb PNG refused" is test-backed; a full size sweep is not claimed.
