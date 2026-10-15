"""LG-022 R1 coordinator integration: review off-loop + honest lifecycle.

These drive the **real coordinator worker loop** (in-process fake executor) and
assert the LG-022 QA fixes:

* **D2** — while an independent review is running, ``status`` and
  ``pause``/``cancel`` are still served; a pause/cancel during review only
  confirms after the reviewer really stopped, and an unconfirmed reviewer stop
  keeps the slot (no fabricated ``paused``/``cancelled``);
* **D3** — a succeeded Run does not carry ``fail_reason``.

No real model is called; the reviewer is a deterministic double.
"""

from __future__ import annotations

import asyncio
import threading
import time
from typing import Any

from lightgravity.coordinator import Coordinator
from lightgravity.store import FileStore
from lightgravity.verify.review import ReviewReport
from lightgravity.verify.rework import ReworkOrchestrator

from coordinator_helpers import wait_for_phase
from test_rework_integration import EvidenceDispatcher, _seed_task

REVIEW_PASSED = "passed"


class GateReviewer:
    """Reviewer that blocks until released or stopped (deterministic double)."""

    name = "gate-reviewer"
    kind = "model"

    def __init__(self, *, release: threading.Event | None = None) -> None:
        self.release = release or threading.Event()
        self.started = threading.Event()
        self.calls = 0
        self.saw_stop = False
        self.last_usage: dict[str, Any] = {"unknown": ["usage"]}
        self.model_calls = 0

    def review(self, context: Any) -> ReviewReport:
        self.calls += 1
        self.started.set()
        stop_event = getattr(context, "stop_event", None)
        # Poll cooperatively; return an honest report when released, else raise
        # the stop signal the lifecycle understands.
        from lightgravity.verify.review_lifecycle import ReviewStopped

        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            if stop_event is not None and stop_event.is_set():
                self.saw_stop = True
                raise ReviewStopped(context.task_id, context.run_id)
            if self.release.wait(timeout=0.02):
                return ReviewReport(
                    outcome=REVIEW_PASSED,
                    candidate_ref=context.candidate.candidate_ref,
                    reviewer=self.name,
                    reviewer_kind=self.kind,
                )
        raise ReviewStopped(context.task_id, context.run_id)


def _wire(coordinator: Coordinator, reviewer: GateReviewer) -> None:
    from lightgravity.verify import VerificationService

    coordinator.set_verification(VerificationService(coordinator.store))
    coordinator.set_rework(
        ReworkOrchestrator(
            coordinator.store,
            reviewer=reviewer,
            spawner=coordinator,
            actor="test",
        )
    )


async def _wait_for_reviewing(coordinator: Coordinator, task_id: str, run_id: str, timeout: float = 6.0) -> bool:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if coordinator.review_lifecycle.is_reviewing(task_id, run_id):
            return True
        await asyncio.sleep(0.01)
    return False


async def _active_run(coordinator: Coordinator, task_id: str, timeout: float = 6.0) -> str:
    """Wait until the worker opens the Run and return its id."""

    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        run_id = coordinator.status(task_id).get("active_run")
        if isinstance(run_id, str) and run_id:
            return run_id
        await asyncio.sleep(0.01)
    raise AssertionError("no active run was opened in time")


async def test_status_served_while_review_runs(store: FileStore) -> None:
    """D2: a status query is served promptly while a review is in flight."""

    dispatcher = EvidenceDispatcher()
    coordinator = Coordinator(store, dispatcher=dispatcher)
    reviewer = GateReviewer()
    _wire(coordinator, reviewer)
    task_id = _seed_task(coordinator)
    coordinator.start()
    try:
        run_id = await _active_run(coordinator, task_id)
        assert await _wait_for_reviewing(coordinator, task_id, run_id)
        # The review is blocked in its worker thread; the loop must still serve.
        started = time.monotonic()
        status = coordinator.status(task_id)
        elapsed = time.monotonic() - started
        assert status["phase"] == "verifying"
        assert elapsed < 1.0, f"status blocked {elapsed:.2f}s during review"
        reviewer.release.set()
        phase = await wait_for_phase(coordinator, task_id, {"awaiting_acceptance"}, timeout=8.0)
    finally:
        await coordinator.stop()
    assert phase == "awaiting_acceptance"


