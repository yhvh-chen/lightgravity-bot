"""Scoped rebuild regressions using real files and a deterministic local backend.

These check cache/metadata preservation, never embedding retrieval quality.
"""

from __future__ import annotations

import json

import pytest

from lightgravity.sources.content import ContentStore
from lightgravity.sources.vectors import (
    EmbeddingServiceError,
    EmbeddingTimeout,
    EmbeddingUnavailable,
    VectorSearchRequest,
    VectorSearchService,
)

from .conftest import FakeEmbeddingBackend, make_source, write_formal, write_original_media


def seed_corpus(source_store, backend):
    service = VectorSearchService(source_store, backend=backend)
    target = make_source(source_store, source_id="scoped-target", title="target")
    other = make_source(
        source_store,
        source_id="scoped-other",
        title="other",
        scope={"task_ref": "task_private", "project_ref": None, "inbox_ref": None},
    )
    write_formal(source_store, target.source_id, "target original text")
    write_formal(source_store, other.source_id, "other retained text")
    assert service.index_source(target.source_id)["indexed"]
    assert service.index_source(other.source_id)["indexed"]
    return service, target.source_id, other.source_id


def test_scoped_success_preserves_other_entries_metadata_and_scope(source_store, backend):
    service, target, other = seed_corpus(source_store, backend)
    other_entries = service.index.entries_for(other)
    other_record = source_store.read_source(other)
    calls = backend.calls
    write_formal(source_store, target, "target replacement text")

    result = service.rebuild(source_ids=[target])

    assert result["rebuilt"] is True
    assert result["indexed"] == [target]
    assert result["documents"] == 1
    assert backend.calls == calls + 1
    assert service.index.entries_for(other) == other_entries
    assert source_store.read_source(other) == other_record
    assert service.index.entries_for(target)[0].text.endswith("target replacement text")
    global_hits = service.search(VectorSearchRequest(query="other", include_global=True))["hits"]
    assert other not in {hit["source_id"] for hit in global_hits}
    scoped_hits = service.search(VectorSearchRequest(query="other", task_ref="task_private"))["hits"]
    assert other in {hit["source_id"] for hit in scoped_hits}


@pytest.mark.parametrize("failure", ["backend", "unsupported", "timeout", "disabled", "empty", "missing",
                                      "model", "dim", "version", "corrupt"])
def test_scoped_failure_preserves_corpus_and_other_metadata(source_store, backend, failure):
    service, target, other = seed_corpus(source_store, backend)
    other_record = source_store.read_source(other)
    expected_reason = {
        "backend": "embedding_failed", "unsupported": "embedding_failed",
        "timeout": "embedding_timeout", "disabled": "vector_backend_unavailable",
        "empty": "no_embeddable_body", "missing": "source_not_found",
        "model": "model_mismatch_rebuild_required", "dim": "model_mismatch_rebuild_required",
        "version": "cache_version_mismatch_rebuild_required", "corrupt": "cache_corrupt_rebuild_required",
    }[failure]
    expected_calls = 0
    if failure in {"backend", "unsupported", "timeout"}:
        backend.fail_with = {
            "backend": EmbeddingServiceError(status=500, message="scripted failure"),
            "unsupported": EmbeddingUnavailable("unsupported input"),
            "timeout": EmbeddingTimeout(timeout_seconds=1.0),
        }[failure]
        expected_calls = 1
    elif failure == "disabled":
        backend._configured = False
    elif failure == "empty":
        ContentStore(source_root=source_store.source_dir(target)).formal_path().write_text("")
    elif failure == "missing":
        target = "source_00000000000000000000000000"
    elif failure in {"model", "dim"}:
        backend = FakeEmbeddingBackend(model="new-model") if failure == "model" else FakeEmbeddingBackend(dim=4)
        service = VectorSearchService(source_store, backend=backend)
        expected_calls = int(failure == "dim")
    elif failure == "version":
        lines = service.index.path.read_text().splitlines()
        header = json.loads(lines[0])
        header["cache_version"] = -1
        lines[0] = json.dumps(header)
        service.index.path.write_text("\n".join(lines) + "\n")
    elif failure == "corrupt":
        service.index.path.write_bytes(b"corrupt cache retained as evidence\n")
    before = service.index.path.read_bytes()
    calls = backend.calls

    result = service.rebuild(source_ids=[target])

    assert service.index.path.exists(), "scoped rebuild deleted the entire vector corpus"
    assert service.index.path.read_bytes() == before
    assert source_store.read_source(other) == other_record
    assert backend.calls == calls + expected_calls
    assert result["rebuilt"] is False
    assert result["indexed"] == []
    assert result["not_indexed"] == [target]
    assert result["documents"] == 0
    assert result["states"][0]["indexed"] is False
    assert result["states"][0]["reason"] == expected_reason


