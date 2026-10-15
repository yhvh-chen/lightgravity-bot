#!/usr/bin/env python3
"""LG-023 controlled evaluation: single implementation worker vs team implementation.

Two real code-delivery samples (S1 independent two-file fix, S2 cross-module
dependency handoff) x two arms (A single worker, B two workers with handoff),
once each = 4 attempts.

Arms share **everything** except the number of implementation workers:

* same fixture / same initial git commit / same requirement text;
* same machine acceptance test (``fixtures/<id>/acceptance.py``, never in the
  model context);
* same independent reviewer (the real product ``ModelReviewer`` over the
  program candidate) and the same ``validate_findings`` machine gate;
* same version acceptance gate (awaiting_acceptance + bound accept);
* same SDK (google-antigravity 0.1.22), model (deepseek-v4-flash), permissions,
  and the one shared persistent generation ledger.

The *only* independent variable is the implementation plan:

* arm A -- one write node (``deliver``) covering all files;
* arm B -- two write nodes (``part_a`` -> ``part_b`` dependent) executed by two
  workers with a versioned+hashed artifact handoff.

Both plans are submitted through the **same** product ``PlanValidator``, so each
is a legal, program-validated plan; we never hand-edit control state or bypass
authority.  This is an explicit experimental limitation (see ``PLAN.md`` §3).

Budget: one persistent generation ledger rooted at ``probes/lg023/ledger``
(env ``LIGHTGRAVITY_GENERATION_LEDGER_DIR``), limit 48; a per-attempt guard caps
each attempt at 12.  Every worker/reviewer/repair request is reserved from the
same ledger *before* forwarding.  Unknown usage is reported ``unknown``, never 0.

Usage::

    LIGHTGRAVITY_GENERATION_LEDGER_DIR=... DEEPSEEK_API_KEY=... \
        uv run python probes/lg023/harness/run_attempt.py --sample s1_independent --arm A
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
PROBE = Path(__file__).resolve().parent.parent
FIXTURES = PROBE / "fixtures"
RUNS = PROBE / "runs"
EVIDENCE = PROBE / "evidence"
LEDGER_DIR = os.environ.get("LIGHTGRAVITY_GENERATION_LEDGER_DIR") or str(PROBE / "ledger")

sys.path.insert(0, str(REPO / "backend"))
sys.path.insert(0, str(REPO / "tests" / "coordinator"))
sys.path.insert(0, str(REPO / "tests" / "workspaces"))

from lightgravity.adapter import (  # noqa: E402
    AntigravityExecutor,
    DirectoryArtifactSink,
    InMemoryCredentialResolver,
)
from lightgravity.adapter.proxy import configure_generation_ledger  # noqa: E402
from lightgravity.collaboration import (  # noqa: E402
    ClaimPolicy,
    CollaborationService,
    ExecutionGrantRegistry,
)
from lightgravity.coordinator import (  # noqa: E402
    DispatchContext,
    GraphDispatcher,
    RoleCatalog,
)
from lightgravity.coordinator.planning import PlanningRequest, PlanningTrigger  # noqa: E402
from lightgravity.coordinator.planner import PlanProposal, RawSubtask  # noqa: E402
from lightgravity.coordinator.state import StateWriter  # noqa: E402
from lightgravity.settings import (  # noqa: E402
    ConnectionService,
    FileSecretStore,
    ROLE_REVIEWER,
)
from lightgravity.store import FileStore, new_id  # noqa: E402
from lightgravity.verify.candidate import load_candidate  # noqa: E402
from lightgravity.verify.review import (  # noqa: E402
    ModelReviewer,
    ReviewContext,
    resolve_candidate_evidence,
    resolve_reviewer_support,
    validate_findings,
)
from lightgravity.workspaces import GraphWorkspaceProvider, WorktreeManager  # noqa: E402

CREDENTIAL_REF = "deepseek-api-key"
MODEL = "deepseek-v4-flash"
BASE_URL = "https://api.deepseek.com/v1"
GLOBAL_LIMIT = int(os.environ.get("LG023_GLOBAL_LIMIT", "48"))
ATTEMPT_LIMIT = int(os.environ.get("LG023_ATTEMPT_LIMIT", "12"))
PER_REQUEST_OUTPUT_CAP = 16000
#: Per-worker SDK ceiling. A few turns fit (discover/claim + write); the global
#: hard cap remains the shared ledger.
WORKER_MODEL_CALLS = 6
WORKER_PROXY_CALLS = 6

#: Sample -> (module names, worker objectives).
SAMPLES: dict[str, dict[str, Any]] = {
    "s1_independent": {
        "files": ("src/slugs.py", "src/ranges.py"),
        "objective": (
            "Implement in the workspace: src/slugs.py (slugify) and src/ranges.py "
            "(clamp, in_range). See the acceptance criteria."
        ),
        "acceptance": (
            "slugify lowercases, collapses runs of non-alphanumerics to '-', trims '-'",
            "clamp clamps to [lo, hi]; in_range returns True iff lo <= v <= hi",
        ),
        "write_a": "src/slugs.py",
        "write_b": "src/ranges.py",
    },
    "s2_interface": {
        "files": ("src/geometry.py", "src/report.py"),
        "objective": (
            "Implement in the workspace: src/geometry.py (area, perimeter) and "
            "src/report.py (describe, which depends on geometry). See the acceptance criteria."
        ),
        "acceptance": (
            "area/perimeter support rect{width,height} and circle{radius}, unknown kind raises ValueError",
            "describe(shape) == '<kind>: area=%.2f perimeter=%.2f' and uses geometry",
        ),
        "write_a": "src/geometry.py",
        "write_b": "src/report.py",
    },
}


class _AttemptGuard:
    """Per-attempt secondary cap (12) charged against the same global ledger."""

    def __init__(self, ledger: Any, attempt_limit: int) -> None:
        self._ledger = ledger
        self._limit = attempt_limit
        self._used = 0

    def reserve(self) -> Any:
        if self._used >= self._limit:
            return None
        result = self._ledger.reserve()
        if getattr(result, "granted", False):
            self._used += 1
        return result

    @property
    def used(self) -> int:
        return self._used


class _FrozenPlanner:
    """Deterministic, program-validated plan frozen *before* the attempt.

    Emitted plans are validated by the product ``PlanValidator`` exactly like any
    other proposal.  This is the experimental mechanism that sets the worker
    count; it is not a control-state edit.
    """

    def __init__(self, arm: str, sample: str) -> None:
        self.name = f"frozen-{arm}"
        self._arm = arm
        self._sample = sample

    async def plan(self, context: DispatchContext) -> PlanProposal:
        spec = SAMPLES[self._sample]
        acceptance = tuple(context.acceptance_criteria) or tuple(spec["acceptance"])
        if self._arm == "A":
            subtasks = (
                RawSubtask(
                    key="deliver",
                    objective=context.objective,
                    capability="implementation",
                    acceptance=acceptance,
                    write=True,
                ),
            )
        else:
            subtasks = (
                RawSubtask(
                    key="part_a",
                    objective=(
                        f"First part: create/complete {spec['write_a']} only. "
                        f"Full task: {context.objective}"
                    ),
                    capability="implementation",
                    acceptance=acceptance,
                    write=True,
                ),
                RawSubtask(
                    key="part_b",
                    objective=(
                        f"Second part (depends on part_a): create/complete {spec['write_b']} only, "
                        f"building on the upstream artifact from part_a. "
                        f"Full task: {context.objective}"
                    ),
                    capability="implementation",
                    acceptance=acceptance,
                    depends_on=("part_a",),
                    write=True,
                ),
            )
        return PlanProposal(
            subtasks=subtasks,
            source=f"frozen-{self.name}",
            notes=(f"LG-023 frozen plan for arm {self._arm}",),
        )


def _credential() -> str | None:
    return os.environ.get("DEEPSEEK_API_KEY") or None


def _init_git_repo(root: Path, initial: Path) -> str:
    import shutil

    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "probe@local"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "probe"], check=True)
    shutil.copytree(initial, root, dirs_exist_ok=True)
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", "initial"], check=True)
    head = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    return head


def _build_resources(store: FileStore) -> None:
    def create(kind: str, entity_id: str, fields: dict[str, Any], body: str = "") -> None:
        fields.setdefault("title", entity_id)
        fields.setdefault("enabled", True)
        store.create(kind, entity_id, fields, actor="probe", request_id=f"req-{kind}-{entity_id}")

    create(
        "connection",
        "primary",
        {"backend": "openai-compat", "model": MODEL, "credential_ref": CREDENTIAL_REF, "base_url": BASE_URL},
    )
    create(
        "conversation",
        "worker",
        {"session_continuation_mode": "create_or_resume", "agent_behavior": "autonomous"},
    )
    for tool_id, impl in (("view-file", "view-file"), ("create-file", "create-file")):
        create("tool", tool_id, {"implementation": impl})
    create("skill", "implementation", {"description": "Implementation"}, body="# Impl\n")
    create("skill", "verification", {"description": "Verification"}, body="# Verify\n")
    create(
        "agent",
        "developer",
        {
            "connection_ref": "primary",
            "conversation_ref": "worker",
            "skills": {"source": "inline", "refs": ["implementation"]},
            "tool_refs": ["view-file", "create-file"],
            "hook_refs": [],
            "mcp_refs": [],
            "trigger_refs": [],
            "subagents": [],
        },
        body=(
            "You are one implementation worker. You work ONLY in your own workspace. The program "
            "fixes your identity and you only REQUEST your assigned node. Use as few turns as "
            "possible:\n"
            "1. Call discover_and_request_claim with NO arguments ONCE to list candidates. Each "
            "candidate has `node_ref`, `objective` and `key`.\n"
            "2. Pick the candidate whose `objective` matches YOUR assigned objective and IMMEDIATELY "
            "call discover_and_request_claim with that `node_ref` plus a `request_id`. Do NOT call "
            "discovery again.\n"
            "3. If granted, use view_file/create_file to complete EXACTLY the files named in your "
            "objective, matching the acceptance criteria, then stop. If refused, stop and report.\n"
            "Do not repeat discovery. Do not explore. Never invent a grant or write outside your "
            "workspace."
        ),
    )
    create(
        "agent",
        "verifier",
        {
            "connection_ref": "primary",
            "conversation_ref": "worker",
            "skills": {"source": "inline", "refs": ["verification"]},
            "tool_refs": ["view-file"],
            "hook_refs": [],
            "mcp_refs": [],
            "trigger_refs": [],
            "subagents": [],
        },
        body="You verify only. You do not write files.\n",
    )


def _build_task_run(
    store: FileStore, workspace_ref: str, sample: str, arm: str
) -> tuple[str, str, Any, DispatchContext]:
    from lightgravity.coordinator import RunController

    spec = SAMPLES[sample]
    workspace = store.resolve_path(workspace_ref, write=True)
    Path(workspace).mkdir(parents=True, exist_ok=True)
    task_id = new_id("task")
    run_id = new_id("run")
    objective = spec["objective"]
    acceptance = list(spec["acceptance"])
    store.create(
        "task",
        task_id,
        {
            "title": f"LG-023 {sample} arm {arm}",
            "objective": objective,
            "acceptance_criteria": acceptance,
            "status": "in-progress",
            "phase": "planning",
            "requirements_revision": 1,
            "project_ref": None,
            "repository_ref": None,
            "workspace_ref": workspace_ref,
            "agent_ref": "developer",
            "depends_on": [],
            "active_run": run_id,
            "deliverable_revision": 0,
            "queue": {"state": "not_queued", "order": None, "queued_at": None, "owner": None, "lease_expires_at": None},
            "acceptance": {
                "status": "pending",
                "requirements_revision": None,
                "deliverable_revision": None,
                "evidence_refs": [],
                "decided_at": None,
                "decision_ref": None,
            },
            "budget": {"max_workers": 3, "max_parallel": 1, "max_repair_rounds": 1, "max_collab_requests": 4},
            "checks": ["evidence-present"],
            "archived": False,
        },
        actor="probe",
        request_id=f"req-{task_id}",
        body=f"# {sample} arm {arm}\n",
    )
    store.create(
        "run",
        run_id,
        {
            "task_ref": task_id,
            "attempt": 1,
            "state": "planning",
            "plan_ref": "PLAN.md",
            "plan": None,
            "plan_hash": "a" * 64,
            "plan_source": "rules",
            "team_refs": [],
            "subtask_refs": [],
            "session_refs": [],
            "cleanup": {"status": "pending"},
            "ended_at": None,
            "fail_reason": None,
        },
        actor="probe",
        request_id=f"req-{run_id}",
        body="# Run\n",
    )
    writer = StateWriter(store, actor="probe")
    writer.write_task(task_id, {"active_run": run_id})
    controller = RunController(writer, task_id, run_id)
    context = DispatchContext(
        task_id=task_id,
        run_id=run_id,
        attempt=1,
        objective=objective,
        acceptance_criteria=tuple(acceptance),
        instructions=(
            "Complete the files named in your objective so the acceptance criteria hold. Claim your "
            "node through the program tool; the program owns identity and authorization."
        ),
        workspace_path=str(workspace),
        allowed_tools=("view-file", "create-file"),
        agent_ref="developer",
        budget={
            "max_workers": 3,
            "max_parallel": 1,
            "max_repair_rounds": 1,
            "max_collab_requests": 4,
            "max_model_calls": WORKER_MODEL_CALLS,
            "max_tool_calls": 10,
        },
        planning_request=PlanningRequest(
            trigger=PlanningTrigger.USER_REQUEST, reason="lg023", requested_by="probe", max_calls=1
        ),
        timeout_seconds=110.0,
    )
    return task_id, run_id, controller, context


def _machine_gate(workspace: Path, acceptance_script: Path) -> dict[str, Any]:
    env = {k: v for k, v in os.environ.items() if k not in ("DEEPSEEK_API_KEY",)}
    proc = subprocess.run(
        [sys.executable, str(acceptance_script), "--workspace", str(workspace)],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )
    lines = proc.stdout.strip().splitlines()
    try:
        report = json.loads(lines[-1]) if lines else {}
    except json.JSONDecodeError:
        report = {"raw": proc.stdout, "stderr": proc.stderr}
    report["exit_code"] = proc.returncode
    return report


def _review_sync(store: FileStore, secret_root: Path, task_id: str) -> dict[str, Any]:
    secret_store = FileSecretStore(secret_root)
    service = ConnectionService(store, secret_store=secret_store)
    service.create_connection(
        "reviewer-conn", model=MODEL, base_url=BASE_URL, credential_ref=CREDENTIAL_REF,
        actor="probe", request_id="req-conn",
    )
    service.update_settings(expected_revision=0, actor="probe", default_reviewer_connection_ref="reviewer-conn")
    pinned = service.resolve_default(ROLE_REVIEWER)
    support = resolve_reviewer_support(pinned)
    if support is None:
        return {"status": "unavailable", "reason": "no reviewer support"}
    candidate = load_candidate(store, task_id)
    resolved = resolve_candidate_evidence(store, candidate)
    context = ReviewContext(task_id=task_id, run_id=candidate.run_id, candidate=candidate, store=store, resolved_evidence=resolved)
    reviewer = ModelReviewer(support, service.credential_resolver.resolve, timeout_seconds=120.0, max_model_calls=1)
    report = reviewer.review(context)
    validated = validate_findings(report, candidate=candidate, resolved_evidence=resolved)
    return {
        "status": "ran",
        "requested_model": support.model,
        "reviewer_kind": report.reviewer_kind,
        "outcome": report.outcome,
        "validated_outcome": validated.outcome,
        "findings": [f.to_dict() for f in validated.findings],
        "unsubstantiated": list(validated.unsubstantiated),
        "reason": report.reason[:600],
        "model_calls": reviewer.model_calls,
        "usage": dict(reviewer.last_usage),
        "resolved_evidence": sorted(resolved),
    }


def _accept(store: FileStore, task_id: str, run_id: str) -> dict[str, Any]:
    """Program-side version acceptance gate: only a complete, verified candidate."""

    from lightgravity.verify.candidate import load_candidate

    candidate = load_candidate(store, task_id)
    task = store.read("task", task_id).entity
    phase = str(task.get("phase", ""))
    acceptance = task.get("acceptance") or {}
    bound = (
        acceptance.get("status") == "pending"
        and acceptance.get("requirements_revision") == candidate.requirements_revision
        and acceptance.get("deliverable_revision") == candidate.deliverable_revision
    )
    return {
        "phase": phase,
        "candidate_complete": candidate.complete,
        "candidate_run_matches": candidate.run_id == run_id,
        "acceptance_pending_bound": bound,
        "accept_reachable": phase == "awaiting_acceptance" and bound,
    }


async def _run_attempt(sample: str, arm: str) -> dict[str, Any]:
    credential = _credential()
    if credential is None:
        return {"status": "skipped", "reason": "no credential in env"}

    import tempfile

    os.environ["LIGHTGRAVITY_GENERATION_LEDGER_DIR"] = LEDGER_DIR
    os.environ["LIGHTGRAVITY_MAX_GENERATION_CALLS"] = str(GLOBAL_LIMIT)
    ledger = configure_generation_ledger(LEDGER_DIR, GLOBAL_LIMIT)
    guard = _AttemptGuard(ledger, ATTEMPT_LIMIT)
    # Count *before* forwarding: every reserve increments the attempt guard too.
    _orig_reserve = ledger.reserve

    def _guarded_reserve() -> Any:
        if guard.used >= ATTEMPT_LIMIT:
            return None
        result = _orig_reserve()
        if getattr(result, "granted", False):
            guard._used += 1  # noqa: SLF001
        return result

    ledger.reserve = _guarded_reserve  # type: ignore[method-assign]

    started = time.monotonic()
    out_dir = RUNS / f"{sample}__{arm}"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "raw").mkdir(exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        workspace_root = root / "workspaces"
        workspace_root.mkdir(parents=True, exist_ok=True)
        store = FileStore(root / "data", workspace_root)
        _build_resources(store)
        task_id, run_id, controller, context = _build_task_run(store, "candidate-ws", sample, arm)

        base_repo = root / "base-ws"
        initial_head = _init_git_repo(base_repo, FIXTURES / sample / "initial")

        # The real git candidate workspace starts from the *same* initial commit.
        import shutil

        candidate_ws = workspace_root / "candidate-ws"
        candidate_ws.mkdir(parents=True, exist_ok=True)
        shutil.copytree(FIXTURES / sample / "initial", candidate_ws, dirs_exist_ok=True)

        provider = GraphWorkspaceProvider(WorktreeManager(workspace_root))
        secrets = root / "secrets"
        resolver = InMemoryCredentialResolver({CREDENTIAL_REF: credential})
        from lightgravity.adapter.compiler import ResourceCompiler

        executor = AntigravityExecutor(
            store,
            ResourceCompiler(store),
            credential_resolver=resolver,
            artifacts=DirectoryArtifactSink(root / "artifacts"),
            workspace_root=workspace_root,
            max_proxy_calls=WORKER_PROXY_CALLS,
            model_calls_cap=None,
            upstream_timeout=110.0,
            allow_loopback_upstream=False,
            generation_budget=ledger,
        )
        collaboration = CollaborationService(
            store, policy=ClaimPolicy(enabled=True, lease_seconds=300, collab_requests_enabled=True)
        )
        registry = ExecutionGrantRegistry()
        dispatcher = GraphDispatcher(
            store,
            executor,
            planner=_FrozenPlanner(arm, sample),
            catalog=RoleCatalog({"implementation": ["developer"], "verification": ["verifier"]}),
            max_parallel=1,
            workspaces=provider,
            collaboration=collaboration,
            grant_registry=registry,
            autonomous_claim=True,
        )

        events: list[dict[str, Any]] = []
        request_log: list[dict[str, Any]] = []

        async def emit(event: dict[str, Any]) -> None:
            if str(event.get("type", "")).startswith("adapter."):
                events.append(event)

        _inner = executor.execute

        async def _capture(request: Any, emit_cb: Any) -> Any:
            request_log.append({
                "subtask_id": getattr(request, "subtask_id", None),
                "objective": str(getattr(request, "objective", ""))[:400],
                "upstream_artifact_refs": list(getattr(request, "upstream_artifact_refs", ()) or ()),
                "workspace_path": getattr(request, "workspace_path", None),
            })
            return await _inner(request, emit_cb)

        executor.execute = _capture  # type: ignore[method-assign]
        try:
            outcome = await dispatcher.dispatch(context, controller, emit)
            dispatch_error = None
        except Exception as exc:  # noqa: BLE001
            outcome = None
            dispatch_error = f"{type(exc).__name__}: {exc}"

        machine = _machine_gate(Path(context.workspace_path), FIXTURES / sample / "acceptance.py")
        try:
            review = await asyncio.to_thread(_review_sync, store, secrets, task_id)
        except Exception as exc:  # noqa: BLE001
            review = {"status": "error", "reason": f"{type(exc).__name__}: {exc}"}
        gate = _accept(store, task_id, run_id)

        # Candidate diff vs the initial commit.
        diff = subprocess.run(
            ["git", "-C", str(candidate_ws), "diff", "--no-index", "--", str(FIXTURES / sample / "initial"), str(candidate_ws)],
            capture_output=True, text=True,
        ).stdout

        result = {
            "status": "ran",
            "sample": sample,
            "arm": arm,
            "task_id": task_id,
            "run_id": run_id,
            "initial_head": initial_head,
            "plan_source": getattr(outcome, "summary", None) if outcome else None,
            "dispatcher_state": getattr(outcome, "state", None) if outcome else "error",
            "dispatch_error": dispatch_error,
            "worker_requests": request_log,
            "worker_count": len(request_log),
            "handoff_refs": sorted({r for rec in request_log for r in rec["upstream_artifact_refs"]}),
            "machine_gate": machine,
            "machine_pass": machine.get("passed") == machine.get("total") and machine.get("total", 0) > 0,
            "first_round_machine_pass": None,  # filled below (single dispatch == first round)
            "review": review,
            "acceptance_gate": gate,
            "attempt_generation_requests": guard.used,
            "attempt_limit": ATTEMPT_LIMIT,
            "global_ledger": ledger.snapshot(),
            "elapsed_seconds": round(time.monotonic() - started, 2),
            "per_request_output_cap": PER_REQUEST_OUTPUT_CAP,
            "events_tail": [e.get("type") for e in events][-60:],
        }
        result["first_round_machine_pass"] = result["machine_pass"]
        result["sample_delivered"] = bool(
            result["machine_pass"]
            and str(review.get("validated_outcome", review.get("outcome", ""))) == "passed"
            and gate["accept_reachable"]
        )
        text = json.dumps(result, indent=2, sort_keys=True, default=str)
        (out_dir / "result.json").write_text(text + "\n", encoding="utf-8")
        (out_dir / "raw" / "machine_gate.json").write_text(json.dumps(machine, indent=2), encoding="utf-8")
        (out_dir / "raw" / "review.json").write_text(json.dumps(review, indent=2, default=str), encoding="utf-8")
        (out_dir / "git.txt").write_text(diff, encoding="utf-8")
        (EVIDENCE / f"{sample}__{arm}.json").parent.mkdir(parents=True, exist_ok=True)
        (EVIDENCE / f"{sample}__{arm}.json").write_text(text + "\n", encoding="utf-8")
        print(text)
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", required=True, choices=sorted(SAMPLES))
    ap.add_argument("--arm", required=True, choices=["A", "B"])
    args = ap.parse_args()
    result = asyncio.run(_run_attempt(args.sample, args.arm))
    if isinstance(result, dict) and result.get("status") == "skipped":
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
