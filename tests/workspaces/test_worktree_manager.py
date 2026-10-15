"""Real-git worktree isolation tests (LG-018).

These exercise the *actual* runtime isolation contract with genuine local git
repositories:

* two parallel write nodes get separate worktrees and their changes do not
  interfere;
* non-conflicting candidate branches merge on an integration branch;
* conflicting candidate branches pause the integration and keep the conflicted
  worktree (no auto-resolution, no cleanup);
* the user's original branch/HEAD/dirty/untracked state is never modified;
* a stop that is not confirmed cannot release worktrees; a confirmed,
  delivered stop can;
* a paused run's worktrees are retained (recovery keeps them);
* the final candidate is bound to the frozen base commit recorded in metadata.

No model is called; all evidence here is real local git, not a mock.
"""

from __future__ import annotations

import json

import pytest

from lightgravity.contracts import ErrorCode
from lightgravity.workspaces import WorkspaceError, WorktreeManager
from lightgravity.workspaces.manager import METADATA_FILENAME, WORKTREE_DIRNAME

from conftest import GitRepo


def manager_for(repo: GitRepo) -> WorktreeManager:
    return WorktreeManager(repo.path.parent)


def test_two_parallel_write_nodes_are_isolated(repo: GitRepo) -> None:
    manager = manager_for(repo)
    session = manager.begin_run("task_A", "run_A", source_repo=repo.path)
    base = session.base_commit
    assert base == repo.head()

    a = session.isolate("write-a", "subtask_a")
    b = session.isolate("write-b", "subtask_b")

    # Real, distinct, existing directories on distinct branches from one base.
    assert a.path != b.path
    assert a.path.is_dir() and b.path.is_dir()
    assert a.path.is_relative_to(manager.worktrees_root)
    assert a.branch != b.branch
    assert a.base_commit == base and b.base_commit == base

    # A writer in node A cannot see node B's uncommitted change, and vice versa.
    (a.path / "from_a.txt").write_text("A\n", "utf-8")
    (b.path / "from_b.txt").write_text("B\n", "utf-8")
    assert not (a.path / "from_b.txt").exists()
    assert not (b.path / "from_a.txt").exists()

    # The user's original working tree is untouched by the worktrees.
    assert repo.current_branch() == "main"
    assert repo.status_porcelain() == ""
    assert not (repo.path / "from_a.txt").exists()


def test_non_conflicting_integration_binds_candidate_to_base(repo: GitRepo) -> None:
    manager = manager_for(repo)
    session = manager.begin_run("task_A", "run_int", source_repo=repo.path)
    base = session.base_commit

    a = session.isolate("write-a", "subtask_a")
    b = session.isolate("write-b", "subtask_b")
    (a.path / "a.txt").write_text("A\n", "utf-8")
    (b.path / "b.txt").write_text("B\n", "utf-8")
    _commit(a.path, "add a")
    _commit(b.path, "add b")

    result = session.integrate(["write-a", "write-b"])
    assert result.conflicted is False
    assert result.conflicts == ()
    assert result.base_commit == base
    assert len(result.merged) == 2
    assert result.candidate_commit  # a real merge commit on the integration branch

    # Integration worktree contains both candidates; base is an ancestor.
    assert (result.integration_path / "a.txt").read_text("utf-8") == "A\n"
    assert (result.integration_path / "b.txt").read_text("utf-8") == "B\n"
    assert _is_ancestor(repo.path, base, result.candidate_commit)

    # Metadata records the frozen base commit + node branches for review.
    metadata = json.loads(
        (manager.worktrees_root / "run_int" / METADATA_FILENAME).read_text("utf-8")
    )
    assert metadata["base_commit"] == base
    assert metadata["nodes"]["write-a"]["branch"] == a.branch
    assert metadata["nodes"]["write-b"]["base_commit"] == base


def test_conflicting_integration_pauses_and_keeps_worktrees(repo: GitRepo) -> None:
    manager = manager_for(repo)
    session = manager.begin_run("task_A", "run_conf", source_repo=repo.path)

    a = session.isolate("write-a", "subtask_a")
    b = session.isolate("write-b", "subtask_b")
    # Both edit the same line -> real merge conflict.
    (a.path / "code.txt").write_text("A wins\n", "utf-8")
    (b.path / "code.txt").write_text("B wins\n", "utf-8")
    _commit(a.path, "a edits shared line")
    _commit(b.path, "b edits shared line")

    result = session.integrate(["write-a", "write-b"])
    assert result.conflicted is True
    assert "code.txt" in result.conflicts
    assert result.merged == (a.branch,)
    assert result.candidate_commit is None

    # Paused: worktrees and the conflicted integration tree are all retained.
    snapshot = session.pause()
    assert snapshot["paused"] is True
    assert (a.path / "code.txt").is_file()
    assert (b.path / "code.txt").is_file()
    assert (result.integration_path / "code.txt").is_file()
    assert session.record_for("write-a") is not None

    # A conflicted candidate is not delivered, so cleanup refuses to remove it.
    removed = session.cleanup(confirmed_stop=True)
    assert removed == []
    assert (a.path / "code.txt").is_file()


