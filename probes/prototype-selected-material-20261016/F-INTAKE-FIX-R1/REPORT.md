# REPORT — F-INTAKE-FIX-R1 (native plaintext UTF-8 intake repair)

**Type:** same-version QA R1 backend repair (NOT a new iteration, NOT a version
PASS claim). **Branch:** `fix/proto-material-intake-r1-20261016`.
**Base HEAD at report time:** `1d7095c`. See the final commit section for the
exact committed SHA.

> Companion diagnosis: `DIAGNOSIS.md` (this directory).
> Durable raw logs: `raw/` (this directory).

## 0. Prior-writer / process check (done first)

- The prior F writer that timed out (wrapper 264 s, exit 143 while updating old
  baseline assertions) is **already gone** — no stale F writer process remains.
- The only other runner is the **G coordinator** session
  (`prototype-G-dialogue-plan-fix-r1-20261016` on `/home/yhvh/code/lightgravity-bot`,
  a *different* worktree). It was **not touched**. No `tests/coordinator` or
  `backend/lightgravity/coordinator` file was modified in this worktree
  (`git status` clean for those paths).
- All prior raw evidence was **preserved**; the pre-fix raw is
  `raw/r1-product-path.txt` and the post-fix raw is `raw/r2-product-path-after.txt`.

## 1. Root cause and fix (source, native, model-free)

**Defect (Finding 5 in DIAGNOSIS):** native, model-free UTF-8 text extraction was
**absent**. The only ingestion path was OCR, which refuses `text/plain`. A real
`text/plain` upload therefore produced **no readable body**, so review/selection
saw `reference_invalid`.

**Fix — one bounded, model-free path + a synchronous pump:**

| File | Change |
|------|--------|
| `backend/lightgravity/sources/processing.py` | New `NATIVE_TEXT_MEDIA_TYPES` (`text/plain`, `text/markdown`, `text/x-markdown`, `text/x-log`, `application/x-ndjson`), `NATIVE_TEXT_MAX_BYTES = 2_000_000`, `is_native_text()`, and `_process_native_text()` which decodes the original as UTF-8 and writes one machine page via the existing `ContentStore.write_machine`. `extractor="native-utf8-text"`, `model="none"`. Non-UTF-8 / oversized → honest `failed` (`_finish_text_failure`), never a fabricated or silently truncated body. **PDF/image/OCR/vector behavior unchanged.** |
| `backend/lightgravity/sources/service.py` | Minimal **pump**: `_auto_extract_native_text()` runs after a receive **only** for native text media, synchronously, so the receipt reaches terminal `extracted`/`done` (docs/09 `received → processing → extracted`). PDF/image stay at `received` (explicit `reprocess` OCR unchanged). Dedup re-receive is a no-op. The pump is best-effort: an extraction failure never turns a successful receive into a 5xx. Receipt line records the real terminal result honestly. |
| `backend/lightgravity/sources/selection.py` | Frozen **error ordering** (docs/10 §5): existence/cross-Task (`422`) → revoke (`404`) → **stale version/hash (`409`) even with no body** → missing body (`503`). `selection_layer()` now returns `body=None` for an existing bodyless source instead of `None`, so the resolver can distinguish stale from a body gap. |
| `backend/lightgravity/sources/content.py` | Honest derivative provenance: `native-utf8-text` renders `record_type: machine_native_text` / `# Machine native text`; all other extractors keep the frozen `machine_ocr` label. |

### Automatic model-free upload path (as implemented)
1. `POST /api/v1/sources` with `media_type` in the native set → original persisted.
2. Pump runs `ProcessingEngine.process` → `_process_native_text` → UTF-8 decode → `ContentStore.write_machine`.
3. Source `received → extracted`, intake job `queued → succeeded/done`, machine derivative + page_map written (`model_version: none`).
4. `GET /sources/{id}/content?kind=auto` serves the derivative; selection resolves the `machine` layer.
No model, OCR backend, network, SDK, browser or new dependency is involved.

## 2. Old-baseline assertion update (expected functional change, NOT washing)

Two existing assertions asserted the **old** (defective) `received` state for a
native `text/plain` upload. They were minimally updated to the new **correct**
terminal state:

- `tests/sources/test_sources_api.py::test_global_inline_source_creates_inbox_ref_not_task`
  — `source.status received→extracted`, `job queued/received→succeeded/done`,
  receipt `searchable False→True`, `formal_path None→derivative/machine.v1.md`.
- `tests/sources/test_intake_jobs.py::test_uploaded_frontmatter_grants_no_execution_permission`
  — `status received→extracted`; the **data-only** guarantee is retained
  (frontmatter grants no execution permission; `index.lexical` stays `not_indexed`;
  no Task/Run created).

