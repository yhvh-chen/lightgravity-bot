"""LG-208: version-aware in-process cache for parsed Markdown reads.

Markdown stays authoritative: every hit is gated by the current file signature
and callers receive an independent snapshot.  These tests use tmp data only.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable

import pytest

from lightgravity.store import ConfigInvalid, EntityNotFound, FileStore

from store_helpers import create_task


def _spy_parse(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Count real ``parse_document`` calls while preserving its behaviour."""

    import lightgravity.store.store as store_module

    calls: list[str] = []
    real_parse: Callable[..., Any] = store_module.parse_document

    def wrapper(text: str, *, source: str = "<memory>") -> Any:
        calls.append(source)
        return real_parse(text, source=source)

    monkeypatch.setattr(store_module, "parse_document", wrapper)
    return calls


def test_repeated_read_uses_cache_and_preserves_version_facts(
    store: FileStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _spy_parse(monkeypatch)
    task_id = create_task(store, title="Cached task")

    first = store.read("task", task_id)
    second = store.read("task", task_id)

    assert len(calls) == 1
    assert second.entity_id == first.entity_id
    assert second.revision == first.revision == 0
    assert second.etag == first.etag == '"0"'
    assert second.content_hash == first.content_hash
    assert second.body == first.body
    assert second.path == first.path


def test_unified_store_write_invalidates_cache(
    store: FileStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _spy_parse(monkeypatch)
    task_id = create_task(store, title="Before")
    assert store.read("task", task_id).entity["title"] == "Before"
    assert len(calls) == 1

    store.write("task", task_id, {"title": "After"}, expected_revision=0, actor="test")
    calls.clear()
    current = store.read("task", task_id)

    # The write itself parses the old file; the next read must parse the new one.
    assert len(calls) == 1
    assert current.entity["title"] == "After"
    assert current.revision == 1
    assert current.etag == '"1"'


def test_external_in_place_edit_is_visible_on_next_read(
    store: FileStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    _spy_parse(monkeypatch)
    task_id = create_task(store, title="Before")
    path = store.entity_path("task", task_id)
    assert store.read("task", task_id).entity["title"] == "Before"

    original = path.read_text("utf-8")
    # Same byte length, deliberately distinguishing the file-version signature
    # rather than relying on a size difference.
    path.write_text(original.replace("Before", "After!"), "utf-8")
    current_stat = path.stat()
    os.utime(
        path,
        ns=(current_stat.st_atime_ns, current_stat.st_mtime_ns + 1_000_000_000),
    )

    assert store.read("task", task_id).entity["title"] == "After!"


def test_external_atomic_replacement_is_visible_on_next_read(
    store: FileStore, tmp_path: Path
) -> None:
    task_id = create_task(store, title="Before")
    path = store.entity_path("task", task_id)
    assert store.read("task", task_id).entity["title"] == "Before"

    replacement = tmp_path / "replacement.md"
    replacement.write_text(path.read_text("utf-8").replace("Before", "After"), "utf-8")
    os.replace(replacement, path)

    assert store.read("task", task_id).entity["title"] == "After"


def test_failed_external_validation_is_rechecked_and_not_cached(
    store: FileStore,
) -> None:
    task_id = create_task(store)
    path = store.entity_path("task", task_id)
    assert store.read("task", task_id).revision == 0

    tampered = path.read_text("utf-8").replace("phase: intake", "phase: executing")
    path.write_text(tampered, "utf-8")
    for _ in range(2):
        with pytest.raises(ConfigInvalid) as excinfo:
            store.read("task", task_id)
        assert "illegal_status_phase" in {
            item["code"] for item in excinfo.value.details["diagnostics"]
        }

    # Repairing the file makes the same Store instance return the new content.
    path.write_text(tampered.replace("phase: executing", "phase: intake"), "utf-8")
    repaired = store.read("task", task_id)
    assert repaired.revision == 0
    assert repaired.entity["phase"] == "intake"


def test_cached_entity_is_not_a_shared_mutable_reference(store: FileStore) -> None:
    task_id = create_task(store, title="Stable")
    first = store.read("task", task_id)
    first.entity["title"] = "mutated by caller"
    first.entity["queue"]["state"] = "claimed"

    second = store.read("task", task_id)

    assert second is not first
    assert second.entity is not first.entity
    assert second.entity["title"] == "Stable"
    assert second.entity["queue"]["state"] == "not_queued"


def test_delete_invalidates_cached_document(store: FileStore) -> None:
    task_id = create_task(store)
    assert store.read("task", task_id).revision == 0
    store.delete("task", task_id, expected_revision=0, actor="test")

    with pytest.raises(EntityNotFound):
        store.read("task", task_id)
