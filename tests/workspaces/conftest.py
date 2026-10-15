"""Real local git fixtures for LG-018 worktree isolation tests.

Every fixture builds a genuine on-disk git repository under pytest ``tmp_path``;
no test mocks git or touches the developer's repository, network or a model.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

# Reuse the LG-008 graph test helpers (real Store/Dispatcher setup) without
# duplicating them; pytest prepends each test directory, so add the neighbour.
_COORDINATOR_TESTS = Path(__file__).resolve().parent.parent / "coordinator"
if str(_COORDINATOR_TESTS) not in sys.path:
    sys.path.insert(0, str(_COORDINATOR_TESTS))


def _git(repo: Path, *args: str, env_extra: dict[str, str] | None = None) -> str:
    """Run git in ``repo`` with a deterministic, hook-free identity."""

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
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=60,
    )
    if proc.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def init_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q", "-b", "main")
    (path / "README.md").write_text("# demo repo\n", "utf-8")
    (path / "code.txt").write_text("base\n", "utf-8")
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", "base commit")
    return path


class GitRepo:
    """Small typed wrapper so tests can script real commits."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def git(self, *args: str) -> str:
        return _git(self.path, *args)

    def write(self, relative: str, content: str) -> None:
        target = self.path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, "utf-8")

    def commit_all(self, message: str) -> str:
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)
        return self.head()

    def head(self) -> str:
        return self.git("rev-parse", "HEAD").strip()

    def current_branch(self) -> str:
        return self.git("rev-parse", "--abbrev-ref", "HEAD").strip()

    def status_porcelain(self) -> str:
        return self.git("status", "--porcelain")


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
