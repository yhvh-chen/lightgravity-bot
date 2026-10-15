#!/usr/bin/env python3
"""LG-018 real-git isolation probe (no model calls).

Builds a genuine temporary git repository, isolates two write nodes into real
worktrees, integrates non-conflicting candidates, then forces a real conflict
and checks the pause/retention behavior.  Emits JSON evidence to stdout and
(optionally) to a file.  This is a *real git* probe, not a mock; the only fake
is the "executor", which here just writes files into its assigned worktree.

Usage:
    uv run python probes/lg018/lg018_worktree_probe.py [--out PATH]
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from lightgravity.workspaces import WorktreeManager  # noqa: E402


def _git(repo: Path, *args: str) -> str:
    env = dict(os.environ)
    env.update(
        {
            "GIT_AUTHOR_NAME": "LG Probe",
            "GIT_AUTHOR_EMAIL": "lg-probe@example.invalid",
            "GIT_COMMITTER_NAME": "LG Probe",
            "GIT_COMMITTER_EMAIL": "lg-probe@example.invalid",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
        }
    )
    proc = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, env=env, timeout=60
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr}")
    return proc.stdout


def _commit(worktree: Path, message: str) -> None:
    env = dict(os.environ)
    env.update(
        {
            "GIT_AUTHOR_NAME": "LG Probe",
            "GIT_AUTHOR_EMAIL": "lg-probe@example.invalid",
            "GIT_COMMITTER_NAME": "LG Probe",
            "GIT_COMMITTER_EMAIL": "lg-probe@example.invalid",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
        }
    )
    for args in (["add", "-A"], ["commit", "-q", "-m", message]):
        proc = subprocess.run(
            ["git", *args], cwd=worktree, capture_output=True, text=True, env=env, timeout=60
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    root = Path(tempfile.mkdtemp(prefix="lg018-probe-"))
    repo = root / "ws" / "project"
    repo.mkdir(parents=True)
    _git(repo, "init", "-q", "-b", "main")
    (repo / "code.txt").write_text("base\n", "utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD").strip()

    manager = WorktreeManager(root / "ws")
    evidence: dict[str, object] = {"base_commit": base, "repo": str(repo)}

    # --- non-conflicting parallel writes ---------------------------------
    session = manager.begin_run("task_probe", "run_ok", source_repo=repo)
    a = session.isolate("write-a", "subtask_a")
    b = session.isolate("write-b", "subtask_b")
    (a.path / "a.txt").write_text("A\n", "utf-8")
    (b.path / "b.txt").write_text("B\n", "utf-8")
    _commit(a.path, "add a")
    _commit(b.path, "add b")
    integration = session.integrate(["write-a", "write-b"])
    evidence["isolated_paths"] = [str(a.path), str(b.path)]
    evidence["distinct_paths"] = str(a.path) != str(b.path)
    evidence["integration"] = integration.to_dict()
    evidence["original_workspace_clean"] = _git(repo, "status", "--porcelain") == ""
    evidence["candidate_is_ancestor_of_base"] = (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", base, integration.candidate_commit or "HEAD"],
            cwd=repo,
            capture_output=True,
        ).returncode
        == 0
    )

    # --- conflicting writes pause and retain ----------------------------
    session2 = manager.begin_run("task_probe", "run_conflict", source_repo=repo)
    a2 = session2.isolate("write-a", "subtask_a")
    b2 = session2.isolate("write-b", "subtask_b")
    (a2.path / "code.txt").write_text("A wins\n", "utf-8")
    (b2.path / "code.txt").write_text("B wins\n", "utf-8")
    _commit(a2.path, "a edits shared")
    _commit(b2.path, "b edits shared")
    conflict = session2.integrate(["write-a", "write-b"])
    session2.pause()
    evidence["conflict"] = conflict.to_dict()
    evidence["conflict_worktrees_retained"] = a2.path.is_dir() and b2.path.is_dir()
    evidence["cleanup_after_unconfirmed"] = None
    evidence["cleanup_kept_undelivered"] = session2.cleanup(confirmed_stop=True) == []

    evidence["passed"] = bool(
        evidence["distinct_paths"]
        and evidence["original_workspace_clean"]
        and evidence["candidate_is_ancestor_of_base"]
        and conflict.conflicted
        and "code.txt" in conflict.conflicts
        and evidence["conflict_worktrees_retained"]
        and evidence["cleanup_kept_undelivered"]
    )

    text = json.dumps(evidence, indent=2, sort_keys=True)
    print(text)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", "utf-8")
    return 0 if evidence["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
