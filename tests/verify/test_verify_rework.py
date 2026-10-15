"""LG-017 bounded business-rework orchestration tests.

Unit evidence only (temp store, fake spawner, no model/network).  These cover
the real risks named in LG-017:

* rework rounds are separate from SDK retries and bounded by
  ``budget.max_repair_rounds``;
* the Task-lifetime ledger is **never** reset by a new Run;
* passing review opens acceptance; a blocking review opens a fresh rework Run
  while keeping the old candidate/evidence;
* an unavailable reviewer does not accept and does not spend a round;
* a review that is not finished / has no evidence cannot open acceptance.
"""

from __future__ import annotations

from typing import Any

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
from lightgravity.verify.rework import (
    REWORK_EXHAUSTED,
    REWORK_OPENED,
    REWORK_SPAWNED,
    REWORK_UNAVAILABLE,
    ReworkOrchestrator,
    SpawnOutcome,
    load_ledger,
)

from verify_helpers import make_verifying_task, write_workspace_file


class ScriptedReviewer:
    """Reviewer returning a fixed report (stands in for a model reviewer)."""

    name = "scripted"

    def __init__(self, outcome: str, *, findings: tuple[Finding, ...] = ()) -> None:
        self._outcome = outcome
        self._findings = findings

    def review(self, context: Any) -> ReviewReport:
        anchor = ""
        if self._findings and context.resolved_evidence:
            anchor = next(iter(context.resolved_evidence))
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
            outcome=self._outcome,
            candidate_ref=context.candidate.candidate_ref,
            findings=findings,
            reviewer=self.name,
        )


