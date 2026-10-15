"""LG-017 independent candidate review tests.

Unit evidence only: temp data dirs, no network/model.  Verifies the reviewer is
independent of the implementer, that findings are bound to real candidate-owned
evidence, and that an unavailable reviewer never becomes a fake pass.
"""

from __future__ import annotations

from lightgravity.store import FileStore
from lightgravity.verify.review import (
    ProgramReviewer,
    REVIEW_PASSED,
    REVIEW_REWORK,
    REVIEW_UNAVAILABLE,
    SEV_BLOCKING,
    ReviewContext,
    ReviewReport,
    UnavailableReviewer,
    resolve_candidate_evidence,
    validate_findings,
)
from lightgravity.verify.candidate import load_candidate

from verify_helpers import make_verifying_task, write_workspace_file


def _context(store: FileStore, task_id: str) -> ReviewContext:
    candidate = load_candidate(store, task_id)
    resolved = resolve_candidate_evidence(store, candidate)
    return ReviewContext(
        task_id=task_id,
        run_id=candidate.run_id,
        candidate=candidate,
        store=store,
        resolved_evidence=resolved,
    )


def test_program_reviewer_passes_when_evidence_resolves(store: FileStore) -> None:
    task_id, run_id, _, _ = make_verifying_task(store)
    write_workspace_file(store, "ws/out/result.txt")
    report = ProgramReviewer().review(_context(store, task_id))
    assert report.outcome == REVIEW_PASSED
    assert report.candidate_ref == run_id
    assert report.findings == ()


def test_program_reviewer_passes_when_no_evidence_declared(store: FileStore) -> None:
    # No artifact refs declared at all: the Task authorized no evidence check, so
    # the reviewer honestly finds nothing to block (consistent with LG-009's
    # "no checks = no machine gate").  It does NOT fabricate a rework.
    task_id, _, _, _ = make_verifying_task(store, evidence=None, checks=None)
    report = ProgramReviewer().review(_context(store, task_id))
    assert report.outcome == REVIEW_PASSED


def test_program_reviewer_unavailable_when_declared_evidence_missing(
    store: FileStore,
) -> None:
    # The subtask declares a workspace ref that does not exist: the candidate
    # claims evidence it cannot produce, so the independent review is
    # unavailable (bounded failure), never a fake pass.
    task_id, _, _, _ = make_verifying_task(
        store, checks=("artifacts-in-workspace",)
    )
    report = ProgramReviewer().review(_context(store, task_id))
    assert report.outcome == REVIEW_UNAVAILABLE
    assert not report.is_pass


def test_program_reviewer_flags_missing_artifact_as_unavailable(store: FileStore) -> None:
    # Same missing artifact, ref recorded but no file: not substantiable.
    task_id, run_id, _, _ = make_verifying_task(
        store, checks=("artifacts-in-workspace",)
    )
    candidate = load_candidate(store, task_id)
    assert resolve_candidate_evidence(store, candidate) == {}
    report = ProgramReviewer().review(_context(store, task_id))
    assert report.outcome == REVIEW_UNAVAILABLE


def test_validate_findings_drops_unsubstantiated(store: FileStore) -> None:
    task_id, run_id, _, _ = make_verifying_task(store)
    write_workspace_file(store, "ws/out/result.txt")
    candidate = load_candidate(store, task_id)
    resolved = resolve_candidate_evidence(store, candidate)
    assert resolved  # sanity: evidence resolves

    foreign = ReviewReport(
        outcome=REVIEW_REWORK,
        candidate_ref=run_id,
        findings=(
            # Cites an artifact that does not belong to this candidate.
            _finding("foreign", "evidence:run_other/secret.txt@sha256:" + "0" * 64),
            # Cites a resolvable candidate artifact: must be kept.
            _finding("real", next(iter(resolved))),
        ),
        reviewer="model",
    )
    validated = validate_findings(foreign, candidate=candidate, resolved_evidence=resolved)
    assert validated.outcome == REVIEW_REWORK
    assert [f.finding_id for f in validated.findings] == ["real"]
    assert validated.unsubstantiated == ("foreign",)
    # Every kept finding is bound to the reviewed candidate, not a foreign one.
    assert all(f.candidate_ref == run_id for f in validated.findings)


def test_validate_findings_rework_without_evidence_degrades_to_unavailable(
    store: FileStore,
) -> None:
    task_id, run_id, _, _ = make_verifying_task(store)
    write_workspace_file(store, "ws/out/result.txt")
    candidate = load_candidate(store, task_id)
    resolved = resolve_candidate_evidence(store, candidate)

    only_foreign = ReviewReport(
        outcome=REVIEW_REWORK,
        candidate_ref=run_id,
        findings=(_finding("foreign", "not-resolvable"),),
        reviewer="model",
    )
    validated = validate_findings(only_foreign, candidate=candidate, resolved_evidence=resolved)
    assert validated.outcome == REVIEW_UNAVAILABLE
    assert validated.unsubstantiated == ("foreign",)


def test_advisory_only_review_cannot_force_rework(store: FileStore) -> None:
    task_id, run_id, _, _ = make_verifying_task(store)
    write_workspace_file(store, "ws/out/result.txt")
    candidate = load_candidate(store, task_id)
    resolved = resolve_candidate_evidence(store, candidate)
    advisory = ReviewReport(
        outcome=REVIEW_REWORK,
        candidate_ref=run_id,
        findings=(
            _finding("note", next(iter(resolved)), severity="advisory"),
        ),
        reviewer="model",
    )
    validated = validate_findings(advisory, candidate=candidate, resolved_evidence=resolved)
    # No *blocking* finding survives, so rework is not forced.
    assert validated.outcome == REVIEW_UNAVAILABLE


def test_unavailable_reviewer_is_explicitly_not_a_pass(store: FileStore) -> None:
    task_id, _, _, _ = make_verifying_task(store)
    write_workspace_file(store, "ws/out/result.txt")
    report = UnavailableReviewer().review(_context(store, task_id))
    assert report.outcome == REVIEW_UNAVAILABLE
    assert report.is_unavailable and not report.is_pass
def _finding(finding_id: str, ref: str, *, severity: str = SEV_BLOCKING):
    from lightgravity.verify.review import Finding

    return Finding(
        finding_id=finding_id,
        severity=severity,
        summary="problem",
        evidence_ref=ref,
        rework_target="deliverable",
    )
