"""Stop gate: confirm executors/sessions stopped before awaiting acceptance (LG-009).

docs/08 §6.1 / §9 and the LG-009 acceptance condition require that a candidate is
only handed to human acceptance after every executor and session has stopped and
the team / execution slot have been released.  A stop is never fabricated: this
module reads authoritative Store state, releases resources only after the Run is
confirmed stopped, and reports every unconfirmed fact instead of writing a
terminal state.

The port is injectable so the coordinator/adapter can supply a stronger
confirmation (for example a live adapter ``cancel``/session close) without
changing this code.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from lightgravity.store import EntityNotFound, LockConflict, Store

from lightgravity.coordinator.state import RunController, StateWriter

#: Run states that mean work may still be executing (holding the slot).
ACTIVE_RUN_STATES = frozenset({"planning", "recruiting", "executing", "pausing", "cancelling"})

#: Member states that no longer occupy an execution slot.
TERMINAL_MEMBER_STATES = frozenset({"released", "failed"})


@dataclass(frozen=True, slots=True)
class StopReport:
    """The result of the stop/release gate."""

    confirmed: bool
    run_stopped: bool
    sessions_stopped: bool
    slot_released: bool
    members_released: tuple[str, ...] = ()
    problems: tuple[str, ...] = ()
    #: Raw adapter stop-confirmation payload when one was consulted (LG-022 R2).
    session_confirmation: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "confirmed": self.confirmed,
            "run_stopped": self.run_stopped,
            "sessions_stopped": self.sessions_stopped,
            "slot_released": self.slot_released,
            "members_released": list(self.members_released),
            "problems": list(self.problems),
            "session_confirmation": self.session_confirmation,
        }


@runtime_checkable
class SessionStopConfirmer(Protocol):
    """Port proving a Run's real sessions/proxy stopped (LG-022 R2).

    The adapter implements this from its actual close/stop facts.  The stop gate
    consults it so a successful Run whose ``cleanup`` is still ``pending`` can be
    released only on a genuine stop, never on a fabricated ``cleanup=done``.
    """

    def confirm_stopped(
        self, run_id: str, session_refs: tuple[str, ...]
    ) -> Any: ...


@runtime_checkable
class ResourceStopper(Protocol):
    """Confirmation port: stop/release a Run's execution resources."""

    def stop(self, task_id: str, run_id: str) -> StopReport: ...


