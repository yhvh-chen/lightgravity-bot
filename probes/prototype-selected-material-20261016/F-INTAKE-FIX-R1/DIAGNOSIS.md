# F-INTAKE-FIX-R1 — LG-047 QA-triggered BACKEND R1 diagnosis + repair

**Owner:** backend R1 repair executor (NOT the LG-047 independent QA; NOT any
A/B/C/D author). **Type:** diagnosis + minimal product repair. **This is NOT a
version PASS claim.**

- Base worktree: `/home/yhvh/code/lightgravity-bot-worktrees/proto-material-intake-fix-r1-20261016`
- Branch: `fix/proto-material-intake-r1-20261016`
- Base commit: `1d7095c` (main); product tree byte-identical to candidate
  `f7a32ac` (`git diff --stat f7a32ac -- backend frontend tests examples` →
  empty except `docs/11` which is PM-owned on main).
- QA evidence read READ-ONLY from `/tmp/lg047-qa/**` and the active QA
  worktree `proto-material-qa-20261016` (never modified). The active QA
  worktree/branch/ledger were not touched.
- No model/upstream calls, no dependency installs, no browser, no port 8123,
  no push. All probes are isolated tmp unit/API-level with zero external calls.

## 0. Raw QA symptom (from E evidence, READ-ONLY)

`/tmp/lg047-qa/flow_a_prep.json`:

- `upload_alpha.status = 201`; `source.status = "received"`,
  `derivatives = []`, `index.lexical = "not_indexed"`.
- `job.status = "queued"`, `stage = "received"`.
- receipt `detail = "original persisted; extraction not started (LG-035)"`,
  `error_code = null`, `searchable = false`.
- `source_content` → **404** `not_found` "no machine content exists".
- `flow_negative.json` N2 (stale) and N5 (no readable body) both return
  **422** `reference_invalid` "does not resolve" instead of the docs/11-expected
  `source_stale` (409) / `not_found`|`capability_unavailable` (404/503).

E harness had to call `harness/seed_machine.py` (product `ContentStore.write_machine`)
to materialize a body before `flow_a_real.json` could read content / select.
A manually seeded derivative is **not** a real user-upload main path.

## Round 1 — reproduce the exact product path (0 external calls)

Probe: `probes/prototype-selected-material-20261016/F-INTAKE-FIX-R1/probe_r1_product_path.py`
Raw: `raw/r1-product-path.txt`.

Real `build_source_service` + real inline upload of a `text/plain` body:

```
status: received | derivatives: []
content_digest: 14b2a088...
content_view ERROR: not_found | no machine content exists for source '...'
selection_layer: None
process_source: {'status': 'failed', ..., 'reason': 'unsupported media type for OCR: text/plain'}
content_view after process ERROR: not_found | no machine content exists for '...'
```

**Finding 1 (confirmed):** with the real product source service, a `text/plain`
upload produces **no readable body**; the only extraction path (OCR,
`POST /sources/{id}/actions {reprocess}`) **refuses text/plain** as
`unsupported media type for OCR`. No model/network was involved.

## Round 2 — (a) is the QA harness running the real product lifespan?

The E harness `probes/.../E-QA/harness/launch_app.py` builds the real runtime via
`lightgravity.api.bootstrap.build_runtime(...)`, then wraps it:

```python
wrapper = FastAPI(routes=[...])
wrapper.mount("/", app)          # <-- product app mounted as a SUB-app
uvicorn.Config(wrapper, ...)
```

Empirical probe (`round-2`, below): Starlette does **not** run a mounted
sub-app's `lifespan` when the parent app is served. The product's lifespan is
`resolved_coordinator.start()` / `await resolved_coordinator.stop()` — the
resident coordinator background worker.

```
$ python - <<'PY'   (FastAPI 0.11x / starlette 0.46.2, TestClient)
sub = FastAPI(lifespan=...appends events...); sub.get("/sub")
outer = FastAPI(); outer.mount("/", sub)
with TestClient(outer): assert GET /sub == 200
print(events)  # -> []
PY
events: []
```

**Finding 2 (harness defect, no product patch):** the E harness serves the
product as a mounted sub-app, so the real product **lifespan never runs**.
*Exact launch fix hint (for the harness owner, not a product change):* serve the
product app directly, e.g. `uvicorn.Config(app, ...)` with the extra evidence
routes added to `app` (or run the product app's lifespan explicitly via
`async with app.router.lifespan_context(app):` around the fixture routes). Do not
mount the product under a wrapper if lifespan-dependent behavior is under test.

