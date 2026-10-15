"""Atomic claims, fencing, expiry, cancel/restart and default-off behavior."""

from __future__ import annotations

import threading

import pytest

from lightgravity.collaboration import (
    ClaimPolicy,
    ClaimRefused,
    ClaimRequest,
    CollaborationService,
    StaleLease,
)
from lightgravity.store import FileStore
from lightgravity.store.clock import to_iso

from collab_helpers import (
    FakeClock,
    create_run,
    create_subtask,
    create_task,
    link_subtasks,
    set_switches,
)


def _service(store: FileStore, clock: FakeClock, *, enabled: bool = True) -> CollaborationService:
    if enabled:
        set_switches(store, enabled=True, lease_seconds=60)
    return CollaborationService(
        store,
        policy=ClaimPolicy(enabled=enabled, lease_seconds=60),
        clock=clock,
    )


def _request(subtask_id: str, owner: str, request_id: str, **kw: object) -> ClaimRequest:
    return ClaimRequest(
        subtask_id=subtask_id,
        owner=owner,
        request_id=request_id,
        **kw,  # type: ignore[arg-type]
    )


def test_claim_grants_and_increments_fence(store: FileStore, clock: FakeClock) -> None:
    service = _service(store, clock)
    task_id = create_task(store)
    run_id = create_run(store, task_id)
    sub = create_subtask(store, run_id, key="a")
    link_subtasks(store, run_id, [sub])

    decision = service.request_claim(run_id, _request(sub, "worker-1", "req-1"))
    assert decision.granted is True
    assert decision.fence == 1
    entity = store.read("subtask", sub).entity
    assert entity["state"] == "running"
    assert entity["owner"] == "worker-1"
    assert entity["fence"] == 1