**Why the update is correct (not washing a failure):**
- The old assertion encoded the *defect itself* (that a plain-text upload yields
  no body). The new behavior is the documented docs/11 Flow A / docs/09 lifecycle
  the product always claimed. The pre-fix (failing) raw is preserved in
  `raw/r1-product-path.txt`; the post-fix raw is `raw/r2-product-path-after.txt`.
- The change is deliberately **not** a blanket "anything becomes extracted":
  - no `media_type` → stays `received` (no guessing; `test_upload_without_media_type_does_not_fabricate_a_body`).
  - malformed UTF-8 → `failed`, no body (`test_malformed_utf8_text_fails_honestly_no_fake_body`).
  - opaque binary → `received`, no derivative, `503` on selection (`test_binary_upload_stays_unreadable_and_never_enters_native_path`).
  - oversized native text → `failed`, no truncation (`test_oversized_native_text_fails_honestly_no_fake_body`).
  - `tests/sources/test_lg038_materials_flow.py` (no media type) and
    `tests/sources/test_durability.py` (IntakeService direct) still assert
    `received` and **pass unchanged** — proof the change is scoped.

## 3. New regression tests (production path, no seeded derivatives)

`tests/sources/test_lg047_intake_r1.py` (13 tests) uses the **real**
`create_app` app + real lifespan + shared coordinator `source_service` (the
`tests/sources/conftest.py` `api`/`app` fixtures), with **no manual derivative
seeding** and no model/network/browser:

1. `test_plain_utf8_upload_extracts_and_is_selectable` — real upload → terminal receipt → exact body via `GET /content` → selectable through the shared resolver; `model_version == "none"`.
2. `test_markdown_upload_extracts_and_is_selectable`.
3. `test_upload_without_media_type_does_not_fabricate_a_body` — no guessing.
4. `test_malformed_utf8_text_fails_honestly_no_fake_body` — failed UTF-8, `404` body, `503` selection.
5. `test_binary_upload_stays_unreadable_and_never_enters_native_path` — no OCR-limit path entered.
6. `test_bodyless_existing_source_missing_body_is_capability_unavailable` — `503`.
7. `test_bodyless_stale_version_is_source_stale_not_missing_body` — `409` wins over body gap.
8. `test_bodyless_stale_content_hash_is_source_stale` — `409`.
9. `test_extracted_source_stale_version_still_409` — real QA N2 case.
10. `test_nonexistent_source_is_reference_invalid` — `422`.
11. `test_revoked_source_is_not_found_404` — revoke unchanged.
12. `test_cross_task_selection_is_reference_invalid_unchanged` — **cross-Task unchanged** on a genuinely extracted (non-seeded) source.
13. `test_oversized_native_text_fails_honestly_no_fake_body` — **bounded no-truncation**.

Frozen error codes used: `reference_invalid` 422, `not_found` 404, `source_stale`
409, `capability_unavailable` 503 — **no new error codes**. The "missing body"
selection error is `capability_unavailable` **503** (the pre-existing stale
version/hash remains `409`); this matches the frozen docs/10 §5 order.

## 4. Public schema unchanged @ 1.12 (verified, no claim beyond)

- No new endpoint, error code, enum, migration direction or request/response
  field was added.
- `record_type`/heading changes live **inside the opaque machine derivative
  file** (local `source_derivative` frontmatter), **not** in the frozen `source`
  top-level fields or the `source.derivatives` entry shape
  `{kind, path, source_version, content_hash, model_version}` — the probe shows
  each derivative entry still has exactly that shape.
- Contract version stays `1.12.0`; docs/08 §6.6.1 and docs/10 are unchanged.

## 5. Test / type evidence (single completed runs, durable logs)

| Command | Result | Log | EXIT |
|---------|--------|-----|------|
| `pytest tests/sources tests/api tests/contracts tests/verify -q` | **358 passed, 1 skipped** | `raw/pytest-FINAL-targeted.log` | **0** |
| `pytest tests/sources -q` | 208 passed, 1 skipped | (superseded by above) | 0 |
| `pytest tests/api -q` | 64 passed | — | 0 |
| `pytest tests/contracts tests/verify tests/startup -q` | 123 passed, 4 skipped | `raw/pytest-contracts-verify-startup.log` | 0 |
| `pytest tests/startup -q` (alone) | 39 passed, 4 skipped | `/tmp/startup-alone.log` | 0 |
| `mypy` (139 source files) | Success | `raw/mypy.log` | **0** |
| probe `probe_r2_after_fix.py` | terminal evidence | `raw/r2-product-path-after.txt` | 0 |

