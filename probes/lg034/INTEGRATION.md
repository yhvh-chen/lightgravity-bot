# LG-034 integration hand-off (for the single integration owner)

This package ships the source-intake implementation but **does not edit
`backend/lightgravity/api/app.py`** (owned by LG-012/LG-019).  Assembly in
`api/app.py` must be applied serially by the single integration owner.

## 1. What already exists (verified in this package)

* Package `backend/lightgravity/sources/**` — `SourceStore` (file source of
  truth), `IntakeService` (receive/idempotency/version/cancel/recovery),
  `SourceService` (attribution + read projections).
* Router factory `build_sources_router()` in `backend/lightgravity/api/sources.py`.
* Tests in `tests/sources/**` mount that factory onto a **real** `create_app`
  app and exercise the endpoints over HTTP (21 tests, all green).

The router factory resolves everything from the existing `ApiContext`
(`ctx.store`, `ctx.data_dir`, `ctx.workspace_root`), so wiring needs no new
dependencies and no changes to any owned file other than `api/app.py`.

## 2. Minimal wiring diff (integration owner)

In `backend/lightgravity/api/app.py`:

1. Add the import next to the other router imports:

   ```python
   from .sources import build_sources_router
   ```

2. Mount the router with the other frozen routers (order does not matter; the
   paths are distinct):

   ```python
   app.include_router(build_sources_router(), prefix=API_PREFIX)
   ```

That is the whole change.  No new dependency, no new environment variable, no
change to `backend/lightgravity/contracts/**` or `store/**`.

## 3. What the wiring produces (docs/08 §4.3, LG-034 rows)

| Method + path | Notes |
|---|---|
| `POST /api/v1/sources` | idempotent on `request_id`; persists the original first, then source+job; never creates a Task/Run |
| `GET /api/v1/sources` | scope-filtered list (`task_ref`/`project_ref`/`inbox_ref`), cursor paging |
| `GET /api/v1/sources/{source_id}` | detail; returns `sources/<id>/SOURCE.md`-relative path, never an absolute escape |
| `GET /api/v1/sources/{source_id}/receipt` | per-file receipt projected from the same file state Files/Chat will read |
| `GET /api/v1/intake/jobs/{job_id}` | logical job view over the file SoT (not a second state store) |
| `POST /api/v1/intake/jobs/{job_id}/actions` | `cancel` (confirmed only) / `retry` (never auto-replays interrupted jobs) |
| `POST /api/v1/inbox/messages` | controlled inbox entry; reports `task_created=false`/`run_created=false` |

## 4. Deliberate non-goals (must not be claimed as wired)

* **No extraction / OCR** — that is LG-035.  Jobs stop honestly at
  `received`/`extracting`; a receipt never fabricates body text.
* **No lexical index / search** — that is LG-036.  `index.lexical` stays
  `not_indexed` and the receipt `searchable` stays `false`.
* **No vectors** — `index.vector` stays `disabled` (LG-037).
* **No Chat/Files UI migration** — that is LG-038; the existing
  `POST /files/upload` semantics are unchanged and were not touched.
* **`project_ref` has no registry** — attribution to a project is refused with
  `reference_invalid` until a project registry exists (honest limitation, not a
  hidden capability).  `task_ref` is verified against the authoritative Store.

## 5. Schema/validation notes

* New entities `source` / `intake_job` use the **frozen** docs/08 §6.6 fields.
  They are validated by `sources/store.py` (not `store/entities.py`) because
  the LG-004 store's `ALL_KINDS` is owned by another task; adding these kinds
  there is a separate, optional integration step and is **not required** for
  the endpoints above to work.
* Event types `source.received`, `source.version_changed`,
  `source.indexed`/`source.invalidated` (later tasks), `intake.stage_changed`,
  `intake.failed`, `intake.cancelled` are already frozen in
  `contracts/enums.py`; this package emits `source.received`,
  `source.version_changed`, `intake.stage_changed`, `intake.failed`,
  `intake.cancelled`.
* Error codes used: `source_conflict` (409), `cancellation_unconfirmed` (409),
  `illegal_transition` (409), `path_outside_workspace` (403),
  `reference_invalid`/`validation_failed` (422), `not_found` (404).  All exist
  in `contracts/errors.py` already.

## 6. Integration checklist

- [ ] `app.include_router(build_sources_router(), prefix=API_PREFIX)` added.
- [ ] `uv run mypy` clean.
- [ ] `uv run pytest tests/sources tests/api -q` green.
- [ ] `docs/06`/`docs/08` row for LG-034 "冻结接口（未实现）" updated to
      `已实现` **only after** the router is actually mounted and verified in an
      integrated candidate (single docs08 owner).
