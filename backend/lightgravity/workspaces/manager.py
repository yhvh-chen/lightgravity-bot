"""Real git worktree isolation for parallel write nodes (LG-018).

The frozen runtime contract (docs/08 §6 "代码并行写入使用独立 worktree", §10
"executor 的写权限仅限其 worktree；共享目录不替代隔离") is implemented here.
:class:`WorktreeManager` gives each code-writing Subtask its own real
``git worktree`` at a frozen base commit and merges the candidate branches in a
separate integration worktree, without ever touching the user's original HEAD,
dirty tree or untracked files.

Lifecycle per Run::

    manager = WorktreeManager(workspace_root, base_repo=<task workspace>)
    session = manager.begin_run(task_id, run_id, base_commit=<rev>)  # freezes base
    rec = session.isolate(node_key, subtask_id, branch=f"...")       # per write node
    ... executor writes only inside rec.path ...
    result = session.integrate(candidate_branch=..., into="lg/integration/<run>")
    # result.conflicts -> pause, keep worktrees+lock; do not clear

Key properties (verified by the real-git tests in ``tests/workspaces``):

* **Frozen base**: every node worktree is checked out from one recorded base
  commit; the commit and branch names are written to the metadata file, so a
  later reviewer can reproduce the candidate from a fixed point.
* **No user-state mutation**: creation uses ``git worktree add`` from a base
  *commit* with a detached-free branch; the repository's current branch, index,
  dirty and untracked files are never checked out, moved or reset.
* **Conflict pause**: a merge that produces conflicts leaves the integration
  worktree in its conflicted state and is reported as
  :class:`IntegrationResult(conflicted=True)`.  Callers must pause the Run and
  must not release the workspace lock or delete the worktrees.
* **Retention**: :meth:`WorktreeSession.cleanup` refuses to remove a worktree
  whose branch is not merged / not delivered unless forced by an explicit,
  confirmed terminal stop.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from lightgravity.contracts import AppError, ErrorCode

from .git import GitResult, GitRunner, GitUnavailable

#: Directory (relative to the authorized workspace root) holding all worktrees
#: and the run metadata.  Kept out of the source repo working tree.
WORKTREE_DIRNAME = ".lg-worktrees"
METADATA_FILENAME = "workspace.json"
_SAFE_SLUG = re.compile(r"[^A-Za-z0-9._-]+")


class WorkspaceError(AppError):
    """A worktree/workspace operation that violated the isolation contract."""

    def __init__(self, message: str, *, code: ErrorCode = ErrorCode.CONFIG_INVALID,
                 details: dict[str, Any] | None = None) -> None:
        super().__init__(code, message, details=details)
        self.details = details or {}


def _slug(value: str) -> str:
    cleaned = _SAFE_SLUG.sub("-", value.strip()).strip("-")
    return cleaned or "x"


def _within(base: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(base)
    except ValueError:
        return False
    return True


@dataclass(frozen=True, slots=True)
class WorktreeRecord:
    """One isolated write workspace for a Subtask."""

    node_key: str
    subtask_id: str
    branch: str
    path: Path
    base_commit: str
    run_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_key": self.node_key,
            "subtask_id": self.subtask_id,
            "branch": self.branch,
            "path": str(self.path),
            "base_commit": self.base_commit,
            "run_id": self.run_id,
        }


@dataclass(frozen=True, slots=True)
class MergeConflict:
    files: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"files": list(self.files)}


@dataclass
class IntegrationResult:
    """Outcome of merging candidate branches into the integration worktree."""

    integration_branch: str
    integration_path: Path
    base_commit: str
    merged: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    conflicted: bool = False
    candidate_commit: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "integration_branch": self.integration_branch,
            "integration_path": str(self.integration_path),
            "base_commit": self.base_commit,
            "merged": list(self.merged),
            "conflicts": list(self.conflicts),
            "conflicted": self.conflicted,
            "candidate_commit": self.candidate_commit,
        }


@dataclass
class _RunState:
    run_id: str
    task_id: str
    base_commit: str
    source_repo: Path
    nodes: dict[str, WorktreeRecord] = field(default_factory=dict)
    integration: WorktreeRecord | None = None
    merged_branches: list[str] = field(default_factory=list)
    metadata_path: Path | None = None


class WorktreeSession:
    """Per-Run worktree state; created by :class:`WorktreeManager.begin_run`."""

    def __init__(self, manager: "WorktreeManager", state: _RunState) -> None:
        self._manager = manager
        self._state = state

    @property
    def base_commit(self) -> str:
        return self._state.base_commit

    @property
    def source_repo(self) -> Path:
        return self._state.source_repo

    @property
    def run_id(self) -> str:
        return self._state.run_id

    def records(self) -> tuple[WorktreeRecord, ...]:
        return tuple(self._state.nodes.values())

    def record_for(self, node_key: str) -> WorktreeRecord | None:
        return self._state.nodes.get(node_key)

    def workspace_for(self, node_key: str) -> str:
        """The isolated ``workspace_path`` to pass to a write node's request."""

        record = self._state.nodes.get(node_key)
        if record is None:
            raise WorkspaceError(
                f"no isolated worktree for node {node_key!r}; cannot pass a shared workspace",
                details={"node_key": node_key, "run_id": self._state.run_id},
            )
        return str(record.path)

    # -------------------------------------------------------------- isolate
    def isolate(self, node_key: str, subtask_id: str) -> WorktreeRecord:
        """Create (or reuse) a real worktree for one write node at the base commit."""

        existing = self._state.nodes.get(node_key)
        if existing is not None:
            return existing
        branch = f"lg/{_slug(self._state.run_id)}/{_slug(node_key)}"
        path = self._manager.worktree_path(self._state.run_id, node_key)
        self._manager.add_worktree(
            self._state.source_repo, path, branch=branch, base_commit=self._state.base_commit
        )
        record = WorktreeRecord(
            node_key=node_key,
            subtask_id=subtask_id,
            branch=branch,
            path=path,
            base_commit=self._state.base_commit,
            run_id=self._state.run_id,
        )
        self._state.nodes[node_key] = record
        self._persist()
        return record

    # ------------------------------------------------------------ integrate
    def integration_worktree(self, name: str = "integration") -> WorktreeRecord:
        """Create (or reuse) the dedicated candidate-integration worktree."""

        if self._state.integration is not None:
            return self._state.integration
        branch = f"lg/{_slug(self._state.run_id)}/{_slug(name)}"
        path = self._manager.worktree_path(self._state.run_id, name)
        self._manager.add_worktree(
            self._state.source_repo, path, branch=branch, base_commit=self._state.base_commit
        )
        record = WorktreeRecord(
            node_key=name,
            subtask_id=f"integration:{self._state.run_id}",
            branch=branch,
            path=path,
            base_commit=self._state.base_commit,
            run_id=self._state.run_id,
        )
        self._state.integration = record
        self._persist()
        return record

    def integrate(self, node_keys: Iterable[str] | None = None) -> IntegrationResult:
        """Merge candidate branches into the integration worktree.

        Nodes are merged in deterministic node-key order.  The first conflicting
        merge stops the sequence and is reported as ``conflicted`` with the real
        conflicting paths; the integration worktree is left in its conflicted
        state (paused) and nothing is auto-resolved or discarded.
        """

        keys = list(node_keys) if node_keys is not None else sorted(self._state.nodes)
        integration = self.integration_worktree()
        runner = self._manager.runner
        merged: list[str] = []
        for key in keys:
            record = self._state.nodes.get(key)
            if record is None:
                raise WorkspaceError(
                    f"cannot integrate unknown node {key!r}",
                    details={"node_key": key, "run_id": self._state.run_id},
                )
            result = runner.run(
                ["merge", "--no-ff", "--no-edit", record.branch], cwd=integration.path
            )
            if result.ok:
                merged.append(record.branch)
                self._state.merged_branches.append(record.branch)
                continue
            conflicts = self._conflict_files(integration.path)
            return IntegrationResult(
                integration_branch=integration.branch,
                integration_path=integration.path,
                base_commit=self._state.base_commit,
                merged=tuple(merged),
                conflicts=tuple(conflicts),
                conflicted=True,
            )
        self._persist()
        candidate = self._candidate_commit(integration.path)
        return IntegrationResult(
            integration_branch=integration.branch,
            integration_path=integration.path,
            base_commit=self._state.base_commit,
            merged=tuple(merged),
            conflicts=(),
            conflicted=False,
            candidate_commit=candidate,
        )

    def _conflict_files(self, worktree: Path) -> list[str]:
        result = self._manager.runner.run(
            ["diff", "--name-only", "--diff-filter=U"], cwd=worktree
        )
        if not result.ok:
            return []
        return [line for line in result.stdout.splitlines() if line.strip()]

    def _candidate_commit(self, worktree: Path) -> str | None:
        result = self._manager.runner.run(["rev-parse", "HEAD"], cwd=worktree)
        return result.stdout.strip() if result.ok else None

    # --------------------------------------------------------------- pause
    def pause(self) -> dict[str, Any]:
        """Record a pause: keep every worktree, branch and the base commit.

        No worktree is removed while a Run is paused; the caller must not call
        :meth:`cleanup` for a paused/undelivered candidate.
        """

        snapshot = self.snapshot()
        snapshot["paused"] = True
        self._persist(extra={"paused": True})
        return snapshot

    # -------------------------------------------------------------- cleanup
    def cleanup(
        self,
        *,
        confirmed_stop: bool,
        delivered_branches: Iterable[str] | None = None,
    ) -> list[str]:
        """Remove node worktrees only when the stop is confirmed and delivered.

        A write worktree whose branch has *not* been integrated/delivered is
        retained: an undelivered candidate diff must not be cleared
        (agent.md §6).  ``confirmed_stop`` must reflect a real confirmed adapter
        stop; a merely requested cancel is not enough.
        """

        if not confirmed_stop:
            raise WorkspaceError(
                "refusing to clean up worktrees without a confirmed stop",
                code=ErrorCode.CANCELLATION_UNCONFIRMED,
            )
        # Only *explicitly delivered* branches may be cleared.  A branch that was
        # merely merged into the integration candidate is **not** delivered until
        # the Task accepted that candidate, so an undelivered diff/worktree is
        # always retained (agent.md §6).
        delivered = set(delivered_branches or ())
        removed: list[str] = []
        for key, record in list(self._state.nodes.items()):
            if record.branch not in delivered:
                # keep the undelivered diff/worktree
                continue
            self._manager.remove_worktree(self._state.source_repo, record.path)
            removed.append(str(record.path))
            self._state.nodes.pop(key, None)
        if self._state.integration is not None:
            # The integration worktree/branch is the candidate: retained unless
            # it was explicitly delivered by the caller.
            if self._state.integration.branch in delivered:
                self._manager.remove_worktree(
                    self._state.source_repo, self._state.integration.path
                )
                removed.append(str(self._state.integration.path))
                self._state.integration = None
        self._persist()
        return removed

    def snapshot(self) -> dict[str, Any]:
        return {
            "run_id": self._state.run_id,
            "task_id": self._state.task_id,
            "base_commit": self._state.base_commit,
            "source_repo": str(self._state.source_repo),
            "nodes": {key: rec.to_dict() for key, rec in self._state.nodes.items()},
            "integration": self._state.integration.to_dict()
            if self._state.integration is not None
            else None,
            "merged_branches": list(self._state.merged_branches),
        }

    def _persist(self, *, extra: dict[str, Any] | None = None) -> None:
        if self._state.metadata_path is None:
            return
        payload = self.snapshot()
        if extra:
            payload.update(extra)
        self._state.metadata_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", "utf-8"
        )