def test_empty_scoped_selection_is_not_full_rebuild(source_store, backend):
    service, _, _ = seed_corpus(source_store, backend)
    before = service.index.path.read_bytes()
    calls = backend.calls
    result = service.rebuild(source_ids=[])
    assert result["rebuilt"] is False
    assert result["indexed"] == result["not_indexed"] == []
    assert service.index.path.read_bytes() == before
    assert backend.calls == calls


def test_full_rebuild_still_switches_model_for_entire_corpus(source_store, backend):
    service, target, other = seed_corpus(source_store, backend)
    replacement = FakeEmbeddingBackend(model="replacement-model")
    service = VectorSearchService(source_store, backend=replacement)
    result = service.rebuild()
    assert result["rebuilt"] is True
    assert set(result["indexed"]) == {target, other}
    assert result["documents"] == 2
    assert replacement.calls == 2
    assert {entry.model for entry in service.index.all_entries()} == {"replacement-model"}


async def test_http_scoped_failure_retains_two_file_sources(api, app, source_store, backend):
    service, target, other = seed_corpus(source_store, backend)
    before = service.index.path.read_bytes()
    other_record = source_store.read_source(other)
    backend.fail_with = EmbeddingServiceError(status=500, message="scripted failure")

    response = await api.post("/api/v1/vector/rebuild", params={"source_id": target})

    assert response.status_code == 200
    assert service.index.path.exists(), "POST scoped rebuild deleted the entire vector corpus"
    assert service.index.path.read_bytes() == before
    assert source_store.read_source(other) == other_record
    assert response.json()["rebuilt"] is False
    assert response.json()["indexed"] == []
    assert response.json()["not_indexed"] == [target]


@pytest.mark.parametrize("old_fingerprint", [None, '["https://old.example/v1","fake-embed-v1"]'])
def test_backend_provenance_survives_restart_and_requires_explicit_full_rebuild(source_store, old_fingerprint):
    old = VectorSearchService(source_store, backend=FakeEmbeddingBackend(), backend_fingerprint=old_fingerprint)
    target = make_source(source_store, source_id="provenance-target", title="target")
    other = make_source(source_store, source_id="provenance-other", title="other")
    for sid in (target.source_id, other.source_id):
        write_formal(source_store, sid, "trusted body")
        assert old.index_source(sid)["indexed"]
    before = old.index.path.read_bytes()
    other_record = source_store.read_source(other.source_id)

    fingerprint = '["https://new.example/v1","fake-embed-v1"]'
    backend = FakeEmbeddingBackend()
    restarted = VectorSearchService(source_store, backend=backend, backend_fingerprint=fingerprint)
    assert restarted.cache_compatibility_reason() == "model_mismatch_rebuild_required"
    result = restarted.index_source(target.source_id)
    assert result["reason"] == "model_mismatch_rebuild_required"
    result = restarted.rebuild(source_ids=[target.source_id])
    assert result["rebuilt"] is False
    assert result["states"][0]["reason"] == "model_mismatch_rebuild_required"
    result = restarted.search(VectorSearchRequest(query="trusted", include_global=True))
    assert result["index_unavailable_reason"] == "model_mismatch_rebuild_required"
    assert backend.calls == 0
    assert restarted.index.path.read_bytes() == before
    assert source_store.read_source(other.source_id) == other_record

    full = restarted.rebuild()
    assert full["rebuilt"] is True
    assert set(full["indexed"]) == {target.source_id, other.source_id}
    assert backend.calls == 2
    assert restarted.index.header()["backend_fingerprint"] == fingerprint
    same_backend = FakeEmbeddingBackend()
    same = VectorSearchService(source_store, backend=same_backend, backend_fingerprint=fingerprint)
    assert same.cache_compatibility_reason() is None
    assert same.rebuild(source_ids=[target.source_id])["rebuilt"] is True
    assert same_backend.calls == 1
    assert len(same.index.all_entries()) == 2


def test_scoped_partial_media_failure_is_reported_without_erasing_other(source_store, backend):
    service, _, other = seed_corpus(source_store, backend)
    media = make_source(
        source_store, source_id="partial-media", title="media",
        original={"path": "original/pic.png", "media_type": "image/png", "bytes": 3, "archived_at": None},
    )
    write_original_media(source_store, media.source_id, "pic.png", b"PNG")
    write_formal(source_store, media.source_id, "trusted text")
    other_entries = service.index.entries_for(other)
    backend.fail_part_types = {"image"}
    result = service.rebuild(source_ids=[media.source_id, media.source_id])
    assert result["rebuilt"] is False
    assert result["indexed"] == [media.source_id]
    assert result["documents"] == 1
    assert result["states"][0]["kinds"] == ["text"]
    assert result["states"][0]["failed_kinds"] == ["image"]
    assert result["states"][0]["reason"] == "partial_index"
    assert service.index.entries_for(other) == other_entries
