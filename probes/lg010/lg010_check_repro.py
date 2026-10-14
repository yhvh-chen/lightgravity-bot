#!/usr/bin/env python3
"""Minimal machine-check reproduction for the LG-010 verification blocker.

No model calls, no network, no product code changes.  It shows that the default
registered check ``artifacts-in-workspace`` treats the executor's absolute
``diff_ref`` (an artifact-sink path outside the Task workspace) as a
workspace-relative artifact and therefore fails, which makes
``VerificationService.verify_and_prepare`` return ``unconfirmed`` and never open
``awaiting_acceptance``.

Run:
    uv run python probes/lg010/lg010_check_repro.py
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "backend"))

from lightgravity.verify.candidate import Candidate  # noqa: E402
from lightgravity.verify.checks import (  # noqa: E402
    CheckContext,
    artifact_path,
    default_check_registry,
    run_checks,
)


def _candidate(workspace: Path, artifacts: tuple[str, ...], diff_ref: str | None) -> Candidate:
    return Candidate(
        task_id="task_repro",
        run_id="run_repro",
        run_state="verifying",
        attempt=1,
        plan_hash="a" * 64,
        requirements_revision=1,
        deliverable_revision=0,
        workspace_ref="demo-repo",
        workspace_path=str(workspace),
        member_refs=("member_1",),
        subtask_refs=("subtask_1",),
        artifact_refs=artifacts,
        diff_ref=diff_ref,
        session_refs=(),
        check_records=(),
    )


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="lg010-repro-"))
    workspace = root / "workspaces" / "demo-repo"
    workspace.mkdir(parents=True)
    (workspace / "demo_target.txt").write_text("LG010_REAL_CLOSURE\n", encoding="utf-8")
    sink_diff = root / "artifacts" / "run_repro" / "lg006-diff.patch"
    sink_diff.parent.mkdir(parents=True)
    sink_diff.write_text("--- a/demo_target.txt\n+++ b/demo_target.txt\n", encoding="utf-8")

    registry = default_check_registry()
    authorized = ["evidence-present", "artifacts-in-workspace"]

    with_diff = _candidate(workspace, ("demo_target.txt", str(sink_diff)), str(sink_diff))
    without_diff = _candidate(workspace, ("demo_target.txt",), None)

    report = {
        "artifact_path_absolute_diff_ref": artifact_path(str(sink_diff)),
        "artifact_path_relative": artifact_path("demo_target.txt"),
        "with_absolute_diff_ref": run_checks(
            registry,
            authorized,
            CheckContext(
                task_id="task_repro",
                run_id="run_repro",
                candidate=with_diff,
                store=None,
                workspace_path=str(workspace),
            ),
        ).to_dict(),
        "without_absolute_diff_ref": run_checks(
            registry,
            authorized,
            CheckContext(
                task_id="task_repro",
                run_id="run_repro",
                candidate=without_diff,
                store=None,
                workspace_path=str(workspace),
            ),
        ).to_dict(),
    }
    print(json.dumps(report, indent=2))
    shutil.rmtree(root, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