**Honest caveat (test layout, not a product failure):** invoking
`tests/sources … tests/startup` in *one* pytest process fails **collection** with
`ImportError: cannot import name 'make_settings' from 'conftest'`
(`tests/startup` does `from conftest import make_settings`, which the
`tests/sources/lexical/conftest.py` shadows when dirs are mixed). This is a
**pre-existing** test-layout quirk — `tests/startup` alone passes (39 passed) —
and is unrelated to this change. It is the only case that did not run as one
combined invocation; it was run separately with EXIT 0.

No full-backend suite was run (integration runs after F+G, as instructed).

## 6. Old QA seeded-body proof (only where relevant)

QA's `flow_a_real.json` only succeeded after calling `harness/seed_machine.py`
(product `ContentStore.write_machine`) to fabricate a body. That manual seed is
**not** a real user-upload path. The new tests deliberately do **no** seeding:
the machine body is produced by the real upload path itself. The old QA
negative N5 (`reference_invalid` for a bodyless source) is corrected to the
frozen ordering (`capability_unavailable` 503 for a genuinely bodyless existing
source; `source_stale` 409 when the version/hash is stale).

## 7. Mounted-app lifespan HARNESS fix hint (no product patch needed)

The QA `E-QA/harness/launch_app.py` mounts the product app as a **sub-app** of a
wrapper `FastAPI` (`wrapper.mount("/", app)`). Starlette does **not** run a
mounted sub-app's `lifespan`, so the product's real coordinator lifespan never
ran under the harness. **Harness-only fix hint:** serve the product app directly
(`uvicorn.Config(app, …)`) and add the extra evidence routes to `app`, or run the
product lifespan explicitly (`async with app.router.lifespan_context(app):`)
around the fixture routes. Do **not** mount the product under a wrapper when
lifespan-dependent behavior is under test. **No product change is required** —
this repair uses the real lifespan directly (`tests/sources/conftest.py`).

## 8. Remaining issues / honesty

- This is a **same-version QA R1 repair**, not a version PASS. No version QA
  claim is made.
- `tests/startup` cannot be collected in the same pytest invocation as
  `tests/sources` (pre-existing conftest shadowing, see §5); it is green alone.
- The pump is intentionally scoped to native text media; PDF/image still rely on
  the explicit `reprocess` OCR action (unchanged, out of scope).
- Lexical/vector indexing of the newly extracted body is not triggered by the
  pump (`index.lexical` stays `not_indexed`), matching prior intake semantics
  (LG-035 indexing is a separate concern).
- G coordinator work (`backend/lightgravity/coordinator`, `tests/coordinator`,
  API new-G-file) was not touched.

## 9. Commit

Committed files (F backend source + owned test edits + probe; **no** symlinks,
**no** QA/G/main-PM files):

- `backend/lightgravity/sources/content.py`
- `backend/lightgravity/sources/processing.py`
- `backend/lightgravity/sources/selection.py`
- `backend/lightgravity/sources/service.py`
- `tests/sources/test_intake_jobs.py`
- `tests/sources/test_sources_api.py`
- `tests/sources/test_lg047_intake_r1.py`
- `probes/prototype-selected-material-20261016/F-INTAKE-FIX-R1/**` (includes this `REPORT.md`)

Final HEAD SHA and `git status` are recorded at the end of this report.

## 10. Final state (recorded post-commit)

- Worktree: `/home/yhvh/code/lightgravity-bot-worktrees/proto-material-intake-fix-r1-20261016`
- Branch: `fix/proto-material-intake-r1-20261016`
- Base HEAD on entry: `1d7095c`
- **F code commit: `09edad2`** — `fix(lg047-r1): native model-free UTF-8 text intake + frozen selected-source error ordering` (backend source + owned tests + probe + REPORT).
- **HEAD:** a report-only follow-up commit titled `docs(lg047-r1): record final HEAD/status/evidence in REPORT (follow-up)` whose **parent is `09edad2`** (the F code commit). Using the final follow-up SHA here would be self-referential; the authoritative node code commit is `09edad2`.
- `git status`: **clean** (all intended files committed; no symlinks; no QA/G/main-PM files).
- Process stop: prior F writer already gone; only my own session and the untouched G coordinator session (`/home/yhvh/code/lightgravity-bot`) were running.
- Exact tests: `pytest tests/sources tests/api tests/contracts tests/verify` → **358 passed, 1 skipped, EXIT 0**; `mypy` → **139 files, EXIT 0**; probe `probe_r2_after_fix.py` → **EXIT 0**.
