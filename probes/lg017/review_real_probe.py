"""LG-017 R1 real-model reviewer probe (gated; NOT a pytest test).

Runs ONE real, minimal, tool-less SDK review turn on the DeepSeek connection
via `run_review_turn`, against a temporary, self-contained candidate with real
resolvable workspace evidence.  It records whether the real model returned a
program-validatable verdict and the real usage counters.

Budget (this package): <= 2 real DeepSeek calls total, <= 8000 output tokens,
one call <= 120s, no API retries.  The credential comes from the process
environment only and is never printed or written.

Usage::

    DEEPSEEK_API_KEY=... uv run python probes/lg017/review_real_probe.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))

from lightgravity.adapter.credentials import EnvCredentialResolver  # noqa: E402
from lightgravity.coordinator.state import StateWriter  # noqa: E402
from lightgravity.store import FileStore, new_id  # noqa: E402
from lightgravity.verify.candidate import load_candidate  # noqa: E402
from lightgravity.verify.review import (  # noqa: E402
    ModelReviewer,
    ReviewContext,
    ReviewerSupport,
    resolve_candidate_evidence,
    validate_findings,
)

CREDENTIAL_REF = "deepseek-api-key"
MODEL = "deepseek-v4-flash"
BASE_URL = "https://api.deepseek.com/v1"
OUT = Path(__file__).resolve().parent / "review_real_probe.json"
MAX_REAL_CALLS = int(os.environ.get("LG017_PROBE_MAX_CALLS", "1"))


def _build_candidate(root: Path) -> tuple[FileStore, str]:
    data = root / "data"
    workspace_root = data / "workspaces"
    store = FileStore(data, workspace_root)
    task_id = new_id("task")
    run_id = new_id("run")
    subtask_id = new_id("subtask")
    writer = StateWriter(store, actor="probe")
    store.create(
        "task",
        task_id,
        {
            "title": "LG-017 real reviewer probe",
            "objective": (
                "Deliver a single text file out/result.txt whose content is exactly "
                "'hello review'."
            ),
            "acceptance_criteria": ["out/result.txt exists and contains 'hello review'"],
            "status": "in-progress",
            "phase": "verifying",
            "requirements_revision": 1,
            "project_ref": None,
            "repository_ref": None,
            "workspace_ref": "probe-ws",
            "agent_ref": "developer",
            "depends_on": [],
            "active_run": run_id,
            "deliverable_revision": 0,
            "queue": {
                "state": "not_queued",
                "order": None,
                "queued_at": None,
                "owner": None,
                "lease_expires_at": None,
            },
            "acceptance": {
                "status": "pending",
                "requirements_revision": None,
                "deliverable_revision": None,
                "evidence_refs": [],
                "decided_at": None,
                "decision_ref": None,
            },
            "budget": {"max_workers": 3, "max_parallel": 1, "max_repair_rounds": 1},
            "checks": ["evidence-present"],
            "archived": False,
        },
        actor="probe",
        request_id=f"req-{task_id}",
        body="# Probe task\n",
    )
    store.create(
        "run",
        run_id,
        {
            "task_ref": task_id,
            "attempt": 1,
            "state": "verifying",
            "plan_ref": "PLAN.md",
            "plan": None,
            "plan_hash": "a" * 64,
            "plan_source": "rules",
            "team_refs": [],
            "subtask_refs": [subtask_id],
            "session_refs": [],
            "cleanup": {"status": "pending"},
            "ended_at": None,
            "fail_reason": None,
        },
        actor="probe",
        request_id=f"req-{run_id}",
        body="# Run\n",
    )
    store.create(
        "subtask",
        subtask_id,
        {
            "run_ref": run_id,
            "state": "passed",
            "depends_on": [],
            "assignee_member_ref": None,
            "upstream_artifact_refs": [],
            "objective": "deliver out/result.txt",
            "capability": "implementation",
            "key": "deliver",
            "write": True,
            "config_hash": None,
            "fail_reason": None,
            "blocked_by": [],
            "acceptance": {
                "status": "passed",
                "criteria": ["it works"],
                "evidence_refs": ["out/result.txt"],
            },
        },
        actor="probe",
        request_id=f"req-{subtask_id}",
        body="# Subtask\n",
    )
    write_run = writer.write_run
    write_run(run_id, {"team_refs": [], "subtask_refs": [subtask_id]})
    # Real, authorized workspace evidence the candidate declares.
    ws = workspace_root / "probe-ws"
    (ws / "out").mkdir(parents=True, exist_ok=True)
    (ws / "out" / "result.txt").write_text("hello review\n", encoding="utf-8")
    return store, task_id


def main() -> int:
    resolver = EnvCredentialResolver()
    if resolver.resolve(CREDENTIAL_REF) is None:
        print(json.dumps({"status": "skipped", "reason": "no credential in env"}))
        return 0
    support = ReviewerSupport(model=MODEL, base_url=BASE_URL, credential_ref=CREDENTIAL_REF)
    with tempfile.TemporaryDirectory() as tmp:
        store, task_id = _build_candidate(Path(tmp))
        candidate = load_candidate(store, task_id)
        resolved = resolve_candidate_evidence(store, candidate)
        context = ReviewContext(
            task_id=task_id,
            run_id=candidate.run_id,
            candidate=candidate,
            store=store,
            resolved_evidence=resolved,
        )
        reviewer = ModelReviewer(
            support,
            resolver.resolve,
            timeout_seconds=120.0,
            max_model_calls=min(MAX_REAL_CALLS, 1),
        )
        report = reviewer.review(context)
        validated = validate_findings(
            report, candidate=candidate, resolved_evidence=resolved
        )
        result = {
            "status": "ran",
            "requested_model": MODEL,
            "reviewer": report.reviewer,
            "reviewer_kind": report.reviewer_kind,
            "outcome": report.outcome,
            "validated_outcome": validated.outcome,
            "findings": [f.to_dict() for f in validated.findings],
            "unsubstantiated": list(validated.unsubstantiated),
            "reason": report.reason[:500],
            "model_calls": reviewer.model_calls,
            "usage": dict(reviewer.last_usage),
            "last_error": (reviewer.last_error or "")[:500],
            "resolved_evidence": sorted(resolved),
        }
        text = json.dumps(result, indent=2, sort_keys=True)
        print(text)
        OUT.write_text(text + "\n", encoding="utf-8")
        print(f"wrote {OUT}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
