"""LG-031 final-candidate review/repair closure over the decentralized graph.

The existing LG-017 tests cover the reviewer/rework machinery with a
single-slot dispatcher double.  This test closes the *LG-031* loop: the real
``GraphDispatcher`` running the decentralized claim/lease/grant path produces
the candidate, and that candidate - not a worker's self-report - is what the
independent reviewer examines before acceptance.  Worker output alone can never
reach ``accepted``; a blocking independent review opens a bounded repair Run and
the old candidate/evidence are retained.

No model is called (scripted reviewer + in-process fake executor); the real
DeepSeek reviewer path is the LG-017 probe and the LG-032 central QA.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from lightgravity.collaboration import ClaimPolicy, CollaborationService, ExecutionGrantRegistry
from lightgravity.coordinator import Coordinator, GraphDispatcher, RoleCatalog
from lightgravity.coordinator.state import StateWriter
from lightgravity.store import FileStore
from lightgravity.verify.review import (
    REVIEW_PASSED,
    REVIEW_REWORK,
    SEV_BLOCKING,
    Finding,
    ReviewReport,
)
from lightgravity.verify.rework import ReworkOrchestrator

from graph_helpers import FakeGraphExecutor, build_environment

TWO_TEAM = RoleCatalog({"implementation": ["developer"], "verification": ["verifier"]})


class ScriptedReviewer:
    """Independent reviewer with a scripted outcome sequence (no model)."""

    name = "lg031-scripted"

    def __init__(self, outcomes: list[str]) -> None:
        self._outcomes = list(outcomes)
        self.calls = 0

    def review(self, context):
        index = min(self.calls, len(self._outcomes) - 1)
        outcome = self._outcomes[index]
        self.calls += 1
        findings = ()
        if outcome == REVIEW_REWORK:
            anchor = next(iter(context.resolved_evidence), "")
            findings = (
                Finding(
                    finding_id="f1",
                    severity=SEV_BLOCKING,
                    summary="deliverable incomplete",
                    evidence_ref=anchor,
                    rework_target="deliverable",
                ),
            )
        return ReviewReport(
            outcome=outcome,
            candidate_ref=context.candidate.candidate_ref,
            findings=findings,
            reviewer=self.name,
        )


def _make(store: FileStore, workspace: Path):
    def responder(request):
        import pathlib

        from lightgravity.adapter import ExecutionRef, ExecutorResult

        # Write a real, resolvable artifact inside the node workspace so the
        # independent reviewer can substantiate a finding against it.
        if request.workspace_path:
            target = pathlib.Path(request.workspace_path) / "out" / "result.txt"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("delivered\n", encoding="utf-8")
        return ExecutorResult(
            state="succeeded",
            summary=f"ok:{request.subtask_id}",
            artifact_refs=("out/result.txt",),
            execution_ref=ExecutionRef(
                execution_id=f"exec_{request.subtask_id}",
                task_id=request.task_id,
                run_id=request.run_id,
                subtask_id=request.subtask_id,
            ),
            stop_confirmed=True,
        )

    dispatcher = GraphDispatcher(
        store,
        FakeGraphExecutor(responder),
        catalog=TWO_TEAM,
        workspaces=None,
        collaboration=CollaborationService(store, policy=ClaimPolicy(enabled=True, lease_seconds=300)),
        grant_registry=ExecutionGrantRegistry(),
    )
    return Coordinator(store, dispatcher=dispatcher), dispatcher


def _wire(coordinator: Coordinator, reviewer: ScriptedReviewer) -> None:
    from lightgravity.verify import VerificationService

    coordinator.set_verification(VerificationService(coordinator.store))
    coordinator.set_rework(
        ReworkOrchestrator(
            coordinator.store, reviewer=reviewer, spawner=coordinator, actor="test"
        )
    )


async def _wait_phase(coordinator: Coordinator, task_id: str, phases: set[str], timeout: float = 8.0) -> str:
    import asyncio

    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        phase = str(coordinator.store.read("task", task_id).entity.get("phase"))
        if phase in phases:
            return phase
        await asyncio.sleep(0.02)
    return str(coordinator.store.read("task", task_id).entity.get("phase"))


@pytest.mark.asyncio
async def test_decentralized_candidate_requires_independent_review(tmp_path: Path) -> None:
    workspace_root = tmp_path / "ws"
    workspace_root.mkdir(parents=True, exist_ok=True)
    store = FileStore(tmp_path / "data", workspace_root)
    build_environment(store)
    coordinator, dispatcher = _make(store, workspace_root)
    reviewer = ScriptedReviewer([REVIEW_PASSED])
    _wire(coordinator, reviewer)

    created = coordinator.create_task(
        "req-lg031", "LG-031 review", "deliver the feature",
        acceptance_criteria=("it works",), workspace_ref="task-ws",
    )
    task_id = created.task_id
    assert task_id is not None
    coordinator.start()
    try:
        phase = await _wait_phase(coordinator, task_id, {"awaiting_acceptance", "waiting_user", "failed"})
    finally:
        await coordinator.stop()
    assert phase == "awaiting_acceptance"
    assert reviewer.calls == 1
    task = store.read("task", task_id).entity
    # The candidate awaits a *human* decision; the worker/reviewer cannot accept.
    assert task["acceptance"]["status"] == "awaiting"
    assert task["status"] != "done"


@pytest.mark.asyncio
async def test_blocking_review_opens_bounded_repair_and_keeps_old_candidate(tmp_path: Path) -> None:
    workspace_root = tmp_path / "ws"
    workspace_root.mkdir(parents=True, exist_ok=True)
    store = FileStore(tmp_path / "data", workspace_root)
    build_environment(store)
    coordinator, dispatcher = _make(store, workspace_root)
    reviewer = ScriptedReviewer([REVIEW_REWORK, REVIEW_PASSED])
    _wire(coordinator, reviewer)

    created = coordinator.create_task(
        "req-lg031b", "LG-031 rework", "deliver the feature",
        acceptance_criteria=("it works",), workspace_ref="task-ws",
    )
    task_id = created.task_id
    assert task_id is not None
    StateWriter(store, actor="test").write_task(
        task_id, {"budget": {"max_workers": 3, "max_parallel": 2, "max_repair_rounds": 1}}
    )
    coordinator.start()
    try:
        phase = await _wait_phase(coordinator, task_id, {"awaiting_acceptance", "waiting_user", "failed"})
    finally:
        await coordinator.stop()
    assert phase == "awaiting_acceptance"
    assert reviewer.calls == 2
    task = store.read("task", task_id).entity
    ledger = task["rework"]
    assert ledger["repair_rounds_spent"] == 1
    # The rejected candidate Run is retained, not deleted.
    prior = next(
        entry["prior_run_id"]
        for entry in ledger["history"]
        if isinstance(entry, dict) and entry.get("prior_run_id")
    )
    retained = store.read("run", prior).entity
    assert retained["state"] == "failed"
    assert task["acceptance"]["status"] == "awaiting"


@pytest.mark.asyncio
async def test_worker_output_alone_never_reaches_accepted(tmp_path: Path) -> None:
    """With no reviewer wired, the honest UnavailableReviewer blocks acceptance."""

    workspace_root = tmp_path / "ws"
    workspace_root.mkdir(parents=True, exist_ok=True)
    store = FileStore(tmp_path / "data", workspace_root)
    build_environment(store)
    coordinator, dispatcher = _make(store, workspace_root)

    created = coordinator.create_task(
        "req-lg031c", "LG-031 unavailable", "deliver the feature",
        acceptance_criteria=("it works",), workspace_ref="task-ws",
    )
    task_id = created.task_id
    assert task_id is not None
    coordinator.start()
    try:
        phase = await _wait_phase(coordinator, task_id, {"waiting_user", "awaiting_acceptance", "failed"})
    finally:
        await coordinator.stop()
    task = store.read("task", task_id).entity
    # No real reviewer ⇒ no acceptance; the program machine gate is not "done".
    assert task["acceptance"]["status"] != "accepted"
    assert task["status"] != "done"
