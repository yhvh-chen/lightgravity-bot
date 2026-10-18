"""Restart inspection and recovery (LG-016, docs/04 §8, docs/08 §9).

On service restart the coordinator must scan queue, active leases and
in-progress Runs before doing any work.  This module answers one question per
affected Task: is the interrupted execution *safely resumable* or does it
require a human decision?

Guiding rules:

* A task that never started (queued/intake/waiting_dependencies) is simply
  available to the queue again.
* A task whose Run was mid-execution when the process died is **not** replayed
  automatically.  Unknown side effects go to ``recovery_required``; only the
  process probe may assert a proven stop, and even then the Task is not
  silently executed again — the user/coordinator decides.
* Stale claims (lease held by this same process identity from a previous boot)
  are released so the slot is not occupied by a dead worker.
* A stopped-but-unaccepted/previously-stopped Run must not keep occupying the
  slot; the lease is cleared and the phase reflects that the slot is free.

The module only reads the filesystem passively to look for artifacts/side
effects; it never rewrites, deletes or replays a workspace or diff.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

from lightgravity.contracts import EventType, TaskPhase
from lightgravity.store import EntityNotFound, Store

from .state import ACTIVE_TASK_PHASES, StateWriter, TERMINAL_RUN_STATES


class ProcessProbe(Protocol):
    """Answers whether a previously observed worker pid is still alive."""

    def is_alive(self, pid: int) -> bool: ...


class DefaultProcessProbe:
    """Conservative liveness probe (``os.kill(pid, 0)`` / ``pid_exists``)."""

    def is_alive(self, pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            # A live process we may not signal still exists.
            return True
        except OSError:
            return False
        return True


@dataclass(frozen=True, slots=True)
class RecoveryDecision:
    task_id: str
    run_id: str | None
    action: str  # requeue | recovery_required | release_stale_claim | none
    reason: str
    alive: bool | None = None
    has_artifacts: bool | None = None


@dataclass(slots=True)
class RecoveryReport:
    decisions: list[RecoveryDecision] = field(default_factory=list)

    @property
    def recovery_required(self) -> list[RecoveryDecision]:
        return [d for d in self.decisions if d.action == "recovery_required"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "decisions": [
                {
                    "task_id": d.task_id,
                    "run_id": d.run_id,
                    "action": d.action,
                    "reason": d.reason,
                    "alive": d.alive,
                    "has_artifacts": d.has_artifacts,
                }
                for d in self.decisions
            ],
            "recovery_required": [d.task_id for d in self.recovery_required],
        }


class RecoveryScanner:
    """One-shot restart inspection over persisted Task/Run state."""

    def __init__(
        self,
        store: Store,
        writer: StateWriter,
        *,
        probe: ProcessProbe | None = None,
        artifact_root: Path | str | None = None,
        pid_lookup: Callable[[str], int | None] | None = None,
    ) -> None:
        self._store = store
        self._writer = writer
        self._probe = probe or DefaultProcessProbe()
        self._artifact_root = (
            Path(artifact_root).resolve() if artifact_root is not None else None
        )
        self._pid_lookup = pid_lookup or self._default_pid_lookup

    def _default_pid_lookup(self, task_id: str) -> int | None:
        """Read a persisted worker pid from the Task's ``queue.owner_pid``.

        The coordinator does not currently persist a pid; the lookup returns
        ``None`` (unknown), which the scanner treats conservatively as "may
        still be alive" only when a Run is non-terminal.  Tests inject a probe.
        """

        try:
            entity = self._store.read("task", task_id).entity
        except EntityNotFound:
            return None
        queue = entity.get("queue")
        if isinstance(queue, dict):
            pid = queue.get("owner_pid")
            if isinstance(pid, int) and not isinstance(pid, bool):
                return pid
        run_ref = entity.get("active_run")
        if isinstance(run_ref, str) and run_ref:
            try:
                run = self._store.read("run", run_ref).entity
            except EntityNotFound:
                return None
            pid = run.get("worker_pid")
            if isinstance(pid, int) and not isinstance(pid, bool):
                return pid
        return None

    def scan(self) -> RecoveryReport:
        report = RecoveryReport()
        for summary in self._store.list_tasks():
            try:
                decision = self._inspect(summary.id)
            except Exception as exc:  # noqa: BLE001 - one bad Task must not abort the scan
                decision = RecoveryDecision(
                    task_id=summary.id,
                    run_id=None,
                    action="recovery_required",
                    reason=f"recovery inspection failed: {type(exc).__name__}: {exc}",
                )
                if not self._mark_recovery_required(summary.id, None, decision.reason):
                    decision = RecoveryDecision(
                        task_id=summary.id, run_id=None, action="none",
                        reason="recovery inspection failed; transition not persisted",
                    )
            if decision is not None:
                report.decisions.append(decision)
        return report

    def _inspect(self, task_id: str) -> RecoveryDecision | None:
        task = self._store.read("task", task_id)
        entity = task.entity
        phase = str(entity.get("phase", ""))
        active_run = entity.get("active_run")
        raw_queue = entity.get("queue")
        queue: dict[str, Any] = raw_queue if isinstance(raw_queue, dict) else {}
        queue_state = str(queue.get("state", "not_queued"))

        # Interrupted execution: a Run that was live when the process stopped.
        if isinstance(active_run, str) and active_run:
            try:
                run = self._store.read("run", active_run).entity
            except EntityNotFound:
                # Referenced Run is gone: the slot is not really held.
                self._writer.set_active_run(task_id, None)
                self._writer.emit(
                    task_id,
                    EventType.ERROR_RECORDED,
                    {
                        "mode": "recovery",
                        "code": "active_run_missing",
                        "message": f"active_run {active_run} not found; cleared",
                    },
                    task_ref=task_id,
                    run_ref=active_run,
                )
                return RecoveryDecision(
                    task_id=task_id,
                    run_id=active_run,
                    action="none",
                    reason="active_run missing; slot cleared",
                )
            except Exception as exc:  # noqa: BLE001 - an unreadable Run is a data fault
                self._writer.set_active_run(task_id, None)
                self._writer.emit(
                    task_id,
                    EventType.ERROR_RECORDED,
                    {
                        "mode": "recovery",
                        "code": "active_run_unreadable",
                        "message": f"active_run {active_run} unreadable: {type(exc).__name__}",
                    },
                    task_ref=task_id,
                    run_ref=active_run,
                )
                return RecoveryDecision(
                    task_id=task_id,
                    run_id=active_run,
                    action="none",
                    reason="active_run unreadable; slot cleared",
                )
            run_state = str(run.get("state", ""))
            if run_state in TERMINAL_RUN_STATES:
                # A finished Run must not keep the slot; release and continue.
                self._writer.set_active_run(task_id, None)
                self._release_stale_claim(task_id, queue_state)
                return RecoveryDecision(
                    task_id=task_id,
                    run_id=active_run,
                    action="release_stale_claim",
                    reason=f"terminal Run {run_state} still marked active; released",
                )

            if phase in ACTIVE_TASK_PHASES or run_state in {
                "planning",
                "recruiting",
                "executing",
                "verifying",
                "repairing",
            }:
                pid = self._pid_lookup(task_id)
                alive = self._probe.is_alive(pid) if pid is not None else None
                has_artifacts = self._has_artifacts(task_id, active_run)
                if alive is True:
                    # Another live worker still owns it: do not touch.
                    return RecoveryDecision(
                        task_id=task_id,
                        run_id=active_run,
                        action="none",
                        reason="worker pid still alive; leaving Run to its owner",
                        alive=True,
                        has_artifacts=has_artifacts,
                    )
                # Process is gone or unknown.  Never auto-replay unknown side
                # effects: require explicit recovery.
                reason = (
                    "worker process gone after restart; execution interrupted"
                    if alive is False
                    else "worker liveness unknown after restart; not auto-replaying"
                )
                if not self._mark_recovery_required(task_id, active_run, reason):
                    return RecoveryDecision(
                        task_id=task_id, run_id=active_run, action="none",
                        reason="recovery transition could not be persisted; inspect diagnostics",
                        alive=alive, has_artifacts=has_artifacts,
                    )
                self._release_stale_claim(task_id, queue_state)
                return RecoveryDecision(
                    task_id=task_id,
                    run_id=active_run,
                    action="recovery_required",
                    reason=reason,
                    alive=alive,
                    has_artifacts=has_artifacts,
                )

        # A stopped-but-unaccepted Run must not occupy the slot.
        if phase in {
            TaskPhase.AWAITING_ACCEPTANCE.value,
            TaskPhase.PAUSED.value,
            TaskPhase.WAITING_USER.value,
            TaskPhase.RECOVERY_REQUIRED.value,
        }:
            if queue_state == "claimed":
                self._release_stale_claim(task_id, queue_state)
                return RecoveryDecision(
                    task_id=task_id,
                    run_id=(
                        active_run if isinstance(active_run, str) and active_run else None
                    ),
                    action="release_stale_claim",
                    reason=f"{phase} Run must not hold the slot; claim released",
                )
        return None

    def _mark_recovery_required(
        self, task_id: str, run_id: str | None, reason: str
    ) -> bool:
        current = str(self._store.read("task", task_id).entity.get("phase", ""))
        if current == TaskPhase.RECOVERY_REQUIRED.value:
            return True
        try:
            self._writer.transition_task(
                task_id,
                TaskPhase.RECOVERY_REQUIRED,
                run_ref=run_id,
                reason=reason,
            )
        except Exception:  # noqa: BLE001 - preserve state and report the failed write
            self._writer.emit(
                task_id, EventType.ERROR_RECORDED,
                {"mode": "recovery", "code": "recovery_transition_failed",
                 "message": f"could not park phase {current!r} for recovery"},
                task_ref=task_id, run_ref=run_id,
            )
            return False
        self._writer.emit(
            task_id,
            EventType.ERROR_RECORDED,
            {"mode": "recovery", "code": "recovery_required", "message": reason},
            task_ref=task_id,
            run_ref=run_id,
        )
        return True

    def _release_stale_claim(self, task_id: str, queue_state: str) -> None:
        if queue_state != "claimed":
            return
        try:
            self._writer.write_task(
                task_id,
                {
                    "queue": {
                        "state": "not_queued",
                        "owner": None,
                        "lease_expires_at": None,
                    }
                },
            )
        except Exception:  # noqa: BLE001 - leave the claim if we cannot clear it
            return

    def _has_artifacts(self, task_id: str, run_id: str) -> bool | None:
        if self._artifact_root is None:
            return None
        candidate = self._artifact_root / "tasks" / task_id / "artifacts" / run_id
        try:
            if not candidate.is_dir():
                return False
            return any(candidate.iterdir())
        except OSError:
            return None


__all__ = [
    "DefaultProcessProbe",
    "ProcessProbe",
    "RecoveryDecision",
    "RecoveryReport",
    "RecoveryScanner",
]
