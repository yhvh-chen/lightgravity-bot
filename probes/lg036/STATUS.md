# LG-036 STATUS — rebuildable lexical index + source-of-truth verification

* Branch: `dev/lg036` (persistent worktree). Base before work: `e4cef4a`.
* Task file: `backlog/tasks/LG-036.md`.
* Status: **in-progress** (implementation complete within scope; the shared
  `api/app.py` wiring is handed to the single integration owner per
  `INTEGRATION.md`, so the endpoint is not yet assembled in the default app).
* Product model / external OCR / embedding calls: **0**.
* Independent/version QA: belongs to **LG-040** — not claimed here.
* Pushed / deployed / released: **no**.

## What was delivered

| Area | File(s) |
|---|---|
| Rebuildable FTS5 cache (stdlib sqlite, no DB service) | `backend/lightgravity/sources/lexical/index.py` |
| Query parsing + authorization + 回源核对 | `backend/lightgravity/sources/lexical/query.py` |
| Search service (build/rebuild/index/remove/search) | `backend/lightgravity/sources/lexical/service.py` |
| Package exports | `backend/lightgravity/sources/lexical/__init__.py` |
| `GET /api/v1/search` router factory | `backend/lightgravity/api/search.py` |
| Minimal index hooks (formal edit / revoke / delete) | `backend/lightgravity/sources/service.py` |
| Exports | `backend/lightgravity/sources/__init__.py` |
| Tests (real HTTP + file SoT) | `tests/sources/lexical/**` (25 tests) |

## Local checks actually run (real output)

* `uv run mypy` → **Success: no issues found in 129 source files**.
* `uv run pytest tests/sources/lexical -q` → **25 passed**.
* `uv run pytest tests/sources -q` → **63 passed**.
* `uv run pytest tests/sources tests/api tests/contracts -q` → **133 passed**.
* `uv run pytest -q` (full) → **669 passed, 4 skipped**.
* Real product-path smoke (real `create_app` + FileStore + mounted routers over
  HTTP): `GET /api/v1/search` returned a verified hit with the current
  `content_hash` and machine page locator; `source.indexed` was written to the
  real `events/<source_id>/events.jsonl`.

## Honest boundaries / not claimed

* **Image/PDF retrieval quality is NOT claimed.** Only *trusted* bodies are
  indexed (human formal version, or a machine derivative whose page map status
  is `succeeded`/`partial`). A source with no trusted body is honestly
  `not_indexed`; no synthetic/English sample is presented as Chinese OCR or
  image-retrieval quality (docs/09 §9). LG-035's real Chinese/table quality gate
  is untouched and remains blocked; LG-040's gate is not lowered.
* **No vector work.** `index.vector` stays `disabled` (LG-037).
* `GET /api/v1/search` is implemented but **not yet mounted in `api/app.py`**,
  which this task must not edit. Wiring is handed to the integration owner
  (`INTEGRATION.md`). Until then the endpoint is not reachable in the default app
  and this task stays `in-progress`.
* `docs/08` §4.3 status row for `/search` and the §5.1 note that
  `source.indexed`/`source.invalidated` are now actually produced are **contract
  docs owned by the docs08 single writer**; the exact wording change is proposed
  in `INTEGRATION.md`, not applied here.

## Integration gap (why not done)

* `backend/lightgravity/api/app.py` (owner: integration) needs the one-line
  `app.include_router(build_search_router(), prefix=API_PREFIX)` mount.
* `docs/08-interface-contract.md` (owner: docs08 single writer) needs the §4.3
  `/search` row and §5.1 note updated to "已实现（待版本 QA LG-040）" after the
  mount is verified in an integrated candidate.
