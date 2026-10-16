"""Task queue ordering on top of the Store (LG-007, docs/04 §5).

The queue is not a second state store: ordering is derived from each Task's
``queue`` frontmatter (``order``, ``queued_at``) and the Store lease
(``owner``/``lease_expires_at``).  Claiming is delegated to ``Store.claim`` so
one Task cannot be executed twice.  Dependency readiness is intentionally
minimal here; LG-008 owns the full scheduler.
"""

from __future__ import annotations

from dataclasses import dataclass

from lightgravity.contracts import EventType, TaskPhase, TaskStatus
from lightgravity.store import Store, TaskSummary, Versioned

from .state import StateWriter


@dataclass(frozen=True, slots=True)
class QueuePosition:
    task_id: str
    order: int | None
    queued_at: str | None
    state: str


class TaskQueue:
    """Deterministic first-version FIFO queue (no priority algorithms)."""

    def __init__(self, store: Store, writer: StateWriter | None = None) -> None:
        self._store = store
        self._writer = writer or StateWriter(store)

    def _ordered(self, summaries: list[TaskSummary]) -> list[TaskSummary]:
        def key(summary: TaskSummary) -> tuple[int, str, str]:
            order = 0
            position = self.position(summary.id)
            if position is not None and position.order is not None:
                order = position.order
            return (order, summary.id, summary.phase)

        return sorted(summaries, key=key)

    def position(self, task_id: str) -> QueuePosition | None:
        entity = self._store.read("task", task_id).entity
        queue = entity.get("queue")
        if not isinstance(queue, dict):
            return None
        order = queue.get("order")
        return QueuePosition(
            task_id=task_id,
            order=order if isinstance(order, int) and not isinstance(order, bool) else None,
            queued_at=queue.get("queued_at") if isinstance(queue.get("queued_at"), str) else None,
            state=str(queue.get("state", "not_queued")),
        )

    def next_order(self) -> int:
        highest = 0
        for summary in self._store.list_tasks():
            position = self.position(summary.id)
            if position is not None and position.order is not None:
                highest = max(highest, position.order)
        return highest + 1

    def dependencies_satisfied(self, task_id: str) -> bool:
        entity = self._store.read("task", task_id).entity
        depends = entity.get("depends_on") or []
        if not depends:
            return True
        for ref in depends:
            if not isinstance(ref, str):
                return False
            try:
                dep = self._store.read("task", ref).entity
            except Exception:  # noqa: BLE001 - a missing/invalid dependency is not ready
                return False
            if dep.get("phase") != TaskPhase.COMPLETED:
                return False
        return True

    def enqueue(self, task_id: str) -> str:
        """Queue a Task (or mark it waiting on dependencies).

        Returns one of ``"queued"``, ``"waiting_dependencies"`` or
        ``"already_queued"``.
        """

        entity = self._store.read("task", task_id).entity
        current_phase = str(entity.get("phase", ""))
        if current_phase in {TaskPhase.QUEUED, TaskPhase.PLANNING, TaskPhase.RECRUITING, TaskPhase.EXECUTING}:
            return "already_queued"
        if not self.dependencies_satisfied(task_id):
            self._writer.transition_task(
                task_id,
                TaskPhase.WAITING_DEPENDENCIES,
                reason="dependencies not completed",
            )
            return "waiting_dependencies"
        order = self.next_order()
        from datetime import datetime, timezone

        queued_at = (
            datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        )
        versioned = self._writer.transition_task(
            task_id,
            TaskPhase.QUEUED,
            extra={
                "queue": {
                    "state": "queued",
                    "order": order,
                    "queued_at": queued_at,
                    "owner": None,
                    "lease_expires_at": None,
                }
            },
        )
        self._writer.emit(
            task_id,
            EventType.QUEUE_ENQUEUED,
            {"order": order, "revision": versioned.revision},
            task_ref=task_id,
        )
        return "queued"

    def next_queued(self) -> TaskSummary | None:
        candidates = [
            summary
            for summary in self._store.list_tasks()
            if not summary.archived
            and summary.status == TaskStatus.TODO
            and summary.phase == TaskPhase.QUEUED
            and summary.queue_state == "queued"
        ]
        if not candidates:
            return None
        return self._ordered(candidates)[0]


__all__ = ["QueuePosition", "TaskQueue"]
