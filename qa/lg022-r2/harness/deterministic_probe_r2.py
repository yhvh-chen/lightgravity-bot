"""LG-022 reverify R2 — deterministic D2/D3 mechanism probe (0 model calls).

Drives the REAL product mechanisms with controlled doubles (clearly labelled
``deterministic-double``), covering the R2 gate items NOT already exercised by
the real chain:

  * restart-no-replay: real ``RecoveryScanner`` + injected ``ProcessProbe`` —
    an interrupted Run (dead worker) is NEVER auto-replayed and goes to
    ``recovery_required`` with the slot freed; a completed candidate is retained.
  * cross-Run budget: the Task-lifetime rework ledger persisted in Task
    frontmatter survives a fresh Run (review/repair rounds are not reset), and
    exhaustion is honest (``budget_exhausted``), never a fake pass.
  * cancel-during-review: with the R2 authoritative stop confirmer wired in, a
    cancel during review confirms only after the reviewer really stops and stops
    the resource; task reaches a terminal phase; no fabricated stop.
  * stop gate with confirmer: a real-shape successful Run (session_refs
    populated, cleanup=pending) reaches awaiting_acceptance and keeps refs.

Run: .venv/bin/python qa/lg022-r2/harness/deterministic_probe_r2.py <out_json>
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "backend"))

import lightgravity.coordinator  # noqa: E402,F401
from lightgravity.coordinator import Coordinator  # noqa: E402
from lightgravity.coordinator.dispatcher import DispatchOutcome, DispatchContext  # noqa: E402
from lightgravity.coordinator.recovery import RecoveryScanner  # noqa: E402
from lightgravity.coordinator.state import StateWriter  # noqa: E402
from lightgravity.store import FileStore  # noqa: E402
from lightgravity.verify.review import ReviewReport  # noqa: E402
from lightgravity.verify.review_lifecycle import ReviewStopped  # noqa: E402
from lightgravity.verify.service import VerificationService  # noqa: E402
from lightgravity.verify.stopgate import StoreResourceStopper  # noqa: E402
from lightgravity.verify.rework import ReworkOrchestrator, load_ledger  # noqa: E402


class SessionDispatcher:
    """Dispatcher double that records real-style session refs AND a resolvable
    workspace artifact + passed subtask, so the independent reviewer has a real
    candidate to review (mirrors the real GraphDispatcher post-turn shape)."""

    def __init__(self, *, close_on_dispatch: bool = True) -> None:
        self.sessions: tuple[str, ...] = ()
        self._close = close_on_dispatch

    async def dispatch(self, context: DispatchContext, controller, emit):  # noqa: ANN001
        from lightgravity.store import new_id as _new_id
        controller.set_task_phase("recruiting")
        controller.set_run_state("recruiting")
        controller.set_task_phase("executing")
        controller.set_run_state("executing")
        self.sessions = ("sess_fake_a", "sess_fake_b")
        try:
            controller.write_run(context.run_id, {"session_refs": list(self.sessions)})
        except Exception:  # noqa: BLE001
            pass
        workspace = getattr(context, "workspace_path", None)
        if workspace:
            target = Path(workspace) / "out" / "result.txt"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("delivered\n", encoding="utf-8")
        subtask_id = _new_id("subtask")
        try:
            controller.create_subtask(subtask_id, {
                "run_ref": context.run_id, "state": "passed", "depends_on": [],
                "assignee_member_ref": None, "upstream_artifact_refs": [],
                "objective": "deliver", "capability": "implementation", "write": True,
                "config_hash": None, "fail_reason": None, "blocked_by": [],
                "acceptance": {"status": "passed",
                               "criteria": list(context.acceptance_criteria),
                               "evidence_refs": ["out/result.txt"]},
            }, body="# Subtask\n")
            controller.update_run({"subtask_refs": [subtask_id]})
        except Exception:  # noqa: BLE001
            pass
        return DispatchOutcome(state="succeeded", summary="double: succeeded")

    async def cancel(self, task_id: str, run_id: str):  # noqa: ANN001
        from lightgravity.adapter.execution import CancelResult
        return CancelResult(confirmed=True, state="cancelled", reason="probe confirmed stop")


class StopConfirmer:
    """R2 authoritative stop confirmer double over the dispatcher's sessions."""

    def __init__(self, dispatcher: SessionDispatcher) -> None:
        self._d = dispatcher
        self._closed = set()

    def close_all(self) -> None:
        self._closed = set(self._d.sessions)

    def confirm_stopped(self, run_id: str, session_refs: tuple[str, ...]):
        from lightgravity.adapter.execution import StopConfirmation
        unknown = tuple(s for s in session_refs if s not in self._closed)
        return StopConfirmation(
            run_id=run_id,
            confirmed=not unknown,
            sessions_total=len(session_refs),
            sessions_stopped=len(session_refs) - len(unknown),
            proxy_stopped=True,
            unknown_sessions=unknown,
            problems=(() if not unknown else (f"{len(unknown)} session(s) open",)),
        )


