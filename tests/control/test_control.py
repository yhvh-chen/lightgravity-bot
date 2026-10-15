"""LG-016 pause/cancel/resume/retry/reopen control semantics.

These are unit tests over the coordinator control seam using a deterministic
in-process dispatcher.  They are explicitly **not** real SDK evidence; the
bounded real SDK cancel/resume/close path is recorded separately in the LG-016
implementation record.
"""

from __future__ import annotations

import asyncio
from typing import Any

from lightgravity.adapter import CancelResult
from lightgravity.coordinator import Coordinator, RunController
from lightgravity.coordinator.dispatcher import DispatchContext, DispatchOutcome
from lightgravity.contracts import TaskPhase
from lightgravity.store import FileStore, new_id

from coordinator_helpers import raw_task, wait_for_phase


class ControllableDispatcher:
    """Blocks in ``executing`` until cancelled; reports a chosen confirmation."""

    name = "controllable"

    def __init__(self, *, cancel_confirmed: bool = True) -> None:
        self.cancel_confirmed = cancel_confirmed
        self.cancel_calls = 0
        self.started = asyncio.Event()
        self._blocker = asyncio.Event()

    async def dispatch(
        self,
        context: DispatchContext,
        controller: RunController,
        emit: Any,
    ) -> DispatchOutcome:
        controller.set_task_phase("recruiting")
        controller.set_run_state("recruiting")
        controller.set_task_phase("executing")
        controller.set_run_state("executing")
        self.started.set()
        await self._blocker.wait()
        return DispatchOutcome(state="succeeded", summary="controllable")

    async def cancel(self, task_id: str, run_id: str) -> CancelResult:
        self.cancel_calls += 1
        # Only release the blocker on a confirmed stop, so an unconfirmed path
        # keeps the Run genuinely in flight.
        if self.cancel_confirmed:
            self._blocker.set()
        return CancelResult(
            confirmed=self.cancel_confirmed,
            state="cancelled" if self.cancel_confirmed else "unconfirmed",
            reason="controllable cancel",
        )


def _make(store: FileStore, dispatcher: ControllableDispatcher) -> Coordinator:
    return Coordinator(store, dispatcher=dispatcher)


async def _running_task(store: FileStore, dispatcher: ControllableDispatcher):
    coordinator = _make(store, dispatcher)
    coordinator.start()
    task_id = coordinator.create_task("req-run", "T", "do").task_id
    assert task_id is not None
    await asyncio.wait_for(dispatcher.started.wait(), timeout=5)
    await wait_for_phase(coordinator, task_id, {"executing"})
    return coordinator, task_id


async def test_pause_confirmed_releases_slot(store: FileStore) -> None:
    dispatcher = ControllableDispatcher()
    coordinator, task_id = await _running_task(store, dispatcher)
    try:
        result = await coordinator.request_control(
            task_id, "pause", request_id="req-pause-1"
        )
        assert result.data["confirmed"] is True
        snapshot = coordinator.status(task_id)
        assert snapshot["phase"] == TaskPhase.PAUSED.value
        assert snapshot["queue"]["state"] != "claimed"
        run = store.read("run", store.read("task", task_id).entity["active_run"]).entity
        assert run["state"] == "paused"
        assert run["cleanup"]["status"] == "done"
    finally:
        await coordinator.stop()


async def test_pause_unconfirmed_stays_pausing_with_diagnostics(
    store: FileStore,
) -> None:
    dispatcher = ControllableDispatcher(cancel_confirmed=False)
    coordinator, task_id = await _running_task(store, dispatcher)
    try:
        result = await coordinator.request_control(
            task_id, "pause", request_id="req-pause-unc"
        )
        assert result.data["confirmed"] is False
        assert coordinator.status(task_id)["phase"] == TaskPhase.PAUSING.value
        assert coordinator.status(task_id)["active_run"] is not None
        errors = [
            r.event for r in store.read_events(task_id)
            if r.event.get("type") == "error.recorded"
        ]
        assert any(
            e["payload"].get("code") == "cancellation_unconfirmed" for e in errors
        )
    finally:
        await coordinator.stop()


async def test_cancel_unconfirmed_never_writes_cancelled(store: FileStore) -> None:
    dispatcher = ControllableDispatcher(cancel_confirmed=False)
    coordinator, task_id = await _running_task(store, dispatcher)
    try:
        result = await coordinator.request_control(
            task_id, "cancel", request_id="req-cancel-unc"
        )
        assert result.data["confirmed"] is False
        assert coordinator.status(task_id)["phase"] == TaskPhase.CANCELLING.value
        assert coordinator.status(task_id)["active_run"] is not None
    finally:
        await coordinator.stop()


async def test_duplicate_control_request_is_idempotent(store: FileStore) -> None:
    dispatcher = ControllableDispatcher()
    coordinator, task_id = await _running_task(store, dispatcher)
    try:
        first = await coordinator.request_control(
            task_id, "cancel", request_id="req-dup"
        )
        assert first.data["confirmed"] is True
        calls_after_first = dispatcher.cancel_calls
        second = await coordinator.request_control(
            task_id, "cancel", request_id="req-dup"
        )
        assert second.data["confirmed"] is True
        assert dispatcher.cancel_calls == calls_after_first
    finally:
        await coordinator.stop()


