#!/usr/bin/env python3
"""LG-010 round-2 model-free repro of the canonical evidence boundary.

No model calls, no network, no product code changes.  Independently exercises
the round-1 rework that fixed blocker 1 (the check treated the executor's
absolute ``diff_ref`` as a workspace-relative path):

* a trusted executor artifact imported via ``import_evidence`` resolves and the
  authorized checks pass;
* a raw absolute ref is rejected (never resolved as a workspace path);
* a ref for another Task is rejected;
* a ref for another Run is rejected;
* an out-of-root / symlink-escape ref is rejected;
* a post-hoc digest tamper is detected.

Run:
    uv run python probes/lg010/lg010_check_repro_r1.py
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "backend"))

from lightgravity.evidence import (  # noqa: E402
    EvidenceRefError,
    canonical_evidence_ref,
    import_evidence,
    resolve_evidence_ref,
)
from lightgravity.verify.candidate import Candidate  # noqa: E402
from lightgravity.verify.checks import (  # noqa: E402
    CheckContext,
    default_check_registry,
    run_checks,
)

AUTHORIZED = ["evidence-present", "artifacts-in-workspace"]


class _FakeStore:
    """Minimal data_dir carrier so checks can resolve the evidence root."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir


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


def _run_checks(workspace: Path, data_dir: Path, refs: tuple[str, ...]) -> dict:
    return run_checks(
        default_check_registry(),
        AUTHORIZED,
        CheckContext(
            task_id="task_repro",
            run_id="run_repro",
            candidate=_candidate(workspace, refs, None),
            store=_FakeStore(data_dir),
            workspace_path=str(workspace),
        ),
    ).to_dict()


def _reject(fn) -> dict:
    try:
        fn()
    except EvidenceRefError as exc:
        return {"rejected": True, "error": str(exc)}
    return {"rejected": False, "error": None}


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="lg010-repro-r1-"))
    data_dir = root / "bot-data"
    workspace = data_dir / "workspaces" / "demo-repo"
    workspace.mkdir(parents=True)
    (workspace / "demo_target.txt").write_text("LG010_REAL_CLOSURE\n", encoding="utf-8")

    # A trusted executor sink artifact (absolute path outside the workspace).
    sink = root / "artifacts" / "run_repro" / "deliver-diff.patch"
    sink.parent.mkdir(parents=True)
    sink.write_text("--- a/demo_target.txt\n+++ b/demo_target.txt\n", encoding="utf-8")

    canonical_ref = import_evidence(
        data_dir, "task_repro", "run_repro", sink, name="subtask_1-deliver-diff.patch"
    )

    report: dict[str, object] = {
        "canonical_ref": canonical_ref,
        "raw_absolute_ref": str(sink),
        "canonical_check": _run_checks(workspace, data_dir, (canonical_ref,)),
        "raw_absolute_check": _run_checks(workspace, data_dir, (str(sink),)),
        "workspace_relative_check": _run_checks(workspace, data_dir, ("demo_target.txt",)),
        "cross_task": _reject(
            lambda: resolve_evidence_ref(
                canonical_ref, data_dir=data_dir, task_id="task_other", run_id="run_repro"
            )
        ),
        "cross_run": _reject(
            lambda: resolve_evidence_ref(
                canonical_ref, data_dir=data_dir, task_id="task_repro", run_id="run_other"
            )
        ),
        "escape_traversal": _reject(
            lambda: resolve_evidence_ref(
                canonical_evidence_ref("run_repro", "..", None),
                data_dir=data_dir,
                task_id="task_repro",
                run_id="run_repro",
            )
        ),
        "no_data_dir": _reject(
            lambda: resolve_evidence_ref(
                canonical_ref, data_dir=None, task_id="task_repro", run_id="run_repro"
            )
        ),
    }

    # Symlink escape: a symlink inside the evidence root pointing outside it.
    evidence_run_dir = data_dir / "tasks" / "task_repro" / "artifacts" / "run_repro"
    outside = root / "outside-secret.txt"
    outside.write_text("secret\n", encoding="utf-8")
    link = evidence_run_dir / "escape.link"
    os.symlink(outside, link)
    report["symlink_escape"] = _reject(
        lambda: resolve_evidence_ref(
            canonical_evidence_ref("run_repro", "escape.link", None),
            data_dir=data_dir,
            task_id="task_repro",
            run_id="run_repro",
        )
    )

    # Digest tamper: rewrite the imported file after it was recorded.
    resolved = resolve_evidence_ref(
        canonical_ref, data_dir=data_dir, task_id="task_repro", run_id="run_repro"
    )
    resolved.write_text("tampered\n", encoding="utf-8")
    report["digest_tamper"] = _reject(
        lambda: resolve_evidence_ref(
            canonical_ref, data_dir=data_dir, task_id="task_repro", run_id="run_repro"
        )
    )
    report["tampered_check"] = _run_checks(workspace, data_dir, (canonical_ref,))

    print(json.dumps(report, indent=2, default=str))
    shutil.rmtree(root, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