class StoreResourceStopper:
    """Default stop gate derived from authoritative Store state.

    * the Run must not be in an active execution state;
    * every session must be closed (no sessions, or ``cleanup.status=done``);
    * non-terminal members are released **only** once the Run is confirmed
      stopped (never before), and
    * the Task execution-slot lease must be released (it is re-released here if
      the owner left the queue claimed).
    """

    def __init__(
        self,
        store: Store,
        *,
        writer: StateWriter | None = None,
        actor: str = "verify",
        session_confirmer: SessionStopConfirmer | None = None,
    ) -> None:
        self._store = store
        self._writer = writer or StateWriter(store, actor=actor)
        #: Optional real stop-confirmation port (adapter/dispatcher/reviewer).
        #: When present, a Run whose sessions are provably stopped does not need
        #: ``cleanup=done`` to pass the gate -- the fact itself is verified.
        self._session_confirmer = session_confirmer

    def stop(self, task_id: str, run_id: str) -> StopReport:
        task = self._store.read("task", task_id)
        run = self._store.read("run", run_id)
        problems: list[str] = []

        run_state = str(run.entity.get("state", ""))
        run_stopped = run_state not in ACTIVE_RUN_STATES
        if not run_stopped:
            problems.append(f"run {run_id} is still in active state {run_state!r}")

        session_refs = _str_tuple(run.entity.get("session_refs"))
        cleanup = run.entity.get("cleanup")
        cleanup_status = cleanup.get("status") if isinstance(cleanup, dict) else None
        # A Run's sessions count as stopped when either the Run recorded a real
        # ``cleanup=done`` stop stage, or an authoritative stop-confirmation port
        # proves each SDK session/proxy is closed.  Unknown/active sessions keep
        # the gate unconfirmed and preserve the refs (never fabricated).
        sessions_stopped = not session_refs or cleanup_status == "done"
        confirm_detail: dict[str, Any] | None = None
        if session_refs and not sessions_stopped and self._session_confirmer is not None:
            confirmation = self._session_confirmer.confirm_stopped(run_id, session_refs)
            if confirmation is not None:
                confirm_detail = getattr(confirmation, "to_dict", None)
                confirm_detail = confirm_detail() if callable(confirm_detail) else None
                sessions_stopped = bool(getattr(confirmation, "confirmed", False))
        if not sessions_stopped:
            detail = f" (cleanup={cleanup_status!r})"
            if confirm_detail is not None:
                confirmation_problems = confirm_detail.get("problems") or []
                detail = f" (cleanup={cleanup_status!r}, adapter={confirmation_problems!r})"
            problems.append(
                f"{len(session_refs)} session(s) not confirmed closed{detail}"
            )

        # LG-022 R2: the independent reviewer is a separate SDK agent/proxy.
        # When it ran, its real teardown fact must show it stopped too -- a
        # pending/failed reviewer resource keeps the gate unconfirmed (the
        # reviewer is never assumed to have stopped because the worker did).
        reviewer_cleanup = run.entity.get("reviewer_cleanup")
        if isinstance(reviewer_cleanup, dict) and reviewer_cleanup:
            if reviewer_cleanup.get("confirmed") is not True:
                problems.append(
                    "reviewer resource not confirmed stopped "
                    f"(status={reviewer_cleanup.get('status')!r})"
                )

        controller = RunController(self._writer, task_id, run_id)
        members_released: list[str] = []
        for member_ref in _str_tuple(run.entity.get("team_refs")):
            try:
                member_state = str(self._store.read("member", member_ref).entity.get("state", ""))
            except EntityNotFound:
                continue
            if member_state in TERMINAL_MEMBER_STATES:
                continue
            if not run_stopped:
                problems.append(
                    f"member {member_ref} is still {member_state!r}; not released without a confirmed stop"
                )
                continue
            try:
                controller.release_member(member_ref, reason="stop gate released team member")
                members_released.append(member_ref)
            except Exception as exc:  # noqa: BLE001 - never fake a release
                problems.append(f"member {member_ref} release failed: {type(exc).__name__}")

        slot_released = self._release_slot(task.entity, task_id, run_stopped, problems)

        confirmed = run_stopped and sessions_stopped and slot_released and not problems
        return StopReport(
            confirmed=confirmed,
            run_stopped=run_stopped,
            sessions_stopped=sessions_stopped,
            slot_released=slot_released,
            members_released=tuple(members_released),
            problems=tuple(problems),
            session_confirmation=confirm_detail,
        )

    def _release_slot(
        self,
        task_entity: dict[str, object],
        task_id: str,
        run_stopped: bool,
        problems: list[str],
    ) -> bool:
        queue = task_entity.get("queue")
        queue_map = queue if isinstance(queue, dict) else {}
        state = queue_map.get("state")
        owner = queue_map.get("owner")
        if state == "not_queued" and owner in (None, ""):
            return True
        if not run_stopped:
            problems.append("task execution slot is still claimed while the run is active")
            return False
        try:
            self._store.release(task_id, owner if isinstance(owner, str) else "")
        except LockConflict as exc:
            problems.append(f"execution slot release conflicted: {exc}")
            return False
        except Exception as exc:  # noqa: BLE001 - report, never fake
            problems.append(f"execution slot release failed: {type(exc).__name__}")
            return False
        return True


def _str_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(item for item in value if isinstance(item, str) and item)


__all__ = [
    "ACTIVE_RUN_STATES",
    "TERMINAL_MEMBER_STATES",
    "ResourceStopper",
    "SessionStopConfirmer",
    "StopReport",
    "StoreResourceStopper",
]