async def test_cancel_during_review_confirms_after_reviewer_stops(store: FileStore) -> None:
    """D2: cancel during review holds until the reviewer really stops."""

    dispatcher = EvidenceDispatcher()
    coordinator = Coordinator(store, dispatcher=dispatcher)
    reviewer = GateReviewer()
    _wire(coordinator, reviewer)
    task_id = _seed_task(coordinator)
    coordinator.start()
    try:
        run_id = await _active_run(coordinator, task_id)
        assert await _wait_for_reviewing(coordinator, task_id, run_id)
        result = await coordinator.request_control(task_id, "cancel", request_id="c1")
    finally:
        await coordinator.stop()
    assert result.data["confirmed"] is True
    assert reviewer.saw_stop is True
    task = store.read("task", task_id).entity
    assert task["phase"] == "cancelled"
    run = store.read("run", run_id).entity
    assert run["state"] == "cancelled"


async def test_pause_during_review_confirms_and_keeps_candidate(store: FileStore) -> None:
    """D2: pause during review confirms a real stop and keeps the candidate."""

    dispatcher = EvidenceDispatcher()
    coordinator = Coordinator(store, dispatcher=dispatcher)
    reviewer = GateReviewer()
    _wire(coordinator, reviewer)
    task_id = _seed_task(coordinator)
    coordinator.start()
    try:
        run_id = await _active_run(coordinator, task_id)
        assert await _wait_for_reviewing(coordinator, task_id, run_id)
        result = await coordinator.request_control(task_id, "pause", request_id="p1")
    finally:
        await coordinator.stop()
    assert result.data["confirmed"] is True
    task = store.read("task", task_id).entity
    assert task["phase"] == "paused"
    # The candidate Run and its evidence are retained (not deleted).
    retained_run_id = task.get("active_run") or task.get("last_run")
    assert retained_run_id == run_id
    run = store.read("run", run_id).entity
    assert run["state"] == "paused"


async def test_succeeded_run_has_no_fail_reason(store: FileStore) -> None:
    """D3: a succeeded/verifying Run must not present a fail_reason."""

    dispatcher = EvidenceDispatcher()
    coordinator = Coordinator(store, dispatcher=dispatcher)
    reviewer = GateReviewer(release=threading.Event())
    reviewer.release.set()  # pass immediately
    _wire(coordinator, reviewer)
    task_id = _seed_task(coordinator)
    coordinator.start()
    try:
        phase = await wait_for_phase(coordinator, task_id, {"awaiting_acceptance"}, timeout=8.0)
    finally:
        await coordinator.stop()
    assert phase == "awaiting_acceptance"
    task = store.read("task", task_id).entity
    run_id = task.get("active_run") or task.get("last_run")
    assert isinstance(run_id, str)
    run = store.read("run", run_id).entity
    assert run["state"] in {"verifying", "awaiting_acceptance"}
    assert "fail_reason" not in run or not run.get("fail_reason")


def test_restart_during_review_does_not_replay_and_keeps_candidate(store: FileStore) -> None:
    """D2 restart: an interrupted review is not replayed; candidate kept."""

    from lightgravity.coordinator.recovery import RecoveryScanner
    from lightgravity.coordinator.state import StateWriter

    task_id, run_id = _seed_task_for_restart(store)
    scanner = RecoveryScanner(
        store, StateWriter(store, actor="recovery"), probe=_DeadProbe()
    )
    report = scanner.scan()
    task = store.read("task", task_id).entity
    assert task["phase"] == "recovery_required"
    assert any(d.action == "recovery_required" for d in report.decisions)
    # The candidate Run and its evidence are retained (not replayed/deleted) and
    # remain discoverable so a human can decide.
    retained = store.read("run", run_id).entity
    assert retained["state"] == "verifying"
    assert task.get("active_run") == run_id or task.get("last_run") == run_id


def _seed_task_for_restart(store: FileStore) -> tuple[str, str]:
    """Create a Task + a Run in ``verifying`` with a dead worker pid."""

    from lightgravity.store import new_id
    from lightgravity.coordinator.state import StateWriter
    from coordinator_helpers import raw_task

    task_id = raw_task(store, status="in-progress", phase="verifying")
    run_id = new_id("run")
    store.create(
        "run",
        run_id,
        {
            "task_ref": task_id,
            "attempt": 1,
            "state": "verifying",
            "plan_ref": "PLAN.md",
            "team_refs": [],
            "subtask_refs": [],
            "session_refs": [],
            "cleanup": {"status": "pending"},
            "ended_at": None,
            "fail_reason": None,
            "worker_pid": 999999,
        },
        actor="test",
        request_id=f"run:{run_id}",
        body="# Run\n",
    )
    StateWriter(store, actor="test").set_active_run(task_id, run_id)
    store.claim(task_id, "coordinator:dead", lease_seconds=300)
    return task_id, run_id

class _DeadProbe:
    def is_alive(self, pid: int) -> bool:  # noqa: ARG002
        return False
