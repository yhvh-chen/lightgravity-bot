"""Global, bounded admission for overlapping Tasks (LG-126, docs/08 §19.5).

The governor is deliberately an **in-memory** scheduling aid.  It never writes
Task/Run/Member/Subtask state and it is not a second status source: the Store's
Markdown frontmatter remains authoritative.  It answers four bounded questions
for the coordinator and graph dispatcher:

* may another Task be admitted (``max_active_tasks``)?
* may another live SDK session start (``max_global_sessions``, worker and
  reviewer share this pool)?
* may another reviewer start (``max_reviewer_sessions`` sub-cap)?
* may a write node use the same canonical workspace (cross-Task writer lock)?

A session slot is only returned by the caller after an **actual** stop/cleanup
fact.  An unconfirmed stop therefore keeps its slot and is presented as such by
the read model rather than being silently recycled.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from ..config import (
    DEFAULT_MAX_ACTIVE_TASKS,
    DEFAULT_MAX_GLOBAL_SESSIONS,
    DEFAULT_MAX_PARALLEL_NODES_PER_TASK,
    DEFAULT_MAX_REVIEWER_SESSIONS,
    ENV_MAX_ACTIVE_TASKS,
    ENV_MAX_GLOBAL_SESSIONS,
    ENV_MAX_PARALLEL_NODES_PER_TASK,
    ENV_MAX_REVIEWER_SESSIONS,
    Settings,
)


@dataclass(frozen=True, slots=True)
class CapacityConfig:
    """Validated global capacity values (initial product defaults 2/3/1/2)."""

    max_active_tasks: int = DEFAULT_MAX_ACTIVE_TASKS
    max_global_sessions: int = DEFAULT_MAX_GLOBAL_SESSIONS
    max_reviewer_sessions: int = DEFAULT_MAX_REVIEWER_SESSIONS
    max_parallel_nodes_per_task: int = DEFAULT_MAX_PARALLEL_NODES_PER_TASK

    def __post_init__(self) -> None:
        problems = self.problems()
        if problems:
            from ..store.errors import ConfigInvalid

            raise ConfigInvalid(
                "invalid multi-task capacity configuration",
                diagnostics=[
                    {"code": "capacity_invalid", "location": problem}
                    for problem in problems
                ],
            )

    def problems(self) -> list[str]:
        problems: list[str] = []
        values = {
            ENV_MAX_ACTIVE_TASKS: self.max_active_tasks,
            ENV_MAX_GLOBAL_SESSIONS: self.max_global_sessions,
            ENV_MAX_REVIEWER_SESSIONS: self.max_reviewer_sessions,
            ENV_MAX_PARALLEL_NODES_PER_TASK: self.max_parallel_nodes_per_task,
        }
        for name, value in values.items():
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                problems.append(f"{name} must be an integer >= 1")
        if problems:
            return problems
        if self.max_reviewer_sessions > self.max_global_sessions:
            problems.append(
                f"{ENV_MAX_REVIEWER_SESSIONS} must be <= {ENV_MAX_GLOBAL_SESSIONS}"
            )
        if self.max_active_tasks > self.max_global_sessions - self.max_reviewer_sessions:
            problems.append(
                f"{ENV_MAX_ACTIVE_TASKS} must be <= "
                f"{ENV_MAX_GLOBAL_SESSIONS} - {ENV_MAX_REVIEWER_SESSIONS}"
            )
        return problems

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "CapacityConfig":
        resolved = Settings.from_env(os.environ if env is None else env)
        return cls(
            max_active_tasks=resolved.max_active_tasks,
            max_global_sessions=resolved.max_global_sessions,
            max_reviewer_sessions=resolved.max_reviewer_sessions,
            max_parallel_nodes_per_task=resolved.max_parallel_nodes_per_task,
        )

    def to_dict(self) -> dict[str, int]:
        return {
            "max_active_tasks": self.max_active_tasks,
            "max_global_sessions": self.max_global_sessions,
            "max_reviewer_sessions": self.max_reviewer_sessions,
            "max_parallel_nodes_per_task": self.max_parallel_nodes_per_task,
        }


@dataclass(slots=True)
class SessionLease:
    """One live worker/reviewer SDK session slot."""

    token: int
    kind: str
    task_id: str
    run_id: str | None = None
    node_ref: str | None = None
    released: bool = False


@dataclass(slots=True)
class WriterLease:
    """One cross-Task canonical workspace writer slot."""

    token: int
    task_id: str
    run_id: str
    key: str
    released: bool = False


@dataclass(frozen=True, slots=True)
class CapacitySnapshot:
    """Read-only diagnostic projection (no secrets, no Task state writes)."""

    config: CapacityConfig
    active_tasks: tuple[str, ...]
    sessions: tuple[dict[str, Any], ...]
    reviewer_sessions: int
    writer_locks: dict[str, str]
    admitted_count: int
    session_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "config": self.config.to_dict(),
            "active_tasks": list(self.active_tasks),
            "admitted_count": self.admitted_count,
            "session_count": self.session_count,
            "reviewer_sessions": self.reviewer_sessions,
            "sessions": [dict(item) for item in self.sessions],
            "writer_locks": dict(self.writer_locks),
        }


class CapacityGovernor:
    """In-process admission/session/writer governor shared by all Tasks."""

    def __init__(self, config: CapacityConfig | None = None) -> None:
        self._config = config or CapacityConfig()
        self._active_tasks: dict[str, None] = {}
        self._sessions: dict[int, SessionLease] = {}
        self._reviewers = 0
        self._writers: dict[str, WriterLease] = {}
        self._next_token = 1
        #: Wakes capacity waiters.  Set() is deliberately synchronous: all
        #: mutations happen on the coordinator event loop, so there is no
        #: cross-thread race between a release and a waiter re-check.
        self._changed = asyncio.Event()
        self._waiters = 0

    @property
    def config(self) -> CapacityConfig:
        return self._config

    # ------------------------------------------------------------------ tasks
    def is_admitted(self, task_id: str) -> bool:
        return task_id in self._active_tasks

    def has_active_slot(self) -> bool:
        return len(self._active_tasks) < self._config.max_active_tasks

    def admit_task(self, task_id: str) -> bool:
        """Admit one Task (idempotent).  Never exceeds the global Task cap."""

        if task_id in self._active_tasks:
            return True
        if not self.has_active_slot():
            return False
        self._active_tasks[task_id] = None
        return True

    def release_task(self, task_id: str) -> bool:
        existed = self._active_tasks.pop(task_id, _MISSING) is not _MISSING
        # A Task release can unblock another Task admission and capacity waiters.
        self._changed.set()
        return existed

    # --------------------------------------------------------------- sessions
    def _session_capacity(self, kind: str) -> bool:
        if len(self._sessions) >= self._config.max_global_sessions:
            return False
        if kind == "reviewer" and self._reviewers >= self._config.max_reviewer_sessions:
            return False
        return True

    def try_acquire_session(
        self,
        task_id: str,
        *,
        kind: str = "worker",
        run_id: str | None = None,
        node_ref: str | None = None,
    ) -> SessionLease | None:
        """Non-blocking session acquisition used by the graph scheduler."""

        if not self._session_capacity(kind):
            return None
        lease = SessionLease(
            token=self._next_token,
            kind=kind,
            task_id=task_id,
            run_id=run_id,
            node_ref=node_ref,
        )
        self._next_token += 1
        self._sessions[lease.token] = lease
        if kind == "reviewer":
            self._reviewers += 1
        return lease

    async def acquire_session(
        self,
        task_id: str,
        *,
        kind: str = "worker",
        run_id: str | None = None,
        node_ref: str | None = None,
    ) -> SessionLease:
        """Wait for a session slot (reviewer waits for both global sub-caps)."""

        while True:
            lease = self.try_acquire_session(
                task_id, kind=kind, run_id=run_id, node_ref=node_ref
            )
            if lease is not None:
                return lease
            await self.wait_for_change()

    def release_session(self, lease: SessionLease | None) -> bool:
        if lease is None or lease.released:
            return False
        lease.released = True
        self._sessions.pop(lease.token, None)
        if lease.kind == "reviewer" and self._reviewers > 0:
            self._reviewers -= 1
        self._changed.set()
        return True

    # ---------------------------------------------------------------- writers
    @staticmethod
    def canonical_writer_key(path: str) -> str:
        if not path:
            return ""
        try:
            return os.path.realpath(str(Path(path).expanduser()))
        except OSError:
            return str(path)

    def try_acquire_writer(
        self,
        *,
        task_id: str,
        run_id: str,
        path: str,
        token: int | None = None,
    ) -> WriterLease | None:
        key = self.canonical_writer_key(path)
        if not key:
            return None
        current = self._writers.get(key)
        if current is not None:
            if current.task_id == task_id and current.run_id == run_id:
                return current
            return None
        lease = WriterLease(
            token=token or self._next_token,
            task_id=task_id,
            run_id=run_id,
            key=key,
        )
        if token is None:
            self._next_token += 1
        self._writers[key] = lease
        return lease

    async def acquire_writer(
        self,
        *,
        task_id: str,
        run_id: str,
        path: str,
    ) -> WriterLease:
        while True:
            lease = self.try_acquire_writer(task_id=task_id, run_id=run_id, path=path)
            if lease is not None:
                return lease
            await self.wait_for_change()

    def release_writer(self, lease: WriterLease | None) -> bool:
        if lease is None or lease.released:
            return False
        lease.released = True
        current = self._writers.get(lease.key)
        if current is lease:
            self._writers.pop(lease.key, None)
        self._changed.set()
        return True

    def writer_conflict(self, *, task_id: str, run_id: str, path: str) -> bool:
        key = self.canonical_writer_key(path)
        current = self._writers.get(key)
        return current is not None and not (
            current.task_id == task_id and current.run_id == run_id
        )

    # ------------------------------------------------------------- waiters
    async def wait_for_change(self, timeout: float = 0.25) -> bool:
        """Wait briefly for a release; bounded so cancellation stays prompt."""

        self._changed.clear()
        self._waiters += 1
        try:
            await asyncio.wait_for(self._changed.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False
        finally:
            self._waiters -= 1

    # -------------------------------------------------------------- snapshot
    def snapshot(self) -> CapacitySnapshot:
        sessions: tuple[dict[str, Any], ...] = tuple(
            {
                "token": lease.token,
                "kind": lease.kind,
                "task_id": lease.task_id,
                "run_id": lease.run_id,
                "node_ref": lease.node_ref,
            }
            for lease in sorted(self._sessions.values(), key=lambda item: item.token)
        )
        return CapacitySnapshot(
            config=self._config,
            active_tasks=tuple(sorted(self._active_tasks)),
            sessions=sessions,
            reviewer_sessions=self._reviewers,
            writer_locks={
                key: f"{lease.task_id}:{lease.run_id}"
                for key, lease in sorted(self._writers.items())
            },
            admitted_count=len(self._active_tasks),
            session_count=len(self._sessions),
        )


_MISSING = object()


__all__ = [
    "CapacityConfig",
    "CapacityGovernor",
    "CapacitySnapshot",
    "SessionLease",
    "WriterLease",
]
