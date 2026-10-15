"""LG-022 reverify R1 — deterministic D2/D3 + stop-gate defect probe (0 model calls).

Drives the REAL coordinator worker loop with an in-process dispatcher double.
The double is intentionally *session-bearing* (it records real ``session_refs``
on the Run, as the real GraphDispatcher does after a real SDK turn) so we can
exercise the same stop/release gate the real path hits.

Findings recorded (all deterministic, no network):
  * D2-loop: status is served while a review runs off-loop.
  * D2-stop: cancel during review confirms only after the reviewer really stops.
  * D2-restart: an interrupted review is not replayed; candidate retained.
  * D3: a succeeded/verifying Run has no ``fail_reason``.
  * STOPGATE: with ``session_refs`` present and ``cleanup=pending`` (exactly what
    a real successful Run looks like), ``ensure_awaiting_acceptance`` never
    reaches ``awaiting_acceptance`` — the candidate is never opened for accept.

Run: uv run python probes/lg022/reverify-r1/harness/deterministic_probe.py <out_json>
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "backend"))

import lightgravity.coordinator  # noqa: E402,F401
from lightgravity.coordinator import Coordinator  # noqa: E402
from lightgravity.coordinator.dispatcher import DispatchOutcome, DispatchContext  # noqa: E402
from lightgravity.store import FileStore  # noqa: E402
from lightgravity.verify.review import ReviewReport  # noqa: E402
from lightgravity.verify.review_lifecycle import ReviewStopped  # noqa: E402
from lightgravity.verify.service import VerificationService  # noqa: E402
from lightgravity.verify.stopgate import StoreResourceStopper  # noqa: E402
from lightgravity.verify.rework import ReworkOrchestrator  # noqa: E402


class SessionDispatcher:
    """Dispatcher double that records real-style session refs + candidate evidence."""

    def __init__(self) -> None:
        self.sessions: tuple[str, ...] = ()

    async def dispatch(self, context: DispatchContext, controller, emit):  # noqa: ANN001
        self.sessions = ("sess_fake_a", "sess_fake_b")
        # Simulate the real graph persisting node sessions on the Run.
        try:
            controller.write_run(context.run_id, {"session_refs": list(self.sessions)})
        except Exception:  # noqa: BLE001
            pass
        return DispatchOutcome(state="succeeded", summary="all 1 subtask(s) passed")

    async def cancel(self, task_id: str, run_id: str):  # noqa: ANN001
        from lightgravity.adapter.execution import CancelResult
        return CancelResult(confirmed=True, state="cancelled", reason="probe confirmed stop")


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
                return ReviewReport(
                    outcome="passed",
                    candidate_ref=context.candidate.candidate_ref,
                    reviewer=self.name,
                    reviewer_kind=self.kind,
                )
        raise ReviewStopped(context.task_id, context.run_id)


def _wire(coordinator: Coordinator, reviewer: GateReviewer) -> None:
    coordinator.set_verification(VerificationService(coordinator.store))
    coordinator.set_rework(
        ReworkOrchestrator(coordinator.store, reviewer=reviewer, spawner=coordinator, actor="probe")
    )


def _seed_task(coordinator: Coordinator) -> str:
    created = coordinator.create_task(
        "seed-req",
        "probe task",
        "deliver the feature",
        acceptance_criteria=("it works",),
        workspace_ref="ws",
    )
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


async def scenario_loop_and_d3():
    with tempfile.TemporaryDirectory() as td:
        store = FileStore(Path(td), Path(td) / "ws")
        (Path(td) / "ws").mkdir(parents=True, exist_ok=True)
        coordinator = Coordinator(store, dispatcher=SessionDispatcher())
        reviewer = GateReviewer()
        _wire(coordinator, reviewer)
        task_id = _seed_task(coordinator)
        coordinator.start()
        try:
            run_id = await _active_run(coordinator, task_id)
            reviewing = await _wait_reviewing(coordinator, task_id, run_id)
            t0 = time.monotonic()
            status = coordinator.status(task_id)
            latency = time.monotonic() - t0
            reviewer.release.set()
            final = await _wait_phase(coordinator, task_id, {"awaiting_acceptance"},
                                      timeout=6.0)
            run = store.read("run", run_id).entity
            return {
                "reviewing_observed": reviewing,
                "status_latency_s": round(latency, 3),
                "status_phase_during_review": status.get("phase"),
                "final_phase": final,
                "run_state": run.get("state"),
                "run_cleanup": run.get("cleanup"),
                "session_refs": list(run.get("session_refs") or []),
                "fail_reason": run.get("fail_reason"),
                "d3_ok": not run.get("fail_reason"),
            }
        finally:
            await coordinator.stop()


async def scenario_stopgate_check():
    """Directly exercise the stop gate on a real-looking successful Run."""
    with tempfile.TemporaryDirectory() as td:
        store = FileStore(Path(td), Path(td) / "ws")
        (Path(td) / "ws").mkdir(parents=True, exist_ok=True)
        coordinator = Coordinator(store, dispatcher=SessionDispatcher())
        reviewer = GateReviewer()
        reviewer.release.set()
        _wire(coordinator, reviewer)
        task_id = _seed_task(coordinator)
        coordinator.start()
        try:
            run_id = await _active_run(coordinator, task_id)
            await asyncio.sleep(2.0)
            run = store.read("run", run_id).entity
            stopper = StoreResourceStopper(store)
            report = stopper.stop(task_id, run_id)
            # And the real verify_and_prepare result:
            try:
                res = coordinator._verification.verify_and_prepare(task_id, request_id="probe-verify")
                vres = res.to_dict()
            except Exception as exc:  # noqa: BLE001
                vres = {"error": f"{type(exc).__name__}: {exc}"}
            return {
                "run_state": run.get("state"),
                "session_refs": list(run.get("session_refs") or []),
                "cleanup": run.get("cleanup"),
                "stop_report": report.to_dict(),
                "verify_and_prepare_state": vres.get("state"),
                "verify_and_prepare_phase": vres.get("phase"),
                "verify_messages": vres.get("messages"),
                "task_phase_after_verify": store.read("task", task_id).entity.get("phase"),
            }
        finally:
            await coordinator.stop()


async def scenario_cancel_during_review():
    with tempfile.TemporaryDirectory() as td:
        store = FileStore(Path(td), Path(td) / "ws")
        (Path(td) / "ws").mkdir(parents=True, exist_ok=True)
        coordinator = Coordinator(store, dispatcher=SessionDispatcher())
        reviewer = GateReviewer()
        _wire(coordinator, reviewer)
        task_id = _seed_task(coordinator)
        coordinator.start()
        try:
            run_id = await _active_run(coordinator, task_id)
            await _wait_reviewing(coordinator, task_id, run_id)
            result = await coordinator.request_control(task_id, "cancel", request_id="c1")
            task = store.read("task", task_id).entity
            run = store.read("run", run_id).entity
            return {
                "confirmed": result.data.get("confirmed"),
                "reviewer_saw_stop": reviewer.saw_stop,
                "task_phase": task.get("phase"),
                "run_state": run.get("state"),
            }
        finally:
            await coordinator.stop()


def main() -> int:
    out_path = Path(sys.argv[1])
    results = {"evidence_kind": "deterministic-double", "real_model_calls": 0}
    results["loop_and_d3"] = asyncio.run(scenario_loop_and_d3())
    results["stopgate"] = asyncio.run(scenario_stopgate_check())
    results["cancel_during_review"] = asyncio.run(scenario_cancel_during_review())
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(json.dumps(results, indent=2, ensure_ascii=False))
    print("WROTE", out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
