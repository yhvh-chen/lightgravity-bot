"""LG-016 restart inspection and recovery-required semantics.

The scanner is exercised with an injected :class:`ProcessProbe` so tests never
depend on real host pids.  Conclusions: a Run interrupted by a restart is never
auto-replayed (unknown side effects go to ``recovery_required``); a live worker
is left alone; a terminal Run or stopped-but-unaccepted Run never keeps the
execution slot.
"""

from __future__ import annotations

from lightgravity.contracts import TaskPhase
from lightgravity.coordinator.recovery import RecoveryScanner
from lightgravity.coordinator.state import StateWriter
from lightgravity.store import FileStore, new_id

from coordinator_helpers import raw_task


class _Probe:
    def __init__(self, alive: dict[int, bool]) -> None:
        self._alive = alive
        self.calls: list[int] = []

    def is_alive(self, pid: int) -> bool:
        self.calls.append(pid)
        return self._alive.get(pid, False)


def _make_run(store: FileStore, task_id: str, *, state: str, pid: int | None) -> str:
    run_id = new_id("run")
    content = {
        "task_ref": task_id,
        "attempt": 1,
        "state": state,
        "plan_ref": "PLAN.md",
        "team_refs": [],
        "subtask_refs": [],
        "session_refs": [],
        "cleanup": {"status": "pending"},
        "ended_at": None,
        "fail_reason": None,
        "worker_pid": pid,
    }
    store.create("run", run_id, content, actor="test", request_id=f"run:{run_id}", body="# Run\n")
    StateWriter(store, actor="test").set_active_run(task_id, run_id)
    return run_id


def _claim(store: FileStore, task_id: str) -> None:
    store.claim(task_id, "coordinator:dead", lease_seconds=300)


def test_interrupted_run_with_dead_worker_requires_recovery(store: FileStore) -> None:
    task_id = raw_task(store, status="in-progress", phase="executing")
    _make_run(store, task_id, state="executing", pid=4242)
    _claim(store, task_id)
    scanner = RecoveryScanner(
        store, StateWriter(store, actor="recovery"), probe=_Probe({4242: False})
    )
    report = scanner.scan()
    decisions = {d.task_id: d for d in report.decisions}
    assert decisions[task_id].action == "recovery_required"
    assert decisions[task_id].alive is False
    entity = store.read("task", task_id).entity
    # Never auto-replayed; requires an explicit decision.
    assert entity["phase"] == TaskPhase.RECOVERY_REQUIRED.value
    assert entity["queue"]["state"] == "not_queued"
    errors = [
        r.event for r in store.read_events(task_id)
        if r.event.get("type") == "error.recorded"
    ]
    assert any(e["payload"].get("code") == "recovery_required" for e in errors)


def test_interrupted_run_unknown_liveness_is_conservative(store: FileStore) -> None:
    task_id = raw_task(store, status="in-progress", phase="executing")
    _make_run(store, task_id, state="executing", pid=None)
    scanner = RecoveryScanner(
        store, StateWriter(store, actor="recovery"), probe=_Probe({})
    )
    report = scanner.scan()
    decisions = {d.task_id: d for d in report.decisions}
    assert decisions[task_id].action == "recovery_required"
    assert decisions[task_id].alive is None
    assert store.read("task", task_id).entity["phase"] == "recovery_required"


def test_live_worker_is_left_alone(store: FileStore) -> None:
    task_id = raw_task(store, status="in-progress", phase="executing")
    _make_run(store, task_id, state="executing", pid=777)
    scanner = RecoveryScanner(
        store, StateWriter(store, actor="recovery"), probe=_Probe({777: True})
    )
    report = scanner.scan()
    decisions = {d.task_id: d for d in report.decisions}
    assert decisions[task_id].action == "none"
    assert decisions[task_id].alive is True
    # The Task and its Run are untouched.
    assert store.read("task", task_id).entity["phase"] == "executing"


def test_terminal_run_still_marked_active_releases_slot(store: FileStore) -> None:
    task_id = raw_task(store, status="in-progress", phase="executing")
    _make_run(store, task_id, state="cancelled", pid=None)
    _claim(store, task_id)
    scanner = RecoveryScanner(
        store, StateWriter(store, actor="recovery"), probe=_Probe({})
    )
    report = scanner.scan()
    decisions = {d.task_id: d for d in report.decisions}
    assert decisions[task_id].action == "release_stale_claim"
    entity = store.read("task", task_id).entity
    assert entity["active_run"] is None
    assert entity["queue"]["state"] == "not_queued"


def test_awaiting_acceptance_claim_is_released(store: FileStore) -> None:
    task_id = raw_task(store, status="in-progress", phase="awaiting_acceptance")
    _make_run(store, task_id, state="completed", pid=None)
    _claim(store, task_id)
    scanner = RecoveryScanner(
        store, StateWriter(store, actor="recovery"), probe=_Probe({})
    )
    report = scanner.scan()
    decisions = {d.task_id: d for d in report.decisions}
    assert decisions[task_id].action == "release_stale_claim"
    assert store.read("task", task_id).entity["queue"]["state"] == "not_queued"


def test_queued_task_is_untouched(store: FileStore) -> None:
    task_id = raw_task(store, status="todo", phase="queued")
    scanner = RecoveryScanner(
        store, StateWriter(store, actor="recovery"), probe=_Probe({})
    )
    report = scanner.scan()
    assert all(d.task_id != task_id for d in report.decisions)


def test_missing_active_run_is_cleared(store: FileStore) -> None:
    task_id = raw_task(store, status="in-progress", phase="executing")
    StateWriter(store, actor="test").set_active_run(task_id, "run_missing")
    scanner = RecoveryScanner(
        store, StateWriter(store, actor="recovery"), probe=_Probe({})
    )
    scanner.scan()
    assert store.read("task", task_id).entity["active_run"] is None
