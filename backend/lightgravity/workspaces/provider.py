"""Workspace isolation provider seam used by the dispatcher (LG-018).

The coordinator/``GraphDispatcher`` must not import git details, and the
``api/bootstrap.py`` assembly point (owned by the integration owner) must be
able to inject the real :class:`~lightgravity.workspaces.manager.WorktreeManager`
without the dispatcher hard-depending on it.  :class:`WorkspaceProvider` is that
minimal seam.

``GraphWorkspaceProvider`` adapts a :class:`WorktreeSession` to the protocol the
dispatcher calls per write node.  It is deliberately small: the dispatcher only
asks "give me the isolated directory for this node, or ``None`` if this
workspace cannot be isolated" — a non-git or unauthorized workspace returns
``None`` so the dispatcher falls back to conservative serial scheduling instead
of faking parallelism (docs/06 §1.1).
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from .manager import WorkspaceError, WorktreeManager, WorktreeSession


@runtime_checkable
class WorkspaceProvider(Protocol):
    """Gives each write node an isolated workspace directory, or ``None``."""

    def isolate(
        self,
        *,
        task_id: str,
        run_id: str,
        node_key: str,
        subtask_id: str,
        base_workspace: str,
    ) -> str | None: ...

    def release(self, *, run_id: str, confirmed_stop: bool) -> list[str]: ...


class GraphWorkspaceProvider:
    """Adapts real :class:`WorktreeManager` sessions to the dispatcher seam."""

    def __init__(
        self,
        manager: WorktreeManager,
        *,
        run_sessions: dict[str, WorktreeSession] | None = None,
    ) -> None:
        self._manager = manager
        self._sessions: dict[str, WorktreeSession] = run_sessions or {}

    @property
    def manager(self) -> WorktreeManager:
        return self._manager

    def session(self, run_id: str) -> WorktreeSession | None:
        return self._sessions.get(run_id)

    def isolate(
        self,
        *,
        task_id: str,
        run_id: str,
        node_key: str,
        subtask_id: str,
        base_workspace: str,
    ) -> str | None:
        """Return an isolated worktree path for a write node, or ``None``.

        ``None`` means the base workspace is not an isolatable git repository
        (or is outside the authorized root).  The dispatcher then keeps the
        conservative single-writer serialization rather than sharing a
        directory between parallel writers.
        """

        base = Path(base_workspace) if base_workspace else None
        if base is None or not base.is_dir():
            return None
        try:
            session = self._sessions.get(run_id)
            if session is None:
                session = self._manager.begin_run(
                    task_id, run_id, source_repo=base
                )
                self._sessions[run_id] = session
            record = session.isolate(node_key, subtask_id)
        except WorkspaceError:
            return None
        return str(record.path)

    def release(self, *, run_id: str, confirmed_stop: bool) -> list[str]:
        session = self._sessions.get(run_id)
        if session is None or not confirmed_stop:
            return []
        try:
            return session.cleanup(confirmed_stop=confirmed_stop)
        except WorkspaceError:
            return []


__all__ = ["WorkspaceProvider", "GraphWorkspaceProvider"]