async def test_resume_after_pause_requeues_without_second_writer(
    store: FileStore,
) -> None:
    dispatcher = ControllableDispatcher()
    blocker = dispatcher._blocker
    coordinator, task_id = await _running_task(store, dispatcher)
    try:
        await coordinator.request_control(task_id, "pause", request_id="req-p1")
        assert coordinator.status(task_id)["phase"] == TaskPhase.PAUSED.value
        result = await coordinator.request_control(
            task_id, "resume", request_id="req-r1"
        )
        assert result.data["confirmed"] is True
        snapshot = coordinator.status(task_id)
        assert snapshot["phase"] in {
            TaskPhase.QUEUED.value,
            TaskPhase.PLANNING.value,
            TaskPhase.EXECUTING.value,
        }
        await asyncio.sleep(0.15)
        runs = [
            data
            for (kind, _), data in _iter_entities(store)
            if kind == "run" and data.get("task_ref") == task_id
        ]
        non_terminal = [
            r for r in runs if r.get("state") not in {"completed", "cancelled", "failed", "paused"}
        ]
        assert len(non_terminal) <= 1
    finally:
        blocker.set()
        await coordinator.stop()


async def test_concurrent_resume_creates_no_second_writer(store: FileStore) -> None:
    """Two resumes racing must not open two non-terminal Runs for one Task."""

    dispatcher = ControllableDispatcher()
    blocker = dispatcher._blocker
    coordinator, task_id = await _running_task(store, dispatcher)
    try:
        await coordinator.request_control(task_id, "pause", request_id="req-cp")
        await asyncio.gather(
            coordinator.request_control(task_id, "resume", request_id="req-cr-1"),
            coordinator.request_control(task_id, "resume", request_id="req-cr-2"),
            return_exceptions=True,
        )
        await asyncio.sleep(0.2)
        runs = [
            data
            for (kind, _), data in _iter_entities(store)
            if kind == "run" and data.get("task_ref") == task_id
        ]
        non_terminal = [
            r
            for r in runs
            if r.get("state")
            not in {"completed", "cancelled", "failed", "paused"}
        ]
        assert len(non_terminal) <= 1, non_terminal
    finally:
        blocker.set()
        await coordinator.stop()


def test_resume_rejected_while_run_still_live(store: FileStore) -> None:
    # A paused-phase Task whose Run is still non-terminal must not requeue.
    task_id = raw_task(store, status="in-progress", phase="paused")
    run_id = new_id("run")
    store.create(
        "run",
        run_id,
        {
            "task_ref": task_id,
            "attempt": 1,
            "state": "executing",
            "plan_ref": "PLAN.md",
            "team_refs": [],
            "subtask_refs": [],
            "session_refs": [],
            "cleanup": {"status": "pending"},
            "ended_at": None,
            "fail_reason": None,
        },
        actor="test",
        request_id=f"run:{run_id}",
        body="# Run\n",
    )
    from lightgravity.coordinator.state import StateWriter

    StateWriter(store, actor="test").set_active_run(task_id, run_id)
    coordinator = Coordinator(store, dispatcher=ControllableDispatcher())
    result = coordinator.control.requeue(task_id, "resume")
    assert result.confirmed is False
    assert "still holds the slot" in (result.reason or "")


async def test_retry_after_failure_enqueues(store: FileStore) -> None:
    task_id = raw_task(store, status="in-progress", phase="failed")
    coordinator = Coordinator(store, dispatcher=ControllableDispatcher())
    result = await coordinator.request_control(task_id, "retry", request_id="req-retry")
    assert result.data["confirmed"] is True
    assert store.read("task", task_id).entity["phase"] == TaskPhase.QUEUED.value


async def test_reopen_completed_task_bumps_requirements(store: FileStore) -> None:
    task_id = raw_task(store, status="done", phase="completed")
    coordinator = Coordinator(store, dispatcher=ControllableDispatcher())
    before = store.read("task", task_id).entity["requirements_revision"]
    result = await coordinator.request_control(
        task_id, "reopen", request_id="req-reopen"
    )
    assert result.data["confirmed"] is True
    after = store.read("task", task_id).entity
    assert after["requirements_revision"] == before + 1
    assert after["acceptance"]["status"] == "pending"


async def test_cancel_message_does_not_wait_for_worker(store: FileStore) -> None:
    dispatcher = ControllableDispatcher()
    coordinator, task_id = await _running_task(store, dispatcher)
    try:
        # The blocking gate is still closed: the control message path must not
        # wait for the code task to finish on its own.
        assert not dispatcher._blocker.is_set()
        from coordinator_helpers import message

        result = await coordinator.submit_task_message(
            task_id, message("取消", message_id="msg-c-1")
        )
        assert result.kind == "control"
        assert coordinator.status(task_id)["phase"] == TaskPhase.CANCELLED.value
    finally:
        await coordinator.stop()


