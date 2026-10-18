"""Program-registered machine checks (LG-009).

Only checks that are (a) registered in-process here and (b) authorized by the
Task can run.  A Task authorization is an optional ``checks:`` list in its
frontmatter; an id that is authorized but not registered is reported as
``unconfigured`` and is **not** run.  Nothing in this module imports or evaluates
Markdown/resource content - a handler is a Python callable registered in code.

The check set is deliberately small and honest: a worker summary is never
accepted as evidence, and an unconfigured/unknown check is never reported as
passed.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lightgravity.evidence import (
    EVIDENCE_SCHEME,
    EvidenceRefError,
    resolve_evidence_ref,
)
from lightgravity.store import Store

from .candidate import Candidate

#: Check statuses. ``passed``/``failed`` are real outcomes, ``skipped`` is a
#: truthful "nothing to check", ``unconfigured`` an authorized-but-unregistered
#: id and ``error`` a handler crash (never silently treated as passed).
CHECK_PASSED = "passed"
CHECK_FAILED = "failed"
CHECK_SKIPPED = "skipped"
CHECK_UNCONFIGURED = "unconfigured"
CHECK_ERROR = "error"

#: Statuses that block preparing a candidate for human acceptance.
BLOCKING_STATUSES = frozenset({CHECK_FAILED, CHECK_ERROR})


@dataclass(frozen=True, slots=True)
class CheckOutcome:
    """What a registered handler returns."""

    passed: bool
    detail: str = ""
    skipped: bool = False


@dataclass(frozen=True, slots=True)
class CheckResult:
    check_id: str
    status: str
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"check_id": self.check_id, "status": self.status, "detail": self.detail}


@dataclass(frozen=True, slots=True)
class CheckContext:
    """Everything a registered check is allowed to inspect (read-only)."""

    task_id: str
    run_id: str
    candidate: Candidate
    store: Store
    workspace_path: str | None = None


CheckHandler = Callable[[CheckContext], CheckOutcome]


@dataclass(frozen=True, slots=True)
class CheckRegistration:
    check_id: str
    handler: CheckHandler
    description: str = ""


class CheckRegistry:
    """In-process registry of machine checks (the only executable gate)."""

    def __init__(self) -> None:
        self._checks: dict[str, CheckRegistration] = {}

    def register(self, registration: CheckRegistration) -> None:
        self._checks[registration.check_id] = registration

    def get(self, check_id: str) -> CheckRegistration | None:
        return self._checks.get(check_id)

    def check_ids(self) -> tuple[str, ...]:
        return tuple(self._checks)

    def __contains__(self, check_id: object) -> bool:
        return isinstance(check_id, str) and check_id in self._checks


@dataclass(frozen=True, slots=True)
class CheckReport:
    """Outcome of running exactly the authorized/registered checks."""

    results: tuple[CheckResult, ...]
    authorized: tuple[str, ...]
    registered: tuple[str, ...]

    @property
    def satisfied(self) -> bool:
        return bool(self.authorized) and all(
            any(result.check_id == check_id and result.status == CHECK_PASSED
                for result in self.results)
            for check_id in self.authorized
        )

    @property
    def failed_ids(self) -> tuple[str, ...]:
        return tuple(check_id for check_id in self.authorized if not any(
            result.check_id == check_id and result.status == CHECK_PASSED
            for result in self.results
        ))

    def to_dict(self) -> dict[str, Any]:
        return {
            "results": [result.to_dict() for result in self.results],
            "authorized": list(self.authorized),
            "registered": list(self.registered),
            "satisfied": self.satisfied,
        }


#: Reference classes understood by the machine checks (docs/08 §6.2/§6.3).
WORKSPACE_REF = "workspace"
EVIDENCE_REF = "evidence"
ABSOLUTE_REF = "absolute"
OPAQUE_REF = "opaque"


def artifact_payload(ref: str) -> str | None:
    """Extract the artifact payload from a handoff or evidence reference.

    Handoff refs are encoded as ``<subtask>@<hash>:<artifact>`` (scheduler.py).
    A canonical evidence ref (``evidence:<run>/<name>@sha256:<hex>``) is kept
    whole; a bare absolute path is kept so callers can classify (and reject) it
    instead of silently treating it as workspace-relative.  URLs/opaque ids are
    ignored rather than guessed at.
    """

    if not isinstance(ref, str) or not ref:
        return None
    if ref.startswith(EVIDENCE_SCHEME):
        return ref
    if os.path.isabs(ref):
        return ref
    if "://" in ref:
        return None
    if "@" in ref:
        _, _, rest = ref.partition("@")
        if ":" not in rest:
            return None
        artifact = rest.partition(":")[2]
        return artifact or None
    return ref


def artifact_path(ref: str) -> str | None:
    """Return the path-like payload of an artifact ref, else ``None``.

    Non-path artifacts (opaque ids, URLs) are ignored rather than guessed at.
    Use :func:`classify_artifact_ref` to tell workspace-relative, canonical
    evidence and unauthorized absolute refs apart.
    """

    artifact = artifact_payload(ref)
    if artifact is None:
        return None
    if "/" in artifact or "." in artifact:
        return artifact
    return None


def classify_artifact_ref(ref: str) -> tuple[str, str | None]:
    """Classify an evidence ref into an explicit resolution namespace.

    Returns ``(kind, payload)`` where ``kind`` is one of ``workspace`` (resolve
    under the authorized workspace root), ``evidence`` (resolve under the
    Task/Run-owned evidence root), ``absolute`` (a raw absolute path with no
    authorized root: rejected), or ``opaque`` (not a path; ignored).
    """

    artifact = artifact_payload(ref)
    if artifact is None:
        return OPAQUE_REF, None
    if artifact.startswith(EVIDENCE_SCHEME):
        return EVIDENCE_REF, artifact
    if os.path.isabs(artifact):
        return ABSOLUTE_REF, artifact
    if "/" in artifact or "." in artifact:
        return WORKSPACE_REF, artifact
    return OPAQUE_REF, None


def _evidence_present(context: CheckContext) -> CheckOutcome:
    candidate = context.candidate
    if candidate.artifact_refs or candidate.diff_ref:
        return CheckOutcome(
            passed=True,
            detail=f"{len(candidate.artifact_refs)} evidence ref(s) recorded",
        )
    return CheckOutcome(
        passed=False,
        detail="no artifact or diff evidence recorded; a worker summary alone is not evidence",
    )


def _workspace_problems(context: CheckContext, refs: Sequence[str]) -> list[str]:
    """Validate workspace-relative refs against the authorized workspace root."""

    problems: list[str] = []
    if not context.workspace_path:
        return ["candidate declares workspace artifacts but has no authorized workspace"]
    base = Path(context.workspace_path).resolve()
    missing: list[str] = []
    escaped: list[str] = []
    for relative in refs:
        try:
            target = (base / relative).resolve()
        except OSError:
            missing.append(relative)
            continue
        if target != base and not str(target).startswith(str(base) + os.sep):
            escaped.append(relative)
            continue
        if not target.exists():
            missing.append(relative)
    if missing:
        problems.append("missing: " + ", ".join(sorted(set(missing))))
    if escaped:
        problems.append("outside workspace: " + ", ".join(sorted(set(escaped))))
    return problems


def _evidence_problems(context: CheckContext, refs: Sequence[str]) -> list[str]:
    """Validate canonical evidence refs against the Task/Run evidence root."""

    data_dir = getattr(context.store, "data_dir", None) if context.store is not None else None
    problems: list[str] = []
    for ref in refs:
        try:
            resolve_evidence_ref(
                ref,
                data_dir=data_dir,
                task_id=context.task_id,
                run_id=context.run_id,
            )
        except EvidenceRefError as exc:
            problems.append(str(exc))
    return problems


def _artifacts_in_workspace(context: CheckContext) -> CheckOutcome:
    candidate = context.candidate
    workspace_refs: list[str] = []
    evidence_refs: list[str] = []
    problems: list[str] = []
    for ref in candidate.artifact_refs:
        kind, payload = classify_artifact_ref(ref)
        if kind == WORKSPACE_REF and payload:
            workspace_refs.append(payload)
        elif kind == EVIDENCE_REF and payload:
            evidence_refs.append(payload)
        elif kind == ABSOLUTE_REF:
            # A raw absolute path has no authorized root; never resolve it.
            problems.append(f"unauthorized absolute artifact ref: {ref}")
        # Opaque refs (ids, URLs) are not paths and are not checked here.
    if not workspace_refs and not evidence_refs:
        if problems:
            return CheckOutcome(passed=False, detail="; ".join(sorted(set(problems))))
        return CheckOutcome(
            passed=True,
            detail="no workspace or evidence artifact paths declared",
            skipped=True,
        )
    if workspace_refs:
        problems.extend(_workspace_problems(context, workspace_refs))
    if evidence_refs:
        problems.extend(_evidence_problems(context, evidence_refs))
    if problems:
        return CheckOutcome(passed=False, detail="; ".join(sorted(set(problems))))
    total = len(workspace_refs) + len(evidence_refs)
    return CheckOutcome(passed=True, detail=f"{total} artifact ref(s) verified")


def default_check_registry() -> CheckRegistry:
    """The minimal registered check set for the first version."""

    registry = CheckRegistry()
    registry.register(
        CheckRegistration(
            check_id="evidence-present",
            handler=_evidence_present,
            description="Candidate must record real artifact/diff evidence, not a summary.",
        )
    )
    registry.register(
        CheckRegistration(
            check_id="artifacts-in-workspace",
            handler=_artifacts_in_workspace,
            description=(
                "Artifact refs must resolve inside the authorized workspace root "
                "(relative refs) or the Task/Run-owned evidence root (canonical "
                "evidence refs); raw absolute paths are rejected."
            ),
        )
    )
    return registry


def run_checks(
    registry: CheckRegistry,
    authorized: Sequence[str],
    context: CheckContext,
) -> CheckReport:
    """Run only authorized+registered checks, honestly reporting the rest."""

    results: list[CheckResult] = []
    for check_id in authorized:
        registration = registry.get(check_id)
        if registration is None:
            results.append(
                CheckResult(
                    check_id=check_id,
                    status=CHECK_UNCONFIGURED,
                    detail="authorized check is not registered; it was not run",
                )
            )
            continue
        try:
            outcome = registration.handler(context)
        except Exception as exc:  # noqa: BLE001 - a crash is an error, never a pass
            results.append(
                CheckResult(
                    check_id=check_id,
                    status=CHECK_ERROR,
                    detail=f"{type(exc).__name__}: {exc}",
                )
            )
            continue
        if outcome.skipped:
            status = CHECK_SKIPPED
        else:
            status = CHECK_PASSED if outcome.passed else CHECK_FAILED
        results.append(CheckResult(check_id=check_id, status=status, detail=outcome.detail))
    return CheckReport(
        results=tuple(results),
        authorized=tuple(authorized),
        registered=registry.check_ids(),
    )


def authorized_checks(task_entity: dict[str, Any]) -> tuple[str, ...]:
    """Read the Task's optional ``checks`` authorization list (strings only)."""

    raw = task_entity.get("checks")
    if not isinstance(raw, (list, tuple)):
        return ()
    result: list[str] = []
    for item in raw:
        if isinstance(item, str) and item.strip() and item not in result:
            result.append(item.strip())
    return tuple(result)


def required_checks(task_entity: dict[str, Any]) -> tuple[str, ...]:
    """Required policy never grants execution authority to missing checks."""
    if task_entity.get("machine_check_policy") == "default_delivery_v1":
        return tuple(dict.fromkeys(("evidence-present", "artifacts-in-workspace", *authorized_checks(task_entity))))
    return authorized_checks(task_entity)


__all__ = [
    "BLOCKING_STATUSES",
    "CHECK_ERROR",
    "CHECK_FAILED",
    "CHECK_PASSED",
    "CHECK_SKIPPED",
    "CHECK_UNCONFIGURED",
    "CheckContext",
    "CheckHandler",
    "CheckOutcome",
    "CheckRegistration",
    "CheckRegistry",
    "CheckReport",
    "CheckResult",
    "ABSOLUTE_REF",
    "EVIDENCE_REF",
    "OPAQUE_REF",
    "WORKSPACE_REF",
    "artifact_path",
    "artifact_payload",
    "authorized_checks",
    "classify_artifact_ref",
    "default_check_registry",
    "run_checks",
    "required_checks",
]