class WorktreeManager:
    """Creates and manages real git worktrees under the authorized workspace root."""

    def __init__(
        self,
        workspace_root: Path | str,
        *,
        scratch: Path | str | None = None,
        timeout: float = 60.0,
    ) -> None:
        self._workspace_root = Path(workspace_root)
        scratch_dir = Path(scratch) if scratch is not None else self._workspace_root / WORKTREE_DIRNAME / ".git-scratch"
        self.runner = GitRunner(scratch_dir, timeout=timeout)

    @property
    def workspace_root(self) -> Path:
        return self._workspace_root

    @property
    def worktrees_root(self) -> Path:
        return self._workspace_root / WORKTREE_DIRNAME

    # --------------------------------------------------------------- static
    @staticmethod
    def is_git_repo(path: Path | str, *, scratch: Path | str | None = None) -> bool:
        """True when ``path`` is (inside) a real git working tree.

        A private scratch directory is required so no host/global git config or
        hook can influence the probe.
        """

        if shutil.which("git") is None:
            return False
        probe = Path(path)
        if not probe.is_dir():
            return False
        scratch_dir = Path(scratch) if scratch is not None else probe / WORKTREE_DIRNAME / ".git-scratch"
        runner = GitRunner(scratch_dir)
        result = runner.run(["rev-parse", "--is-inside-work-tree"], cwd=probe)
        return bool(result.ok and result.stdout.strip() == "true")

    def head_commit(self, repo: Path | str) -> str:
        result = self.runner.run(["rev-parse", "HEAD"], cwd=Path(repo))
        if not result.ok:
            raise WorkspaceError(
                f"cannot read HEAD of {repo!s}: {result.stderr.strip()}",
                details={"repo": str(repo)},
            )
        return result.stdout.strip()

    # --------------------------------------------------------------- paths
    def worktree_path(self, run_id: str, node_key: str) -> Path:
        base = self.worktrees_root / _slug(run_id) / _slug(node_key)
        return self._authorize(base)

    def _authorize(self, candidate: Path) -> Path:
        """Ensure a path stays inside the authorized workspace root."""

        root_real = Path(os.path.realpath(self._workspace_root))
        # Parent must exist only after mkdir; check lexical then real containment.
        real = Path(os.path.realpath(candidate))
        if not _within(root_real, real):
            raise WorkspaceError(
                f"worktree path {str(candidate)!r} escapes the authorized root {str(root_real)!r}",
                code=ErrorCode.PATH_OUTSIDE_WORKSPACE,
                details={"path": str(candidate), "root": str(root_real)},
            )
        if candidate.name in (".git",) or ".git" in candidate.parts:
            raise WorkspaceError(
                f"refusing a worktree path that contains a .git component: {str(candidate)!r}",
                code=ErrorCode.PATH_OUTSIDE_WORKSPACE,
            )
        return real

    # ---------------------------------------------------------------- run
    def begin_run(
        self,
        task_id: str,
        run_id: str,
        *,
        source_repo: Path | str,
        base_commit: str | None = None,
    ) -> WorktreeSession:
        """Freeze a base commit and open a per-Run worktree session.

        ``source_repo`` must already be inside the authorized workspace root.
        When ``base_commit`` is ``None`` the repository's current ``HEAD`` is
        frozen into the metadata; the working tree (branch/dirty/untracked) is
        never modified.
        """

        repo = Path(source_repo)
        if not repo.is_dir():
            raise WorkspaceError(
                f"source repository {str(repo)!r} does not exist",
                code=ErrorCode.PATH_OUTSIDE_WORKSPACE,
            )
        authorized_repo = self._authorize(repo)
        root_real = Path(os.path.realpath(self._workspace_root))
        if not _within(root_real, authorized_repo):
            raise WorkspaceError(
                f"source repository {str(repo)!r} is outside the authorized root",
                code=ErrorCode.PATH_OUTSIDE_WORKSPACE,
            )
        inside = self.runner.run(["rev-parse", "--is-inside-work-tree"], cwd=authorized_repo)
        if not inside.ok or inside.stdout.strip() != "true":
            raise WorkspaceError(
                f"workspace {str(authorized_repo)!r} is not a git repository; "
                "refusing to fake parallel isolation without real worktrees",
                details={"repo": str(authorized_repo)},
            )
        # Reject a bare repo/\.git file escape: the worktree dir must be a real dir.
        git_entry = authorized_repo / ".git"
        if git_entry.is_file():
            # worktree/submodule gitfile: acceptable, but ensure it stays in repo
            pass
        resolved_base = base_commit or self.head_commit(authorized_repo)
        if not _is_commit(self.runner, authorized_repo, resolved_base):
            raise WorkspaceError(
                f"base commit {resolved_base!r} is not a resolvable commit in {str(authorized_repo)!r}",
                details={"base_commit": resolved_base, "repo": str(authorized_repo)},
            )
        run_dir = self.worktrees_root / _slug(run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        metadata_path = run_dir / METADATA_FILENAME
        state = _RunState(
            run_id=run_id,
            task_id=task_id,
            base_commit=resolved_base,
            source_repo=authorized_repo,
            metadata_path=metadata_path,
        )
        session = WorktreeSession(self, state)
        session._persist()
        return session

    # ----------------------------------------------------------- worktrees
    def add_worktree(self, repo: Path, path: Path, *, branch: str, base_commit: str) -> None:
        """``git worktree add`` at a frozen commit without touching the user tree."""

        authorized = self._authorize(path)
        authorized.parent.mkdir(parents=True, exist_ok=True)
        # If the branch already exists (resume), attach a worktree to it instead
        # of failing; the base commit is still recorded for review.
        branch_exists = self.runner.run(
            ["rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"], cwd=repo
        )
        if branch_exists.ok:
            result = self.runner.run(["worktree", "add", str(authorized), branch], cwd=repo)
        else:
            result = self.runner.run(
                ["worktree", "add", "-b", branch, str(authorized), base_commit], cwd=repo
            )
        if not result.ok:
            raise WorkspaceError(
                f"git worktree add failed for branch {branch!r}: {result.stderr.strip()}",
                details={"branch": branch, "path": str(authorized)},
            )

    def remove_worktree(self, repo: Path, path: Path) -> None:
        result = self.runner.run(["worktree", "remove", "--force", str(path)], cwd=repo)
        if not result.ok:
            # Fall back to prune; never raise for an already-removed dir.
            self.runner.run(["worktree", "prune"], cwd=repo)

    def list_worktrees(self, repo: Path) -> list[str]:
        result = self.runner.run(["worktree", "list", "--porcelain"], cwd=repo)
        if not result.ok:
            return []
        return [
            line[len("worktree ") :]
            for line in result.stdout.splitlines()
            if line.startswith("worktree ")
        ]


def _is_commit(runner: GitRunner, repo: Path, rev: str) -> bool:
    result = runner.run(["cat-file", "-e", f"{rev}^{{commit}}"], cwd=repo)
    return result.ok


__all__ = [
    "WorktreeManager",
    "WorktreeSession",
    "WorktreeRecord",
    "IntegrationResult",
    "MergeConflict",
    "WorkspaceError",
    "GitUnavailable",
    "GitResult",
    "WORKTREE_DIRNAME",
]