class SessionEmittingDispatcher(ControllableDispatcher):
    """Emits a real ``adapter.session_started`` event mid-execution."""

    async def dispatch(self, context, controller, emit):
        result = emit(
            {
                "type": "adapter.session_started",
                "session": {
                    "session_id": "sess_real_1",
                    "conversation_id": "conv_real_1",
                    "state": "created",
                },
            }
        )
        if asyncio.iscoroutine(result) or hasattr(result, "__await__"):
            await result
        return await super().dispatch(context, controller, emit)


async def test_adapter_session_is_recorded_on_run(store: FileStore) -> None:
    """The real SDK session is persisted so the stop gate can confirm closure.

    ``adapter.session_started`` is recorded on the Run's ``session_refs``
    exactly once, and the control-confirmed stop then marks cleanup done so
    the stop gate sees every session closed.
    """

    dispatcher = SessionEmittingDispatcher()
    coordinator, task_id = await _running_task(store, dispatcher)
    active_run = store.read("task", task_id).entity["active_run"]
    try:
        run = store.read("run", active_run).entity
        assert list(run["session_refs"]) == ["sess_real_1"]
        result = await coordinator.request_control(
            task_id, "pause", request_id="req-session-pause"
        )
        assert result.data["confirmed"] is True
        run = store.read("run", active_run).entity
        assert run["cleanup"]["status"] == "done"
        assert list(run["session_refs"]) == ["sess_real_1"]
    finally:
        await coordinator.stop()


async def test_cleanup_failure_is_recorded_without_masking_stop(
    store: FileStore,
) -> None:
    """A cleanup problem is reported on the Run and never hides the stop.

    The stop was genuinely confirmed, so the Task still reaches ``paused``; the
    cleanup failure is recorded independently (Run field + error event) and no
    original diff/worktree/history is removed by this path.
    """

    dispatcher = ControllableDispatcher()
    coordinator, task_id = await _running_task(store, dispatcher)
    active_run = store.read("task", task_id).entity["active_run"]

    # Force only the successful-cleanup bookkeeping write to fail.
    writer = coordinator.control._writer  # type: ignore[attr-defined]
    original = writer.write_run
    calls: list[Any] = []

    def failing_write_run(run_id: str, updates: dict[str, Any]):
        calls.append(updates)
        if (
            run_id == active_run
            and isinstance(updates, dict)
            and updates.get("cleanup", {}).get("status") == "done"
        ):
            raise RuntimeError("simulated cleanup failure")
        return original(run_id, updates)

    writer.write_run = failing_write_run  # type: ignore[method-assign]
    try:
        result = await coordinator.request_control(
            task_id, "cancel", request_id="req-cleanup-fail"
        )
        # The stop is genuinely confirmed; cleanup trouble must not mask it.
        assert result.data["confirmed"] is True
        assert result.data.get("cleanup") == "failed"
        assert coordinator.status(task_id)["phase"] == TaskPhase.CANCELLED.value
        run = store.read("run", active_run).entity
        assert run["cleanup"]["status"] == "failed"
        cleanup_events = [
            r.event
            for r in store.read_events(task_id)
            if r.event.get("type") == "cleanup.updated"
        ]
        assert any(
            e["payload"].get("status") == "failed" for e in cleanup_events
        )
    finally:
        writer.write_run = original  # type: ignore[method-assign]
        await coordinator.stop()


async def test_shutdown_is_not_user_cancel(store: FileStore) -> None:
    """Stopping the service must not fabricate a terminal state.

    A shutdown mid-execution leaves the Run non-terminal; the restart scan must
    then require an explicit recovery decision instead of replaying it or
    writing ``cancelled``/``failed``.
    """

    from lightgravity.coordinator.recovery import RecoveryScanner
    from lightgravity.coordinator.state import StateWriter

    dispatcher = ControllableDispatcher()
    coordinator, task_id = await _running_task(store, dispatcher)
    active_run = store.read("task", task_id).entity["active_run"]

    # Shutdown: cancel the worker loop without a user control request.
    await coordinator.stop()

    task = store.read("task", task_id).entity
    assert task["phase"] in {"executing", "planning", "recruiting"}
    assert task["phase"] not in {"cancelled", "failed", "completed"}
    assert store.read("run", active_run).entity["state"] not in {
        "cancelled",
        "failed",
        "completed",
    }

    # A restart scan sees the interrupted Run and refuses to auto-replay it.
    report = RecoveryScanner(store, StateWriter(store, actor="recovery")).scan()
    decisions = {d.task_id: d for d in report.decisions}
    assert decisions[task_id].action == "recovery_required"
    assert store.read("task", task_id).entity["phase"] == "recovery_required"


def _iter_entities(store: FileStore):
    ensure = getattr(store, "_ensure_index", None)
    if callable(ensure):
        ensure()
    entries = getattr(store, "_entries", {}) or {}
    for (kind, _), entry in entries.items():
        yield (kind, entry), entry.data
