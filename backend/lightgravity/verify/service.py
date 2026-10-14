"""Verification and human-acceptance service (LG-009).

This service owns the ``verifying`` -> ``awaiting_acceptance`` -> ``completed``
(or ``repairing``) transitions described in docs/08 §6.1 and §9.  It:

* runs only program-registered checks that the Task authorizes;
* refuses to hand a candidate to human acceptance until every executor and
  session is confirmed stopped and the team / execution slot are released;
* binds accept/reject to the exact requirements + candidate (run/plan) version;
* is idempotent per ``request_id`` and rejects stale/duplicate decisions;
* never merges, pushes or deploys.

All control state is written through :class:`~lightgravity.coordinator.state.StateWriter`
(and therefore the ``Store``), preserving the Markdown body and unknown
frontmatter fields.  Workers never write control state.  Multi-round repair
orchestration stays with LG-017; this service only exposes the repair interface
and leaves new-Run creation to the coordinator's real state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lightgravity.contracts import (
    AcceptanceStatus,
    AppError,
    ErrorCode,
    EventType,
    RunState,
    TaskPhase,
)
from lightgravity.coordinator.logs import IdempotencyLog
from lightgravity.coordinator.state import StateWriter
from lightgravity.store import RevisionConflict, Store
from lightgravity.store.locking import LockManager

from .candidate import Candidate, load_candidate
from .checks import (
    CheckRegistry,
    CheckReport,
    CheckContext,
    authorized_checks,
    default_check_registry,
    run_checks,
)
from .stopgate import ResourceStopper, StopReport, StoreResourceStopper

_DECISION_ACTIONS = frozenset({"accept", "reject"})


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _int_field(entity: dict[str, Any], key: str) -> int:
    value = entity.get(key)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return 0


@dataclass(frozen=True, slots=True)
class ActionResult:
    """Serializable result of a verify/accept/reject/repair call."""

    action: str
    state: str  # confirmed | unconfirmed
    confirmed: bool
    task_id: str
    phase: str
    acceptance: dict[str, Any] = field(default_factory=dict)
    request_id: str | None = None
    candidate_ref: str | None = None
    messages: tuple[str, ...] = ()
    candidate: dict[str, Any] | None = None
    checks: dict[str, Any] | None = None
    stop: dict[str, Any] | None = None

    @property
    def status(self) -> str:
        """Alias for the wire ``state`` field (docs/08 §4.3 response shape)."""

        return self.state

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "state": self.state,
            "confirmed": self.confirmed,
            "task_id": self.task_id,
            "phase": self.phase,
            "acceptance": self.acceptance,
            "request_id": self.request_id,
            "candidate_ref": self.candidate_ref,
            "messages": list(self.messages),
            "candidate": self.candidate,
            "checks": self.checks,
            "stop": self.stop,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ActionResult":
        acceptance_raw = data.get("acceptance")
        return cls(
            action=str(data.get("action", "")),
            state=str(data.get("state", "unconfirmed")),
            confirmed=bool(data.get("confirmed", False)),
            task_id=str(data.get("task_id", "")),
            phase=str(data.get("phase", "")),
            acceptance=dict(acceptance_raw) if isinstance(acceptance_raw, dict) else {},
            request_id=data.get("request_id") if isinstance(data.get("request_id"), str) else None,
            candidate_ref=(
                data.get("candidate_ref") if isinstance(data.get("candidate_ref"), str) else None
            ),
            messages=tuple(str(item) for item in data.get("messages") or ()),
            candidate=data.get("candidate") if isinstance(data.get("candidate"), dict) else None,
            checks=data.get("checks") if isinstance(data.get("checks"), dict) else None,
            stop=data.get("stop") if isinstance(data.get("stop"), dict) else None,
        )


@dataclass(frozen=True, slots=True)
class AcceptanceView:
    """Read-only snapshot of a Task's candidate + acceptance state."""

    task_id: str
    phase: str
    status: str
    revision: int
    requirements_revision: int
    deliverable_revision: int
    acceptance: dict[str, Any]
    candidate: dict[str, Any] | None = None
    checks: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "phase": self.phase,
            "status": self.status,
            "revision": self.revision,
            "requirements_revision": self.requirements_revision,
            "deliverable_revision": self.deliverable_revision,
            "acceptance": self.acceptance,
            "candidate": self.candidate,
            "checks": self.checks,
        }


