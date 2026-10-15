"""Isolated git worktree workspace management (LG-018).

This package implements the *product runtime* isolation contract that
docs/08 §6 and §10 require: parallel code-writing Subtasks must not share a
writable directory.  A file allow-list is not isolation; each write node gets a
real ``git worktree`` checked out at a **frozen base commit** on its own branch,
and only a separate integration worktree merges the candidate branches.

Design boundaries (do not overstate):

* The manager only operates on repositories that already live **inside** the
  authorized workspace root.  Every created path is re-checked with
  ``realpath`` containment and symlink/``.git`` checks; nothing is written
  outside ``<workspace_root>/.lg-worktrees``.
* Git hooks are neutralized for every git invocation
  (``core.hooksPath`` pointed at an empty directory and the ``--no-optional-locks``
  safety flags), and the manager **never** runs user/remote hooks itself.  This
  is a concrete boundary, not a full sandbox: a worktree still shares the
  repository object store and the host environment.
* The child process environment is built from an allow-list, so inherited
  secret environment variables are not forwarded to git.  This bounds *git*
  subprocesses, not the executor's own model/tool subprocesses (that is the
  adapter's/loopback-proxy's responsibility, see docs/08 §8.1).
* This is explicitly **not** a security sandbox for arbitrary untrusted code.
  It gives real write isolation between parallel nodes and preserves the user's
  original HEAD/dirty/untracked state; it does not confine a hostile process.
"""

from .manager import (
    WorktreeManager,
    WorktreeRecord,
    IntegrationResult,
    MergeConflict,
    WorkspaceError,
    GitUnavailable,
)
from .provider import GraphWorkspaceProvider, WorkspaceProvider

__all__ = [
    "WorktreeManager",
    "WorktreeRecord",
    "IntegrationResult",
    "MergeConflict",
    "WorkspaceError",
    "GitUnavailable",
    "GraphWorkspaceProvider",
    "WorkspaceProvider",
]
