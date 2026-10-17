"""Task/Run state helpers written exclusively through the ``Store`` (LG-007).

The executor adapter and any future planner graph must not edit TASK.md/RUN.md.
:class:`StateWriter` and :class:`RunController` are the only control-state
mutation helpers the dispatcher receives; they apply optimistic-concurrency
retries and emit the frozen contract events.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Protocol, cast

from lightgravity.contracts import EventType, TaskPhase, TaskStatus
from lightgravity.store import (
    RevisionConflict,
    Store,
    Versioned,
)


def _value(value: Any) -> Any:
    return value.value if isinstance(value, Enum) else value

#: Run states that no longer occupy the execution slot.
TERMINAL_RUN_STATES: frozenset[str] = frozenset({"completed", "cancelled", "failed"})

#: Task phases that mean a Run is still active / holding the slot.
ACTIVE_TASK_PHASES: frozenset[str] = frozenset(
    {
        TaskPhase.PLANNING,
        TaskPhase.RECRUITING,
        TaskPhase.EXECUTING,
        TaskPhase.VERIFYING,
        TaskPhase.REPAIRING,
        TaskPhase.PAUSING,
        TaskPhase.CANCELLING,
    }
)

#: Task phases for a stopped-but-unaccepted Run (no execution slot).
WAITING_TASK_PHASES: frozenset[str] = frozenset(
    {
        TaskPhase.WAITING_USER,
        TaskPhase.PAUSED,
        TaskPhase.AWAITING_ACCEPTANCE,
        TaskPhase.RECOVERY_REQUIRED,
    }
)

_STATUS_FOR_PHASE: dict[str, str] = {
    TaskPhase.INTAKE: TaskStatus.TODO,
    TaskPhase.QUEUED: TaskStatus.TODO,
    TaskPhase.WAITING_DEPENDENCIES: TaskStatus.TODO,
    TaskPhase.CANCELLED: TaskStatus.IN_PROGRESS,
    TaskPhase.COMPLETED: TaskStatus.DONE,
}


def status_for_phase(phase: str) -> str:
    """Return the legal ``status`` for a Task ``phase``.

    Terminal ``cancelled`` may legally be ``todo`` (never started) or
    ``in-progress`` (started then cancelled); the caller passes the current
    status through :meth:`StateWriter.transition_task` for that case.
    """

    if phase == TaskPhase.CANCELLED:
        return TaskStatus.IN_PROGRESS
    return _STATUS_FOR_PHASE.get(phase, TaskStatus.IN_PROGRESS)


class _BodyCreateStore(Protocol):
    """Concrete store accepts Markdown prose; the frozen protocol does not."""

    def create(
        self,
        kind: str,
        entity_id: str,
        content: dict[str, Any],
        *,
        actor: str,
        request_id: str,
        body: str | None = None,
    ) -> Versioned: ...


class StateWriter:
    """Read-modify-write helper for Task/Run entities and their event streams."""

    def __init__(self, store: Store, *, actor: str = "coordinator", max_retries: int = 8) -> None:
        self._store = store
        self._actor = actor
        self._max_retries = max_retries

    @property
    def store(self) -> Store:
        return self._store

    def emit(
        self,
        stream_id: str,
        event_type: EventType,
        payload: dict[str, Any] | None = None,
        *,
        task_ref: str | None = None,
        run_ref: str | None = None,
        actor: str | None = None,
    ) -> None:
        self._store.append_event(
            stream_id,
            {
                "type": event_type.value,
                "actor": actor or self._actor,
                "task_ref": task_ref,
                "run_ref": run_ref,
                "payload": payload or {},
            },
        )

    def write_task(self, task_id: str, updates: dict[str, Any], *, actor: str | None = None) -> Versioned:
        last: RevisionConflict | None = None
        for _ in range(self._max_retries):
            current = self._store.read("task", task_id)
            try:
                return self._store.write(
                    "task",
                    task_id,
                    updates,
                    expected_revision=current.revision,
                    actor=actor or self._actor,
                )
            except RevisionConflict as exc:  # concurrent writer won; re-read
                last = exc
        assert last is not None
        raise last

    def write_run(self, run_id: str, updates: dict[str, Any], *, actor: str | None = None) -> Versioned:
        last: RevisionConflict | None = None
        for _ in range(self._max_retries):
            current = self._store.read("run", run_id)
            try:
                return self._store.write(
                    "run",
                    run_id,
                    updates,
                    expected_revision=current.revision,
                    actor=actor or self._actor,
                )
            except RevisionConflict as exc:
                last = exc
        assert last is not None
        raise last

    def create(
        self,
        kind: str,
        entity_id: str,
        content: dict[str, Any],
        *,
        body: str | None = None,
        actor: str | None = None,
        request_id: str | None = None,
    ) -> Versioned:
        """Create a state entity (RunController-owned Subtask/Member) via Store."""

        return cast(_BodyCreateStore, self._store).create(
            kind,
            entity_id,
            content,
            actor=actor or self._actor,
            request_id=request_id or f"{kind}:{entity_id}",
            body=body,
        )

    def read_subtask(self, subtask_id: str) -> Versioned:
        return self._store.read("subtask", subtask_id)

    def write_subtask(
        self, subtask_id: str, updates: dict[str, Any], *, actor: str | None = None
    ) -> Versioned:
        last: RevisionConflict | None = None
        for _ in range(self._max_retries):
            current = self._store.read("subtask", subtask_id)
            try:
                return self._store.write(
                    "subtask",
                    subtask_id,
                    updates,
                    expected_revision=current.revision,
                    actor=actor or self._actor,
                )
            except RevisionConflict as exc:
                last = exc
        assert last is not None
        raise last

    def write_member(
        self, member_id: str, updates: dict[str, Any], *, actor: str | None = None
    ) -> Versioned:
        last: RevisionConflict | None = None
        for _ in range(self._max_retries):
            current = self._store.read("member", member_id)
            try:
                return self._store.write(
                    "member",
                    member_id,
                    updates,
                    expected_revision=current.revision,
                    actor=actor or self._actor,
                )
            except RevisionConflict as exc:
                last = exc
        assert last is not None
        raise last

    def transition_task(
        self,
        task_id: str,
        phase: str,
        *,
        status: str | None = None,
        run_ref: str | None = None,
        extra: dict[str, Any] | None = None,
        reason: str | None = None,
    ) -> Versioned:
        current = self._store.read("task", task_id)
        from_phase = current.entity.get("phase")
        current_status = current.entity.get("status")
        phase = _value(phase)
        new_status = _value(status) if status is not None else self._effective_status(phase, current_status)
        new_status = _value(new_status)
        updates: dict[str, Any] = {"phase": phase, "status": new_status}
        if extra:
            updates.update(extra)
        versioned = self.write_task(task_id, updates)
        if from_phase != phase:
            payload: dict[str, Any] = {"from": from_phase, "to": phase}
            if reason:
                payload["reason"] = reason
            self.emit(
                task_id,
                EventType.TASK_PHASE_CHANGED,
                payload,
                task_ref=task_id,
                run_ref=run_ref,
            )
        if current_status != new_status:
            self.emit(
                task_id,
                EventType.TASK_STATUS_CHANGED,
                {"from": current_status, "to": new_status},
                task_ref=task_id,
                run_ref=run_ref,
            )
        return versioned

    def transition_run(
        self,
        run_id: str,
        state: str,
        *,
        task_ref: str | None = None,
        extra: dict[str, Any] | None = None,
        reason: str | None = None,
    ) -> Versioned:
        current = self._store.read("run", run_id)
        from_state = current.entity.get("state")
        state = _value(state)
        updates: dict[str, Any] = {"state": state}
        if extra:
            updates.update(extra)
        versioned = self.write_run(run_id, updates)
        if from_state != state:
            payload: dict[str, Any] = {"from": from_state, "to": state}
            if reason:
                payload["reason"] = reason
            self.emit(
                run_id,
                EventType.RUN_STATE_CHANGED,
                payload,
                task_ref=task_ref or current.entity.get("task_ref"),
                run_ref=run_id,
            )
        return versioned

    def _effective_status(self, phase: str, current_status: Any) -> str:
        if phase == TaskPhase.CANCELLED and current_status == TaskStatus.TODO:
            return TaskStatus.TODO
        return status_for_phase(phase)

    def set_active_run(self, task_id: str, run_id: str | None) -> Versioned:
        return self.write_task(task_id, {"active_run": run_id})


class RunController:
    """Safe state-mutation surface handed to a :class:`Dispatcher`.

    LG-008's planner/recruiter/scheduler graph uses this instead of touching
    files, so the single-writer rule (docs/08 §7/§11) holds.
    """

    def __init__(self, writer: StateWriter, task_id: str, run_id: str) -> None:
        self._writer = writer
        self._task_id = task_id
        self._run_id = run_id

    @property
    def task_id(self) -> str:
        return self._task_id

    @property
    def run_id(self) -> str:
        return self._run_id

    def emit(
        self,
        event_type: EventType,
        payload: dict[str, Any] | None = None,
        *,
        actor: str = "coordinator",
    ) -> None:
        self._writer.emit(
            self._task_id,
            event_type,
            payload,
            task_ref=self._task_id,
            run_ref=self._run_id,
            actor=actor,
        )

    def set_task_phase(
        self,
        phase: str,
        *,
        status: str | None = None,
        extra: dict[str, Any] | None = None,
        reason: str | None = None,
    ) -> Versioned:
        return self._writer.transition_task(
            self._task_id,
            phase,
            status=status,
            run_ref=self._run_id,
            extra=extra,
            reason=reason,
        )

    def set_run_state(
        self,
        state: str,
        *,
        extra: dict[str, Any] | None = None,
        reason: str | None = None,
    ) -> Versioned:
        return self._writer.transition_run(
            self._run_id, state, task_ref=self._task_id, extra=extra, reason=reason
        )

    def set_run_cleanup(self, status: str, *, reason: str | None = None) -> Versioned:
        versioned = self._writer.write_run(self._run_id, {"cleanup": {"status": status}})
        self.emit(
            EventType.CLEANUP_UPDATED,
            {"status": status, **({"reason": reason} if reason else {})},
        )
        return versioned

    def set_active_run(self, run_id: str | None) -> Versioned:
        return self._writer.set_active_run(self._task_id, run_id)

    def update_run(self, updates: dict[str, Any]) -> Versioned:
        """Write non-state Run fields (plan, team_refs, subtask_refs)."""

        return self._writer.write_run(self._run_id, updates)

    def read_run(self) -> dict[str, Any]:
        """Read the current Run entity mapping (empty when it vanished)."""

        return self._writer.store.read("run", self._run_id).entity

    def set_run_waiting_reason(self, reason: str | None) -> Versioned:
        """Additive scheduling hint on the Run (never a state/phase value)."""

        current = self._writer.store.read("run", self._run_id).entity
        if current.get("waiting_reason") == reason:
            return self._writer.store.read("run", self._run_id)
        return self._writer.write_run(self._run_id, {"waiting_reason": reason})

    def set_subtask_waiting_reason(self, subtask_id: str, reason: str | None) -> Versioned:
        """Additive scheduling hint on a pending Subtask; no state transition."""

        current = self._writer.read_subtask(subtask_id)
        if current.entity.get("waiting_reason") == reason:
            return current
        return self._writer.write_subtask(subtask_id, {"waiting_reason": reason})

    def update_member(self, member_id: str, updates: dict[str, Any]) -> Versioned:
        """Write non-state Member fields (e.g. the resolved ``session_ref``).

        State transitions stay on :meth:`transition_member`; this seam exists so
        LG-016's node-session flow can attach a non-secret native session record
        to the member that executed a node without fabricating a state change.
        """

        return self._writer.write_member(member_id, updates)

    def set_member_session(self, member_id: str, session: dict[str, Any]) -> Versioned:
        """Attach the non-secret native ``session_ref`` to an executing member."""

        return self.update_member(member_id, {"session_ref": session})

    def create_subtask(
        self, subtask_id: str, content: dict[str, Any], *, body: str | None = None
    ) -> Versioned:
        return self._writer.create("subtask", subtask_id, content, body=body)

    def transition_subtask(
        self,
        subtask_id: str,
        state: str,
        *,
        extra: dict[str, Any] | None = None,
        acceptance: dict[str, Any] | None = None,
        reason: str | None = None,
    ) -> Versioned:
        current = self._writer.read_subtask(subtask_id)
        from_state = current.entity.get("state")
        updates: dict[str, Any] = {"state": state}
        if extra:
            updates.update(extra)
        if acceptance is not None:
            updates["acceptance"] = acceptance
        versioned = self._writer.write_subtask(subtask_id, updates)
        if from_state != state:
            payload: dict[str, Any] = {
                "subtask_ref": subtask_id,
                "from": from_state,
                "to": state,
            }
            if reason:
                payload["reason"] = reason
            self.emit(EventType.SUBTASK_STATE_CHANGED, payload)
        return versioned

    def create_member(
        self, member_id: str, content: dict[str, Any], *, body: str | None = None
    ) -> Versioned:
        return self._writer.create("member", member_id, content, body=body)

    def transition_member(
        self,
        member_id: str,
        state: str,
        *,
        extra: dict[str, Any] | None = None,
        reason: str | None = None,
    ) -> Versioned:
        current = self._writer.store.read("member", member_id)
        from_state = current.entity.get("state")
        updates: dict[str, Any] = {"state": state}
        if extra:
            updates.update(extra)
        versioned = self._writer.write_member(member_id, updates)
        if from_state != state:
            payload: dict[str, Any] = {
                "member_ref": member_id,
                "from": from_state,
                "to": state,
            }
            if reason:
                payload["reason"] = reason
            self.emit(EventType.MEMBER_STATE_CHANGED, payload)
        return versioned

    def recruit_member(self, member_id: str, payload: dict[str, Any]) -> None:
        self.emit(EventType.MEMBER_RECRUITED, {"member_ref": member_id, **payload})

    def release_member(self, member_id: str, *, reason: str | None = None) -> Versioned:
        versioned = self.transition_member(member_id, "released", reason=reason)
        self.emit(
            EventType.MEMBER_RELEASED,
            {"member_ref": member_id, **({"reason": reason} if reason else {})},
        )
        return versioned

    def record_artifact(
        self, subtask_id: str, refs: tuple[str, ...], handoff: dict[str, Any]
    ) -> None:
        self.emit(
            EventType.ARTIFACT_PRODUCED,
            {"subtask_ref": subtask_id, "artifact_refs": list(refs), "handoff": handoff},
        )


__all__ = [
    "TERMINAL_RUN_STATES",
    "ACTIVE_TASK_PHASES",
    "WAITING_TASK_PHASES",
    "status_for_phase",
    "StateWriter",
    "RunController",
]
