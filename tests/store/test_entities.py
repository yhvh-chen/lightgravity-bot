"""Versioned entity reads/writes, revision conflicts and preservation."""

from __future__ import annotations

import hashlib

import pytest

from lightgravity.store import (
    ConfigInvalid,
    EntityNotFound,
    FileStore,
    RevisionConflict,
    Store,
    new_id,
)

from store_helpers import create_task


def test_create_then_read_roundtrip(store: FileStore) -> None:
    task_id = create_task(store, title="Roundtrip")
    versioned = store.read("task", task_id)
    assert versioned.revision == 0
    assert versioned.entity["title"] == "Roundtrip"
    assert versioned.body == "\n# Task\n"
    on_disk = versioned.path
    with open(on_disk, "rb") as handle:
        assert versioned.content_hash == hashlib.sha256(handle.read()).hexdigest()
    assert versioned.etag == '"0"'


def test_create_duplicate_id_rejected(store: FileStore) -> None:
    task_id = create_task(store)
    with pytest.raises(ConfigInvalid) as excinfo:
        store.create("task", task_id, {"status": "todo"}, actor="t", request_id="r")
    assert "duplicate_id" in {d["code"] for d in excinfo.value.details["diagnostics"]}


def test_write_increments_revision_once(store: FileStore) -> None:
    task_id = create_task(store)
    updated = store.write("task", task_id, {"title": "v1"}, expected_revision=0, actor="t")
    assert updated.revision == 1
    assert store.read("task", task_id).entity["title"] == "v1"


def test_write_revision_conflict_reports_both_versions(store: FileStore) -> None:
    task_id = create_task(store)
    store.write("task", task_id, {"title": "v1"}, expected_revision=0, actor="t")
    with pytest.raises(RevisionConflict) as excinfo:
        store.write("task", task_id, {"title": "stale"}, expected_revision=0, actor="t")
    details = excinfo.value.details
    assert details["expected_revision"] == 0
    assert details["actual_revision"] == 1
    assert details["etag"] == '"1"'
    # The newer value is not silently overwritten.
    assert store.read("task", task_id).entity["title"] == "v1"


def test_write_requires_expected_revision(store: FileStore) -> None:
    task_id = create_task(store)
    with pytest.raises(ConfigInvalid):
        store.write("task", task_id, {"title": "x"}, expected_revision=None, actor="t")


def test_write_preserves_unknown_fields_and_body(store: FileStore) -> None:
    task_id = create_task(store, body="keep this body\n")
    store.write(
        "task",
        task_id,
        {"title": "new", "extension_field": {"keep": True}},
        expected_revision=0,
        actor="t",
    )
    again = store.write("task", task_id, {"phase": "queued"}, expected_revision=1, actor="t")
    assert again.entity["extension_field"] == {"keep": True}
    assert again.entity["phase"] == "queued"
    assert again.body == "keep this body\n"


def test_read_missing_entity(store: FileStore) -> None:
    with pytest.raises(EntityNotFound):
        store.read("task", new_id("task"))


def test_read_rejects_tampered_state(store: FileStore) -> None:
    task_id = create_task(store)
    path = store.entity_path("task", task_id)
    path.write_text(path.read_text().replace("phase: intake", "phase: executing"))
    with pytest.raises(ConfigInvalid) as excinfo:
        store.read("task", task_id)
    assert "illegal_status_phase" in {d["code"] for d in excinfo.value.details["diagnostics"]}


def test_unsupported_kind_rejected(store: FileStore) -> None:
    with pytest.raises(ConfigInvalid):
        store.read("bogus", "whatever")


def test_filestore_satisfies_store_protocol(store: FileStore) -> None:
    assert isinstance(store, Store)
