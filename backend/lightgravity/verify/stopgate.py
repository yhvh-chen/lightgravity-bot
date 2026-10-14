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
from typing import Protocol, runtime_checkable

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

    def to_dict(self) -> dict[str, object]:
        return {
            "confirmed": self.confirmed,
            "run_stopped": self.run_stopped,
            "sessions_stopped": self.sessions_stopped,
            "slot_released": self.slot_released,
            "members_released": list(self.members_released),
            "problems": list(self.problems),
        }


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

    def __init__(self, store: Store, *, writer: StateWriter | None = None, actor: str = "verify") -> None:
        self._store = store
        self._writer = writer or StateWriter(store, actor=actor)

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
        sessions_stopped = not session_refs or cleanup_status == "done"
        if not sessions_stopped:
            problems.append(
                f"{len(session_refs)} session(s) not confirmed closed (cleanup={cleanup_status!r})"
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
    "StopReport",
    "StoreResourceStopper",
]
