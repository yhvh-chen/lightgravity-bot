"""Boundary tests for worktree isolation (LG-018).

These assert concrete, honest boundaries rather than claiming a full sandbox:

* a repository hook placed in the source repo's ``.git/hooks`` is **not**
  executed by the manager's git invocations (``core.hooksPath`` is redirected);
* an inherited secret environment variable is **not** forwarded to the git
  subprocess;
* a worktree path containing a ``.git`` component is rejected;
* a symlink that escapes the authorized root is rejected.

A worktree still shares the repository object store and the host process, so
this is write isolation, not untrusted-code confinement.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from lightgravity.contracts import ErrorCode
from lightgravity.workspaces import WorkspaceError, WorktreeManager
from lightgravity.workspaces.git import GitRunner

from gitfixtures import GitRepo


def test_repo_hooks_are_not_executed(repo: GitRepo, tmp_path: Path) -> None:
    marker = tmp_path / "HOOK_RAN"
    hooks_dir = repo.path / ".git" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook = hooks_dir / "post-checkout"
    hook.write_text(f"#!/bin/sh\ntouch {marker}\n", "utf-8")
    hook.chmod(hook.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    manager = WorktreeManager(repo.path.parent)
    session = manager.begin_run("task_A", "run_hook", source_repo=repo.path)
    session.isolate("write-a", "subtask_a")

    assert not marker.exists(), "a repository hook must not run during worktree creation"


def test_inherited_secret_env_is_not_forwarded(repo: GitRepo, monkeypatch) -> None:
    monkeypatch.setenv("LG_TEST_SECRET_KEY", "super-secret-value")
    runner = GitRunner(repo.path.parent / ".lg-worktrees" / ".git-scratch")
    # ``git config --get-regexp`` would print an injected config; instead check
    # the child environment cannot see the secret via a tiny hook-free command
    # that echoes the environment through git's own alias-free path is awkward,
    # so we assert the allow-list directly through the runner's construction.
    from lightgravity.workspaces.git import _child_env

    env = _child_env(runner._scratch / "home", runner.hooks_dir)
    assert "LG_TEST_SECRET_KEY" not in env
    assert env["GIT_CONFIG_NOSYSTEM"] == "1"
    assert env["GIT_CONFIG_GLOBAL"].endswith("gitconfig")


def test_dot_git_component_path_is_rejected(repo: GitRepo) -> None:
    manager = WorktreeManager(repo.path.parent)
    with pytest.raises(WorkspaceError) as excinfo:
        manager._authorize(manager.worktrees_root / "run_x" / ".git" / "evil")
    assert excinfo.value.code is ErrorCode.PATH_OUTSIDE_WORKSPACE


def test_symlink_escape_is_rejected(repo: GitRepo, tmp_path: Path) -> None:
    manager = WorktreeManager(repo.path.parent)
    outside = tmp_path / "outside-target"
    outside.mkdir()
    link = manager.worktrees_root / "run_x" / "escape"
    link.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(outside, link)

    with pytest.raises(WorkspaceError) as excinfo:
        manager._authorize(link)
    assert excinfo.value.code is ErrorCode.PATH_OUTSIDE_WORKSPACE
