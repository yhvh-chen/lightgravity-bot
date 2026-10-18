"""LG-126 reviewer sub-cap, global session accounting and real stop release."""

from __future__ import annotations

import asyncio

from lightgravity.coordinator import Coordinator
from lightgravity.store import FileStore

from test_lg022_review_lifecycle import GateReviewer, _wire
from test_rework_integration import EvidenceDispatcher


def _task(coordinator: Coordinator, request_id: str, workspace: str) -> str:
    created = coordinator.create_task(
        request_id,
        f"Review {request_id}",
        f"deliver reviewed output for {request_id}",
        acceptance_criteria=("it works",),
        workspace_ref=workspace,
    )
    assert created.task_id is not None
    return created.task_id


def _run_id(coordinator: Coordinator, task_id: str) -> str | None:
    value = coordinator.status(task_id).get("active_run")
    return value if isinstance(value, str) and value else None


async def test_only_one_reviewer_and_second_waits_for_real_release(
    store: FileStore,
) -> None:
    for name in ("review-a", "review-b"):
        store.resolve_path(name, write=True).mkdir(parents=True, exist_ok=True)
    coordinator = Coordinator(store, dispatcher=EvidenceDispatcher(), poll_interval=0.01)
    reviewer = GateReviewer()
    _wire(coordinator, reviewer)
    coordinator.start()
    try:
        first = _task(coordinator, "review-a", "review-a")
        second = _task(coordinator, "review-b", "review-b")
        # Wait until the one permitted reviewer is genuinely in its turn.
        for _ in range(600):
            if reviewer.started.is_set():
                break
            await asyncio.sleep(0.01)
        assert reviewer.started.is_set()
        assert reviewer.calls == 1
        snapshot = coordinator.capacity_snapshot()
        assert snapshot["reviewer_sessions"] == 1
        assert snapshot["session_count"] == 1

        waiting: list[str] = []
        for task_id in (first, second):
            run_id = _run_id(coordinator, task_id)
            if run_id is None:
                continue
            run = store.read("run", run_id).entity
            if run.get("waiting_reason") == "reviewer_limit":
                waiting.append(task_id)
        assert len(waiting) == 1
        # Stop gate: the waiting Run is still verifying, not accepted.
        assert coordinator.status(waiting[0])["phase"] == "verifying"

        reviewer.release.set()
        for _ in range(800):
            phases = {coordinator.status(first)["phase"], coordinator.status(second)["phase"]}
            if phases == {"awaiting_acceptance"}:
                break
            await asyncio.sleep(0.01)
        assert coordinator.status(first)["phase"] == "awaiting_acceptance"
        assert coordinator.status(second)["phase"] == "awaiting_acceptance"
        assert reviewer.calls == 2
        final = coordinator.capacity_snapshot()
        assert final["reviewer_sessions"] == 0
        assert final["admitted_count"] == 0
    finally:
        reviewer.release.set()
        await coordinator.stop()
