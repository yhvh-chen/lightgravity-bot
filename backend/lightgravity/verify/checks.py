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
        return not any(result.status in BLOCKING_STATUSES for result in self.results)

    @property
    def failed_ids(self) -> tuple[str, ...]:
        return tuple(result.check_id for result in self.results if result.status in BLOCKING_STATUSES)

    def to_dict(self) -> dict[str, Any]:
        return {
            "results": [result.to_dict() for result in self.results],
            "authorized": list(self.authorized),
            "registered": list(self.registered),
            "satisfied": self.satisfied,
        }


def artifact_path(ref: str) -> str | None:
    """Return the workspace-relative path of an artifact ref, else ``None``.

    Handoff refs are encoded as ``<subtask>@<hash>:<artifact>`` (scheduler.py);
    non-path artifacts (opaque ids, URLs) are ignored rather than guessed at.
    """

    _, _, rest = ref.partition("@")
    artifact = rest.partition(":")[2] if "@" in ref else ref
    if not artifact or "://" in artifact:
        return None
    if "/" in artifact or "." in artifact:
        return artifact
    return None


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


def _artifacts_in_workspace(context: CheckContext) -> CheckOutcome:
    candidate = context.candidate
    raw_refs = [ref for ref in candidate.artifact_refs]
    paths = [path for path in (artifact_path(ref) for ref in raw_refs) if path]
    if not paths:
        return CheckOutcome(
            passed=True,
            detail="no workspace-relative artifact paths declared",
            skipped=True,
        )
    if not context.workspace_path:
        return CheckOutcome(
            passed=False,
            detail="candidate declares workspace artifacts but has no authorized workspace",
        )
    base = Path(context.workspace_path).resolve()
    missing: list[str] = []
    escaped: list[str] = []
    for relative in paths:
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
    problems: list[str] = []
    if missing:
        problems.append("missing: " + ", ".join(sorted(set(missing))))
    if escaped:
        problems.append("outside workspace: " + ", ".join(sorted(set(escaped))))
    if problems:
        return CheckOutcome(passed=False, detail="; ".join(problems))
    return CheckOutcome(passed=True, detail=f"{len(paths)} artifact path(s) verified")


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
            description="Workspace-relative artifact refs must exist inside the task workspace.",
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
    "artifact_path",
    "authorized_checks",
    "default_check_registry",
    "run_checks",
]
