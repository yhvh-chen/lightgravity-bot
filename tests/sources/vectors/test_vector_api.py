"""HTTP tests for the optional vector router (LG-037).

The router is mounted onto a **real** ``create_app`` app (``api/app.py`` is
untouched); the stand-in backend means no network service is contacted.  These
tests pin the verified response contract: status, search with回源 filtering,
honest fallback, POST-only rebuild, and read-only GET.
"""

from __future__ import annotations

from .conftest import make_source, write_formal, write_original_media


async def test_status_reports_configured_backend(api):
    response = await api.get("/api/v1/vector/status")
    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is True
    assert body["backend"]["model"] == "fake-embed-v1"
    assert body["cache"]["exists"] is False


async def test_search_reports_unavailable_when_cache_missing(api):
    response = await api.get("/api/v1/vector/search", params={"q": "alpha"})
    assert response.status_code == 200
    body = response.json()
    assert body["index_status"] == "index_unavailable"
    assert body["index_unavailable_reason"] == "cache_missing"
    assert body["hits"] == []
    assert body["lexical_fallback"] is True


async def test_rebuild_then_search_finds_hit(api, source_store):
    rec = make_source(source_store, source_id="source_http", title="http doc")
    write_formal(source_store, rec.source_id, "alpha beta gamma")
    rebuild = await api.post("/api/v1/vector/rebuild")
    assert rebuild.status_code == 200
    assert rebuild.json()["rebuilt"] is True

    response = await api.get("/api/v1/vector/search", params={"q": "alpha"})
    body = response.json()
    assert body["index_status"] == "ok"
    assert [h["source_id"] for h in body["hits"]] == [rec.source_id]
    assert body["vector_model"] == "fake-embed-v1"


async def test_get_rebuild_is_method_not_allowed(api):
    response = await api.get("/api/v1/vector/rebuild")
    assert response.status_code == 405


async def test_scope_filtering_over_http(api, source_store):
    rec = make_source(
        source_store,
        source_id="source_scoped",
        title="scoped",
        scope={"task_ref": "task_9", "project_ref": None, "inbox_ref": None},
    )
    write_formal(source_store, rec.source_id, "alpha")
    await api.post("/api/v1/vector/rebuild")
    # A global-scope caller does not see task-scoped material.
    global_view = await api.get("/api/v1/vector/search", params={"q": "alpha", "include_global": "true"})
    assert global_view.json()["hits"] == []
    scoped = await api.get("/api/v1/vector/search", params={"q": "alpha", "task_ref": "task_9"})
    assert [h["source_id"] for h in scoped.json()["hits"]] == [rec.source_id]


async def test_media_only_source_is_searchable(api, source_store):
    rec = make_source(
        source_store,
        source_id="source_media",
        title="media",
        original={"path": "original/pic.png", "media_type": "image/png", "bytes": 3, "archived_at": None},
    )
    write_original_media(source_store, rec.source_id, "pic.png", b"\x89PNGdata")
    body = await api.get("/api/v1/vector/search", params={"q": "anything", "rebuild_if_missing": "true"})
    assert body.status_code == 200
    payload = body.json()
    assert payload["index_status"] == "ok"