**Scope note:** this harness defect does **not** explain the body-less source.
Selected-source resolution and `GET /sources/{id}/content` are synchronous read
paths independent of the coordinator worker; Finding 1 holds even with the real
lifespan running (confirmed by the direct unit probe, which constructs the
service without any lifespan at all).

## Round 3 — (b)/(d) bootstrap / CLI source-service wiring

Code read (`backend/lightgravity/api/app.py`, `api/bootstrap.py`):

- `create_app` defines `_source_service_provider()` which lazily builds one
  `build_source_service(data_dir=resolved.data_dir, task_store=broadcasting,
  resolve_path=..., events=broadcasting)` and calls
  `resolved_coordinator.set_source_service_provider(_source_service_provider)`.
- `build_runtime` (real CLI `lightgravity start` **and** the E harness) passes
  `dispatcher=` (not `coordinator=`), so `create_app` constructs the coordinator
  and attaches that provider.

**Finding 3 (d is NOT present on the real path):** the shared `SourceService`
**is** wired to the coordinator in the real CLI/bootstrap assembly (and the
sources router uses the same `app.state.source_service`). There is **no**
duplicate source-of-truth on the real path. QA's `reference_invalid` is **not**
caused by a missing shared service or a data-root mismatch: the referenced
sources exist on disk in the isolated data dir.

**Finding 4 (b, partial):** there is **no extraction pump at all**. `IntakeService.receive`
persists the original and stops at `received`; `SourceService.receive_*` never
invokes `processing`; the only trigger is the explicit `reprocess` action
(`SourceService.source_actions`). The lifecycle documented in docs/09
(`received → processing → extracted`) is never advanced automatically. This is
the "real assembly doesn't attach a SourceProcessor/extraction pump" gap — but
the *minimum* needed for the prototype is that the upload path produce a
readable body, not a general background pump.

## Round 4 — (c) is native text extraction actually absent?

The processing path (`sources/processing.py`) supports **PDF + raster images**
only:

```python
IMAGE_MEDIA_TYPES = ("image/png","image/jpeg","image/webp","image/gif","image/bmp")
def can_process(self, media_type, data):
    if is_pdf_bytes(data): return True
    return _normalize_media_type(media_type) in IMAGE_MEDIA_TYPES
```

`text/plain` / `text/markdown` are not in the set, and there is no native UTF-8
branch anywhere in `processing.py`. `_finish_unprocessable(...)` marks the source
`status="failed"` with `reason="unsupported media type for OCR: text/plain"`.

**Finding 5 (root cause, product defect — confirmed):** native, model-free
UTF-8 text extraction is **actually absent**. Every fixture in the prototype is
plain UTF-8 text (docs/11 §5), and docs/11 Flow A A1/A3 require that upload leads
to a selectable body and that `GET /sources/{id}/content?kind=auto` serves it.
The product cannot satisfy its own documented prototype flow for its own
plain-text fixtures. This is a genuine product defect, not a QA-harness artifact.

## Round 5 — candidate decision

**Product defect confirmed → fix minimally (this task).**

Candidate (minimal, bounded, model-free):

1. **Native deterministic extraction** for `text/plain` and `text/markdown`
   in `ProcessingEngine`: decode UTF-8 (bounded), write the *existing* machine
   derivative via `ContentStore.write_machine` / `MachineDraft` with
   `extractor="native-utf8-text"`, `model="none"` (no LLM, no OCR, no network).
   Reject non-UTF-8 with an honest failure (never a fabricated body). Do **not**
   touch PDF/image/OCR/vector behavior.
2. **Minimal pump** on the real upload path: after a successful receive, run the
   extraction **only for native text media**, synchronously, so the receipt
   reaches a terminal state with a readable body. Leave PDF/image at `received`
   for the existing explicit `reprocess` (OCR) path — unchanged.

Explicit non-goals (honoring the brief): no OCR change, no Office/PDF-reader/
generic-reader framework, no new prompts/planner/API fields, no new error codes,
no background worker, no vector change.

Negative-case ordering (Finding from Round 3): for a source with **no** body,
`resolve_selected_sources` hits the `selection_layer() is None` →
`reference_invalid` branch **before** the stale version/hash check. After the
fix a native-text upload has a body, so:
- real stale version/hash → `source_stale` (409) as docs/11 expects;
- cross-Task / revoked → unchanged;
- a genuinely body-less source (e.g. unsupported binary) still fails
  `reference_invalid` (honest, not a fabricated success).

(continued in REPORT.md §Fix & Evidence)
