"""Vector cache mechanism tests (LG-037): model/dim/hash/version + rebuild.

These use the deterministic stand-in embedder only.  They verify the *cache*
rules — never a retrieval-quality claim.
"""

from __future__ import annotations

import json

import pytest

from lightgravity.sources.vectors import (
    VECTOR_CACHE_VERSION,
    VectorCacheCorruptError,
    VectorEntry,
    VectorIndex,
    VectorModelMismatchError,
    fragment_hash,
)


def _entry(**overrides):
    base = dict(
        source_id="source_a",
        source_version=1,
        content_hash="c" * 64,
        basis="formal",
        kind="text",
        model="m1",
        dim=4,
        cache_version=VECTOR_CACHE_VERSION,
        fragment_hash=fragment_hash("hello"),
        vector=(1.0, 0.0, 0.0, 0.0),
        title="t",
    )
    base.update(overrides)
    return VectorEntry(**base)


def test_replace_all_records_model_dim_and_version(tmp_path):
    index = VectorIndex(tmp_path / "v")
    report = index.replace_all([_entry()], model="m1", dim=4)
    assert report.documents == 1
    header = index.header()
    assert header["model"] == "m1"
    assert header["dim"] == 4
    assert header["cache_version"] == VECTOR_CACHE_VERSION
    entry = index.all_entries()[0]
    assert entry.model == "m1"
    assert entry.dim == 4
    assert entry.fragment_hash == fragment_hash("hello")


def test_model_switch_is_not_mixed(tmp_path):
    index = VectorIndex(tmp_path / "v")
    index.replace_all([_entry(model="m1")], model="m1", dim=4)
    # A different model must not be appended into the same cache.
    with pytest.raises(VectorModelMismatchError):
        index.replace_all([_entry(model="m2")], model="m1", dim=4)


def test_search_refuses_other_model(tmp_path):
    index = VectorIndex(tmp_path / "v")
    index.replace_all([_entry(model="m1", vector=(1.0, 0.0, 0.0, 0.0))], model="m1", dim=4)
    assert index.search((1.0, 0.0, 0.0, 0.0), model="m2") == []
    hits = index.search((1.0, 0.0, 0.0, 0.0), model="m1")
    assert len(hits) == 1
    assert hits[0]["model"] == "m1"


def test_search_skips_dimension_mismatch(tmp_path):
    index = VectorIndex(tmp_path / "v")
    index.replace_all([_entry(model="m1", dim=4, vector=(1.0, 0.0, 0.0, 0.0))], model="m1", dim=4)
    # A query vector of a different length must never be compared.
    assert index.search((1.0, 0.0), model="m1") == []


def test_delete_and_rebuild_reproduces_entries(tmp_path):
    cache = tmp_path / "v"
    index = VectorIndex(cache)
    index.replace_all([_entry()], model="m1", dim=4)
    before = [e.to_dict() for e in index.all_entries()]
    index.delete()
    assert not index.exists()
    index.replace_all([_entry()], model="m1", dim=4)
    after = [e.to_dict() for e in index.all_entries()]
    assert before == after


def test_corrupt_cache_is_reported(tmp_path):
    cache = tmp_path / "v"
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "vectors.jsonl").write_text("not json\n", encoding="utf-8")
    index = VectorIndex(cache)
    assert index.exists()
    assert index.readable() is False
    with pytest.raises(VectorCacheCorruptError):
        index.all_entries()


def test_remove_drops_one_source(tmp_path):
    index = VectorIndex(tmp_path / "v")
    index.replace_all(
        [_entry(source_id="source_a"), _entry(source_id="source_b")], model="m1", dim=4
    )
    index.remove("source_a")
    remaining = {e.source_id for e in index.all_entries()}
    assert remaining == {"source_b"}


def test_header_written_as_first_line(tmp_path):
    index = VectorIndex(tmp_path / "v")
    index.replace_all([_entry()], model="m1", dim=4)
    lines = (tmp_path / "v" / "vectors.jsonl").read_text("utf-8").splitlines()
    header = json.loads(lines[0])
    assert header["record"] == "header"
    assert header["model"] == "m1"
