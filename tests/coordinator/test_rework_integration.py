"""LG-017 coordinator integration: independent review before acceptance.

These drive the real coordinator worker loop (in-process fake executor; the
real SDK path is LG-010) and assert:

* a passing independent review lets the candidate reach ``awaiting_acceptance``;
* a blocking review opens a fresh rework Run that re-recruits and re-verifies,
  keeping the old candidate/evidence, and the review can then pass;
* a reviewer that is unavailable parks the Task at ``waiting_user`` and never
  opens acceptance (no fake pass).
"""

from __future__ import annotations

import asyncio
from typing import Any

from lightgravity.coordinator import Coordinator
from lightgravity.coordinator.state import StateWriter
from lightgravity.store import FileStore
from lightgravity.verify.review import (
    REVIEW_PASSED,
    REVIEW_REWORK,
    REVIEW_UNAVAILABLE,
    Finding,
    ReviewReport,
    SEV_BLOCKING,
)
from lightgravity.verify.rework import ReworkOrchestrator

from coordinator_helpers import FakeExecutor, make_coordinator, wait_for_phase


class ScriptedReviewer:
    """Reviewer with a scripted sequence of outcomes (one per review call)."""

    name = "scripted-integration"

    def __init__(self, outcomes: list[str], *, findings: tuple[Finding, ...] = ()) -> None:
        self._outcomes = list(outcomes)
        self._findings = findings
        self.calls = 0

    def review(self, context: Any) -> ReviewReport:
        index = min(self.calls, len(self._outcomes) - 1)
        outcome = self._outcomes[index]
        self.calls += 1
        findings: tuple[Finding, ...] = ()
        if outcome == REVIEW_REWORK:
            anchor = next(iter(context.resolved_evidence), "")
            findings = tuple(
                Finding(
                    finding_id=f.finding_id,
                    severity=f.severity,
                    summary=f.summary,
                    evidence_ref=anchor or f.evidence_ref,
                    rework_target=f.rework_target,
                )
                for f in self._findings
            )
        return ReviewReport(
            outcome=outcome,
            candidate_ref=context.candidate.candidate_ref,
            findings=findings,
            reviewer=self.name,
        )


class EvidenceDispatcher:
    """Dispatcher double that records a resolvable workspace artifact.

    Stands in for a real executor: it runs the same single-slot phase sequence
    and writes the declared workspace file so the candidate has real evidence —
    which the independent reviewer can then substantiate a finding against.
    """

    name = "evidence-fake"

    def __init__(self) -> None:
        self.dispatches = 0

    async def dispatch(self, context, controller, emit):
        self.dispatches += 1
        from lightgravity.contracts import EventType
        from lightgravity.store import new_id

        controller.set_task_phase("recruiting")
        controller.set_run_state("recruiting")
        controller.set_task_phase("executing")
        controller.set_run_state("executing")
        # Write the declared artifact inside the authorized workspace.
        workspace = context.workspace_path
        if workspace:
            from pathlib import Path as _P

            target = _P(workspace) / "out" / "result.txt"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("delivered\n", encoding="utf-8")
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
                    "evidence_refs": ["out/result.txt"],
                },
            },
            body="# Subtask deliver\n",
        )
        controller.update_run({"subtask_refs": [subtask_id]})
        from lightgravity.coordinator.dispatcher import DispatchOutcome

        return DispatchOutcome(state="succeeded", summary="evidence-fake: succeeded")

    async def cancel(self, task_id, run_id):
        from lightgravity.adapter import CancelResult

        return CancelResult(confirmed=True, state="cancelled", reason="evidence-fake")


def _wire(coordinator: Coordinator, reviewer: ScriptedReviewer) -> None:
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


def _make(store: FileStore) -> tuple[Coordinator, EvidenceDispatcher]:
    from lightgravity.coordinator import Coordinator

    dispatcher = EvidenceDispatcher()
    return Coordinator(store, dispatcher=dispatcher), dispatcher


