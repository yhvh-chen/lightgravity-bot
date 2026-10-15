"""Bounded business rework orchestration (LG-017, docs/08 §6.1/§9).

LG-009 stops at "candidate ready for human acceptance".  This module owns the
runtime loop that turns an independent review into **bounded business rework**:

    verifying --(review passed)--> awaiting_acceptance
    verifying --(review rework, budget left)--> repairing -> (new Run re-recruits + re-verifies)
    verifying --(review rework, budget spent)--> failed / waiting_user (budget_exhausted)
    verifying --(review unavailable)--> waiting_user (no fake pass, no round spent)

It keeps three counters strictly separate, as the contract requires:

* ``sdk_retries``         - adapter/SDK retries; **not** business rounds;
* ``review_rounds``       - candidate reviews performed;
* ``repair_rounds_spent`` - business rework rounds actually started.

The ledger lives in Task frontmatter (additive ``rework`` map), so it survives
the process and **cannot be reset by a new Run**: ``_TaskTotalLedger`` reads the
existing count and only ever adds.  ``budget.max_repair_rounds`` bounds
``repair_rounds_spent`` across the whole Task lifetime; ``budget.max_review_rounds``
(optional, additive) bounds ``review_rounds`` when present.

New-Run creation is *not* implemented here: the coordinator owns Run creation
(the single-writer rule).  The orchestrator calls a :class:`RunSpawner` port
whose concrete implementation is the coordinator; the port returns the new Run
id, or ``None`` when it could not open one (which is reported, never faked).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

from lightgravity.contracts import ErrorCode, EventType, TaskPhase
from lightgravity.coordinator.state import StateWriter
from lightgravity.store import Store

from .candidate import Candidate, load_candidate
from .review import (
    REVIEW_PASSED,
    REVIEW_UNAVAILABLE,
    ReviewContext,
    ReviewReport,
    Reviewer,
    resolve_candidate_evidence,
    validate_findings,
)

#: Rework outcomes returned to the caller (coordinator/API).
REWORK_OPENED = "awaiting_acceptance"
REWORK_SPAWNED = "repairing"
REWORK_EXHAUSTED = "budget_exhausted"
REWORK_UNAVAILABLE = "review_unavailable"
REWORK_BLOCKED = "not_applicable"

_DEFAULT_MAX_REPAIR_ROUNDS = 1
_MAX_REVIEW_ROUNDS_CAP = 8


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _int_field(entity: dict[str, Any], key: str, default: int = 0) -> int:
    value = entity.get(key)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return default


def _budget(entity: dict[str, Any], key: str, default: int | None) -> int | None:
    raw = entity.get("budget")
    if not isinstance(raw, dict):
        return default
    value = raw.get(key)
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return default


@dataclass(frozen=True, slots=True)
class ReworkLedger:
    """The Task-lifetime rework accounting (never resettable by a new Run)."""

    review_rounds: int = 0
    repair_rounds_spent: int = 0
    sdk_retries: int = 0
    outcomes: tuple[str, ...] = ()
    last_findings: tuple[dict[str, Any], ...] = ()
    last_candidate_ref: str | None = None
    history: tuple[dict[str, Any], ...] = ()
    #: LG-017 R1 additive: the last reviewer identity/kind and its real model
    #: usage.  ``reviewer`` distinguishes a program machine gate from a real
    #: independent (model) review; ``model_usage`` lists unknown counters too.
    reviewer: str = ""
    reviewer_kind: str = ""
    model_usage: dict[str, Any] = field(default_factory=dict)

    @property
    def max_repair_rounds(self) -> int:
        return _DEFAULT_MAX_REPAIR_ROUNDS

    def to_frontmatter(self) -> dict[str, Any]:
        return {
            "review_rounds": self.review_rounds,
            "repair_rounds_spent": self.repair_rounds_spent,
            "sdk_retries": self.sdk_retries,
            "outcomes": list(self.outcomes),
            "last_findings": [dict(f) for f in self.last_findings],
            "last_candidate_ref": self.last_candidate_ref,
            "history": [dict(h) for h in self.history],
            "reviewer": self.reviewer,
            "reviewer_kind": self.reviewer_kind,
            "model_usage": dict(self.model_usage),
        }


def load_ledger(entity: dict[str, Any]) -> ReworkLedger:
    raw = entity.get("rework")
    if not isinstance(raw, dict):
        return ReworkLedger()
    outcomes = raw.get("outcomes")
    findings = raw.get("last_findings")
    history = raw.get("history")
    last_ref = raw.get("last_candidate_ref")
    usage = raw.get("model_usage")
    return ReworkLedger(
        review_rounds=_int_field(raw, "review_rounds"),
        repair_rounds_spent=_int_field(raw, "repair_rounds_spent"),
        sdk_retries=_int_field(raw, "sdk_retries"),
        outcomes=tuple(str(x) for x in outcomes) if isinstance(outcomes, list) else (),
        last_findings=(
            tuple(dict(x) for x in findings if isinstance(x, dict))
            if isinstance(findings, list)
            else ()
        ),
        last_candidate_ref=last_ref if isinstance(last_ref, str) and last_ref else None,
        history=(
            tuple(dict(x) for x in history if isinstance(x, dict))
            if isinstance(history, list)
            else ()
        ),
        reviewer=str(raw.get("reviewer", "")),
        reviewer_kind=str(raw.get("reviewer_kind", "")),
        model_usage=dict(usage) if isinstance(usage, dict) else {},
    )


@dataclass(frozen=True, slots=True)
class ReworkResult:
    """Outcome of one rework-orchestration pass."""

    state: str  # awaiting_acceptance | repairing | budget_exhausted | review_unavailable | not_applicable
    task_id: str
    phase: str
    confirmed: bool
    candidate_ref: str | None = None
    review: dict[str, Any] | None = None
    new_run_id: str | None = None
    repair_rounds_spent: int = 0
    max_repair_rounds: int = _DEFAULT_MAX_REPAIR_ROUNDS
    messages: tuple[str, ...] = ()
    request_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "task_id": self.task_id,
            "phase": self.phase,
            "confirmed": self.confirmed,
            "candidate_ref": self.candidate_ref,
            "review": self.review,
            "new_run_id": self.new_run_id,
            "repair_rounds_spent": self.repair_rounds_spent,
            "max_repair_rounds": self.max_repair_rounds,
            "messages": list(self.messages),
            "request_id": self.request_id,
        }


@dataclass(frozen=True, slots=True)
class SpawnOutcome:
    """Result of asking the runtime to start a repair Run.

    ``queued`` is True only when a fresh rework Run has really been scheduled
    (the coordinator's worker will open it on the next claim).  ``run_id`` is
    set only when a Run id is already known; a queued-but-not-yet-opened Run
    leaves it ``None`` rather than fabricating an id.  ``detail`` explains a
    non-spawn.
    """

    queued: bool
    run_id: str | None = None
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"queued": self.queued, "run_id": self.run_id, "detail": self.detail}


@runtime_checkable
class RunSpawner(Protocol):
    """Port for starting a fresh rework Run (the coordinator implements it).

    The spawner is responsible for re-recruiting a team and writing the new
    Run's ``attempt``; the orchestrator only supplies the review findings and
    keeps the old candidate + evidence untouched.  A spawner that cannot start
    a Run returns ``SpawnOutcome(queued=False, ...)`` (never a fabricated id).
    """

    def spawn_repair_run(
        self,
        task_id: str,
        *,
        prior_run_id: str,
        findings: tuple[dict[str, Any], ...],
        request_id: str,
    ) -> SpawnOutcome: ...


class ReworkOrchestrator:
    """Drive independent review -> bounded rework for one Store."""

    def __init__(
        self,
        store: Store,
        *,
        reviewer: Reviewer,
        writer: StateWriter | None = None,
        spawner: RunSpawner | None = None,
        actor: str = "verify",
        max_review_rounds: int = _MAX_REVIEW_ROUNDS_CAP,
    ) -> None:
        self._store = store
        self._reviewer = reviewer
        self._writer = writer or StateWriter(store, actor=actor)
        self._spawner = spawner
        self._actor = actor
        self._max_review_rounds = max_review_rounds
        #: Last reviewer meta (kind/reviewer/usage) for the ledger, refreshed on
        #: every review; never used as a verdict.
        self._last_review_meta: dict[str, Any] = {}

    # ------------------------------------------------------------------ read
    def ledger(self, task_id: str) -> ReworkLedger:
        return load_ledger(self._store.read("task", task_id).entity)

    # --------------------------------------------------------------- review
    def review_candidate(
        self, task_id: str, *, stop_event: Any | None = None
    ) -> tuple[ReviewReport, Candidate]:
        """Run the independent reviewer against the active candidate.

        ``stop_event`` (LG-022 R1) is an optional cooperative stop channel; it
        is handed to the reviewer so a long model turn can be stopped by the
        coordinator's review lifecycle.  ``None`` keeps the sync fixture path.
        """

        candidate = load_candidate(self._store, task_id)
        resolved = resolve_candidate_evidence(self._store, candidate)
        context = ReviewContext(
            task_id=task_id,
            run_id=candidate.run_id,
            candidate=candidate,
            store=self._store,
            resolved_evidence=resolved,
            stop_event=stop_event,
        )
        try:
            raw = self._reviewer.review(context)
        except Exception as exc:  # noqa: BLE001 - a reviewer crash is unavailable, not a pass
            raw = ReviewReport(
                outcome=REVIEW_UNAVAILABLE,
                candidate_ref=candidate.candidate_ref,
                reviewer=getattr(self._reviewer, "name", "unknown"),
                reason=f"reviewer raised {type(exc).__name__}: {exc}",
            )
        # Stamp which kind of reviewer actually ran and any real model usage, so
        # the ledger/events cannot mislabel a program machine gate as an
        # independent (model) review.  Unknown usage is preserved, never zeroed.
        kind = str(getattr(self._reviewer, "kind", "") or getattr(raw, "reviewer_kind", ""))
        model_calls = getattr(self._reviewer, "model_calls", None)
        if not isinstance(model_calls, int) or isinstance(model_calls, bool):
            model_calls = raw.model_calls
        usage = getattr(self._reviewer, "last_usage", None)
        raw = ReviewReport(
            outcome=raw.outcome,
            candidate_ref=raw.candidate_ref,
            findings=raw.findings,
            unsubstantiated=raw.unsubstantiated,
            reviewer=raw.reviewer,
            reason=raw.reason,
            reviewer_kind=kind,
            model_calls=model_calls,
            usage=dict(usage) if isinstance(usage, dict) else raw.usage,
        )
        self._last_review_meta = {
            "reviewer": raw.reviewer,
            "reviewer_kind": raw.reviewer_kind,
            "model_calls": raw.model_calls,
            "model_usage": dict(raw.usage),
        }
        return validate_findings(raw, candidate=candidate, resolved_evidence=resolved), candidate

    def _record_ledger(
        self,
        task_id: str,
        *,
        review_rounds: int,
        repair_rounds_spent: int,
        outcome: str,
        candidate_ref: str | None,
        findings: tuple[dict[str, Any], ...],
        extra_history: dict[str, Any] | None = None,
    ) -> ReworkLedger:
        entity = self._store.read("task", task_id).entity
        ledger = load_ledger(entity)
        history = ledger.history
        entry = {
            "at": _now_iso(),
            "outcome": outcome,
            "candidate_ref": candidate_ref,
            "findings": len(findings),
        }
        if extra_history:
            entry.update(extra_history)
        meta = getattr(self, "_last_review_meta", {}) or {}
        updated = ReworkLedger(
            review_rounds=review_rounds,
            repair_rounds_spent=repair_rounds_spent,
            sdk_retries=ledger.sdk_retries,
            outcomes=(*ledger.outcomes, outcome),
            last_findings=findings,
            last_candidate_ref=candidate_ref,
            history=(*history, entry),
            reviewer=str(meta.get("reviewer", ledger.reviewer)),
            reviewer_kind=str(meta.get("reviewer_kind", ledger.reviewer_kind)),
            model_usage=(
                dict(meta["model_usage"])
                if isinstance(meta.get("model_usage"), dict)
                else ledger.model_usage
            ),
        )
        self._writer.write_task(task_id, {"rework": updated.to_frontmatter()})
        return updated

    # ------------------------------------------------------------------ step
    def process(
        self,
        task_id: str,
        *,
        request_id: str | None = None,
        note: str | None = None,
        stop_event: Any | None = None,
    ) -> ReworkResult:
        """One review+rework pass for a Task in ``verifying`` (or ``repairing``).

        Idempotency is handled by the caller (coordinator/API) via the existing
        LG-009 ``request_id`` seam; this method is a single pure-ish step over
        current Store state and never resets the lifetime ledger.  ``stop_event``
        is the optional LG-022 R1 cooperative stop channel forwarded to the
        reviewer.
        """

        task = self._store.read("task", task_id)
        phase = str(task.entity.get("phase", ""))
        if phase != TaskPhase.VERIFYING.value:
            return ReworkResult(
                state=REWORK_BLOCKED,
                task_id=task_id,
                phase=phase,
                confirmed=False,
                request_id=request_id,
                messages=(f"task phase {phase!r} is not reviewable",),
            )

        ledger = load_ledger(task.entity)
        max_repair = _budget(task.entity, "max_repair_rounds", _DEFAULT_MAX_REPAIR_ROUNDS)
        assert max_repair is not None
        max_review = _budget(task.entity, "max_review_rounds", self._max_review_rounds)
        assert max_review is not None

        # Bound total reviews so a forever-rework cannot loop without a Run.
        if ledger.review_rounds >= max_review:
            self._writer.emit(
                task_id,
                EventType.ERROR_RECORDED,
                {
                    "mode": "rework",
                    "code": ErrorCode.BUDGET_EXHAUSTED.value,
                    "message": f"review budget exhausted ({ledger.review_rounds}/{max_review})",
                },
            )
            return ReworkResult(
                state=REWORK_EXHAUSTED,
                task_id=task_id,
                phase=phase,
                confirmed=False,
                candidate_ref=ledger.last_candidate_ref,
                repair_rounds_spent=ledger.repair_rounds_spent,
                max_repair_rounds=max_repair,
                request_id=request_id,
                messages=("review budget exhausted; no further round started",),
            )

        report, candidate = self.review_candidate(task_id, stop_event=stop_event)
        review_rounds = ledger.review_rounds + 1
        findings = tuple(f.to_dict() for f in report.findings)
        self._writer.emit(
            task_id,
            EventType.ERROR_RECORDED,
            {
                "mode": "review",
                "code": "review_completed",
                "outcome": report.outcome,
                "findings": len(report.findings),
                "unsubstantiated": len(report.unsubstantiated),
                "reviewer": report.reviewer,
                "reviewer_kind": report.reviewer_kind,
                "model_calls": report.model_calls,
                "usage": dict(report.usage),
                # LG-022 R1: keep the reviewer's own error/reason on the event so
                # an ``unavailable`` review is diagnosable, not a bare outcome.
                "reason": report.reason,
            },
            run_ref=candidate.run_id,
        )

        # ------------------------------------------------------- unavailable
        if report.is_unavailable:
            # Do not accept, do not spend a repair round: park for a human.
            self._record_ledger(
                task_id,
                review_rounds=review_rounds,
                repair_rounds_spent=ledger.repair_rounds_spent,
                outcome=REVIEW_UNAVAILABLE,
                candidate_ref=candidate.candidate_ref,
                findings=(),
            )
            self._writer.transition_task(
                task_id,
                TaskPhase.WAITING_USER,
                run_ref=candidate.run_id,
                reason="independent review unavailable; not accepting without review",
            )
            return ReworkResult(
                state=REWORK_UNAVAILABLE,
                task_id=task_id,
                phase=TaskPhase.WAITING_USER.value,
                confirmed=False,
                candidate_ref=candidate.candidate_ref,
                review=report.to_dict(),
                repair_rounds_spent=ledger.repair_rounds_spent,
                max_repair_rounds=max_repair,
                request_id=request_id,
                messages=(report.reason or "no independent reviewer available",),
            )

        # ------------------------------------------------------------- pass
        if report.is_pass:
            self._record_ledger(
                task_id,
                review_rounds=review_rounds,
                repair_rounds_spent=ledger.repair_rounds_spent,
                outcome=REVIEW_PASSED,
                candidate_ref=candidate.candidate_ref,
                findings=(),
            )
            return ReworkResult(
                state=REWORK_OPENED,
                task_id=task_id,
                phase=phase,
                confirmed=True,
                candidate_ref=candidate.candidate_ref,
                review=report.to_dict(),
                repair_rounds_spent=ledger.repair_rounds_spent,
                max_repair_rounds=max_repair,
                request_id=request_id,
                messages=("independent review passed",),
            )

        # ----------------------------------------------------------- rework
        if ledger.repair_rounds_spent >= max_repair:
            self._record_ledger(
                task_id,
                review_rounds=review_rounds,
                repair_rounds_spent=ledger.repair_rounds_spent,
                outcome="budget_exhausted",
                candidate_ref=candidate.candidate_ref,
                findings=findings,
            )
            self._writer.emit(
                task_id,
                EventType.ERROR_RECORDED,
                {
                    "mode": "rework",
                    "code": ErrorCode.BUDGET_EXHAUSTED.value,
                    "message": (
                        f"repair budget spent ({ledger.repair_rounds_spent}/{max_repair}); "
                        "stopping without faking acceptance"
                    ),
                },
                run_ref=candidate.run_id,
            )
            self._writer.transition_task(
                task_id,
                TaskPhase.WAITING_USER,
                run_ref=candidate.run_id,
                reason="repair budget exhausted; human decision required",
            )
            return ReworkResult(
                state=REWORK_EXHAUSTED,
                task_id=task_id,
                phase=TaskPhase.WAITING_USER.value,
                confirmed=False,
                candidate_ref=candidate.candidate_ref,
                review=report.to_dict(),
                repair_rounds_spent=ledger.repair_rounds_spent,
                max_repair_rounds=max_repair,
                request_id=request_id,
                messages=(f"repair budget {ledger.repair_rounds_spent}/{max_repair} exhausted",),
            )

        return self._open_rework(
            task_id, candidate, report, findings, ledger, review_rounds, max_repair, request_id
        )

    def _open_rework(
        self,
        task_id: str,
        candidate: Candidate,
        report: ReviewReport,
        findings: tuple[dict[str, Any], ...],
        ledger: ReworkLedger,
        review_rounds: int,
        max_repair: int,
        request_id: str | None,
    ) -> ReworkResult:
        if self._spawner is None:
            # No RunSpawner wired: stay in ``repairing`` transparently (the
            # coordinator/next claim decides), never pretend a Run was opened.
            self._record_ledger(
                task_id,
                review_rounds=review_rounds,
                repair_rounds_spent=ledger.repair_rounds_spent,
                outcome="rework_requested_no_spawner",
                candidate_ref=candidate.candidate_ref,
                findings=findings,
            )
            self._enter_repairing(task_id, candidate, report)
            return ReworkResult(
                state=REWORK_SPAWNED,
                task_id=task_id,
                phase=TaskPhase.REPAIRING.value,
                confirmed=False,
                candidate_ref=candidate.candidate_ref,
                review=report.to_dict(),
                repair_rounds_spent=ledger.repair_rounds_spent,
                max_repair_rounds=max_repair,
                request_id=request_id,
                messages=("rework requested; no RunSpawner wired in this runtime",),
            )

        self._enter_repairing(task_id, candidate, report)
        spawn = self._spawner.spawn_repair_run(
            task_id,
            prior_run_id=candidate.run_id,
            findings=findings,
            request_id=request_id or f"rework:{task_id}:{candidate.run_id}",
        )
        queued = bool(getattr(spawn, "queued", False))
        new_run_id = getattr(spawn, "run_id", None)
        if not isinstance(new_run_id, str) or not new_run_id:
            new_run_id = None
        # The repair round is spent **only** when a fresh Run was really
        # scheduled; a failed spawn is reported and does not silently consume
        # budget.
        spent = ledger.repair_rounds_spent + (1 if queued else 0)
        self._record_ledger(
            task_id,
            review_rounds=review_rounds,
            repair_rounds_spent=spent,
            outcome="rework_queued" if queued else "rework_spawn_failed",
            candidate_ref=candidate.candidate_ref,
            findings=findings,
            extra_history={
                "new_run_id": new_run_id,
                "queued": queued,
                "prior_run_id": candidate.run_id,
            },
        )
        if not queued:
            detail = str(getattr(spawn, "detail", "")) or "no new Run could be started"
            self._writer.emit(
                task_id,
                EventType.ERROR_RECORDED,
                {
                    "mode": "rework",
                    "code": ErrorCode.NOT_READY.value,
                    "message": f"rework requested but no new Run could be started: {detail}",
                },
                run_ref=candidate.run_id,
            )
        return ReworkResult(
            state=REWORK_SPAWNED,
            task_id=task_id,
            phase=TaskPhase.REPAIRING.value,
            confirmed=queued,
            candidate_ref=candidate.candidate_ref,
            review=report.to_dict(),
            new_run_id=new_run_id,
            repair_rounds_spent=spent,
            max_repair_rounds=max_repair,
            request_id=request_id,
            messages=(
                (
                    f"rework Run queued (id={new_run_id or 'pending'}); old candidate "
                    f"{candidate.candidate_ref} and evidence retained",
                )
                if queued
                else ("rework requested; could not start a new Run",)
            ),
        )

    def _enter_repairing(self, task_id: str, candidate: Candidate, report: ReviewReport) -> None:
        """verifying -> repairing, preserving the old candidate + evidence.

        The Run is marked ``failed`` with a rework reason, but the Task keeps its
        old acceptance/candidate binding fields and the Run record/artifacts stay
        on disk untouched.  ``active_run`` is cleared here only via the normal
        rework path so the coordinator can open exactly one new Run.
        """

        self._writer.transition_run(
            candidate.run_id,
            "failed",
            task_ref=task_id,
            extra={
                "ended_at": _now_iso(),
                "fail_reason": "independent review requested rework",
            },
            reason="review rework",
        )
        self._writer.transition_task(
            task_id,
            TaskPhase.REPAIRING,
            extra={
                "active_run": None,
                "last_run": candidate.run_id,
                "review_findings": [f.to_dict() for f in report.findings],
            },
            run_ref=candidate.run_id,
            reason="independent review requested rework",
        )


__all__ = [
    "REWORK_BLOCKED",
    "REWORK_EXHAUSTED",
    "REWORK_OPENED",
    "REWORK_SPAWNED",
    "REWORK_UNAVAILABLE",
    "ReworkLedger",
    "ReworkOrchestrator",
    "ReworkResult",
    "RunSpawner",
    "SpawnOutcome",
    "load_ledger",
]
