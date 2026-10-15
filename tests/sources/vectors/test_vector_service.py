"""Vector service mechanism tests over a real ``SourceStore`` (LG-037).

The stand-in embedder verifies only the *mechanism*: invalidation, scope
filtering, dimension/model switching, delete-and-rebuild, failure downgrade and
media-direct vectors.  It is explicitly **not** a retrieval-quality claim.
"""

from __future__ import annotations

import pytest

from lightgravity.contracts import AppError
from lightgravity.sources.vectors import (
    EmbeddingServiceError,
    VectorSearchRequest,
    VectorSearchService,
)

from .conftest import FAKE_DIM, FakeEmbeddingBackend, make_source, write_formal, write_original_media


def test_index_and_search_text(service, source_store):
    rec = make_source(source_store, source_id="source_t1", title="量子物理")
    sid = rec.source_id
    write_formal(source_store, sid, "量子色动力学描述胶子之间的强相互作用。")
    result = service.index_source(sid)
    assert result["indexed"] is True
    assert result["vector"] == "indexed"
    assert result["dim"] == FAKE_DIM

    record = source_store.read_source(sid)
    assert record.entity["index"]["vector"] == "indexed"
    assert record.entity["index"]["vector_model"] == "fake-embed-v1"


def test_media_vectors_are_media_not_text(service, source_store):
    rec = make_source(
        source_store,
        source_id="source_m1",
        title="image",
        original={"path": "original/pic.png", "media_type": "image/png", "bytes": 3, "archived_at": None},
    )
    sid = rec.source_id
    write_original_media(source_store, sid, "pic.png", b"\x89PNG-bytes")
    # No formal text: only the media is embeddable.
    result = service.index_source(sid)
    assert result["indexed"] is True
    assert result["kinds"] == ["image"]
    entry = service.index.all_entries()[0]
    assert entry.kind == "image"
    # A media vector is never fabricated text.
    assert entry.text == ""


def test_audio_media_embeds_directly(service, source_store):
    rec = make_source(
        source_store,
        source_id="source_a1",
        title="audio",
        original={"path": "original/voice.wav", "media_type": "audio/wav", "bytes": 4, "archived_at": None},
    )
    sid = rec.source_id
    write_original_media(source_store, sid, "voice.wav", b"RIFFdata")
    result = service.index_source(sid)
    assert result["kinds"] == ["audio"]
    entry = service.index.all_entries()[0]
    assert entry.kind == "audio"


def test_no_trusted_body_is_not_indexed(service, source_store):
    rec = make_source(source_store, source_id="source_empty", title="empty")
    result = service.index_source(rec.source_id)
    assert result["indexed"] is False
    assert result["vector"] == "not_indexed"


def test_disabled_backend_reports_disabled(source_store):
    service = VectorSearchService(source_store, backend=FakeEmbeddingBackend(configured=False))
    rec = make_source(source_store, source_id="source_d1", title="d")
    write_formal(source_store, rec.source_id, "some text")
    result = service.index_source(rec.source_id)
    assert result["indexed"] is False
    assert result["vector"] == "disabled"
    record = source_store.read_source(rec.source_id)
    assert record.entity["index"]["vector"] == "disabled"


def test_scope_filter_never_widens(service, source_store):
    rec = make_source(
        source_store,
        source_id="source_s1",
        title="task material",
        scope={"task_ref": "task_1", "project_ref": None, "inbox_ref": None},
    )
    sid = rec.source_id
    write_formal(source_store, sid, "secret task alpha")
    service.index_source(sid)
    # A caller without the task scope gets no hit (filter only narrows).
    result = service.search(VectorSearchRequest(query="source", task_ref=None, include_global=True))
    assert result["index_status"] == "ok"
    assert result["hits"] == []
    skipped = {row["source_id"] for row in result["skipped"]}
    assert sid in skipped
    # The authorized caller does get the hit.
    allowed = service.search(VectorSearchRequest(query="source", task_ref="task_1"))
    assert [h["source_id"] for h in allowed["hits"]] == [sid]


def test_revoked_source_is_stale(service, source_store):
    rec = make_source(source_store, source_id="source_r1", title="rev")
    sid = rec.source_id
    write_formal(source_store, sid, "alpha beta")
    service.index_source(sid)
    record = source_store.read_source(sid)
    source_store.update_source(sid, {"status": "archived"}, expected_revision=record.revision)
    result = service.search(VectorSearchRequest(query="alpha", include_global=True))
    assert result["hits"] == []
    reasons = {row["source_id"]: row["reason"] for row in result["stale"]}
    assert reasons.get(sid) == "source_revoked"