def _seed_task(coordinator: Coordinator, *, max_repair_rounds: int = 1) -> str:
    # The Coordinator's create_task builds a real Task with default budget; we
    # patch the budget directly for the bounded-round test.
    created = coordinator.create_task(
        "req-lg017",
        "LG-017 review",
        "deliver the feature",
        acceptance_criteria=("it works",),
        workspace_ref="task-ws",
    )
    task_id = created.task_id
    assert task_id is not None
    if max_repair_rounds != 1:
        StateWriter(coordinator.store, actor="test").write_task(
            task_id, {"budget": {"max_workers": 3, "max_parallel": 2, "max_repair_rounds": max_repair_rounds}}
        )
    return task_id


def _finding() -> Finding:
    return Finding(
        finding_id="f1",
        severity=SEV_BLOCKING,
        summary="deliverable incomplete",
        evidence_ref="out/result.txt",
        rework_target="deliverable",
    )


async def test_passing_review_reaches_acceptance(store: FileStore) -> None:
    coordinator, dispatcher = _make(store)
    reviewer = ScriptedReviewer([REVIEW_PASSED])
    _wire(coordinator, reviewer)
    task_id = _seed_task(coordinator)
    coordinator.start()
    try:
        phase = await wait_for_phase(coordinator, task_id, {"awaiting_acceptance"}, timeout=6.0)
    finally:
        await coordinator.stop()
    assert phase == "awaiting_acceptance"
    assert reviewer.calls == 1
    task = store.read("task", task_id).entity
    assert task["acceptance"]["status"] == "awaiting"
    assert task["rework"]["repair_rounds_spent"] == 0


async def test_blocking_review_opens_fresh_rework_run_then_passes(store: FileStore) -> None:
    coordinator, dispatcher = _make(store)
    # First review rejects; second (on the rework Run) passes.
    reviewer = ScriptedReviewer([REVIEW_REWORK, REVIEW_PASSED], findings=(_finding(),))
    _wire(coordinator, reviewer)
    task_id = _seed_task(coordinator)
    coordinator.start()
    try:
        phase = await wait_for_phase(coordinator, task_id, {"awaiting_acceptance"}, timeout=8.0)
    finally:
        await coordinator.stop()
    assert phase == "awaiting_acceptance"
    # Both reviews ran and the rework Run executed (so the executor ran twice:
    # original + repair).
    assert reviewer.calls == 2
    assert dispatcher.dispatches == 2
    task = store.read("task", task_id).entity
    ledger = task["rework"]
    assert ledger["repair_rounds_spent"] == 1
    assert ledger["sdk_retries"] == 0
    assert "rework_queued" in ledger["outcomes"]
    # The rejected candidate Run is retained (not deleted, still readable).
    prior = next(
        entry["prior_run_id"]
        for entry in ledger["history"]
        if isinstance(entry, dict) and entry.get("prior_run_id")
    )
    retained = store.read("run", prior).entity
    assert retained["state"] == "failed"
    assert retained["attempt"] == 1
    # The rework Run recorded attempt 2 in the ledger history's spawn entry.
    assert any(
        entry.get("new_run_id") is None and entry.get("queued")
        for entry in ledger["history"]
        if isinstance(entry, dict)
    )


async def test_repair_budget_stops_and_does_not_accept(store: FileStore) -> None:
    coordinator, dispatcher = _make(store)
    # Always reject: with max_repair_rounds=1 the second review must stop.
    reviewer = ScriptedReviewer([REVIEW_REWORK], findings=(_finding(),))
    _wire(coordinator, reviewer)
    task_id = _seed_task(coordinator, max_repair_rounds=1)
    coordinator.start()
    try:
        phase = await wait_for_phase(coordinator, task_id, {"waiting_user", "failed"}, timeout=8.0)
    finally:
        await coordinator.stop()
    assert phase in {"waiting_user", "failed"}
    task = store.read("task", task_id).entity
    assert task["phase"] != "completed"
    assert task["acceptance"]["status"] != "accepted"
    ledger = task["rework"]
    assert ledger["repair_rounds_spent"] <= 1


async def test_unavailable_review_never_opens_acceptance(store: FileStore) -> None:
    coordinator, dispatcher = _make(store)
    reviewer = ScriptedReviewer([REVIEW_UNAVAILABLE])
    _wire(coordinator, reviewer)
    task_id = _seed_task(coordinator)
    coordinator.start()
    try:
        phase = await wait_for_phase(coordinator, task_id, {"waiting_user"}, timeout=6.0)
    finally:
        await coordinator.stop()
    assert phase == "waiting_user"
    task = store.read("task", task_id).entity
    assert task["acceptance"]["status"] != "awaiting"
    assert task["acceptance"]["status"] != "accepted"
    assert task["rework"]["repair_rounds_spent"] == 0


