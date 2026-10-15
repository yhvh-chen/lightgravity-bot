# LG-035 integration hand-off (for the single integration owner)

This package implements image/PDF OCR **inside the already-owned source files**
and adds API routes **inside `backend/lightgravity/api/sources.py`** (this
package is the sole owner of that file).  It does **not** edit
`backend/lightgravity/api/app.py`, `frontend/**`, `coordinator/**`,
`store/**` or `contracts/**`.

## 1. Wiring status — already live, no new `app.py` change

The sources router is already mounted by the integration owner
(`app.include_router(build_sources_router(), prefix=API_PREFIX)`).  Because the
new endpoints are registered by the same factory, they are **already reachable
in the default app**.  Verified against a real `create_app()`:

```
/api/v1/sources/{source_id}/content
/api/v1/sources/{source_id}/download
/api/v1/sources/{source_id}/actions
/api/v1/sources/{source_id}/formal
```

So there is **no additional `api/app.py` diff** required for this task.

## 2. Dependency addition (this package owns it)

* `pyproject.toml`: `pypdfium2>=5,<6`; `uv.lock` updated.
* License proven permissive (BSD-3-Clause + Apache-2.0 + permissive bundled
  deps; no GPL/AGPL).  It is a self-contained wheel, so no `poppler` system
  package is required at product runtime.  It is imported **lazily** and only
  when a PDF is actually OCRed.
* No `Pillow` dependency was added: PNG encoding uses the standard library.
* New optional environment variables (no secrets logged, no LAN default):
  `LIGHTGRAVITY_OCR_BASE_URL`, `LIGHTGRAVITY_OCR_MODEL`,
  `LIGHTGRAVITY_OCR_TOKEN`, `LIGHTGRAVITY_OCR_TIMEOUT_SECONDS`,
  `LIGHTGRAVITY_OCR_COLD_TIMEOUT_SECONDS`, `LIGHTGRAVITY_OCR_MAX_TOKENS`.
  With none set, OCR stays an explicit `capability_unavailable` failure.

## 3. Frozen-contract deltas

* **No new error codes, events or enums were invented.** Only frozen codes are
  used (`capability_unavailable`, `not_found`, `validation_failed`,
  `cancellation_unconfirmed`, `revision_conflict`, `path_outside_workspace`).
* Events emitted: `source.attributed` on successful/partial extraction and
  `intake.failed` on failure (both already frozen in `contracts/enums.py`).
* Endpoint paths match docs/08 §4.3 exactly for LG-035/036 rows
  (`/content`, `/download`, `/actions`).  The extra `POST
  /sources/{id}/formal` is a **minimal controlled formal-version write**; if the
  integration owner prefers a different shape, only `api/sources.py` +
  `service.edit_formal` change.  This is an additive proposal, not a frozen row.
* `source.status` uses only the frozen display enum
  (`extracted`/`partial`/`failed`/`archived`); it never enters the Task `phase`
  enum.

## 4. Store/schema note

`source.derivatives[]` entries use the frozen
`{kind, path, source_version, content_hash, model_version}` shape.  Machine
versions live under `sources/<id>/derivative/`; the human version under
`sources/<id>/formal/FORMAL.md` — a **separate directory**, which is what makes
`reprocess` non-destructive.  No change to `store/entities.py` is required.

## 5. Integration checklist

- [x] New endpoints reachable through the existing router mount.
- [x] `uv run mypy` clean (122 files).
- [x] `uv run pytest tests/sources tests/api tests/contracts -q` green.
- [x] Full suite green (585 passed, 4 skipped).
- [ ] docs/08 §4.3 LG-035/036 rows updated from "冻结接口（未实现）" to
      "已实现" — **only the single docs08 owner** should do this, after
      LG-036 lands, so the row reflects the whole line.