def test_version_change_makes_hit_stale(service, source_store):
    rec = make_source(source_store, source_id="source_v1", title="v")
    sid = rec.source_id
    write_formal(source_store, sid, "alpha")
    service.index_source(sid)
    record = source_store.read_source(sid)
    source_store.update_source(sid, {"source_version": 2}, expected_revision=record.revision)
    result = service.search(VectorSearchRequest(query="alpha", include_global=True))
    assert result["hits"] == []
    assert any(row["reason"] == "source_stale" for row in result["stale"])


def test_delete_and_rebuild_reproduces(service, source_store):
    rec = make_source(source_store, source_id="source_b1", title="b")
    write_formal(source_store, rec.source_id, "alpha beta gamma")
    service.index_source(rec.source_id)
    before = [e.to_dict() for e in service.index.all_entries()]
    service.index.delete()
    rebuilt = service.rebuild()
    assert rebuilt["rebuilt"] is True
    after = [e.to_dict() for e in service.index.all_entries()]
    assert before == after


def test_model_switch_rebuilds_not_mixes(source_store):
    rec = make_source(source_store, source_id="source_ms", title="ms")
    sid = rec.source_id
    write_formal(source_store, sid, "alpha")
    service1 = VectorSearchService(source_store, backend=FakeEmbeddingBackend(model="model-a"))
    service1.index_source(sid)
    assert {e.model for e in service1.index.all_entries()} == {"model-a"}

    service2 = VectorSearchService(source_store, backend=FakeEmbeddingBackend(model="model-b"))
    service2.index_source(sid)
    entries = service2.index.all_entries()
    assert {e.model for e in entries} == {"model-b"}
    assert service2.index.header()["model"] == "model-b"
    # The old-model vector was not retained alongside the new one.
    assert all(e.model == "model-b" for e in entries)


def test_search_model_mismatch_requires_rebuild(service, source_store):
    rec = make_source(source_store, source_id="source_mm", title="mm")
    write_formal(source_store, rec.source_id, "alpha")
    service.index_source(rec.source_id)
    # Swap the backend model without rebuilding: search reports a rebuild need.
    service._backend = FakeEmbeddingBackend(model="other-model")  # noqa: SLF001
    result = service.search(VectorSearchRequest(query="alpha", include_global=True))
    assert result["index_status"] == "index_unavailable"
    assert result["index_unavailable_reason"] == "model_mismatch_rebuild_required"
    assert result["lexical_fallback"] is True


def test_backend_failure_downgrades_honestly(source_store):
    backend = FakeEmbeddingBackend()
    backend.fail_with = EmbeddingServiceError(status=500, message="boom")
    service = VectorSearchService(source_store, backend=backend)
    rec = make_source(source_store, source_id="source_f1", title="f")
    write_formal(source_store, rec.source_id, "alpha")
    with pytest.raises(AppError):
        service.index_source(rec.source_id)
    record = source_store.read_source(rec.source_id)
    assert record.entity["index"]["vector"] == "failed"
    # Search still answers honestly rather than fabricating hits.
    result = service.search(VectorSearchRequest(query="alpha", include_global=True))
    assert result["index_status"] == "index_unavailable"
    assert result["hits"] == []
    assert result["lexical_fallback"] is True


def test_missing_cache_reports_unavailable(service, source_store):
    rec = make_source(source_store, source_id="source_c1", title="c")
    write_formal(source_store, rec.source_id, "alpha")
    result = service.search(VectorSearchRequest(query="alpha", include_global=True))
    assert result["index_status"] == "index_unavailable"
    assert result["index_unavailable_reason"] == "cache_missing"


def test_cache_holds_no_permission_state(service, source_store):
    rec = make_source(
        source_store,
        source_id="source_p1",
        title="p",
        scope={"task_ref": "task_x", "project_ref": None, "inbox_ref": None},
    )
    write_formal(source_store, rec.source_id, "alpha")
    service.index_source(rec.source_id)
    raw = (service.index.path).read_text("utf-8")
    # The cache must not carry the scope/permission vocabulary at all.
    assert "task_x" not in raw
    assert "task_ref" not in raw


def test_empty_query_returns_no_hits(service, source_store):
    rec = make_source(source_store, source_id="source_e2", title="e")
    write_formal(source_store, rec.source_id, "alpha")
    service.index_source(rec.source_id)
    result = service.search(VectorSearchRequest(query="   ", include_global=True))
    assert result["hits"] == []
    assert result["index_status"] == "ok"


def test_remove_invalidates(service, source_store):
    rec = make_source(source_store, source_id="source_rm", title="rm")
    write_formal(source_store, rec.source_id, "alpha")
    service.index_source(rec.source_id)
    service.remove(rec.source_id, reason="deleted")
    assert service.index.entries_for(rec.source_id) == []
    record = source_store.read_source(rec.source_id)
    assert record.entity["index"]["vector"] == "not_indexed"
