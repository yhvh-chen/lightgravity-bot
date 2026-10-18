"""Vector service mechanism tests over a real ``SourceStore`` (LG-037).

The stand-in embedder verifies only the *mechanism*: invalidation, scope
filtering, dimension/model switching, delete-and-rebuild, failure downgrade and
media-direct vectors.  It is explicitly **not** a retrieval-quality claim.
"""

from __future__ import annotations

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


def test_model_switch_per_source_fails_closed_and_preserves_corpus(source_store):
    rec_a = make_source(source_store, source_id="source_ms_a", title="a")
    rec_b = make_source(source_store, source_id="source_ms_b", title="b")
    write_formal(source_store, rec_a.source_id, "alpha")
    write_formal(source_store, rec_b.source_id, "beta")
    service1 = VectorSearchService(source_store, backend=FakeEmbeddingBackend(model="model-a"))
    service1.index_source(rec_a.source_id)
    assert {e.model for e in service1.index.all_entries()} == {"model-a"}

    # A per-source index under a different configured model must not clear or
    # mix the old corpus; only an explicit rebuild may replace it.
    service2 = VectorSearchService(source_store, backend=FakeEmbeddingBackend(model="model-b"))
    result = service2.index_source(rec_b.source_id)
    assert result["indexed"] is False
    assert result["vector"] == "failed"
    assert result["reason"] == "model_mismatch_rebuild_required"
    assert result["failed_kinds"] == ["text"]
    entries = service2.index.all_entries()
    assert {e.source_id for e in entries} == {rec_a.source_id}
    assert {e.model for e in entries} == {"model-a"}
    assert service2.index.header()["model"] == "model-a"
    assert source_store.read_source(rec_b.source_id).entity["index"]["vector"] == "failed"

    # The explicit rebuild is the only path that replaces the old corpus.
    rebuilt = service2.rebuild()
    assert rebuilt["rebuilt"] is True
    assert {e.model for e in service2.index.all_entries()} == {"model-b"}


def test_missing_cache_is_initialized_with_current_source_only(source_store):
    service = VectorSearchService(source_store, backend=FakeEmbeddingBackend())
    rec_a = make_source(source_store, source_id="source_new_a", title="a")
    rec_b = make_source(source_store, source_id="source_new_b", title="b")
    write_formal(source_store, rec_a.source_id, "alpha")
    write_formal(source_store, rec_b.source_id, "beta")
    service.index_source(rec_a.source_id)
    assert {e.source_id for e in service.index.all_entries()} == {rec_a.source_id}
    service.index_source(rec_b.source_id)
    assert {e.source_id for e in service.index.all_entries()} == {
        rec_a.source_id,
        rec_b.source_id,
    }


def test_corrupt_cache_is_preserved_and_never_rebuilt_implicitly(source_store):
    service = VectorSearchService(source_store, backend=FakeEmbeddingBackend())
    rec_a = make_source(source_store, source_id="source_corrupt_a", title="a")
    rec_b = make_source(source_store, source_id="source_corrupt_b", title="b")
    write_formal(source_store, rec_a.source_id, "alpha")
    write_formal(source_store, rec_b.source_id, "beta")
    service.index_source(rec_a.source_id)
    service.index.path.write_bytes(b"not a vector cache\n")
    before = service.index.path.read_bytes()

    result = service.index_source(rec_b.source_id)
    assert result["indexed"] is False
    assert result["vector"] == "failed"
    assert result["reason"] == "cache_corrupt_rebuild_required"
    assert service.index.path.read_bytes() == before


def test_partial_kind_failure_keeps_successful_media(source_store):
    backend = FakeEmbeddingBackend()
    backend.fail_part_types = {"image"}
    service = VectorSearchService(source_store, backend=backend)
    rec = make_source(
        source_store,
        source_id="source_partial",
        title="image with text",
        original={"path": "original/pic.png", "media_type": "image/png", "bytes": 3, "archived_at": None},
    )
    write_original_media(source_store, rec.source_id, "pic.png", b"\x89PNGdata")
    write_formal(source_store, rec.source_id, "trusted text body")

    result = service.index_source(rec.source_id)
    assert result["indexed"] is True
    assert result["vector"] == "indexed"
    assert result["reason"] == "partial_index"
    assert result["kinds"] == ["text"]
    assert result["failed_kinds"] == ["image"]
    # The successful text vector survives the independent media failure.
    assert [(e.source_id, e.kind) for e in service.index.all_entries()] == [
        (rec.source_id, "text")
    ]
    assert source_store.read_source(rec.source_id).entity["index"]["vector"] == "indexed"


