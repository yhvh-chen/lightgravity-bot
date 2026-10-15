"""Independent candidate review (LG-017, docs/08 §6.1/§9).

LG-009 hands a *verified* candidate to human acceptance.  LG-017 adds the
runtime step the product actually needs: an **independent reviewer** that looks
at the *candidate version's real evidence* and produces structured findings
before the candidate is offered for acceptance.

Two hard rules from the task:

* the reviewer is a separate context/role from the implementer.  It does not run
  the executor, it receives a read-only snapshot and the program-resolved
  evidence payloads (never the worker's own summary as proof);
* a finding is only valid when it cites a **resolvable** evidence reference
  belonging to the reviewed candidate.  Findings that cite missing/foreign
  evidence are dropped and reported as ``unsubstantiated`` rather than trusted.

There are three honest reviewer outcomes:

* :data:`REVIEW_PASSED`  - the reviewer examined the candidate and found no
  blocking problem;
* :data:`REVIEW_REWORK`  - the reviewer found problems and named rework targets;
* :data:`REVIEW_UNAVAILABLE` - **no usable independent reviewer** was available.
  This is *not* a pass: the candidate cannot be accepted and no round is spent.

The default reviewer is program-driven and deterministic: it re-derives the
authorized machine checks *in the reviewer's own context* and additionally
verifies that every recorded candidate artifact ref resolves under the owning
Task/Run.  A model-backed reviewer can be injected through the
:class:`Reviewer` port without changing the orchestrator; whatever it returns is
still passed through :func:`validate_findings`, so a model can never directly
mark a Task done.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from lightgravity.evidence import (
    EvidenceRefError,
    resolve_evidence_ref,
)
from lightgravity.store import Store

from .candidate import Candidate
from .checks import (
    ABSOLUTE_REF,
    BLOCKING_STATUSES,
    EVIDENCE_REF,
    WORKSPACE_REF,
    CheckRegistry,
    authorized_checks,
    classify_artifact_ref,
    default_check_registry,
    run_checks,
)

#: Reviewer outcomes (docs/08 §6.1 phase ``verifying`` -> ``repairing``).
REVIEW_PASSED = "passed"
REVIEW_REWORK = "rework"
REVIEW_UNAVAILABLE = "unavailable"

#: Severities a finding may carry.  Only ``blocking`` prevents acceptance.
SEV_BLOCKING = "blocking"
SEV_ADVISORY = "advisory"
_SEVERITIES = frozenset({SEV_BLOCKING, SEV_ADVISORY})

#: Empty placeholder that is **never** treated as a finding.
_NO_REF = ""


@dataclass(frozen=True, slots=True)
class Finding:
    """One structured review problem with a real evidence target.

    ``evidence_ref`` must resolve inside the reviewed candidate's Task/Run
    evidence root; ``rework_target`` names what a repair Run should change.
    """

    finding_id: str
    severity: str
    summary: str
    evidence_ref: str
    rework_target: str
    candidate_ref: str = ""
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "severity": self.severity,
            "summary": self.summary,
            "evidence_ref": self.evidence_ref,
            "rework_target": self.rework_target,
            "candidate_ref": self.candidate_ref,
            "detail": self.detail,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Finding":
        return cls(
            finding_id=str(data.get("finding_id", "")),
            severity=str(data.get("severity", SEV_BLOCKING)),
            summary=str(data.get("summary", "")),
            evidence_ref=str(data.get("evidence_ref", "")),
            rework_target=str(data.get("rework_target", "")),
            candidate_ref=str(data.get("candidate_ref", "")),
            detail=str(data.get("detail", "")),
        )


@dataclass(frozen=True, slots=True)
class ReviewContext:
    """The read-only material a reviewer may inspect (no executor, no control)."""

    task_id: str
    run_id: str
    candidate: Candidate
    store: Store
    #: Evidence refs the program resolved to real, owned files (ref -> path).
    resolved_evidence: dict[str, Path] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ReviewReport:
    """Reviewer outcome for exactly one candidate version."""

    outcome: str
    candidate_ref: str
    findings: tuple[Finding, ...] = ()
    unsubstantiated: tuple[str, ...] = ()
    reviewer: str = ""
    reason: str = ""

    @property
    def is_pass(self) -> bool:
        return self.outcome == REVIEW_PASSED

    @property
    def is_rework(self) -> bool:
        return self.outcome == REVIEW_REWORK

    @property
    def is_unavailable(self) -> bool:
        return self.outcome == REVIEW_UNAVAILABLE

    @property
    def blocking(self) -> tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.severity == SEV_BLOCKING)

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome,
            "candidate_ref": self.candidate_ref,
            "findings": [f.to_dict() for f in self.findings],
            "unsubstantiated": list(self.unsubstantiated),
            "reviewer": self.reviewer,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReviewReport":
        raw = data.get("findings")
        findings = tuple(
            Finding.from_dict(item) for item in raw if isinstance(item, dict)
        ) if isinstance(raw, list) else ()
        unsub = data.get("unsubstantiated")
        return cls(
            outcome=str(data.get("outcome", REVIEW_UNAVAILABLE)),
            candidate_ref=str(data.get("candidate_ref", "")),
            findings=findings,
            unsubstantiated=tuple(str(x) for x in unsub) if isinstance(unsub, list) else (),
            reviewer=str(data.get("reviewer", "")),
            reason=str(data.get("reason", "")),
        )


@runtime_checkable
class Reviewer(Protocol):
    """Independent reviewer port.

    Implementations must be *independent of the implementer*: they only receive
    :class:`ReviewContext` and return a :class:`ReviewReport`.  They never write
    control state.  A reviewer that cannot run must return
    ``outcome=unavailable`` (never a fabricated pass).
    """

    name: str

    def review(self, context: ReviewContext) -> ReviewReport: ...


def resolve_candidate_evidence(store: Store, candidate: Candidate) -> dict[str, Path]:
    """Resolve every recorded candidate artifact ref to a real owned file.

    Only canonical ``evidence:`` refs (owned by this Task/Run) and
    workspace-relative refs (under the authorized workspace root) resolve.
    Opaque refs (executor artifact ids that are not paths) and raw absolute
    paths are left out of the map: a finding citing them is unsubstantiated, and
    they must not be mistaken for missing workspace evidence.
    """

    resolved: dict[str, Path] = {}
    data_dir = getattr(store, "data_dir", None)
    for ref in candidate.artifact_refs:
        if not isinstance(ref, str) or not ref:
            continue
        kind, payload = classify_artifact_ref(ref)
        if kind == EVIDENCE_REF and payload:
            try:
                path = resolve_evidence_ref(
                    payload,
                    data_dir=data_dir,
                    task_id=candidate.task_id,
                    run_id=candidate.run_id,
                )
            except EvidenceRefError:
                continue
            resolved[ref] = path
            continue
        if kind == WORKSPACE_REF and payload:
            workspace_file = _resolve_workspace_ref(store, candidate, payload)
            if workspace_file is not None:
                resolved[ref] = workspace_file
    return resolved


def _resolve_workspace_ref(store: Store, candidate: Candidate, payload: str) -> Path | None:
    """Resolve a workspace-relative ref under the candidate's workspace root.

    Mirrors the machine-check containment rule (docs/08 §6.2/§6.3): the ref is
    joined to the candidate's authorized ``workspace_path`` and must stay inside
    it; a ref that escapes or does not resolve to a file is absent.
    """

    base_raw = candidate.workspace_path
    if not base_raw:
        return None
    try:
        base = Path(base_raw).resolve()
        target = (base / payload).resolve()
    except OSError:
        return None
    if target != base and base not in target.parents:
        return None
    return target if target.is_file() else None

def declared_path_refs(candidate: Candidate) -> tuple[str, ...]:
    """Candidate artifact refs that *claim* to be resolvable path evidence.

    Opaque executor ids are excluded: they are not missing files, they are just
    not path evidence.  An empty tuple means the candidate declares no path
    evidence at all (LG-009 runs zero evidence checks in that case).
    """

    refs: list[str] = []
    for ref in candidate.artifact_refs:
        if not isinstance(ref, str) or not ref:
            continue
        kind, payload = classify_artifact_ref(ref)
        if kind in {EVIDENCE_REF, WORKSPACE_REF, ABSOLUTE_REF} and payload:
            refs.append(ref)
    return tuple(refs)


def validate_findings(
    report: ReviewReport,
    *,
    candidate: Candidate,
    resolved_evidence: dict[str, Path],
) -> ReviewReport:
    """Drop findings that do not cite a resolvable, candidate-owned artifact.

    This is the program gate that makes the reviewer's output trustworthy: a
    model (or check) can only raise a problem against *real* evidence.  Findings
    that fail are reported under ``unsubstantiated``; a ``rework`` report whose
    every finding is dropped degrades to ``unavailable`` rather than blocking
    with no evidence.
    """

    kept: list[Finding] = []
    dropped: list[str] = []
    for finding in report.findings:
        ref = finding.evidence_ref
        if (
            not finding.summary.strip()
            or finding.severity not in _SEVERITIES
            or not ref
            or ref == _NO_REF
            or ref not in resolved_evidence
        ):
            dropped.append(finding.finding_id or finding.summary or "<unnamed>")
            continue
        # Bind the finding to the reviewed candidate, never a foreign one.
        kept.append(
            Finding(
                finding_id=finding.finding_id,
                severity=finding.severity,
                summary=finding.summary,
                evidence_ref=ref,
                rework_target=finding.rework_target,
                candidate_ref=candidate.candidate_ref,
                detail=finding.detail,
            )
        )
    outcome = report.outcome
    if outcome == REVIEW_REWORK and not any(f.severity == SEV_BLOCKING for f in kept):
        # A rework with no substantiated blocking finding cannot force rework.
        outcome = REVIEW_UNAVAILABLE
    return ReviewReport(
        outcome=outcome,
        candidate_ref=candidate.candidate_ref,
        findings=tuple(kept),
        unsubstantiated=tuple(dropped),
        reviewer=report.reviewer,
        reason=report.reason,
    )


class ProgramReviewer:
    """Deterministic default reviewer (no model call).

    Independent of the implementer because it only reads the candidate snapshot
    and re-runs the Task-authorized machine checks in its own context, then
    confirms every candidate artifact actually resolves.  It produces a
    ``rework`` finding against the failing evidence when checks fail, and a
    ``passed`` report only when there is at least one real resolvable artifact
    to have reviewed (a candidate with *no* evidence is ``unavailable``, never a
    silent pass).
    """

    name = "program-reviewer"

    def __init__(self, registry: CheckRegistry | None = None) -> None:
        self._registry = registry or default_check_registry()

    def review(self, context: ReviewContext) -> ReviewReport:
        candidate = context.candidate
        resolved = context.resolved_evidence

        # Declared-but-unresolvable path evidence is a real integrity problem:
        # the candidate claims artifacts it cannot produce.  Opaque executor ids
        # (not paths) are excluded.  The reviewer cannot anchor a finding to a
        # missing file, so it reports unavailable (an honest bounded failure)
        # rather than a pass or a fabricated finding.
        declared = declared_path_refs(candidate)
        if declared and not resolved:
            return ReviewReport(
                outcome=REVIEW_UNAVAILABLE,
                candidate_ref=candidate.candidate_ref,
                reviewer=self.name,
                reason=(
                    f"candidate declares {len(declared)} artifact ref(s) but none resolve; "
                    "cannot substantiate an independent review"
                ),
            )

        authorized = authorized_checks(
            context.store.read("task", candidate.task_id).entity
        )
        from .checks import CheckContext

        report = run_checks(
            self._registry,
            authorized,
            CheckContext(
                task_id=candidate.task_id,
                run_id=candidate.run_id,
                candidate=candidate,
                store=context.store,
                workspace_path=candidate.workspace_path,
            ),
        )
        failed = [r for r in report.results if r.status in BLOCKING_STATUSES]
        if failed:
            if not resolved:
                # Nothing resolvable to anchor a finding to; this is an
                # unavailable review, never a fabricated rework or a pass.
                return ReviewReport(
                    outcome=REVIEW_UNAVAILABLE,
                    candidate_ref=candidate.candidate_ref,
                    reviewer=self.name,
                    reason="blocking check(s) failed but no candidate evidence resolves",
                )
            # Cite the first resolvable artifact as the evidence anchor: the
            # finding is about the candidate as a whole, and the anchor must be
            # a real owned file for the finding to survive validation.
            anchor = next(iter(resolved))
            findings = tuple(
                Finding(
                    finding_id=f"check:{r.check_id}",
                    severity=SEV_BLOCKING,
                    summary=f"machine check {r.check_id!r} reported {r.status}",
                    evidence_ref=anchor,
                    rework_target=(
                        candidate.subtask_refs[0] if candidate.subtask_refs else "deliverable"
                    ),
                    detail=r.detail,
                )
                for r in failed
            )
            return ReviewReport(
                outcome=REVIEW_REWORK,
                candidate_ref=candidate.candidate_ref,
                findings=findings,
                reviewer=self.name,
                reason=f"{len(failed)} blocking machine check(s) failed",
            )
        return ReviewReport(
            outcome=REVIEW_PASSED,
            candidate_ref=candidate.candidate_ref,
            reviewer=self.name,
            reason=(
                "independent program review found no blocking problem "
                f"across {len(resolved)} artifact(s)"
            ),
        )


class UnavailableReviewer:
    """Explicit "no independent reviewer is wired" reviewer.

    Used as the honest default when the runtime has no reviewer configured: it
    returns ``unavailable`` so the orchestrator keeps the candidate pending for
    a human/next step instead of accepting it, and never spends a rework round.
    """

    name = "unavailable"

    def review(self, context: ReviewContext) -> ReviewReport:
        return ReviewReport(
            outcome=REVIEW_UNAVAILABLE,
            candidate_ref=context.candidate.candidate_ref,
            reviewer=self.name,
            reason="no independent reviewer is configured in this runtime",
        )


__all__ = [
    "Finding",
    "ProgramReviewer",
    "REVIEW_PASSED",
    "REVIEW_REWORK",
    "REVIEW_UNAVAILABLE",
    "ReviewContext",
    "ReviewReport",
    "Reviewer",
    "SEV_ADVISORY",
    "SEV_BLOCKING",
    "UnavailableReviewer",
    "declared_path_refs",
    "resolve_candidate_evidence",
    "validate_findings",
]
