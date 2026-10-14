"""Queue ordering, dependencies and single-slot selection (LG-007)."""

from __future__ import annotations

from lightgravity.coordinator.queue import TaskQueue
from lightgravity.store import FileStore

from coordinator_helpers import raw_task


def test_fifo_order_and_next_selection(store: FileStore) -> None:
    queue = TaskQueue(store)
    first = raw_task(store)
    second = raw_task(store)
    assert queue.enqueue(first) == "queued"
    assert queue.enqueue(second) == "queued"
    assert queue.position(first).order == 1  # type: ignore[union-attr]
    assert queue.position(second).order == 2  # type: ignore[union-attr]
    nxt = queue.next_queued()
    assert nxt is not None and nxt.id == first


def test_enqueue_is_idempotent(store: FileStore) -> None:
    queue = TaskQueue(store)
    task_id = raw_task(store)
    assert queue.enqueue(task_id) == "queued"
    assert queue.enqueue(task_id) == "already_queued"
    assert queue.position(task_id).order == 1  # type: ignore[union-attr]


def test_unresolved_dependency_waits(store: FileStore) -> None:
    queue = TaskQueue(store)
    dep = raw_task(store)
    dependent = raw_task(store, depends_on=[dep])
    assert queue.enqueue(dependent) == "waiting_dependencies"
    entity = store.read("task", dependent).entity
    assert entity["phase"] == "waiting_dependencies"
    assert queue.next_queued() is None


def test_resolved_dependency_queues(store: FileStore) -> None:
    queue = TaskQueue(store)
    dep = raw_task(store, status="done", phase="completed")
    dependent = raw_task(store, depends_on=[dep])
    assert queue.enqueue(dependent) == "queued"
    assert queue.next_queued().id == dependent  # type: ignore[union-attr]
