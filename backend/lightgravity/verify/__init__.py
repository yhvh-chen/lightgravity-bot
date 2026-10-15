"""Machine verification and human acceptance (LG-009).

This package owns the ``verify/**`` boundary from docs/08 §11:

* :mod:`~lightgravity.verify.candidate` snapshots a Run's delivery evidence;
* :mod:`~lightgravity.verify.checks` is the in-process registry of machine
  checks a Task may authorize (Markdown never supplies executable code);
* :mod:`~lightgravity.verify.stopgate` confirms executors/sessions stopped and
  releases the team / execution slot before ``awaiting_acceptance``;
* :class:`~lightgravity.verify.service.VerificationService` runs verification,
  binds decisions to the requirements + candidate version and is idempotent;
* :mod:`~lightgravity.verify.review` is the independent reviewer port +
  deterministic program reviewer with structured, evidence-bound findings;
* :class:`~lightgravity.verify.rework.ReworkOrchestrator` drives bounded business
  rework (separate from SDK retries, Task-lifetime budget across Runs);
* :mod:`~lightgravity.verify.router` exposes an independent router factory for
  LG-012 / the integration owner to mount (``api/app.py`` is untouched).

Scope boundary: LG-009 implements the first-version verification + acceptance
seam.  LG-017 adds the independent candidate review and bounded rework loop; the
real SDK end-to-end path is LG-010; new-Run creation stays with the coordinator.
"""

from .candidate import Candidate, load_candidate
from .checks import (
    BLOCKING_STATUSES,
    CHECK_ERROR,
    CHECK_FAILED,
    CHECK_PASSED,
    CHECK_SKIPPED,
    CHECK_UNCONFIGURED,
    CheckContext,
    CheckOutcome,
    CheckRegistration,
    CheckRegistry,
    CheckReport,
    CheckResult,
    ABSOLUTE_REF,
    EVIDENCE_REF,
    OPAQUE_REF,
    WORKSPACE_REF,
    artifact_path,
    artifact_payload,
    authorized_checks,
    classify_artifact_ref,
    default_check_registry,
    run_checks,
)
from .review import (
    DEFAULT_REVIEW_MODEL_CALLS,
    DEFAULT_REVIEW_TIMEOUT_SECONDS,
    Finding,
    ModelReviewer,
    ProgramReviewer,
    REVIEW_PASSED,
    REVIEW_REWORK,
    REVIEW_UNAVAILABLE,
    SEV_ADVISORY,
    SEV_BLOCKING,
    ReviewContext,
    ReviewReport,
    Reviewer,
    ReviewerSupport,
    UnavailableReviewer,
    resolve_candidate_evidence,
    resolve_reviewer_support,
    run_review_turn,
    validate_findings,
)
from .rework import (
    REWORK_BLOCKED,
    REWORK_EXHAUSTED,
    REWORK_OPENED,
    REWORK_SPAWNED,
    REWORK_UNAVAILABLE,
    ReworkLedger,
    ReworkOrchestrator,
    ReworkResult,
    RunSpawner,
    load_ledger,
)
from .router import ActionRequest, build_acceptance_router, build_router
from .service import ActionResult, AcceptanceView, VerificationService
from .stopgate import (
    ACTIVE_RUN_STATES,
    TERMINAL_MEMBER_STATES,
    ResourceStopper,
    StopReport,
    StoreResourceStopper,
)

__all__ = [
    "ACTIVE_RUN_STATES",
    "BLOCKING_STATUSES",
    "CHECK_ERROR",
    "CHECK_FAILED",
    "CHECK_PASSED",
    "CHECK_SKIPPED",
    "CHECK_UNCONFIGURED",
    "TERMINAL_MEMBER_STATES",
    "AcceptanceView",
    "ActionResult",
    "ActionRequest",
    "Candidate",
    "CheckContext",
    "CheckOutcome",
    "CheckRegistration",
    "CheckRegistry",
    "CheckReport",
    "CheckResult",
    "Finding",
    "ModelReviewer",
    "ProgramReviewer",
    "REVIEW_PASSED",
    "REVIEW_REWORK",
    "REVIEW_UNAVAILABLE",
    "REWORK_BLOCKED",
    "REWORK_EXHAUSTED",
    "REWORK_OPENED",
    "REWORK_SPAWNED",
    "REWORK_UNAVAILABLE",
    "ResourceStopper",
    "ReviewContext",
    "ReviewReport",
    "Reviewer",
    "ReviewerSupport",
    "ReworkLedger",
    "ReworkOrchestrator",
    "ReworkResult",
    "RunSpawner",
    "SEV_ADVISORY",
    "SEV_BLOCKING",
    "StopReport",
    "StoreResourceStopper",
    "UnavailableReviewer",
    "VerificationService",
    "load_ledger",
    "resolve_candidate_evidence",
    "resolve_reviewer_support",
    "run_review_turn",
    "validate_findings",
    "ABSOLUTE_REF",
    "EVIDENCE_REF",
    "OPAQUE_REF",
    "WORKSPACE_REF",
    "artifact_path",
    "artifact_payload",
    "authorized_checks",
    "classify_artifact_ref",
    "build_acceptance_router",
    "build_router",
    "default_check_registry",
    "load_candidate",
    "run_checks",
]
