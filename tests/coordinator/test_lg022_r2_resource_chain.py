"""LG-022 R2: a session-bearing Run must reach acceptance through the real gate.

The R1 stop-gate deadlock only manifests for a Run that recorded real
``session_refs`` -- the earlier coordinator tests used a dispatcher double with
``session_refs: []`` and so never exercised the gate.  This test drives the
**real coordinator worker loop** with a dispatcher that persists a real session
ref (like the SDK adapter does) plus a real stop-confirmation port, and asserts
the candidate is released to ``awaiting_acceptance`` without deleting the refs
or fabricating ``cleanup=done``.  An unconfirmable session keeps it deadlocked.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any

from lightgravity.coordinator import Coordinator
from lightgravity.store import FileStore, new_id
from lightgravity.verify import StoreResourceStopper, VerificationService
from lightgravity.verify.review import ReviewReport

from coordinator_helpers import wait_for_phase
from test_rework_integration import _seed_task

REVIEW_PASSED = "passed"


class SessionRecordingDispatcher:
    """Dispatcher double that persists a real ``session_refs`` on the Run.

    Mirrors the adapter's real success shape: the Run ends ``verifying`` with a
    non-empty ``session_refs`` and ``cleanup.status == 'pending'``.  No test
    tolerance for a session-less fake -- this is the shape that deadlocked.
    """

    name = "session-recording-fake"

    def __init__(self, session_id: str, *, close_on_dispatch: bool = True) -> None:
        self.session_id = session_id
        # The real ``AntigravityExecutor.execute`` closes the SDK agent and stops
        # the loopback proxy in its ``finally`` *before* returning the outcome, so
        # by the time verification runs the session is provably closed.  Mirror
        # that here; keep it open to exercise the unconfirmed branch.
        self._close_on_dispatch = close_on_dispatch
        self.session_open = True

    async def dispatch(self, context: Any, controller: Any, emit: Any) -> Any:
        from lightgravity.coordinator.dispatcher import DispatchOutcome

        controller.set_task_phase("recruiting")
        controller.set_run_state("recruiting")
        controller.set_task_phase("executing")
        controller.set_run_state("executing")
        subtask_id = new_id("subtask")
        controller.create_subtask(
            subtask_id,
            {
                "run_ref": context.run_id,
                "state": "passed",
                "depends_on": [],
                "assignee_member_ref": None,
                "upstream_artifact_refs": [],
                "objective": "deliver",
                "capability": "implementation",
                "key": "deliver",
                "write": True,
                "config_hash": None,
                "fail_reason": None,
                "blocked_by": [],
                "acceptance": {
                    "status": "passed",
                    "criteria": list(context.acceptance_criteria),
                    "evidence_refs": [],
                },
            },
            body="# Subtask deliver\n",
        )
        controller.update_run(
            {"subtask_refs": [subtask_id], "session_refs": [self.session_id]}
        )
        # Real executor teardown happens before the outcome is returned; the Run
        # keeps ``session_refs`` and ``cleanup=pending`` (never fabricated done).
        if self._close_on_dispatch:
            self.session_open = False
        return DispatchOutcome(state="succeeded", summary="session-recording-fake")

    async def cancel(self, task_id: str, run_id: str) -> Any:
        from lightgravity.adapter import CancelResult

        return CancelResult(confirmed=True, state="cancelled")


class _StopConfirmer:
    """Stand-in for the real adapter's ``confirm_stopped`` fact source."""

    def __init__(self, session_id: str, dispatcher: SessionRecordingDispatcher) -> None:
        self.session_id = session_id
        self.dispatcher = dispatcher

    def confirm_stopped(self, run_id: str, session_refs: tuple[str, ...]) -> Any:
        from lightgravity.adapter.execution import StopConfirmation

        # Mirrors AntigravityExecutor: the session is only confirmed when the
        # dispatcher reports its real session closed.
        closed = not self.dispatcher.session_open
        unknown = () if closed and self.session_id in session_refs else tuple(session_refs)
        return StopConfirmation(
            run_id=run_id,
            confirmed=closed and not unknown,
            sessions_total=len(session_refs),
            sessions_stopped=0 if unknown else len(session_refs),
            proxy_stopped=closed,
            unknown_sessions=unknown,
            problems=() if closed else ("session still open",),
        )