def test_dirty_user_head_is_preserved(repo: GitRepo) -> None:
    # Create uncommitted, staged and untracked user state before any worktree.
    (repo.path / "code.txt").write_text("user staged change\n", "utf-8")
    repo.git("add", "code.txt")
    (repo.path / "untracked.txt").write_text("keep me\n", "utf-8")
    branch_before = repo.current_branch()
    head_before = repo.head()

    manager = manager_for(repo)
    session = manager.begin_run("task_A", "run_dirty", source_repo=repo.path)
    rec = session.isolate("write-a", "subtask_a")
    (rec.path / "new.txt").write_text("node change\n", "utf-8")
    _commit(rec.path, "node writes")

    # The user's branch, HEAD, staged change and untracked file are unchanged.
    assert repo.current_branch() == branch_before
    assert repo.head() == head_before
    assert (repo.path / "untracked.txt").read_text("utf-8") == "keep me\n"
    assert (repo.path / "code.txt").read_text("utf-8") == "user staged change\n"
    status = repo.status_porcelain()
    assert "untracked.txt" in status
    assert "code.txt" in status  # staged modification still present


def test_stop_lock_only_releases_on_confirmed_delivered_stop(repo: GitRepo) -> None:
    manager = manager_for(repo)
    session = manager.begin_run("task_A", "run_lock", source_repo=repo.path)
    a = session.isolate("write-a", "subtask_a")
    (a.path / "a.txt").write_text("A\n", "utf-8")
    _commit(a.path, "add a")
    session.integrate(["write-a"])

    # Unconfirmed stop: refuse, keep everything (lock not released).
    with pytest.raises(WorkspaceError) as excinfo:
        session.cleanup(confirmed_stop=False)
    assert excinfo.value.code is ErrorCode.CANCELLATION_UNCONFIRMED
    assert a.path.is_dir()

    # Confirmed stop but undelivered branch: still retained.
    assert session.cleanup(confirmed_stop=True) == []
    assert a.path.is_dir()

    # Confirmed stop with the branch explicitly delivered: now removable.
    removed = session.cleanup(confirmed_stop=True, delivered_branches=[a.branch])
    assert str(a.path) in removed


def test_recovery_keeps_paused_worktrees_and_metadata(repo: GitRepo) -> None:
    manager = manager_for(repo)
    session = manager.begin_run("task_A", "run_rec", source_repo=repo.path)
    a = session.isolate("write-a", "subtask_a")
    (a.path / "partial.txt").write_text("wip\n", "utf-8")  # uncommitted work
    session.pause()

    # A second manager instance (simulating a restart) sees the same worktree.
    reopened = manager_for(repo)
    worktrees = reopened.list_worktrees(repo.path)
    assert str(a.path) in worktrees
    metadata = json.loads(
        (manager.worktrees_root / "run_rec" / METADATA_FILENAME).read_text("utf-8")
    )
    assert metadata["paused"] is True
    assert (a.path / "partial.txt").read_text("utf-8") == "wip\n"


def test_worktree_path_escape_is_rejected(repo: GitRepo) -> None:
    manager = manager_for(repo)
    with pytest.raises(WorkspaceError) as excinfo:
        manager._authorize(repo.path.parent.parent / "outside" / "x")
    assert excinfo.value.code is ErrorCode.PATH_OUTSIDE_WORKSPACE


def test_non_git_workspace_is_refused_not_faked(repo: GitRepo) -> None:
    # A plain directory inside the authorized workspace root but not a git repo.
    plain = repo.path.parent / "not-a-repo"
    plain.mkdir()
    manager = manager_for(repo)
    with pytest.raises(WorkspaceError) as excinfo:
        manager.begin_run("task_A", "run_nogit", source_repo=plain)
    assert "not a git repository" in excinfo.value.message


# --------------------------------------------------------------------- helpers
def _commit(worktree, message: str) -> str:
    import subprocess
    import os

    env = dict(os.environ)
    env.update(
        {
            "GIT_AUTHOR_NAME": "LG Test",
            "GIT_AUTHOR_EMAIL": "lg-test@example.invalid",
            "GIT_COMMITTER_NAME": "LG Test",
            "GIT_COMMITTER_EMAIL": "lg-test@example.invalid",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
        }
    )
    for args in (["add", "-A"], ["commit", "-q", "-m", message]):
        proc = subprocess.run(
            ["git", *args], cwd=worktree, capture_output=True, text=True, env=env, timeout=60
        )
        assert proc.returncode == 0, proc.stderr
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=worktree,
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    ).stdout.strip()


def _is_ancestor(repo, ancestor: str, descendant: str) -> bool:
    import subprocess

    proc = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return proc.returncode == 0
