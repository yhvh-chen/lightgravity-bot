"""Task claim/renew/release leases and expiry takeover."""

from __future__ import annotations

import pytest

from lightgravity.store import FileStore, LockConflict
from lightgravity.store.clock import from_iso

from store_helpers import FakeClock, create_task


def test_claim_renew_release(store: FileStore) -> None:
    task_id = create_task(store)
    claim = store.claim(task_id, "owner-a", lease_seconds=60)
    assert claim.claimed is True
    assert claim.owner == "owner-a"
    entity = store.read("task", task_id)
    assert entity.entity["queue"]["state"] == "claimed"
    assert entity.entity["queue"]["owner"] == "owner-a"

    assert store.renew(task_id, "owner-a", lease_seconds=60) is True

    store.release(task_id, "owner-a")
    queue = store.read("task", task_id).entity["queue"]
    assert queue["state"] == "not_queued"
    assert queue["owner"] is None
    assert queue["lease_expires_at"] is None


def test_second_owner_cannot_claim_active_lease(store: FileStore) -> None:
    task_id = create_task(store)
    store.claim(task_id, "owner-a", lease_seconds=600)
    with pytest.raises(LockConflict) as excinfo:
        store.claim(task_id, "owner-b", lease_seconds=600)
    assert excinfo.value.details["owner"] == "owner-a"


def test_expired_lease_allows_takeover(data_dir, workspace_root) -> None:
    clock = FakeClock()
    store = FileStore(data_dir, workspace_root, clock=clock)
    task_id = create_task(store)
    first = store.claim(task_id, "owner-a", lease_seconds=10)
    clock.advance(11)
    taken = store.claim(task_id, "owner-b", lease_seconds=10)
    assert taken.owner == "owner-b"
    assert from_iso(taken.lease_expires_at) > from_iso(first.lease_expires_at)


def test_renew_after_expiry_fails(data_dir, workspace_root) -> None:
    clock = FakeClock()
    store = FileStore(data_dir, workspace_root, clock=clock)
    task_id = create_task(store)
    store.claim(task_id, "owner-a", lease_seconds=10)
    clock.advance(11)
    assert store.renew(task_id, "owner-a", lease_seconds=10) is False


def test_cross_instance_lease_conflict(data_dir, workspace_root) -> None:
    store_a = FileStore(data_dir, workspace_root)
    store_b = FileStore(data_dir, workspace_root)
    task_id = create_task(store_a)
    store_a.claim(task_id, "a", lease_seconds=600)
    with pytest.raises(LockConflict):
        store_b.claim(task_id, "b", lease_seconds=600)


def test_release_by_wrong_owner_rejected(store: FileStore) -> None:
    task_id = create_task(store)
    store.claim(task_id, "owner-a", lease_seconds=600)
    with pytest.raises(LockConflict):
        store.release(task_id, "owner-b")