class PassingReviewer:
    name = "pass-reviewer"
    kind = "model"

    def review(self, context: Any) -> ReviewReport:
        return ReviewReport(
            outcome=REVIEW_PASSED,
            candidate_ref=context.candidate.candidate_ref,
            reviewer=self.name,
            reviewer_kind=self.kind,
        )


def _wire(coordinator: Coordinator, reviewer: Any, stopper: Any) -> None:
    from lightgravity.verify.rework import ReworkOrchestrator

    coordinator.set_verification(
        VerificationService(coordinator.store, stopper=stopper)
    )
    coordinator.set_rework(
        ReworkOrchestrator(
            coordinator.store, reviewer=reviewer, spawner=coordinator, actor="test"
        )
    )


async def test_session_bearing_run_reaches_acceptance_via_real_stop(store: FileStore) -> None:
    session_id = "sess_real_1"
    dispatcher = SessionRecordingDispatcher(session_id)
    confirmer = _StopConfirmer(session_id, dispatcher)
    stopper = StoreResourceStopper(store, session_confirmer=confirmer)
    coordinator = Coordinator(store, dispatcher=dispatcher)
    _wire(coordinator, PassingReviewer(), stopper)
    task_id = _seed_task(coordinator)
    coordinator.start()
    try:
        # The session is closed by the dispatcher (like the real executor's
        # ``finally``); the stop gate must confirm it via the real fact source.
        phase = await wait_for_phase(
            coordinator, task_id, {"awaiting_acceptance"}, timeout=8.0
        )
    finally:
        await coordinator.stop()
    assert phase == "awaiting_acceptance"
    task = store.read("task", task_id).entity
    run_id = task.get("active_run") or task.get("last_run")
    run = store.read("run", run_id).entity
    # The real session refs are preserved (never deleted to bypass the gate).
    assert run["session_refs"] == [session_id]
    assert run["state"] in {"verifying", "awaiting_acceptance"}


async def test_open_session_keeps_run_unconfirmed(store: FileStore) -> None:
    """An unconfirmable (still-open) session must NOT reach acceptance."""

    session_id = "sess_never_closed"
    dispatcher = SessionRecordingDispatcher(session_id, close_on_dispatch=False)
    confirmer = _StopConfirmer(session_id, dispatcher)
    stopper = StoreResourceStopper(store, session_confirmer=confirmer)
    coordinator = Coordinator(store, dispatcher=dispatcher)
    _wire(coordinator, PassingReviewer(), stopper)
    task_id = _seed_task(coordinator)
    coordinator.start()
    try:
        # Give the loop time to run review+verify; the session stays open.
        await asyncio.sleep(0.6)
        task = store.read("task", task_id).entity
        phase = task["phase"]
        run_id = task.get("active_run") or task.get("last_run")
        run = store.read("run", run_id).entity
    finally:
        await coordinator.stop()
    assert phase != "awaiting_acceptance"
    assert run["session_refs"] == [session_id]
    assert run["cleanup"]["status"] == "pending"


def test_reviewer_stop_fact_is_recorded_on_run(store: FileStore) -> None:
    """A real reviewer teardown fact is persisted to the Run (LG-022 R2)."""

    from lightgravity.coordinator import Coordinator as _Coord
    from lightgravity.verify.rework import ReworkResult

    coordinator = _Coord(store)
    task_id = _seed_task(coordinator)
    # Create a Run to attach the reviewer fact to.
    from lightgravity.coordinator.state import StateWriter

    writer = StateWriter(store, actor="test")
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
        },
        actor="test",
        request_id=f"req-{run_id}",
        body=f"# Run {run_id}\n",
    )
    outcome = ReworkResult(
        state="awaiting_acceptance",
        task_id=task_id,
        phase="verifying",
        confirmed=True,
        reviewer_stop_fact={"confirmed": True, "agent_closed": True, "proxy_stopped": True},
    )
    coordinator._record_reviewer_stop(run_id, outcome)
    run = store.read("run", run_id).entity
    assert run["reviewer_cleanup"]["confirmed"] is True
    assert run["reviewer_cleanup"]["status"] == "done"
    assert writer is not None