def test_all_kind_failure_reports_failed_without_fabricating_vectors(source_store):
    backend = FakeEmbeddingBackend()
    backend.fail_part_types = {"audio"}
    service = VectorSearchService(source_store, backend=backend)
    rec = make_source(
        source_store,
        source_id="source_audio_fail",
        title="audio",
        original={"path": "original/voice.wav", "media_type": "audio/wav", "bytes": 4, "archived_at": None},
    )
    write_original_media(source_store, rec.source_id, "voice.wav", b"RIFFdata")
    result = service.index_source(rec.source_id)
    assert result["indexed"] is False
    assert result["vector"] == "failed"
    assert result["kinds"] == []
    assert result["failed_kinds"] == ["audio"]
    assert service.index.all_entries() == []
    assert source_store.read_source(rec.source_id).entity["index"]["vector"] == "failed"


def test_index_result_has_frozen_seam_fields(service, source_store):
    rec = make_source(source_store, source_id="source_shape", title="shape")
    write_formal(source_store, rec.source_id, "alpha")
    result = service.index_source(rec.source_id)
    for key in ("source_id", "indexed", "vector", "reason", "model", "kinds", "failed_kinds"):
        assert key in result
    assert result["model"] == "fake-embed-v1"


def test_search_hits_carry_kind_and_reverify_hash(service, source_store):
    rec = make_source(
        source_store,
        source_id="source_kind",
        title="image",
        original={"path": "original/pic.png", "media_type": "image/png", "bytes": 3, "archived_at": None},
    )
    write_original_media(source_store, rec.source_id, "pic.png", b"\x89PNGkind")
    service.index_source(rec.source_id)
    found = service.search(VectorSearchRequest(query="image", include_global=True))
    assert found["index_status"] == "ok"
    assert found["hits"][0]["kind"] == "image"

    # Changing only the source content hash (same version) must also invalidate
    # the cached hit during回源 re-verification.
    record = source_store.read_source(rec.source_id)
    source_store.update_source(
        rec.source_id,
        {"content_hash": "f" * 64},
        expected_revision=record.revision,
    )
    stale = service.search(VectorSearchRequest(query="image", include_global=True))
    assert stale["hits"] == []
    assert any(row["reason"] == "source_stale" for row in stale["stale"])


def test_search_without_rebuild_does_not_create_a_cache(service, source_store):
    rec = make_source(source_store, source_id="source_ro", title="ro")
    write_formal(source_store, rec.source_id, "alpha")
    assert service.index.exists() is False
    result = service.search(VectorSearchRequest(query="alpha", include_global=True))
    assert result["index_unavailable_reason"] == "cache_missing"
    assert service.index.exists() is False


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
    result = service.index_source(rec.source_id)
    assert result["indexed"] is False
    assert result["vector"] == "failed"
    assert result["failed_kinds"] == ["text"]
    record = source_store.read_source(rec.source_id)
    assert record.entity["index"]["vector"] == "failed"
    # Search still answers honestly rather than fabricating hits.
    empty = service.search(VectorSearchRequest(query="alpha", include_global=True))
    assert empty["index_status"] == "index_unavailable"
    assert empty["hits"] == []
    assert empty["lexical_fallback"] is True


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


def test_dimension_change_per_source_fails_closed_and_preserves_corpus(source_store):
    rec_a = make_source(source_store, source_id="source_dim_a", title="a")
    rec_b = make_source(source_store, source_id="source_dim_b", title="b")
    write_formal(source_store, rec_a.source_id, "alpha")
    write_formal(source_store, rec_b.source_id, "beta")
    service1 = VectorSearchService(source_store, backend=FakeEmbeddingBackend(dim=8))
    service1.index_source(rec_a.source_id)

    service2 = VectorSearchService(source_store, backend=FakeEmbeddingBackend(dim=4))
    result = service2.index_source(rec_b.source_id)
    assert result["indexed"] is False
    assert result["reason"] == "model_mismatch_rebuild_required"
    assert {e.source_id for e in service2.index.all_entries()} == {rec_a.source_id}
    assert {e.dim for e in service2.index.all_entries()} == {8}


def test_cancel_check_before_first_input_does_not_call_backend(source_store):
    class NoCalls(FakeEmbeddingBackend):
        def embed(self, item):
            raise AssertionError("cancelled input must not reach backend")

    service = VectorSearchService(source_store, backend=NoCalls())
    rec = make_source(source_store, source_id="source_cancel_before", title="cancel")
    write_formal(source_store, rec.source_id, "trusted body")
    result = service.index_source(rec.source_id, cancel_check=lambda: True)
    assert result["indexed"] is False
    assert result["reason"] == "interrupted"
    assert result["kinds"] == []
    assert result["failed_kinds"] == ["text"]
    assert service.index.entries_for(rec.source_id) == []