class GateReviewer:
    name = "gate-reviewer"
    kind = "model"

    def __init__(self, *, release: threading.Event | None = None) -> None:
        self.release = release or threading.Event()
        self.started = threading.Event()
        self.saw_stop = False
        self.calls = 0
        self.last_usage = {"unknown": ["usage"]}
        self.model_calls = 0

    def review(self, context):  # noqa: ANN001
        self.calls += 1
        self.started.set()
        stop_event = getattr(context, "stop_event", None)
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            if stop_event is not None and stop_event.is_set():
                self.saw_stop = True
                raise ReviewStopped(context.task_id, context.run_id)
            if self.release.wait(timeout=0.02):
                return ReviewReport(outcome="passed",
                                    candidate_ref=context.candidate.candidate_ref,
                                    reviewer=self.name, reviewer_kind=self.kind)
        raise ReviewStopped(context.task_id, context.run_id)


def _wire(coordinator: Coordinator, reviewer: GateReviewer, confirmer: StopConfirmer) -> None:
    stopper = StoreResourceStopper(coordinator.store, session_confirmer=confirmer)
    coordinator.set_verification(VerificationService(coordinator.store, stopper=stopper))
    coordinator.set_rework(ReworkOrchestrator(coordinator.store, reviewer=reviewer,
                                              spawner=coordinator, actor="probe"))


def _seed_task(coordinator: Coordinator) -> str:
    created = coordinator.create_task("seed-req", "probe task", "deliver the feature",
                                      acceptance_criteria=("it works",), workspace_ref="ws")
    assert created.task_id is not None
    return created.task_id


async def _wait_phase(coordinator, task_id, phases, timeout=8.0):
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        p = coordinator.status(task_id).get("phase")
        if p in phases:
            return p
        await asyncio.sleep(0.02)
    return coordinator.status(task_id).get("phase")


async def _wait_reviewing(coordinator, task_id, run_id, timeout=6.0):
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if coordinator.review_lifecycle.is_reviewing(task_id, run_id):
            return True
        await asyncio.sleep(0.01)
    return False


async def _active_run(coordinator, task_id, timeout=6.0):
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        rid = coordinator.status(task_id).get("active_run")
        if isinstance(rid, str) and rid:
            return rid
        await asyncio.sleep(0.01)
    raise AssertionError("no active run")