class VerificationService:
    """Machine verification + human acceptance for one Store."""

    def __init__(
        self,
        store: Store,
        *,
        registry: CheckRegistry | None = None,
        stopper: ResourceStopper | None = None,
        actor: str = "verify",
        max_retries: int = 8,
    ) -> None:
        self._store = store
        self._registry = registry or default_check_registry()
        self._writer = StateWriter(store, actor=actor, max_retries=max_retries)
        self._stopper: ResourceStopper = stopper or StoreResourceStopper(store, writer=self._writer)
        self._actor = actor
        data_dir = getattr(store, "data_dir", None)
        if data_dir is None:
            raise AppError(
                ErrorCode.INTERNAL_ERROR,
                "verification service requires a store exposing data_dir",
            )
        self._idempotency = IdempotencyLog(data_dir, LockManager(Path(data_dir) / "locks"))

    # -------------------------------------------------------------- read-only
    @property
    def registry(self) -> CheckRegistry:
        return self._registry

    def candidate(self, task_id: str) -> Candidate | None:
        try:
            return load_candidate(self._store, task_id)
        except AppError:
            return None

    def acceptance(self, task_id: str) -> AcceptanceView:
        task = self._store.read("task", task_id)
        acceptance = task.entity.get("acceptance")
        acceptance_map = acceptance if isinstance(acceptance, dict) else {}
        candidate = self.candidate(task_id)
        checks: CheckReport | None = None
        if candidate is not None:
            try:
                checks = self._run_checks(task.entity, candidate)
            except AppError:
                checks = None
        return AcceptanceView(
            task_id=task_id,
            phase=str(task.entity.get("phase", "")),
            status=str(task.entity.get("status", "")),
            revision=task.revision,
            requirements_revision=_int_field(task.entity, "requirements_revision"),
            deliverable_revision=_int_field(task.entity, "deliverable_revision"),
            acceptance=dict(acceptance_map),
            candidate=candidate.to_dict() if candidate else None,
            checks=checks.to_dict() if checks else None,
        )

    def _run_checks(self, task_entity: dict[str, Any], candidate: Candidate) -> CheckReport:
        authorized = authorized_checks(task_entity)
        context = CheckContext(
            task_id=candidate.task_id,
            run_id=candidate.run_id,
            candidate=candidate,
            store=self._store,
            workspace_path=candidate.workspace_path,
        )
        return run_checks(self._registry, authorized, context)

    # ------------------------------------------------------------- verification
    def verify_and_prepare(
        self,
        task_id: str,
        *,
        request_id: str | None = None,
        expected_revision: int | None = None,
    ) -> ActionResult:
        """Run machine checks and, when safe, open the candidate for acceptance."""

        key = self._key("verify", request_id)
        if key is not None:
            existing = self._idempotency.lookup(key)
            if existing is not None:
                return ActionResult.from_dict(existing)

        task = self._store.read("task", task_id)
        phase = str(task.entity.get("phase", ""))
        if expected_revision is not None and task.revision != expected_revision:
            raise self._revision_conflict(task_id, expected_revision, task.revision)

        if phase == TaskPhase.AWAITING_ACCEPTANCE.value:
            current = self._store.read("task", task_id)
            acceptance_map = current.entity.get("acceptance")
            result = ActionResult(
                action="verify",
                state="confirmed",
                confirmed=True,
                task_id=task_id,
                phase=phase,
                acceptance=dict(acceptance_map) if isinstance(acceptance_map, dict) else {},
                request_id=request_id,
                candidate_ref=self._candidate_ref(task, None),
                messages=("candidate already awaiting acceptance",),
            )
        elif phase != TaskPhase.VERIFYING.value:
            raise AppError(
                ErrorCode.ILLEGAL_TRANSITION,
                f"task phase {phase!r} cannot be verified into awaiting_acceptance",
                details={"task_id": task_id, "phase": phase},
            )
        else:
            candidate = load_candidate(self._store, task_id)
            checks = self._run_checks(task.entity, candidate)
            if not checks.satisfied:
                result = ActionResult(
                    action="verify",
                    state="unconfirmed",
                    confirmed=False,
                    task_id=task_id,
                    phase=phase,
                    acceptance=dict(task.entity.get("acceptance") or {}),
                    request_id=request_id,
                    candidate_ref=candidate.candidate_ref,
                    messages=(
                        "machine checks failed: " + ", ".join(checks.failed_ids),
                    ),
                    candidate=candidate.to_dict(),
                    checks=checks.to_dict(),
                )
            else:
                stop = self._stopper.stop(task_id, candidate.run_id)
                if not stop.confirmed:
                    result = ActionResult(
                        action="verify",
                        state="unconfirmed",
                        confirmed=False,
                        task_id=task_id,
                        phase=phase,
                        acceptance=dict(task.entity.get("acceptance") or {}),
                        request_id=request_id,
                        candidate_ref=candidate.candidate_ref,
                        messages=("resources not confirmed stopped", *stop.problems),
                        candidate=candidate.to_dict(),
                        checks=checks.to_dict(),
                        stop=stop.to_dict(),
                    )
                else:
                    result = self._open_acceptance(
                        task, candidate, checks, stop, request_id=request_id
                    )
        if key is not None:
            self._idempotency.record(key, result.to_dict())
        return result

    def _open_acceptance(
        self,
        task: Any,
        candidate: Candidate,
        checks: CheckReport,
        stop: StopReport,
        *,
        request_id: str | None,
    ) -> ActionResult:
        task_id = candidate.task_id
        new_deliverable = _int_field(task.entity, "deliverable_revision") + 1
        acceptance = {
            "status": AcceptanceStatus.AWAITING.value,
            "requirements_revision": _int_field(task.entity, "requirements_revision"),
            "deliverable_revision": new_deliverable,
            "evidence_refs": list(candidate.artifact_refs),
            "decided_at": None,
            "decision_ref": None,
            # Additive candidate binding so a decision cannot silently apply to
            # a different Run/plan (docs/08 §6.1 + §9).
            "candidate_ref": candidate.candidate_ref,
            "candidate_plan_hash": candidate.plan_hash,
            "check_records": [record.to_dict() for record in checks.results],
        }
        self._writer.transition_task(
            task_id,
            TaskPhase.AWAITING_ACCEPTANCE,
            extra={"deliverable_revision": new_deliverable, "acceptance": acceptance},
            run_ref=candidate.run_id,
            reason="machine checks passed and resources confirmed stopped",
        )
        self._writer.transition_run(
            candidate.run_id,
            RunState.AWAITING_ACCEPTANCE.value,
            task_ref=task_id,
            reason="candidate handed to human acceptance",
        )
        self._writer.emit(
            task_id,
            EventType.DECISION_REQUESTED,
            {
                "candidate_ref": candidate.candidate_ref,
                "requirements_revision": acceptance["requirements_revision"],
                "deliverable_revision": new_deliverable,
                "evidence_refs": acceptance["evidence_refs"],
                "checks": [record.to_dict() for record in checks.results],
            },
            task_ref=task_id,
            run_ref=candidate.run_id,
        )
        return ActionResult(
            action="verify",
            state="confirmed",
            confirmed=True,
            task_id=task_id,
            phase=TaskPhase.AWAITING_ACCEPTANCE.value,
            acceptance=acceptance,
            request_id=request_id,
            candidate_ref=candidate.candidate_ref,
            messages=("candidate ready for human acceptance",),
            candidate=candidate.to_dict(),
            checks=checks.to_dict(),
            stop=stop.to_dict(),
        )

    # ---------------------------------------------------------------- decision
    def decide(
        self,
        task_id: str,
        action: str,
        *,
        request_id: str,
        expected_revision: int | None = None,
        expected_requirements_revision: int | None = None,
        expected_deliverable_revision: int | None = None,
        target_run_id: str | None = None,
        note: str | None = None,
    ) -> ActionResult:
        """Apply an accept/reject decision, idempotent per ``request_id``."""

        if action not in _DECISION_ACTIONS:
            raise AppError(
                ErrorCode.INVALID_REQUEST,
                f"unsupported decision action {action!r}",
                details={"action": action},
            )
        if not isinstance(request_id, str) or not request_id.strip():
            raise AppError(
                ErrorCode.INVALID_REQUEST,
                "request_id is required for a decision",
                details={"field": "request_id"},
            )
        key = self._key("decision", request_id)
        assert key is not None
        existing = self._idempotency.lookup(key)
        if existing is not None:
            return ActionResult.from_dict(existing)

        task = self._store.read("task", task_id)
        if expected_revision is not None and task.revision != expected_revision:
            raise self._revision_conflict(task_id, expected_revision, task.revision)

        phase = str(task.entity.get("phase", ""))
        acceptance = task.entity.get("acceptance")
        acceptance_map = dict(acceptance) if isinstance(acceptance, dict) else {}
        req_rev = _int_field(task.entity, "requirements_revision")
        del_rev = _int_field(task.entity, "deliverable_revision")
        acc_req = acceptance_map.get("requirements_revision")
        acc_del = acceptance_map.get("deliverable_revision")
        acc_status = acceptance_map.get("status")

        replay = self._replay_result(
            task, action, phase, acceptance_map, req_rev, del_rev, request_id
        )
        if replay is not None:
            self._idempotency.record(key, replay.to_dict())
            return replay

        if phase != TaskPhase.AWAITING_ACCEPTANCE.value:
            raise AppError(
                ErrorCode.ILLEGAL_TRANSITION,
                f"task phase {phase!r} has no pending acceptance decision",
                details={"task_id": task_id, "phase": phase, "action": action},
            )
        self._assert_fresh(
            task_id,
            acceptance_map,
            req_rev,
            del_rev,
            expected_requirements_revision=expected_requirements_revision,
            expected_deliverable_revision=expected_deliverable_revision,
            target_run_id=target_run_id,
        )

        candidate_ref = self._candidate_ref(task, acceptance_map)
        now = _now_iso()
        decision = dict(acceptance_map)
        decision["decided_at"] = now
        decision["decision_ref"] = request_id
        if note:
            decision["note"] = note
        if action == "accept":
            decision["status"] = AcceptanceStatus.ACCEPTED.value
            self._writer.transition_task(
                task_id,
                TaskPhase.COMPLETED,
                extra={"acceptance": decision, "active_run": None},
                run_ref=candidate_ref,
                reason="human accepted the candidate",
            )
            if candidate_ref is not None:
                self._writer.transition_run(
                    candidate_ref,
                    RunState.COMPLETED.value,
                    task_ref=task_id,
                    extra={"ended_at": now, "cleanup": {"status": "done"}},
                    reason="accepted by user",
                )
            state = "confirmed"
            phase_out = TaskPhase.COMPLETED.value
        else:
            decision["status"] = AcceptanceStatus.REJECTED.value
            self._writer.transition_task(
                task_id,
                TaskPhase.REPAIRING,
                extra={"acceptance": decision, "active_run": None},
                run_ref=candidate_ref,
                reason="human rejected the candidate; repair requested",
            )
            if candidate_ref is not None:
                self._writer.transition_run(
                    candidate_ref,
                    RunState.FAILED.value,
                    task_ref=task_id,
                    extra={
                        "ended_at": now,
                        "fail_reason": "acceptance rejected; repair requested",
                    },
                    reason="rejected by user",
                )
            state = "confirmed"
            phase_out = TaskPhase.REPAIRING.value

        self._writer.emit(
            task_id,
            EventType.DECISION_RESOLVED,
            {
                "action": action,
                "candidate_ref": candidate_ref,
                "requirements_revision": req_rev,
                "deliverable_revision": del_rev,
                "decision_ref": request_id,
            },
            task_ref=task_id,
            run_ref=candidate_ref,
        )
        result = ActionResult(
            action=action,
            state=state,
            confirmed=True,
            task_id=task_id,
            phase=phase_out,
            acceptance=decision,
            request_id=request_id,
            candidate_ref=candidate_ref,
            messages=(f"decision {action!r} recorded; no merge/push/deploy performed",),
        )
        self._idempotency.record(key, result.to_dict())
        return result

    def _replay_result(
        self,
        task: Any,
        action: str,
        phase: str,
        acceptance_map: dict[str, Any],
        req_rev: int,
        del_rev: int,
        request_id: str,
    ) -> ActionResult | None:
        """Idempotent replay of an already-applied decision (new request id)."""

        expected_status = (
            AcceptanceStatus.ACCEPTED.value if action == "accept" else AcceptanceStatus.REJECTED.value
        )
        expected_phase = (
            TaskPhase.COMPLETED.value if action == "accept" else TaskPhase.REPAIRING.value
        )
        bound = (
            acceptance_map.get("requirements_revision") == req_rev
            and acceptance_map.get("deliverable_revision") == del_rev
        )
        if (
            acceptance_map.get("status") == expected_status
            and phase == expected_phase
            and bound
        ):
            return ActionResult(
                action=action,
                state="confirmed",
                confirmed=True,
                task_id=task.entity_id,
                phase=phase,
                acceptance=dict(acceptance_map),
                request_id=request_id,
                candidate_ref=self._candidate_ref(task, acceptance_map),
                messages=(f"decision {action!r} already recorded for this candidate",),
            )
        return None

    def _assert_fresh(
        self,
        task_id: str,
        acceptance_map: dict[str, Any],
        req_rev: int,
        del_rev: int,
        *,
        expected_requirements_revision: int | None,
        expected_deliverable_revision: int | None,
        target_run_id: str | None,
    ) -> None:
        details: dict[str, Any] = {"task_id": task_id}
        if (
            expected_requirements_revision is not None
            and expected_requirements_revision != req_rev
        ):
            details.update(
                {
                    "expected_requirements_revision": expected_requirements_revision,
                    "actual_requirements_revision": req_rev,
                }
            )
            raise AppError(
                ErrorCode.ACCEPTANCE_STALE,
                "decision targets a stale requirements revision",
                details=details,
            )
        if (
            expected_deliverable_revision is not None
            and expected_deliverable_revision != del_rev
        ):
            details.update(
                {
                    "expected_deliverable_revision": expected_deliverable_revision,
                    "actual_deliverable_revision": del_rev,
                }
            )
            raise AppError(
                ErrorCode.ACCEPTANCE_STALE,
                "decision targets a stale deliverable revision",
                details=details,
            )
        if (
            acceptance_map.get("status") != AcceptanceStatus.AWAITING.value
            or acceptance_map.get("requirements_revision") != req_rev
            or acceptance_map.get("deliverable_revision") != del_rev
        ):
            details.update(
                {
                    "acceptance_status": acceptance_map.get("status"),
                    "acceptance_requirements_revision": acceptance_map.get(
                        "requirements_revision"
                    ),
                    "acceptance_deliverable_revision": acceptance_map.get(
                        "deliverable_revision"
                    ),
                    "actual_requirements_revision": req_rev,
                    "actual_deliverable_revision": del_rev,
                }
            )
            raise AppError(
                ErrorCode.ACCEPTANCE_STALE,
                "acceptance snapshot no longer matches the current requirements/deliverable",
                details=details,
            )
        bound_run = acceptance_map.get("candidate_ref")
        if target_run_id is not None and target_run_id != bound_run:
            raise AppError(
                ErrorCode.ACCEPTANCE_STALE,
                "decision targets a different candidate run",
                details={"target_run_id": target_run_id, "candidate_ref": bound_run},
            )

    # ------------------------------------------------------------------ repair
    def request_repair(
        self,
        task_id: str,
        *,
        request_id: str | None = None,
        note: str | None = None,
    ) -> ActionResult:
        """Expose the repair seam: ``verifying -> repairing`` (LG-017 drives rounds).

        Keeps the Task ID and does **not** create a Run; the coordinator decides
        whether a new Run is warranted from real state.
        """

        key = self._key("repair", request_id)
        if key is not None:
            existing = self._idempotency.lookup(key)
            if existing is not None:
                return ActionResult.from_dict(existing)

        task = self._store.read("task", task_id)
        phase = str(task.entity.get("phase", ""))
        if phase == TaskPhase.REPAIRING.value:
            result = ActionResult(
                action="repair",
                state="confirmed",
                confirmed=True,
                task_id=task_id,
                phase=phase,
                acceptance=dict(task.entity.get("acceptance") or {}),
                request_id=request_id,
                messages=("task is already repairing",),
            )
        else:
            if phase != TaskPhase.VERIFYING.value:
                raise AppError(
                    ErrorCode.ILLEGAL_TRANSITION,
                    f"task phase {phase!r} cannot request repair",
                    details={"task_id": task_id, "phase": phase},
                )
            candidate = load_candidate(self._store, task_id)
            reason = note or "machine verification requested repair"
            self._writer.transition_task(
                task_id,
                TaskPhase.REPAIRING,
                extra={"active_run": None},
                run_ref=candidate.run_id,
                reason=reason,
            )
            self._writer.transition_run(
                candidate.run_id,
                RunState.FAILED.value,
                task_ref=task_id,
                extra={"ended_at": _now_iso(), "fail_reason": reason},
                reason=reason,
            )
            result = ActionResult(
                action="repair",
                state="confirmed",
                confirmed=True,
                task_id=task_id,
                phase=TaskPhase.REPAIRING.value,
                acceptance=dict(task.entity.get("acceptance") or {}),
                request_id=request_id,
                candidate_ref=candidate.candidate_ref,
                messages=(reason,),
            )
        if key is not None:
            self._idempotency.record(key, result.to_dict())
        return result

    # ----------------------------------------------------------------- helpers
    def _candidate_ref(self, task: Any, acceptance_map: dict[str, Any] | None) -> str | None:
        if acceptance_map is not None:
            ref = acceptance_map.get("candidate_ref")
            if isinstance(ref, str) and ref:
                return ref
        active = task.entity.get("active_run")
        return active if isinstance(active, str) and active else None

    def _key(self, kind: str, request_id: str | None) -> str | None:
        if not isinstance(request_id, str) or not request_id.strip():
            return None
        return f"verify:{kind}:{request_id}"

    @staticmethod
    def _revision_conflict(task_id: str, expected: int, actual: int) -> RevisionConflict:
        return RevisionConflict("task", task_id, expected=expected, actual=actual)


__all__ = ["ActionResult", "AcceptanceView", "VerificationService"]
