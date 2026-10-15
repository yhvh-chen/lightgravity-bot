"""Real local git fixtures for LG-018 worktree isolation tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from gitfixtures import GitRepo, init_repo


@pytest.fixture
def repo(tmp_path: Path) -> GitRepo:
    root = tmp_path / "ws"
    path = init_repo(root / "project")
    return GitRepo(path)


@pytest.fixture
def task_repo(tmp_path: Path) -> GitRepo:
    """A git repo at ``<workspace_root>/task-ws`` matching ``make_dispatch_setup``."""

    root = tmp_path / "ws"
    path = init_repo(root / "task-ws")
    return GitRepo(path)
