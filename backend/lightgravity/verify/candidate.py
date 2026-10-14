"""Candidate evidence snapshot for verification and acceptance (LG-009).

A *candidate* is the delivery produced by one Run (docs/08 §6.1/§6.2): the
Task's requirements/deliverable revisions, the Run's plan hash, the recruited
members and the evidence refs recorded on its Subtasks.  Verification and human
acceptance bind to this snapshot.  Loading a candidate only reads Store
frontmatter; it never executes a resource, reads a Markdown body as code, or
treats a worker summary as evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lightgravity.contracts import AppError, ErrorCode
from lightgravity.evidence import EVIDENCE_SCHEME, EvidenceRefError, parse_evidence_ref
from lightgravity.store import EntityNotFound, Store

#: Suffixes that let a recorded artifact ref be reported as the candidate diff.
_DIFF_SUFFIXES = (".diff", ".patch")


@dataclass(frozen=True, slots=True)
class Candidate:
    """The delivery snapshot bound to a human acceptance decision."""

    task_id: str
    run_id: str
    run_state: str
    attempt: int
    plan_hash: str | None
    requirements_revision: int
    deliverable_revision: int
    workspace_ref: str | None
    workspace_path: str | None
    member_refs: tuple[str, ...]
    subtask_refs: tuple[str, ...]
    artifact_refs: tuple[str, ...]
    diff_ref: str | None
    session_refs: tuple[str, ...]
    check_records: tuple[dict[str, Any], ...]

    @property
    def binding(self) -> dict[str, Any]:
        """The version tuple an accept/reject decision is bound to."""

        return {
            "task_id": self.task_id,
            "run_id": self.run_id,
            "requirements_revision": self.requirements_revision,
            "deliverable_revision": self.deliverable_revision,
            "plan_hash": self.plan_hash,
        }

    @property
    def candidate_ref(self) -> str:
        return self.run_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "candidate_ref": self.candidate_ref,
            "run_id": self.run_id,
            "run_state": self.run_state,
            "attempt": self.attempt,
            "plan_hash": self.plan_hash,
            "requirements_revision": self.requirements_revision,
            "deliverable_revision": self.deliverable_revision,
            "workspace_ref": self.workspace_ref,
            "workspace_path": self.workspace_path,
            "member_refs": list(self.member_refs),
            "subtask_refs": list(self.subtask_refs),
            "artifact_refs": list(self.artifact_refs),
            "diff_ref": self.diff_ref,
            "session_refs": list(self.session_refs),
            "check_records": list(self.check_records),
        }


def _str_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(item for item in value if isinstance(item, str) and item)


def _is_diff_ref(ref: str) -> bool:
    """Whether a recorded ref names a diff/patch artifact.

    Canonical evidence refs append a digest after the name
    (``evidence:<run>/<name>@sha256:<hex>``), so the suffix check must look at
    the parsed artifact name rather than the raw string tail.
    """

    if ref.startswith(EVIDENCE_SCHEME):
        try:
            parsed = parse_evidence_ref(ref)
        except EvidenceRefError:
            return False
        if parsed is None:
            return False
        return parsed.name.lower().endswith(_DIFF_SUFFIXES)
    return ref.lower().endswith(_DIFF_SUFFIXES)


def load_candidate(store: Store, task_id: str) -> Candidate:
    """Load the active Run's candidate, or raise ``not_ready``."""

    task = store.read("task", task_id)
    run_id = task.entity.get("active_run")
    if not isinstance(run_id, str) or not run_id:
        raise AppError(
            ErrorCode.NOT_READY,
            "task has no active run candidate",
            details={"task_id": task_id},
        )
    try:
        run = store.read("run", run_id)
    except EntityNotFound as exc:
        raise AppError(
            ErrorCode.NOT_READY,
            f"active run {run_id!r} no longer exists",
            details={"task_id": task_id, "run_id": run_id},
        ) from exc

    subtask_refs = _str_tuple(run.entity.get("subtask_refs"))
    artifacts: list[str] = []
    records: list[dict[str, Any]] = []
    for ref in subtask_refs:
        try:
            subtask = store.read("subtask", ref)
        except EntityNotFound:
            continue
        acceptance = subtask.entity.get("acceptance")
        if isinstance(acceptance, dict):
            for item in _str_tuple(acceptance.get("evidence_refs")):
                if item not in artifacts:
                    artifacts.append(item)
        for record in subtask.entity.get("check_records") or []:
            if isinstance(record, dict):
                records.append(dict(record))

    diff_ref = next(
        (ref for ref in artifacts if _is_diff_ref(ref)), None
    )
    workspace_ref_raw = task.entity.get("workspace_ref")
    workspace_ref = (
        workspace_ref_raw if isinstance(workspace_ref_raw, str) and workspace_ref_raw else None
    )
    workspace_path: str | None = None
    if workspace_ref is not None:
        try:
            workspace_path = str(store.resolve_path(workspace_ref, write=False))
        except Exception:  # noqa: BLE001 - an unresolvable workspace is reported, not faked
            workspace_path = None

    requirements_revision = task.entity.get("requirements_revision")
    deliverable_revision = task.entity.get("deliverable_revision")
    attempt = run.entity.get("attempt")
    plan_hash = run.entity.get("plan_hash")
    return Candidate(
        task_id=task_id,
        run_id=run_id,
        run_state=str(run.entity.get("state", "")),
        attempt=attempt if isinstance(attempt, int) and not isinstance(attempt, bool) else 1,
        plan_hash=plan_hash if isinstance(plan_hash, str) and plan_hash else None,
        requirements_revision=(
            requirements_revision
            if isinstance(requirements_revision, int) and not isinstance(requirements_revision, bool)
            else 0
        ),
        deliverable_revision=(
            deliverable_revision
            if isinstance(deliverable_revision, int) and not isinstance(deliverable_revision, bool)
            else 0
        ),
        workspace_ref=workspace_ref,
        workspace_path=workspace_path,
        member_refs=_str_tuple(run.entity.get("team_refs")),
        subtask_refs=subtask_refs,
        artifact_refs=tuple(artifacts),
        diff_ref=diff_ref,
        session_refs=_str_tuple(run.entity.get("session_refs")),
        check_records=tuple(records),
    )


__all__ = ["Candidate", "load_candidate"]
