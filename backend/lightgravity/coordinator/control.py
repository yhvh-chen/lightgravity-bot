"""Control actions and stop confirmation (LG-016, docs/04 §5, docs/08 §9).

This module owns the *delivery* of pause/cancel/resume/retry/reopen/enqueue
for the resident coordinator.  Its single hard rule is the one in docs/08 §9:
a Task/Run may only enter a terminal ``cancelled``/``paused`` state after the
dispatcher reports ``confirmed=True``.  An unconfirmed or timed-out stop keeps
the intermediate ``cancelling``/``pausing`` phase, preserves the Run and its
recovery point, records a diagnostic and never fabricates a stop.

Action semantics (docs/08 §4.3, §9):

* ``pause``   — block new dispatch, ask the dispatcher to stop, confirm first.
* ``cancel``  — same stop gate, then write ``cancelled`` and free the slot.
* ``resume``  — re-queue a stopped/paused Task; the store lease guarantees a
  single writer, so a resume can never create a second concurrent Run.
* ``retry``   — enqueue after a failure/cancellation (new Run on the next claim).
* ``reopen``  — completed Task gets a new requirements revision and requeues.
* ``enqueue`` — explicit queue request.

The module never touches files directly: all writes go through
:class:`~lightgravity.coordinator.state.StateWriter` and ``Store`` leases.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from lightgravity.contracts import AppError, ErrorCode, EventType, TaskPhase
from lightgravity.store import EntityNotFound, Store

from .dispatcher import Dispatcher
from .queue import TaskQueue
from .state import StateWriter, TERMINAL_RUN_STATES

if TYPE_CHECKING:  # pragma: no cover - import cycle guard
    from lightgravity.verify.review_lifecycle import ReviewLifecycle

#: Phases from which a Task may be resumed into the queue.
RESUMABLE_PHASES: frozenset[str] = frozenset(
    {
        TaskPhase.PAUSED.value,
        TaskPhase.WAITING_USER.value,
        TaskPhase.RECOVERY_REQUIRED.value,
    }
)

#: Phases from which an explicit retry may enqueue a new Run.
RETRYABLE_PHASES: frozenset[str] = frozenset(
    {
        TaskPhase.FAILED.value,
        TaskPhase.CANCELLED.value,
        TaskPhase.RECOVERY_REQUIRED.value,
    }
)

#: Terminal phases that ``reopen`` may move back into the queue.
REOPENABLE_PHASES: frozenset[str] = frozenset(
    {TaskPhase.COMPLETED.value, TaskPhase.CANCELLED.value}
)


@dataclass(frozen=True, slots=True)
class ControlOutcome:
    """Result of one control action, mapped to the API control record."""

    action: str
    state: str  # requested | confirmed | unconfirmed | not_applicable
    confirmed: bool
    task_id: str
    run_id: str | None = None
    phase: str | None = None
    reason: str | None = None
    cleanup: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "action": self.action,
            "state": self.state,
            "confirmed": self.confirmed,
            "task_id": self.task_id,
        }
        if self.run_id:
            payload["run_id"] = self.run_id
        if self.phase:
            payload["phase"] = self.phase
        if self.reason:
            payload["reason"] = self.reason
        if self.cleanup:
            payload["cleanup"] = self.cleanup
        return payload


class ControlService:
    """pause/cancel/resume/retry/reopen/enqueue over the coordinator seams."""

    def __init__(
        self,
        store: Store,
        writer: StateWriter,
        queue: TaskQueue,
        dispatcher: Dispatcher,
        *,
        owner: str | None = None,
    ) -> None:
        self._store = store
        self._writer = writer
        self._queue = queue
        self._dispatcher = dispatcher
        self._owner = owner
        #: LG-022 R1 independent-reviewer lifecycle (set by the coordinator).
        self._review_lifecycle: "ReviewLifecycle | None" = None

    def set_review_lifecycle(self, lifecycle: "ReviewLifecycle | None") -> None:
        """Attach the reviewer lifecycle so pause/cancel can stop a review."""

        self._review_lifecycle = lifecycle

    # ------------------------------------------------------------------ stop
    async def stop(self, task_id: str, action: str) -> ControlOutcome:
        """Apply ``pause``/``cancel`` and only confirm after a real stop."""

        task = self._store.read("task", task_id)
        entity = task.entity
        phase = str(entity.get("phase", ""))
        active_run = entity.get("active_run")
        if not isinstance(active_run, str) or not active_run:
            return self._stop_without_run(task_id, phase, action)

        if action == "cancel":
            if phase not in {
                TaskPhase.CANCELLING.value,
                TaskPhase.AWAITING_ACCEPTANCE.value,
            }:
                self._writer.transition_task(
                    task_id, TaskPhase.CANCELLING, run_ref=active_run
                )
        elif action == "pause":
            if phase == TaskPhase.EXECUTING.value:
                self._writer.transition_task(
                    task_id, TaskPhase.PAUSING, run_ref=active_run
                )
            elif phase == TaskPhase.WAITING_USER.value:
                self._writer.transition_task(
                    task_id, TaskPhase.PAUSED, run_ref=active_run
                )
            elif phase in {TaskPhase.VERIFYING.value, TaskPhase.REPAIRING.value}:
                # LG-022 R1: the independent reviewer can be the long-running
                # thing in ``verifying``.  ``verifying -> pausing`` is not a
                # frozen transition, so a confirmed reviewer stop parks the Task
                # at ``waiting_user`` and the same action then moves it to
                # ``paused`` (both legal), preserving the candidate.
                pass
            else:
                return ControlOutcome(
                    action=action,
                    state="not_applicable",
                    confirmed=False,
                    task_id=task_id,
                    run_id=active_run,
                    phase=phase,
                    reason=f"phase {phase!r} does not allow {action}",
                )
        else:
            return ControlOutcome(
                action=action,
                state="not_applicable",
                confirmed=False,
                task_id=task_id,
                run_id=active_run,
                phase=phase,
                reason=f"phase {phase!r} does not allow {action}",
            )

        cancel_result = await self._dispatcher.cancel(task_id, active_run)
        confirmed = bool(getattr(cancel_result, "confirmed", False))
        reason = getattr(cancel_result, "reason", None) or None

        # LG-022 R1 (D2): an independent review may be the thing that is really
        # running while the dispatcher's ``_inflight`` is empty.  Stop the
        # reviewer too and require its real stop confirmation; an unconfirmed
        # (unknown) reviewer stop keeps the intermediate phase and the slot.
        reviewing = self._review_lifecycle is not None and self._review_lifecycle.is_reviewing(
            task_id, active_run
        )
        if reviewing:
            review_stop = await self._review_lifecycle.request_stop_async(  # type: ignore[union-attr]
                task_id, active_run
            )
            if not review_stop.confirmed:
                self._record_review_stop_unconfirmed(task_id, active_run, action, review_stop.reason)
                return ControlOutcome(
                    action=action,
                    state="unconfirmed",
                    confirmed=False,
                    task_id=task_id,
                    run_id=active_run,
                    phase=str(self._store.read("task", task_id).entity.get("phase")),
                    reason=review_stop.reason,
                )
            # Reviewer really stopped.  The dispatcher cancel above may have
            # reported ``not_found`` because the worker had already returned;
            # the confirmed reviewer stop is sufficient to proceed.
            confirmed = True
            reason = reason or review_stop.reason
        elif not confirmed and phase in {
            TaskPhase.VERIFYING.value,
            TaskPhase.REPAIRING.value,
        }:
            # Nothing is executing/reviewing; a stop request on an idle
            # verify/repair phase has nothing left to stop, so the slot release
            # is confirmed honestly rather than reported as unconfirmed.
            confirmed = True
            reason = reason or "no executor or reviewer running; slot released"

        if not confirmed:
            self._record_unconfirmed(task_id, active_run, action, reason)
            return ControlOutcome(
                action=action,
                state="unconfirmed",
                confirmed=False,
                task_id=task_id,
                run_id=active_run,
                phase=str(self._store.read("task", task_id).entity.get("phase")),
                reason=reason,
            )

        if action == "cancel":
            self._writer.transition_run(
                active_run, "cancelled", task_ref=task_id, reason=reason
            )
            cleanup = self._finalize_stop(task_id, active_run)
            self._writer.transition_task(task_id, TaskPhase.CANCELLED, run_ref=active_run)
            self._writer.set_active_run(task_id, None)
        else:
            self._writer.transition_run(active_run, "paused", task_ref=task_id, reason=reason)
            cleanup = self._finalize_stop(task_id, active_run)
            current_phase = str(self._store.read("task", task_id).entity.get("phase"))
            if current_phase in {TaskPhase.VERIFYING.value, TaskPhase.REPAIRING.value}:
                # Legal two-step for a pause during independent review: park at
                # ``waiting_user`` first, then move to ``paused`` (both frozen
                # directions exist) so the candidate/evidence are retained.
                self._writer.transition_task(
                    task_id, TaskPhase.WAITING_USER, run_ref=active_run,
                    reason="independent review stopped by pause request",
                )
            self._writer.transition_task(task_id, TaskPhase.PAUSED, run_ref=active_run)
        self._release_claim(task_id)
        return ControlOutcome(
            action=action,
            state="confirmed",
            confirmed=True,
            task_id=task_id,
            run_id=active_run,
            phase=str(self._store.read("task", task_id).entity.get("phase")),
            reason=reason,
            cleanup=cleanup,
        )

    def _finalize_stop(self, task_id: str, run_id: str) -> str:
        """Mark cleanup done independently; never delete diff/worktree/history.

        A cleanup failure is recorded on the Run's own ``cleanup`` field (and an
        error event) so a successful delivery is never masked by a cleanup
        problem, and no original artifact is removed here.
        """

        try:
            self._writer.write_run(run_id, {"cleanup": {"status": "done"}})
            self._writer.emit(
                task_id,
                EventType.CLEANUP_UPDATED,
                {"status": "done"},
                task_ref=task_id,
                run_ref=run_id,
            )
            return "done"
        except Exception as exc:  # noqa: BLE001 - cleanup is reported, not hidden
            reason = f"cleanup failed: {type(exc).__name__}: {exc}"
            try:
                self._writer.write_run(run_id, {"cleanup": {"status": "failed"}})
            except Exception:  # noqa: BLE001 - best effort to persist the failure
                pass
            self._writer.emit(
                task_id,
                EventType.CLEANUP_UPDATED,
                {"status": "failed", "reason": reason},
                task_ref=task_id,
                run_ref=run_id,
            )
            return "failed"

    def _release_claim(self, task_id: str) -> None:
        """Free the Task lease once a stop is confirmed (docs/04 §5).

        The worker loop also releases its own claim; this is best-effort and
        tolerates the worker having released first.  It never touches another
        owner's live lease.
        """

        if self._owner is None:
            return
        try:
            self._store.release(task_id, self._owner)
        except Exception:  # noqa: BLE001 - the worker loop will release its own claim
            pass

    def _record_unconfirmed(
        self, task_id: str, run_id: str, action: str, reason: str | None
    ) -> None:
        self._writer.emit(
            task_id,
            EventType.ERROR_RECORDED,
            {
                "mode": "control",
                "code": "cancellation_unconfirmed",
                "action": action,
                "message": reason or f"{action} not confirmed within timeout",
            },
            task_ref=task_id,
            run_ref=run_id,
        )

    def _record_review_stop_unconfirmed(
        self, task_id: str, run_id: str, action: str, reason: str
    ) -> None:
        """Record an unconfirmed independent-reviewer stop (LG-022 D2).

        The task keeps its ``cancelling``/``pausing`` phase and its execution
        slot; we never fabricate a stop or release the slot on ``unknown``.
        """

        self._writer.emit(
            task_id,
            EventType.ERROR_RECORDED,
            {
                "mode": "control",
                "code": "review_stop_unconfirmed",
                "action": action,
                "message": reason,
            },
            task_ref=task_id,
            run_ref=run_id,
        )

    def _stop_without_run(self, task_id: str, phase: str, action: str) -> ControlOutcome:
        if action != "cancel":
            return ControlOutcome(
                action=action,
                state="not_applicable",
                confirmed=False,
                task_id=task_id,
                phase=phase,
                reason="no active Run to pause",
            )
        if phase in {TaskPhase.CANCELLED.value, TaskPhase.COMPLETED.value}:
            return ControlOutcome(
                action=action,
                state="not_applicable",
                confirmed=False,
                task_id=task_id,
                phase=phase,
                reason=f"Task already {phase}",
            )
        self._writer.transition_task(task_id, TaskPhase.CANCELLED)
        return ControlOutcome(
            action=action,
            state="confirmed",
            confirmed=True,
            task_id=task_id,
            phase=TaskPhase.CANCELLED.value,
            reason="cancelled before execution started",
        )

    # ---------------------------------------------------------------- resume
    def requeue(self, task_id: str, action: str) -> ControlOutcome:
        """resume/retry/reopen/enqueue: queue a Task without a second writer.

        The store lease plus ``active_run`` guard in the worker loop make a
        duplicate Run impossible: the loop refuses to open a second
        non-terminal Run for the same Task.  A Task with a live Run cannot be
        requeued at all.
        """

        task = self._store.read("task", task_id)
        entity = task.entity
        phase = str(entity.get("phase", ""))
        active_run = entity.get("active_run")

        if action == "enqueue":
            if phase not in {TaskPhase.INTAKE.value, TaskPhase.FAILED.value}:
                return ControlOutcome(
                    action=action,
                    state="not_applicable",
                    confirmed=False,
                    task_id=task_id,
                    phase=phase,
                    reason="Task is already in or past the queue",
                )
        elif action == "resume":
            if phase not in RESUMABLE_PHASES:
                return ControlOutcome(
                    action=action,
                    state="not_applicable",
                    confirmed=False,
                    task_id=task_id,
                    phase=phase,
                    reason=f"phase {phase!r} is not resumable",
                )
            if isinstance(active_run, str) and active_run:
                live = self._run_is_live(active_run)
                if live:
                    return ControlOutcome(
                        action=action,
                        state="not_applicable",
                        confirmed=False,
                        task_id=task_id,
                        run_id=active_run,
                        phase=phase,
                        reason="active Run still holds the slot; stop it first",
                    )
        elif action == "retry":
            if phase not in RETRYABLE_PHASES:
                return ControlOutcome(
                    action=action,
                    state="not_applicable",
                    confirmed=False,
                    task_id=task_id,
                    phase=phase,
                    reason=f"phase {phase!r} is not retryable",
                )
        elif action == "reopen":
            if phase not in REOPENABLE_PHASES:
                return ControlOutcome(
                    action=action,
                    state="not_applicable",
                    confirmed=False,
                    task_id=task_id,
                    phase=phase,
                    reason=f"phase {phase!r} cannot be reopened",
                )
            current = entity.get("requirements_revision")
            bumped = current + 1 if isinstance(current, int) else 1
            self._writer.write_task(
                task_id,
                {
                    "requirements_revision": bumped,
                    "acceptance": {
                        "status": "pending",
                        "requirements_revision": None,
                        "deliverable_revision": None,
                        "evidence_refs": [],
                        "decided_at": None,
                        "decision_ref": None,
                    },
                },
            )
            self._writer.emit(
                task_id,
                EventType.TASK_REQUIREMENTS_CHANGED,
                {"requirements_revision": bumped, "reason": "reopen"},
                task_ref=task_id,
            )
        else:  # pragma: no cover - action names are validated by the API
            raise AppError(
                ErrorCode.INVALID_REQUEST,
                f"unsupported requeue action {action!r}",
                details={"action": action},
            )

        if isinstance(active_run, str) and active_run and self._run_is_live(active_run):
            return ControlOutcome(
                action=action,
                state="not_applicable",
                confirmed=False,
                task_id=task_id,
                run_id=active_run,
                phase=phase,
                reason="active Run still holds the slot",
            )
        if isinstance(active_run, str) and active_run:
            # The referenced Run is stopped (paused/failed/cancelled).  Clear the
            # pointer so the worker can open exactly one new Run; the stopped
            # Run is retained as history with its own diff/worktree.  ``last_run``
            # keeps the stopped Run discoverable so a confirmed-pause resume can
            # continue the same native SDK session (LG-016 continuation).
            self._writer.write_task(task_id, {"last_run": active_run})
            self._writer.set_active_run(task_id, None)

        state = self._queue.enqueue(task_id)
        phase_now = str(self._store.read("task", task_id).entity.get("phase"))
        if state == "already_queued":
            return ControlOutcome(
                action=action,
                state="not_applicable",
                confirmed=False,
                task_id=task_id,
                phase=phase_now,
                reason="Task is already queued or executing",
            )
        return ControlOutcome(
            action=action,
            state="confirmed",
            confirmed=True,
            task_id=task_id,
            phase=phase_now,
            reason=state,
        )

    def _run_is_live(self, run_id: str) -> bool:
        try:
            state = str(self._store.read("run", run_id).entity.get("state"))
        except EntityNotFound:
            return False
        return state not in TERMINAL_RUN_STATES and state not in {"paused"}


__all__ = [
    "ControlOutcome",
    "ControlService",
    "RESUMABLE_PHASES",
    "RETRYABLE_PHASES",
    "REOPENABLE_PHASES",
]