def test_two_owner_race_on_real_store_only_one_wins(
    data_dir, workspace_root, clock: FakeClock
) -> None:
    """Two worker identities race the same Subtask through two FileStore instances."""

    setup = FileStore(data_dir, workspace_root)
    task_id = create_task(setup)
    run_id = create_run(setup, task_id)
    sub = create_subtask(setup, run_id, key="a")
    link_subtasks(setup, run_id, [sub])
    set_switches(setup, enabled=True, lease_seconds=60)

    barrier = threading.Barrier(2)
    results: list[object] = []
    errors: list[BaseException] = []

    def worker(owner: str) -> None:
        store = FileStore(data_dir, workspace_root)
        service = CollaborationService(
            store, policy=ClaimPolicy(enabled=True, lease_seconds=60), clock=clock
        )
        barrier.wait()
        try:
            results.append(
                service.request_claim(run_id, _request(sub, owner, f"req-{owner}"))
            )
        except BaseException as exc:  # noqa: BLE001 - record for the assertion
            errors.append(exc)

    threads = [
        threading.Thread(target=worker, args=("worker-a",)),
        threading.Thread(target=worker, args=("worker-b",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert errors == []
    assert len(results) == 2
    granted = [d for d in results if getattr(d, "granted")]
    refused = [d for d in results if not getattr(d, "granted")]
    assert len(granted) == 1, results
    assert len(refused) == 1
    assert refused[0].reason == "held_by_other"
    entity = setup.read("subtask", sub).entity
    assert entity["owner"] == granted[0].owner
    assert entity["fence"] == 1


def test_claim_request_id_is_idempotent(store: FileStore, clock: FakeClock) -> None:
    service = _service(store, clock)
    task_id = create_task(store)
    run_id = create_run(store, task_id)
    sub = create_subtask(store, run_id, key="a")
    link_subtasks(store, run_id, [sub])

    first = service.request_claim(run_id, _request(sub, "worker-1", "req-1"))
    second = service.request_claim(run_id, _request(sub, "worker-1", "req-1"))
    assert first.granted and second.granted
    assert second.idempotent_replay is True
    assert second.fence == first.fence == 1
    assert store.read("subtask", sub).entity["fence"] == 1


def test_claim_refused_for_undiscoverable_capability_and_budget(
    store: FileStore, clock: FakeClock
) -> None:
    service = _service(store, clock)
    task_id = create_task(store)
    run_id = create_run(store, task_id)
    sub = create_subtask(store, run_id, key="a", capability="implementation")
    link_subtasks(store, run_id, [sub])

    # Capability mismatch is a refusal, not a grant.
    denied = service.request_claim(
        run_id, _request(sub, "worker-2", "req-cap"), capability_ok=False
    )
    assert denied.granted is False
    assert denied.reason == "capability_mismatch"

    denied_budget = service.request_claim(
        run_id, _request(sub, "worker-2", "req-budget"), budget_available=False
    )
    assert denied_budget.granted is False
    assert denied_budget.reason == "budget_exhausted"

    denied_dep = service.request_claim(
        run_id, _request(sub, "worker-2", "req-dep"), dependencies_ready=False
    )
    assert denied_dep.reason == "dependencies_unmet"
    # No lease was written for any refusal.
    assert store.read("subtask", sub).entity["owner"] is None


def test_claim_refused_when_feature_disabled(store: FileStore, clock: FakeClock) -> None:
    service = _service(store, clock, enabled=False)
    task_id = create_task(store)
    run_id = create_run(store, task_id)
    sub = create_subtask(store, run_id, key="a")
    link_subtasks(store, run_id, [sub])

    with pytest.raises(ClaimRefused) as excinfo:
        service.request_claim(run_id, _request(sub, "worker-1", "req-1"))
    assert excinfo.value.reason == "feature_disabled"
    assert store.read("subtask", sub).entity["owner"] is None


def test_renew_requires_matching_fence_and_live_lease(
    store: FileStore, clock: FakeClock
) -> None:
    service = _service(store, clock)
    task_id = create_task(store)
    run_id = create_run(store, task_id)
    sub = create_subtask(store, run_id, key="a")
    link_subtasks(store, run_id, [sub])
    decision = service.request_claim(run_id, _request(sub, "worker-1", "req-1"))

    ok = service.renew(sub, "worker-1", fence=decision.fence, lease_seconds=60)
    assert ok.renewed is True

    with pytest.raises(StaleLease):
        service.renew(sub, "worker-1", fence=decision.fence + 5, lease_seconds=60)

    # Expired lease cannot be renewed back to life.
    clock.advance(120)
    expired = service.renew(sub, "worker-1", fence=decision.fence, lease_seconds=60)
    assert expired.renewed is False
    assert expired.reason == "lease_expired"


def test_expiry_is_not_a_stop_and_write_node_goes_recovery_required(
    store: FileStore, clock: FakeClock
) -> None:
    service = _service(store, clock)
    task_id = create_task(store)
    run_id = create_run(store, task_id)
    read_node = create_subtask(store, run_id, key="ro", write=False)
    write_node = create_subtask(store, run_id, key="rw", write=True)
    link_subtasks(store, run_id, [read_node, write_node])

    service.request_claim(run_id, _request(read_node, "worker-1", "req-ro"))
    service.request_claim(run_id, _request(write_node, "worker-1", "req-rw"))

    state = service.lease_state(read_node)
    assert state is not None and state.expired is False and state.stopped is False

    clock.advance(120)

    expired = service.lease_state(read_node)
    assert expired is not None
    assert expired.expired is True
    # Expiry never means the execution stopped.
    assert expired.stopped is False

    ro_reclaim = service.reclaim_expired(read_node)
    assert ro_reclaim.reclaimed is True
    assert ro_reclaim.recovery_required is False

    rw_reclaim = service.reclaim_expired(write_node)
    assert rw_reclaim.reclaimed is True
    assert rw_reclaim.recovery_required is True
    rw_entity = store.read("subtask", write_node).entity
    assert rw_entity["state"] == "waiting_user"
    assert "recovery_required" in str(rw_entity["fail_reason"])


def test_old_fence_write_back_rejected_without_persisting(
    store: FileStore, clock: FakeClock
) -> None:
    service = _service(store, clock)
    task_id = create_task(store)
    run_id = create_run(store, task_id)
    sub = create_subtask(store, run_id, key="a")
    link_subtasks(store, run_id, [sub])

    first = service.request_claim(run_id, _request(sub, "worker-1", "req-1"))
    assert first.fence == 1

    # Lease expires, another holder claims it -> fence advances and owner changes.
    clock.advance(120)
    service.reclaim_expired(sub)
    second = service.request_claim(run_id, _request(sub, "worker-2", "req-2"))
    assert second.granted is True
    assert second.fence > first.fence

    # The old holder's fenced write-back must be rejected and change nothing.
    with pytest.raises(StaleLease) as excinfo:
        service.guard_write_back(sub, "worker-1", first.fence, {"state": "passed"})
    assert excinfo.value.provided_fence == first.fence
    assert excinfo.value.current_fence == second.fence

    entity = store.read("subtask", sub).entity
    assert entity["state"] == "running"
    assert entity["owner"] == "worker-2"

    # A stale assert_current (handoff/emit/member-release gate) also fails.
    with pytest.raises(StaleLease):
        service.assert_current(sub, "worker-1", first.fence)

    # The current holder can write back.
    service.guard_write_back(sub, "worker-2", second.fence, {"state": "passed"})
    assert store.read("subtask", sub).entity["state"] == "passed"


def test_cancel_releases_lease_and_restart_does_not_duplicate_write(
    data_dir, workspace_root, clock: FakeClock
) -> None:
    store = FileStore(data_dir, workspace_root)
    service = _service(store, clock)
    task_id = create_task(store)
    run_id = create_run(store, task_id)
    sub = create_subtask(store, run_id, key="a")
    link_subtasks(store, run_id, [sub])
    decision = service.request_claim(run_id, _request(sub, "worker-1", "req-1"))

    # Cancel releases the lease; the node is claimable again and fence advances
    # only on the next grant.
    assert service.release(sub, "worker-1", fence=decision.fence, reason="cancelled") is True
    released = store.read("subtask", sub).entity
    assert released["owner"] is None
    assert released["lease_expires_at"] is None
    assert released["fence"] == decision.fence

    # A restarted process re-reads the same file SoT and does not replay: a new
    # service instance refuses the stale request id replay only as idempotent,
    # and a fresh owner gets a strictly higher fence.
    restarted = CollaborationService(
        FileStore(data_dir, workspace_root),
        policy=ClaimPolicy(enabled=True, lease_seconds=60),
        clock=clock,
    )
    grant = restarted.request_claim(run_id, _request(sub, "worker-2", "req-2"))
    assert grant.granted is True
    assert grant.fence == decision.fence + 1
    assert store.read("subtask", sub).entity["owner"] == "worker-2"


def test_same_request_id_after_restart_does_not_grant_again(
    data_dir, workspace_root, clock: FakeClock
) -> None:
    """A replayed ``request_id`` after a restart never produces a second lease."""

    store = FileStore(data_dir, workspace_root)
    service = _service(store, clock)
    task_id = create_task(store)
    run_id = create_run(store, task_id)
    sub = create_subtask(store, run_id, key="a")
    link_subtasks(store, run_id, [sub])
    first = service.request_claim(run_id, _request(sub, "worker-1", "req-1"))
    assert first.granted is True
    fence_after_first = store.read("subtask", sub).entity["fence"]

    # New process, same persisted file SoT; replay the same request id.
    restarted = CollaborationService(
        FileStore(data_dir, workspace_root),
        policy=ClaimPolicy(enabled=True, lease_seconds=60),
        clock=clock,
    )
    replay = restarted.request_claim(run_id, _request(sub, "worker-1", "req-1"))
    assert replay.granted is True
    assert replay.idempotent_replay is True
    assert replay.fence == first.fence
    # No second grant/lease write happened.
    assert store.read("subtask", sub).entity["fence"] == fence_after_first


def test_side_effect_node_is_not_replayed_after_restart(
    data_dir, workspace_root, clock: FakeClock
) -> None:
    """A crashed write node with unknown side effects is never auto-replayed."""

    store = FileStore(data_dir, workspace_root)
    service = _service(store, clock)
    task_id = create_task(store)
    run_id = create_run(store, task_id)
    sub = create_subtask(store, run_id, key="rw", write=True)
    link_subtasks(store, run_id, [sub])
    service.request_claim(run_id, _request(sub, "worker-1", "req-1"))

    # The process dies mid-execution; the lease is left running and then expires.
    clock.advance(120)
    restarted = CollaborationService(
        FileStore(data_dir, workspace_root),
        policy=ClaimPolicy(enabled=True, lease_seconds=60),
        clock=clock,
    )
    outcome = restarted.reclaim_expired(sub)
    assert outcome.reclaimed is True
    assert outcome.recovery_required is True

    entity = store.read("subtask", sub).entity
    assert entity["state"] == "waiting_user"
    assert "recovery_required" in str(entity["fail_reason"])
    # The node is not silently claimable again after the reclaim.
    view = restarted.discover(run_id, "worker-2")
    assert sub not in {c.subtask_id for c in view.candidates}


def test_release_by_wrong_owner_rejected(store: FileStore, clock: FakeClock) -> None:
    service = _service(store, clock)
    task_id = create_task(store)
    run_id = create_run(store, task_id)
    sub = create_subtask(store, run_id, key="a")
    link_subtasks(store, run_id, [sub])
    service.request_claim(run_id, _request(sub, "worker-1", "req-1"))

    with pytest.raises(ClaimRefused) as excinfo:
        service.release(sub, "worker-2")
    assert excinfo.value.reason == "not_owner"
    assert store.read("subtask", sub).entity["owner"] == "worker-1"


def test_lease_events_recorded(store: FileStore, clock: FakeClock) -> None:
    service = _service(store, clock)
    task_id = create_task(store)
    run_id = create_run(store, task_id)
    sub = create_subtask(store, run_id, key="a")
    link_subtasks(store, run_id, [sub])
    decision = service.request_claim(run_id, _request(sub, "worker-1", "req-1"))
    service.renew(sub, "worker-1", fence=decision.fence, lease_seconds=60)
    service.release(sub, "worker-1", fence=decision.fence)

    records = store.read_events(run_id, after_seq=0, limit=100)
    types = [record.type for record in records]
    assert "subtask.lease_granted" in types
    assert "subtask.lease_renewed" in types
    assert "subtask.lease_revoked" in types


def test_default_off_without_settings_and_legacy_fence_zero(
    store: FileStore, clock: FakeClock
) -> None:
    task_id = create_task(store)
    run_id = create_run(store, task_id)
    # Legacy subtask with no fence field at all.
    sub = create_subtask(store, run_id, key="legacy")
    link_subtasks(store, run_id, [sub])
    set_switches(store, enabled=True, lease_seconds=60)

    service = CollaborationService(
        store, policy=ClaimPolicy(enabled=True, lease_seconds=60), clock=clock
    )
    assert store.read("subtask", sub).entity.get("fence") is None
    decision = service.request_claim(run_id, _request(sub, "worker-1", "req-1"))
    assert decision.granted is True
    assert decision.fence == 1  # legacy fence treated as 0, then incremented
