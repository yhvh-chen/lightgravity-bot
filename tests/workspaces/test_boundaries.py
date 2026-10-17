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


def test_automatic_task_under_host_repo_gets_independent_empty_base(tmp_path: Path) -> None:
    from gitfixtures import git, init_repo
    from lightgravity.workspaces import GraphWorkspaceProvider

    host = init_repo(tmp_path / "host")
    for name in ("AGENTS.md", "PROJECT.md", "design.md"):
        (host / name).write_text("HOST CANARY: must not enter task\n")
    git(host, "add", "-A")
    git(host, "commit", "-qm", "host canaries")
    host_head = git(host, "rev-parse", "HEAD").strip()
    root = host / "runtime" / "workspaces"
    task = root / "tasks" / "task_new"
    task.mkdir(parents=True)
    manager = WorktreeManager(root)
    assert not manager.is_git_repo(task, scratch=root / ".scratch")
    provider = GraphWorkspaceProvider(manager)
    isolated = provider.isolate(
        task_id="task_new", run_id="run_new", node_key="deliver",
        subtask_id="subtask_new", base_workspace=str(task),
    )
    assert isolated is not None
    worktree = Path(isolated)
    assert git(task, "rev-parse", "--show-toplevel").strip() == str(task)
    assert git(task, "ls-tree", "-r", "--name-only", "HEAD") == ""
    assert git(task, "rev-list", "--count", "HEAD").strip() == "1"
    assert git(task, "rev-parse", "HEAD").strip() != host_head
    assert set(p.name for p in worktree.iterdir()) == {".git"}
    assert git(host, "rev-parse", "HEAD").strip() == host_head
    # A later Run reuses the task's own repository rather than reinitializing.
    second = manager.begin_run("task_new", "run_again", source_repo=task)
    assert second.base_commit == git(task, "rev-parse", "HEAD").strip()


@pytest.mark.parametrize("nonempty", [False, True])
def test_unowned_directory_never_borrows_ancestor_repo(tmp_path: Path, nonempty: bool) -> None:
    from gitfixtures import init_repo

    host = init_repo(tmp_path / "host")
    root = host / "workspace"
    # Even an ancestor inside the authorized root is not the requested repo.
    init_repo(root)
    child = root / ("tasks/task_new" if nonempty else "project-subdirectory")
    child.mkdir(parents=True)
    if nonempty:
        (child / "existing.txt").write_text("preserve me")
    manager = WorktreeManager(root)
    with pytest.raises(WorkspaceError, match="not a git repository root"):
        manager.begin_run("task_new", "run_reject", source_repo=child)
    assert not (child / ".git").exists()
    if nonempty:
        assert (child / "existing.txt").read_text() == "preserve me"


def test_source_symlink_outside_authorized_root_is_rejected(tmp_path: Path) -> None:
    from gitfixtures import init_repo

    outside = init_repo(tmp_path / "outside")
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "project").symlink_to(outside, target_is_directory=True)
    with pytest.raises(WorkspaceError) as excinfo:
        WorktreeManager(root).begin_run("task_new", "run_bad", source_repo=root / "project")
    assert excinfo.value.code is ErrorCode.PATH_OUTSIDE_WORKSPACE


def test_explicit_linked_worktree_root_remains_supported(repo: GitRepo) -> None:
    manager = WorktreeManager(repo.path.parent)
    first = manager.begin_run("task_A", "run_original", source_repo=repo.path)
    linked = first.isolate("deliver", "subtask_A").path
    assert manager.is_git_repo(linked, scratch=manager.worktrees_root / ".probe")
    second = manager.begin_run("task_A", "run_linked", source_repo=linked)
    assert second.base_commit == first.base_commit
    assert (second.isolate("deliver", "subtask_B").path / "README.md").exists()