async def test_honest_default_reviewer_is_unavailable_and_blocks_accept(
    store: FileStore,
) -> None:
    """The unreviewed default runtime never accepts without a reported reviewer.

    LG-017 R1: a program-only machine check is the LG-009 gate, not independent
    QA.  With no real reviewer assembled, the coordinator's default is an honest
    ``UnavailableReviewer``: the candidate parks at ``waiting_user`` and never
    opens acceptance.
    """

    from lightgravity.verify import VerificationService
    from lightgravity.verify.review import UnavailableReviewer

    coordinator, dispatcher = _make(store)
    # No set_rework call: exercise the real lazy default.
    coordinator.set_verification(VerificationService(coordinator.store))
    task_id = _seed_task(coordinator)
    coordinator.start()
    try:
        phase = await wait_for_phase(coordinator, task_id, {"waiting_user"}, timeout=6.0)
    finally:
        await coordinator.stop()
    assert phase == "waiting_user"
    task = store.read("task", task_id).entity
    assert task["acceptance"]["status"] != "awaiting"
    ledger = task["rework"]
    assert ledger["reviewer_kind"] == "unavailable"
    assert ledger["repair_rounds_spent"] == 0
    orchestrator = coordinator._resolved_rework()
    assert isinstance(orchestrator._reviewer, UnavailableReviewer)


async def test_program_reviewer_is_recorded_as_machine_gate(store: FileStore) -> None:
    """An explicitly wired ProgramReviewer is recorded as ``program``, not model."""

    from lightgravity.verify import VerificationService
    from lightgravity.verify.review import ProgramReviewer
    from lightgravity.verify.rework import ReworkOrchestrator

    coordinator, dispatcher = _make(store)
    coordinator.set_verification(VerificationService(coordinator.store))
    coordinator.set_rework(
        ReworkOrchestrator(
            coordinator.store,
            reviewer=ProgramReviewer(),
            spawner=coordinator,
            actor="test",
        )
    )
    task_id = _seed_task(coordinator)
    coordinator.start()
    try:
        phase = await wait_for_phase(
            coordinator, task_id, {"awaiting_acceptance", "waiting_user"}, timeout=8.0
        )
    finally:
        await coordinator.stop()
    task = store.read("task", task_id).entity
    ledger = task["rework"]
    assert ledger["reviewer_kind"] == "program"
    assert ledger["model_usage"].get("unknown") in (["usage"], None)


async def test_review_ledger_records_model_kind_and_usage(store: FileStore) -> None:
    """A model reviewer's kind and real (unknown-preserving) usage are persisted."""

    from lightgravity.verify import REVIEW_PASSED as _PASS
    from lightgravity.verify import VerificationService

    class UsageReviewer:
        name = "model-reviewer"
        kind = "model"
        model_calls = 1
        last_usage = {"prompt_tokens": 11, "candidates_tokens": 2}

        def review(self, context):
            from lightgravity.verify.review import ReviewReport

            return ReviewReport(
                outcome=_PASS,
                candidate_ref=context.candidate.candidate_ref,
                reviewer=self.name,
                reviewer_kind=self.kind,
                model_calls=self.model_calls,
                usage=dict(self.last_usage),
            )

    coordinator, dispatcher = _make(store)
    coordinator.set_verification(VerificationService(coordinator.store))
    coordinator.set_rework(
        ReworkOrchestrator(
            coordinator.store,
            reviewer=UsageReviewer(),
            spawner=coordinator,
            actor="test",
        )
    )
    task_id = _seed_task(coordinator)
    coordinator.start()
    try:
        phase = await wait_for_phase(coordinator, task_id, {"awaiting_acceptance"}, timeout=8.0)
    finally:
        await coordinator.stop()
    assert phase == "awaiting_acceptance"
    ledger = store.read("task", task_id).entity["rework"]
    assert ledger["reviewer_kind"] == "model"
    assert ledger["reviewer"] == "model-reviewer"
    assert ledger["model_usage"] == {"prompt_tokens": 11, "candidates_tokens": 2}