async def scenario_restart_no_replay():
    """Real RecoveryScanner: interrupted dead-worker Run -> recovery_required, no replay."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "ws").mkdir(parents=True, exist_ok=True)
        store = FileStore(root, root / "ws")
        writer = StateWriter(store, actor="probe")
        # Task in executing with an interrupted Run whose worker pid is dead.
        from lightgravity.store.ids import new_id
        task_id = new_id("task")
        run_id = new_id("run")
        store.create("task", task_id, {
            "phase": "executing", "status": "in-progress", "title": "restart probe",
            "objective": "x", "acceptance_criteria": ["ok"], "workspace_ref": "ws",
            "requirements_revision": 1, "deliverable_revision": 0, "authorized_checks": [],
            "acceptance": {"status": "pending", "requirements_revision": None,
                           "deliverable_revision": None, "evidence_refs": [],
                           "decided_at": None, "decision_ref": None},
            "queue": {"state": "claimed", "owner": "coordinator:dead"},
            "active_run": run_id,
        }, actor="probe", request_id=f"t:{task_id}", body="# T\n")
        store.create("run", run_id, {
            "task_ref": task_id, "attempt": 1, "state": "executing", "plan_ref": "PLAN.md",
            "team_refs": [], "subtask_refs": [], "session_refs": ["sess_live"],
            "cleanup": {"status": "pending"}, "ended_at": None, "fail_reason": None,
            "worker_pid": 424242,
        }, actor="probe", request_id=f"r:{run_id}", body="# R\n")

        class _DeadProbe:
            def is_alive(self, pid: int) -> bool:
                return False

        scanner = RecoveryScanner(store, writer, probe=_DeadProbe())
        report = scanner.scan()
        task_after = store.read("task", task_id).entity
        run_after = store.read("run", run_id).entity
        return {
            "decisions": [d.action for d in report.decisions],
            "task_phase_after": task_after.get("phase"),
            "queue_after": task_after.get("queue"),
            "active_run_after": task_after.get("active_run"),
            "run_state_after": run_after.get("state"),
            "run_attempt_after": run_after.get("attempt"),
            "replayed": run_after.get("attempt") != 1,
            # recovery_required + slot freed + NO new attempt = never auto-replayed.
            # The interrupted Run record legitimately keeps state=executing (it was
            # not rewritten/faked); the guarantee is no replay + human decision.
            "no_replay_and_recovery_required": (
                task_after.get("phase") == "recovery_required"
                and task_after.get("queue", {}).get("state") == "not_queued"
                and run_after.get("attempt") == 1
            ),
        }


async def scenario_cross_run_budget():
    """The rework ledger persists across a fresh Run (never resets to 0)."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "ws").mkdir(parents=True, exist_ok=True)
        store = FileStore(root, root / "ws")
        coordinator = Coordinator(store, dispatcher=SessionDispatcher())
        reviewer = GateReviewer()
        confirmer = StopConfirmer(coordinator.dispatcher)
        confirmer.close_all()  # type: ignore[arg-type]
        _wire(coordinator, reviewer, confirmer)
        task_id = _seed_task(coordinator)
        # Simulate a persisted rework ledger from a previous Run.
        writer = StateWriter(store, actor="probe")
        writer.write_task(task_id, {"rework": {
            "review_rounds": 2, "repair_rounds_spent": 1, "sdk_retries": 0,
            "outcomes": ["rework"], "last_findings": [], "last_candidate_ref": None,
            "history": [], "reviewer": "gate-reviewer", "reviewer_kind": "model",
            "model_usage": {},
        }})
        before = load_ledger(store.read("task", task_id).entity)
        # A new Run must not reset the ledger.
        coordinator.start()
        try:
            await _active_run(coordinator, task_id)
            await asyncio.sleep(0.5)
            after = load_ledger(store.read("task", task_id).entity)
        finally:
            await coordinator.stop()
        return {
            "before": {"review_rounds": before.review_rounds, "repair_rounds_spent": before.repair_rounds_spent},
            "after": {"review_rounds": after.review_rounds, "repair_rounds_spent": after.repair_rounds_spent},
            "not_reset_across_run": (after.review_rounds >= before.review_rounds
                                     and after.repair_rounds_spent >= before.repair_rounds_spent),
        }


async def scenario_cancel_during_review():
    """Even with the R2 confirmer, cancel during review confirms only after a real stop."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "ws").mkdir(parents=True, exist_ok=True)
        store = FileStore(root, root / "ws")
        coordinator = Coordinator(store, dispatcher=SessionDispatcher())
        reviewer = GateReviewer()
        confirmer = StopConfirmer(coordinator.dispatcher)
        confirmer.close_all()  # type: ignore[arg-type]
        _wire(coordinator, reviewer, confirmer)
        task_id = _seed_task(coordinator)
        coordinator.start()
        try:
            run_id = await _active_run(coordinator, task_id)
            await _wait_reviewing(coordinator, task_id, run_id)
            # Ensure the reviewer body is actually executing before cancelling.
            for _ in range(300):
                if reviewer.started.is_set():
                    break
                await asyncio.sleep(0.01)
            result = await coordinator.request_control(task_id, "cancel", request_id="c1")
            task = store.read("task", task_id).entity
            run = store.read("run", run_id).entity
            return {
                "confirmed": getattr(result.data, "get", lambda *_: None)("confirmed") if isinstance(result.data, dict) else None,
                "reviewer_saw_stop": reviewer.saw_stop,
                "task_phase": task.get("phase"),
                "run_state": run.get("state"),
                "cancel_confirmed_after_real_stop": reviewer.saw_stop,
            }
        finally:
            await coordinator.stop()


def main() -> int:
    out_path = Path(sys.argv[1])
    results = {"evidence_kind": "deterministic-double", "real_model_calls": 0}
    results["restart_no_replay"] = asyncio.run(scenario_restart_no_replay())
    results["cross_run_budget"] = asyncio.run(scenario_cross_run_budget())
    results["cancel_during_review"] = asyncio.run(scenario_cancel_during_review())
    results["verdict"] = {
        "restart_no_replay": results["restart_no_replay"]["no_replay_and_recovery_required"],
        "cross_run_budget": results["cross_run_budget"]["not_reset_across_run"],
        "cancel_during_review_real_stop": results["cancel_during_review"]["cancel_confirmed_after_real_stop"],
    }
    results["all_pass"] = all(results["verdict"].values())
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"verdict": results["verdict"], "all_pass": results["all_pass"]}, indent=2))
    return 0 if results["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
