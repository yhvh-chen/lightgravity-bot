"""Discovery authorization: only authorized, ready, affordable nodes are visible."""

from __future__ import annotations

from lightgravity.collaboration import CollaborationService, DiscoveryLimits
from lightgravity.store import FileStore

from collab_helpers import (
    FakeClock,
    create_run,
    create_subtask,
    create_task,
    link_subtasks,
    set_switches,
)


def _enabled(store: FileStore, clock: FakeClock) -> CollaborationService:
    set_switches(store, enabled=True)
    from lightgravity.collaboration import ClaimPolicy

    return CollaborationService(
        store,
        policy=ClaimPolicy(enabled=True, lease_seconds=60),
        clock=clock,
    )


def test_disabled_by_default_is_empty(store: FileStore, clock: FakeClock) -> None:
    task_id = create_task(store)
    run_id = create_run(store, task_id)
    subtask_id = create_subtask(store, run_id, key="a")
    link_subtasks(store, run_id, [subtask_id])

    # No SETTINGS.md switch at all -> closed, deterministic scheduling retained.
    service = CollaborationService(store, clock=clock)
    view = service.discover(run_id, "worker-1")
    assert view.enabled is False
    assert view.candidates == ()
    assert service.enabled is False


def test_unauthorized_run_is_not_discoverable(store: FileStore, clock: FakeClock) -> None:
    service = _enabled(store, clock)
    task_a = create_task(store)
    run_a = create_run(store, task_a)
    sub_a = create_subtask(store, run_a, key="a")
    link_subtasks(store, run_a, [sub_a])

    view = service.discover("run_01J00000000000000000000ZZ", "worker-1")
    assert view.candidates == ()
    assert view.excluded.get("run_unknown") == 1

    # A subtask not listed in run.subtask_refs is not projected even if it exists.
    task_b = create_task(store)
    run_b = create_run(store, task_b)
    other = create_subtask(store, run_b, key="b")
    view_b = service.discover(run_a, "worker-1")
    assert [c.subtask_id for c in view_b.candidates] == [sub_a]
    assert other not in {c.subtask_id for c in view_b.candidates}


def test_capability_mismatch_excluded(store: FileStore, clock: FakeClock) -> None:
    service = _enabled(store, clock)
    task_id = create_task(store)
    run_id = create_run(store, task_id)
    impl = create_subtask(store, run_id, key="impl", capability="implementation")
    verify = create_subtask(store, run_id, key="verify", capability="verification")
    link_subtasks(store, run_id, [impl, verify])

    view = service.discover(
        run_id,
        "worker-1",
        limits=DiscoveryLimits(capabilities=("implementation",)),
    )
    assert [c.key for c in view.candidates] == ["impl"]
    assert view.excluded.get("capability_mismatch") == 1


def test_dependency_unmet_excluded(store: FileStore, clock: FakeClock) -> None:
    service = _enabled(store, clock)
    task_id = create_task(store)
    run_id = create_run(store, task_id)
    upstream = create_subtask(store, run_id, key="up", state="pending")
    downstream = create_subtask(store, run_id, key="down", depends_on=[upstream])
    link_subtasks(store, run_id, [upstream, downstream])

    view = service.discover(run_id, "worker-1")
    assert [c.key for c in view.candidates] == ["up"]

    # Complete the upstream node -> downstream becomes discoverable with a handoff.
    current = store.read("subtask", upstream)
    store.write(
        "subtask",
        upstream,
        {"state": "passed"},
        expected_revision=current.revision,
        actor="test",
    )
    view2 = service.discover(run_id, "worker-1")
    assert [c.key for c in view2.candidates] == ["down"]


def test_budget_exhausted_excluded(store: FileStore, clock: FakeClock) -> None:
    service = _enabled(store, clock)
    task_id = create_task(store)
    run_id = create_run(store, task_id)
    sub = create_subtask(store, run_id, key="a")
    link_subtasks(store, run_id, [sub])

    view = service.discover(
        run_id, "worker-1", limits=DiscoveryLimits(budget_remaining=0)
    )
    assert view.candidates == ()
    assert view.excluded.get("budget_exhausted") == 1


def test_terminal_and_write_held_excluded(store: FileStore, clock: FakeClock) -> None:
    service = _enabled(store, clock)
    task_id = create_task(store)
    run_id = create_run(store, task_id)
    done = create_subtask(store, run_id, key="done", state="passed")
    writer = create_subtask(store, run_id, key="writer", write=True)
    link_subtasks(store, run_id, [done, writer])

    view = service.discover(
        run_id,
        "worker-1",
        limits=DiscoveryLimits(write_held_keys=frozenset({"writer"})),
    )
    assert view.candidates == ()
    assert view.excluded.get("terminal") == 1
    assert view.excluded.get("write_serialization") == 1


def test_concurrency_ceiling_excluded(store: FileStore, clock: FakeClock) -> None:
    service = _enabled(store, clock)
    task_id = create_task(store)
    run_id = create_run(store, task_id)
    sub = create_subtask(store, run_id, key="a")
    link_subtasks(store, run_id, [sub])

    view = service.discover(
        run_id, "worker-1", limits=DiscoveryLimits(max_parallel=1, running=1)
    )
    assert view.candidates == ()
    assert view.excluded.get("concurrency_limited") == 1
