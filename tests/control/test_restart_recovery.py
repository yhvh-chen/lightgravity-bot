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


def test_waiting_user_verifying_restart_parks_without_inventing_stop(store: FileStore) -> None:
    task_id = raw_task(store, status="in-progress", phase="waiting_user")
    run_id = _make_run(store, task_id, state="verifying", pid=None)
    writer = StateWriter(store, actor="test")
    writer.write_run(run_id, {"session_refs": ["old-session"], "cleanup": {"status": "pending"}})
    report = RecoveryScanner(store, writer, probe=_Probe({})).scan()
    assert report.recovery_required[0].task_id == task_id
    assert store.read("task", task_id).entity["phase"] == "recovery_required"
    assert store.read("task", task_id).entity["active_run"] == run_id
    run = store.read("run", run_id).entity
    assert run["state"] == "verifying"
    assert run["cleanup"]["status"] == "pending"
    assert run["session_refs"] == ["old-session"]


async def test_restart_unknown_stop_keeps_slot_and_resume_blocked(store: FileStore) -> None:
    from lightgravity.coordinator import Coordinator, GraphDispatcher
    from lightgravity.coordinator.dispatcher import UnavailableExecutor

    task_id = raw_task(store, status="in-progress", phase="waiting_user")
    run_id = _make_run(store, task_id, state="verifying", pid=None)
    writer = StateWriter(store, actor="test")
    writer.write_run(run_id, {"session_refs": ["old-session"]})
    coordinator = Coordinator(store, dispatcher=GraphDispatcher(store, UnavailableExecutor()))
    coordinator._recovery.scan()
    resume = await coordinator.request_control(task_id, "resume", request_id="blocked-resume")
    assert resume.data["confirmed"] is False
    cancel = await coordinator.request_control(task_id, "cancel", request_id="unknown-cancel")
    assert cancel.data["confirmed"] is False
    assert "not confirmed stopped" in cancel.data["reason"]
    task = store.read("task", task_id).entity
    assert task["phase"] == "recovery_required"
    assert task["active_run"] == run_id
    assert store.read("run", run_id).entity["cleanup"]["status"] == "pending"
    assert store.read("run", run_id).entity["state"] == "verifying"


async def test_restart_proven_cleanup_can_cancel_then_retry(store: FileStore) -> None:
    from lightgravity.coordinator import Coordinator, GraphDispatcher
    from lightgravity.coordinator.dispatcher import UnavailableExecutor

    task_id = raw_task(store, status="in-progress", phase="waiting_user")
    run_id = _make_run(store, task_id, state="verifying", pid=None)
    writer = StateWriter(store, actor="test")
    writer.write_run(run_id, {"session_refs": ["closed-session"], "cleanup": {"status": "done"}})
    coordinator = Coordinator(store, dispatcher=GraphDispatcher(store, UnavailableExecutor()))
    coordinator._recovery.scan()
    cancel = await coordinator.request_control(task_id, "cancel", request_id="proven-cancel")
    assert cancel.data["confirmed"] is True
    assert store.read("task", task_id).entity["active_run"] is None
    assert store.read("run", run_id).entity["state"] == "cancelled"
    retry = await coordinator.request_control(task_id, "retry", request_id="proven-retry")
    assert retry.data["confirmed"] is True
    assert store.read("task", task_id).entity["phase"] == "queued"
    assert store.read("run", run_id).entity["session_refs"] == ["closed-session"]


async def test_idle_waiting_pause_does_not_invent_stop(store: FileStore) -> None:
    from lightgravity.coordinator import Coordinator, GraphDispatcher
    from lightgravity.coordinator.dispatcher import UnavailableExecutor

    task_id = raw_task(store, status="in-progress", phase="waiting_user")
    run_id = _make_run(store, task_id, state="verifying", pid=None)
    coordinator = Coordinator(store, dispatcher=GraphDispatcher(store, UnavailableExecutor()))
    result = await coordinator.request_control(task_id, "pause", request_id="unknown-pause")
    assert result.data["confirmed"] is False
    assert store.read("task", task_id).entity["phase"] == "waiting_user"
    assert store.read("task", task_id).entity["active_run"] == run_id


async def test_adapter_stop_fact_can_confirm_pending_cleanup(store: FileStore) -> None:
    from types import SimpleNamespace
    from lightgravity.coordinator import Coordinator, GraphDispatcher
    from lightgravity.coordinator.dispatcher import UnavailableExecutor

    class StoppedAdapter(UnavailableExecutor):
        def confirm_stopped(self, run_id, session_refs):
            assert session_refs == ("closed-session",)
            return SimpleNamespace(confirmed=True)

    task_id = raw_task(store, status="in-progress", phase="waiting_user")
    run_id = _make_run(store, task_id, state="verifying", pid=None)
    StateWriter(store, actor="test").write_run(run_id, {"session_refs": ["closed-session"]})
    coordinator = Coordinator(store, dispatcher=GraphDispatcher(store, StoppedAdapter()))
    coordinator._recovery.scan()
    result = await coordinator.request_control(task_id, "cancel", request_id="adapter-cancel")
    assert result.data["confirmed"] is True
    assert store.read("run", run_id).entity["cleanup"]["status"] == "done"


async def test_pending_reviewer_cleanup_blocks_idle_cancel(store: FileStore) -> None:
    from lightgravity.coordinator import Coordinator, GraphDispatcher
    from lightgravity.coordinator.dispatcher import UnavailableExecutor

    task_id = raw_task(store, status="in-progress", phase="waiting_user")
    run_id = _make_run(store, task_id, state="verifying", pid=None)
    StateWriter(store, actor="test").write_run(run_id, {
        "cleanup": {"status": "done"},
        "reviewer_cleanup": {"status": "pending", "confirmed": False},
    })
    coordinator = Coordinator(store, dispatcher=GraphDispatcher(store, UnavailableExecutor()))
    coordinator._recovery.scan()
    result = await coordinator.request_control(task_id, "cancel", request_id="reviewer-unknown")
    assert result.data["confirmed"] is False
    assert store.read("task", task_id).entity["active_run"] == run_id
    assert store.read("run", run_id).entity["state"] == "verifying"


def test_recovery_write_failure_does_not_report_success(store: FileStore, monkeypatch) -> None:
    task_id = raw_task(store, status="in-progress", phase="waiting_user")
    _make_run(store, task_id, state="verifying", pid=None)
    writer = StateWriter(store, actor="test")

    def fail(*args, **kwargs):
        raise RuntimeError("fixture storage failure")

    monkeypatch.setattr(writer, "transition_task", fail)
    report = RecoveryScanner(store, writer, probe=_Probe({})).scan()
    assert report.recovery_required == []
    assert report.decisions[0].action == "none"
    assert store.read("task", task_id).entity["phase"] == "waiting_user"
    errors = [record.event for record in store.read_events(task_id)]
    assert any(event.get("payload", {}).get("code") == "recovery_transition_failed" for event in errors)