class RecordingSpawner:
    """RunSpawner that records calls and returns a scripted outcome."""

    def __init__(self, *, queued: bool = True, run_id: str | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._queued = queued
        self._run_id = run_id

    def spawn_repair_run(
        self,
        task_id: str,
        *,
        prior_run_id: str,
        findings: tuple[dict[str, Any], ...],
        request_id: str,
    ) -> SpawnOutcome:
        self.calls.append(
            {
                "task_id": task_id,
                "prior_run_id": prior_run_id,
                "findings": findings,
                "request_id": request_id,
            }
        )
        return SpawnOutcome(queued=self._queued, run_id=self._run_id, detail="scripted")


def _blocking_finding() -> Finding:
    return Finding(
        finding_id="f1",
        severity=SEV_BLOCKING,
        summary="output does not meet acceptance",
        evidence_ref="out/result.txt",
        rework_target="deliverable",
    )


def test_review_pass_opens_acceptance_and_spends_no_round(store: FileStore) -> None:
    task_id, run_id, _, _ = make_verifying_task(store)
    write_workspace_file(store, "ws/out/result.txt")
    spawner = RecordingSpawner()
    orch = ReworkOrchestrator(store, reviewer=ScriptedReviewer(REVIEW_PASSED), spawner=spawner)

    result = orch.process(task_id, request_id="r1")
    assert result.state == REWORK_OPENED
    assert result.confirmed is True
    assert spawner.calls == []
    ledger = load_ledger(store.read("task", task_id).entity)
    assert ledger.review_rounds == 1
    assert ledger.repair_rounds_spent == 0
    assert ledger.sdk_retries == 0
    # The orchestrator does not move the phase on a pass; verification opens it.
    assert store.read("task", task_id).entity["phase"] == "verifying"


def test_blocking_review_opens_rework_run_keeping_old_candidate(store: FileStore) -> None:
    task_id, run_id, _, subtasks = make_verifying_task(store)
    write_workspace_file(store, "ws/out/result.txt")
    spawner = RecordingSpawner(queued=True)
    orch = ReworkOrchestrator(
        store,
        reviewer=ScriptedReviewer(REVIEW_REWORK, findings=(_blocking_finding(),)),
        spawner=spawner,
    )

    result = orch.process(task_id, request_id="r1")
    assert result.state == REWORK_SPAWNED
    assert result.confirmed is True
    assert result.new_run_id is None  # worker loop opens the Run; none fabricated
    assert spawner.calls and spawner.calls[0]["prior_run_id"] == run_id

    task = store.read("task", task_id).entity
    assert task["phase"] == "repairing"
    assert task["active_run"] is None
    # The old candidate/evidence are retained, not deleted or rewritten.
    assert task["last_run"] == run_id
    assert any(f["finding_id"] == "f1" for f in task["review_findings"])
    run = store.read("run", run_id).entity
    assert run["state"] == "failed"
    ledger = load_ledger(task)
    assert ledger.repair_rounds_spent == 1
    assert ledger.last_candidate_ref == run_id


def test_repair_budget_spent_stops_without_fake_acceptance(store: FileStore) -> None:
    task_id, _, _, _ = make_verifying_task(
        store, extra={"budget": {"max_workers": 3, "max_parallel": 2, "max_repair_rounds": 1}}
    )
    write_workspace_file(store, "ws/out/result.txt")
    spawner = RecordingSpawner(queued=True)
    orch = ReworkOrchestrator(
        store,
        reviewer=ScriptedReviewer(REVIEW_REWORK, findings=(_blocking_finding(),)),
        spawner=spawner,
    )
    first = orch.process(task_id, request_id="r1")
    assert first.state == REWORK_SPAWNED

    # Re-run the review against a fresh candidate with the budget already spent.
    # Simulate the new Run reaching verifying again with the same ledger.
    writer = StateWriter(store, actor="test")
    new_run = _make_second_candidate(store, task_id)
    writer.transition_run(new_run, "verifying", task_ref=task_id)
    # Legal path back to verifying: repairing -> executing -> verifying.
    writer.transition_task(task_id, "executing", run_ref=new_run, extra={"active_run": new_run})
    writer.transition_task(task_id, "verifying", run_ref=new_run)

    second = orch.process(task_id, request_id="r2")
    assert second.state == REWORK_EXHAUSTED
    assert second.confirmed is False
    assert second.repair_rounds_spent == 1
    assert store.read("task", task_id).entity["phase"] == "waiting_user"
    # No second spawn happened.
    assert len(spawner.calls) == 1


def test_lifetime_ledger_not_reset_by_new_run(store: FileStore) -> None:
    task_id, _, _, _ = make_verifying_task(store)
    write_workspace_file(store, "ws/out/result.txt")
    spawner = RecordingSpawner(queued=True)
    orch = ReworkOrchestrator(
        store,
        reviewer=ScriptedReviewer(REVIEW_REWORK, findings=(_blocking_finding(),)),
        spawner=spawner,
    )
    orch.process(task_id, request_id="r1")
    spent_after_first = load_ledger(store.read("task", task_id).entity).repair_rounds_spent
    assert spent_after_first == 1
    # A completely new Run record + verifying phase must not zero the ledger.
    writer = StateWriter(store, actor="test")
    new_run = _make_second_candidate(store, task_id)
    writer.transition_run(new_run, "verifying", task_ref=task_id)
    writer.transition_task(task_id, "executing", run_ref=new_run, extra={"active_run": new_run})
    writer.transition_task(task_id, "verifying", run_ref=new_run)
    assert load_ledger(store.read("task", task_id).entity).repair_rounds_spent == 1


def test_unavailable_review_does_not_accept_or_spend_round(store: FileStore) -> None:
    task_id, _, _, _ = make_verifying_task(store, evidence=None)
    spawner = RecordingSpawner()
    orch = ReworkOrchestrator(store, reviewer=ScriptedReviewer(REVIEW_UNAVAILABLE), spawner=spawner)
    result = orch.process(task_id, request_id="r1")
    assert result.state == REWORK_UNAVAILABLE
    assert result.confirmed is False
    assert spawner.calls == []
    task = store.read("task", task_id).entity
    assert task["phase"] == "waiting_user"
    ledger = load_ledger(task)
    assert ledger.repair_rounds_spent == 0


def test_exhausted_review_budget_stops_without_run(store: FileStore) -> None:
    task_id, _, _, _ = make_verifying_task(
        store, extra={"budget": {"max_repair_rounds": 1, "max_review_rounds": 1}}
    )
    write_workspace_file(store, "ws/out/result.txt")
    orch = ReworkOrchestrator(
        store, reviewer=ScriptedReviewer(REVIEW_PASSED), spawner=RecordingSpawner()
    )
    assert orch.process(task_id, request_id="r1").state == REWORK_OPENED
    second = orch.process(task_id, request_id="r2")
    assert second.state == REWORK_EXHAUSTED
    assert second.confirmed is False


def test_spawn_failure_does_not_spend_repair_round(store: FileStore) -> None:
    task_id, _, _, _ = make_verifying_task(store)
    write_workspace_file(store, "ws/out/result.txt")
    spawner = RecordingSpawner(queued=False)
    orch = ReworkOrchestrator(
        store,
        reviewer=ScriptedReviewer(REVIEW_REWORK, findings=(_blocking_finding(),)),
        spawner=spawner,
    )
    result = orch.process(task_id, request_id="r1")
    assert result.state == REWORK_SPAWNED
    assert result.confirmed is False
    ledger = load_ledger(store.read("task", task_id).entity)
    assert ledger.repair_rounds_spent == 0


def test_review_of_non_verifying_phase_is_not_applicable(store: FileStore) -> None:
    task_id, _, _, _ = make_verifying_task(store)
    write_workspace_file(store, "ws/out/result.txt")
    StateWriter(store, actor="test").transition_task(task_id, "awaiting_acceptance")
    orch = ReworkOrchestrator(
        store, reviewer=ScriptedReviewer(REVIEW_PASSED), spawner=RecordingSpawner()
    )
    result = orch.process(task_id, request_id="r1")
    assert result.state == "not_applicable"
    assert result.confirmed is False


def _make_second_candidate(store: FileStore, task_id: str) -> str:
    """Build a second verifying Run with its own resolvable evidence."""

    from verify_helpers import create_run, create_subtask

    run_id = create_run(store, task_id, state="verifying")
    subtask = create_subtask(store, run_id, evidence=("out/result2.txt",))
    StateWriter(store, actor="test").write_run(
        run_id, {"subtask_refs": [subtask]}
    )
    write_workspace_file(store, "ws/out/result2.txt")
    return run_id
