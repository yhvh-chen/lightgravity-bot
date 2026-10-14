"""Machine verification and human acceptance (LG-009).

This package owns the ``verify/**`` boundary from docs/08 §11:

* :mod:`~lightgravity.verify.candidate` snapshots a Run's delivery evidence;
* :mod:`~lightgravity.verify.checks` is the in-process registry of machine
  checks a Task may authorize (Markdown never supplies executable code);
* :mod:`~lightgravity.verify.stopgate` confirms executors/sessions stopped and
  releases the team / execution slot before ``awaiting_acceptance``;
* :class:`~lightgravity.verify.service.VerificationService` runs verification,
  binds decisions to the requirements + candidate version and is idempotent;
* :mod:`~lightgravity.verify.router` exposes an independent router factory for
  LG-012 / the integration owner to mount (``api/app.py`` is untouched).

Scope boundary: LG-009 implements the first-version verification + acceptance
seam.  Multi-round repair orchestration is LG-017; the real SDK end-to-end path
is LG-010; new-Run creation stays with the coordinator's real state.
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
    "ResourceStopper",
    "StopReport",
    "StoreResourceStopper",
    "VerificationService",
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
