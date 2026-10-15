# LG-036 integration hand-off (for the single integration owner)

This package ships `GET /api/v1/search` and the rebuildable lexical cache but
**does not edit `backend/lightgravity/api/app.py`** (owned by the integration
writer). The contract docs (`docs/08`) are owned by the docs08 single writer.

## 1. What already exists (verified in this package)

* `backend/lightgravity/sources/lexical/**` — `LexicalIndex` (stdlib-sqlite
  FTS5 cache), `parse_query`/`authorize_and_verify` (query + 回源核对),
  `LexicalSearchService` (build/rebuild/index/remove/search).
* `backend/lightgravity/api/search.py` — `build_search_router()`.
* Minimal hooks in `sources/service.py`: `edit_formal` re-indexes; `revoke`/
  `delete` invalidate old hits; `SourceService.search(...)` delegates.
* Tests `tests/sources/lexical/**` (25) mount `build_search_router()` onto a
  **real** `create_app` app and exercise `/search` over HTTP.

The router factory resolves everything from the existing `ApiContext`
(`ctx.store`, `ctx.data_dir`), so wiring needs no new dependency and no changes
to any owned file other than `api/app.py`.

## 2. Minimal wiring diff (integration owner)

In `backend/lightgravity/api/app.py`:

1. Add the import next to the other router imports:

   ```python
   from .search import build_search_router
   ```

2. Mount the router with the other frozen routers:

   ```python
   app.include_router(build_search_router(), prefix=API_PREFIX)
   ```

That is the whole change. No new dependency, no new environment variable, no
change to `backend/lightgravity/contracts/**` or `store/**`.

## 3. What the wiring produces (docs/08 §4.3, LG-036 row)

| Method + path | Notes |
|---|---|
| `GET /api/v1/search?q=&task_ref=&project_ref=&inbox_ref=&include_global=&limit=&rebuild_if_missing=` | lexical-first search; each hit is re-verified回源 (existence/hash/version/scope). Missing scope ⇒ only global material. Corrupt/missing cache ⇒ `index_status=index_unavailable` (HTTP 200 body state; endpoint may also surface 503) and empty hits — never a dangling result. |

Response body (additive, non-authoritative projection):

```json
{
  "query": "\"HT-2024-001\"",
  "kind": ["phrase"],
  "hits": [
    {
      "source_id": "source_01J...",
      "source_version": 1,
      "content_hash": "…64 hex…",
      "basis": "formal",
      "scope": {"task_ref": null, "project_ref": null, "inbox_ref": null},
      "title": "…",
      "locators": [{"layer": "formal", "path": "formal/FORMAL.md"}],
      "snippet": "…",
      "verified": true,
      "stale": false,
      "reason": null
    }
  ],
  "stale": [{"source_id": "…", "cached_version": 1, "current_version": 2, "reason": "source_stale"}],
  "skipped": [{"source_id": "…", "reason": "out_of_scope"}],
  "index_status": "ok",
  "authorized_scope": {"task_ref": null, "project_ref": null, "inbox_ref": null, "include_global": true}
}
```

`source_id` values match the `/sources/{source_id}` endpoints; `content_hash` is
the current cryptographic hash (not a stat token). Reviewer note: this response
shape is a **new, additively-frozen endpoint**; the exact field names above are
this package's implementation of the §4.3 minimal semantics ("返回候选 + 来源
证据引用；命中必须回源核对"). If the docs08 owner wants a different field
spelling, that is a contract change to register serially — do not silently
diverge.

## 4. Deliberate non-goals (must not be claimed as wired)

* **No vectors** — `index.vector` stays `disabled` (LG-037).
* **No OCR quality claim** — only trusted bodies are indexed; untrusted/absent
  bodies are `not_indexed` (LG-035 quality gate untouched, LG-040 gate intact).
* **No Chat/Files UI migration** — that is LG-038.
* `sources/lexical/**` is an independent module; it does **not** import or
  modify `ocr/`, `processing/`, `content/`, `intake/`, `coreStore`, coordinator,
  adapter or settings.

## 5. Schema/validation notes

* `index.lexical` ∈ `not_indexed|indexed|stale|failed` and `lexical_hash` are the
  **already frozen** §6.6 fields; LG-036 only writes them. The cache itself adds
  no wire schema.
* Event types `source.indexed` / `source.invalidated` are already frozen in
  `contracts/enums.py`; this package now actually emits them (via the injected
  event sink). `source.deleted` is **not** emitted (the entity is removed; a
  `source.invalidated` with `reason=deleted` is emitted instead) — the docs08
  owner may want to note this in §5.1.
* Error codes used: `index_unavailable` (503) and `source_stale` (409) — both
  already exist in `contracts/errors.py`. `/search` itself returns the honest
  `index_status` state in the body for missing/unreadable caches; a stricter 503
  envelope is available if the docs08 owner prefers it.

## 6. Proposed contract-doc updates (owner: docs08 single writer)

* §4.3 `GET /api/v1/search` status: `冻结接口（未实现，向量可选）` →
  `已实现（待版本 QA LG-040）` **after** the mount is verified in an integrated
  candidate.
* §5.1 note: `source.indexed`/`source.invalidated` are now **actually produced**
  by LG-036 (leave `source.deleted`/`intake.receipt` for later tasks).
* §6.6: no field change.

## 7. Integration checklist

- [ ] `app.include_router(build_search_router(), prefix=API_PREFIX)` added.
- [ ] `uv run mypy` clean.
- [ ] `uv run pytest tests/sources tests/api -q` green.
- [ ] `docs/08` §4.3 `/search` row updated only after the mount is verified.
