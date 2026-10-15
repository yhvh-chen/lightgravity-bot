# LG-036 REPORT — rebuildable lexical index and source verification

## 1. Inputs and base point

* Base commit before work: **`e4cef4a`** (`dev/lg036`, clean at start).
* Dependency correction already recorded by the PM: `depends_on` is
  **LG-033 (done) + LG-034 (done)**; evidence copy at
  `probes/lg036/DEPENDENCY-AUDIT.md` (not modified). LG-035's real OCR quality
  gate is **not** a precondition and is **not** bypassed.
* Frozen interface consumed: `docs/08` §4.3 `GET /api/v1/search` ("冻结接口（未
  实现，向量可选）"), §4.2 `source_stale`/`index_unavailable`, §5.1
  `source.indexed`/`source.invalidated`, §6.6 `index.lexical`/`lexical_hash`.
  Semantics also from `docs/09` §5/§7 and
  `docs/contracts/LG-033-preparation.md` §5.3/§7.3/§7.5/§8.1.
* Reused (read-only) content interfaces delivered by LG-033/LG-034/LG-035:
  `SourceStore`, `SourceRecord`, `ContentStore.read_formal`/
  `read_machine_markdown`/`read_pages`, `SourceService.content_view`,
  `SourceService.edit_formal`, `SourceService.source_actions`.

## 2. Truth query set (real, reproducible)

The tests use a real `create_app` + real `FileStore` + the routers mounted at
`/api/v1`, with the authoritative file SoT under pytest `tmp_path`. Query set and
expected behavior (see `tests/sources/lexical/`):

| Query | Type | Expected |
|---|---|---|
| `"合同编号"` | exact CJK phrase | the one source that contains it |
| `"HT-2024-001"` | identifier | that source |
| `"2026-10-16"` | date | that source |
| `"1,234.56"` | amount | that source |
| `"合同编号 HT-2024-001"` | cross-script phrase | that source |
| `"不存在的编号"` | negative control | no hit (never fabricated) |
| `"编号"` with `task_ref=X` | scope filter | only scope-X sources; global query returns none |

## 3. Architecture (LG-036 owns `sources/lexical/**` + `api/search.py`)

* **Cache = stdlib `sqlite3` FTS5 file** under
  `<data>/sources-index/lexical/lexical.sqlite3`. It is a派生 cache, deleted and
  rebuilt at will; **no separate database service** is started (docs/09 §7).
* **Only trusted text is indexed**: the human `formal/FORMAL.md` when present,
  else a machine derivative whose page-map status is `succeeded`/`partial`.
  Absent/untrusted bodies → honest `not_indexed` (never fabricated).
* **Two-phase search**: FTS `MATCH` produces *candidates* → `query.py`
  re-reads `SOURCE.md`, drops out-of-scope candidates, marks version-changed or
  missing-body candidates `source_stale`, then returns verified hits with the
  *current* `content_hash` and page/line locators.
* **No unique permission/state in the cache**: authorization and version always
  come from the file SoT. `index.lexical`/`lexical_hash` are written to the
  source frontmatter (still file SoT), not only to SQLite.
* **GET is read-only**: `/search` never writes business state, never creates a
  Task/Run, and its scope filter can only narrow, never widen.
* **Tokenizer agreement**: our `tokenize()` is verified against the real FTS5
  `unicode61` tokenizer (`test_tokenize_roundtrips_through_fts5`), so stored
  terms equal query terms; CJK is split per-ideograph before indexing so exact
  CJK phrase queries work (raw `unicode61` would group CJK runs).

## 4. Commands and results (real)

```
uv run mypy                         -> Success: no issues found in 129 source files
uv run pytest tests/sources/lexical -q -> 25 passed
uv run pytest tests/sources -q      -> 63 passed
uv run pytest tests/sources tests/api tests/contracts -q -> 133 passed
uv run pytest -q                    -> 669 passed, 4 skipped
```

Real product-path smoke (real app + mounted routers over HTTP): search returned a
verified hit and wrote `source.indexed` into the real event log (see
`STATUS.md`).

## 5. Acceptance-condition mapping

| LG-036 acceptance condition | Where verified |
|---|---|
| Derived index from files/metadata/formal content | `test_index_service.py::test_formal_wins_over_machine_and_writes_index_state`; `test_index.py` |
| Exact phrase / identifier / date / amount | `test_search_api.py::test_search_exact_phrase_number_date_amount`; `test_index.py::test_exact_queries_hit` |
| Authorized-scope filtering | `test_search_api.py::test_scope_authorization_filter` |
| Hit 回源核对 existence/permission/version/hash | `query.authorize_and_verify`; `test_search_api.py::test_content_change_invalidates_old_hit`; `test_index_service.py::test_moved_source_invalidates_hit` |
| Old hits invalid after edit/revoke/delete/move | `test_search_api.py::test_content_change_invalidates_old_hit`, `test_revoke_and_delete_invalidate_hits`; `test_index_service.py::test_moved_source_invalidates_hit` |
| Delete cache → rebuild → reproduce query | `test_search_api.py::test_delete_cache_rebuilds_and_reproduces`; `test_index_service.py::test_rebuild_reproduces_lexical_hash` |
| Corrupt / unavailable state reported honestly | `test_index.py::test_corrupt_cache_is_reported_not_silently_empty`; `test_search_api.py::test_corrupt_cache_reports_index_unavailable`; `test_index_service.py::test_rebuild_of_corrupt_cache_recovers` |
| No separate DB service | stdlib `sqlite3` FTS5 only; no service started |
| No cross-Task content without authorization | `test_scope_authorization_filter`; cache stores no permission |
| `not_indexed` for no/untrusted body | `test_search_api.py::test_not_indexed_when_no_trusted_body`; `test_index_service.py::test_index_source_without_trusted_body_is_not_indexed` |
| Concurrency | `test_index_service.py::test_concurrent_index_writes_stay_consistent` |
| GET does not widen business write authorization | `test_search_api.py::test_search_get_does_not_create_or_modify_state` |

## 6. Real-substitution boundary

* Real: HTTP routing, `FileStore`, source frontmatter, formal/machine content
  files, event log, SQLite FTS5, rebuild from files.
* Substituted (only where a live backend is unavailable): the machine
  derivative in tests is written directly via `ContentStore.write_machine`
  instead of a live OCR call. This exercises the lexical path with a *real*
  structured machine body; it is **not** an OCR-quality claim and does not
  replace LG-035's quality gate.
* Not done: no live OCR, no embedding, no vector path (LG-037), no browser UI
  (LG-038), no Chinese/image retrieval quality assertion.

## 7. Unknown / out-of-scope

* Whether Google-style model embeddings would improve recall: not measured
  (vectors are optional, LG-037).
* Office/email/folder-crawl sources: not in scope.
* Docs status rows and `api/app.py` mount: owned by other writers (see
  `INTEGRATION.md`).
