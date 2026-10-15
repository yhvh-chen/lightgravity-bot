"""LG-031 phase3 — real SDK two-worker autonomous closure via the PRODUCT graph.

This closes the exact gap R2 left open.  R2 *bypassed* the product coordinator:
it hand-rolled a pool grant and a ``claim_callback`` in the probe.  Here the
**real product ``GraphDispatcher``** runs with ``autonomous_claim=True`` and a
shared ``ExecutionGrantRegistry``, so the worker's own ``discover_and_request_claim``
tool call is routed through ``GraphDispatcher._claim_for_worker`` - the program
authenticates/validates and atomically grants the fenced lease + node grant.

What is real here (no fake executor, no hand-rolled authority):
* two real ``AntigravityExecutor`` SDK workers, each in its **own real git
  worktree** provisioned by the product ``GraphWorkspaceProvider``;
* the worker autonomously calls the program tool (discovery -> claim request);
* the program's atomic grant + lease/fence;
* a versioned+hashed artifact handoff into the dependent node;
* the final candidate is reviewed by the **real product ModelReviewer**
  (``lightgravity.verify.review.ModelReviewer``) + the machine gate
  (``validate_findings``).

Budget: the single authoritative cap is the LG-022 R2 **persistent generation
ledger** rooted at ``probes/lg031/phase3/ledger`` (env
``LIGHTGRAVITY_GENERATION_LEDGER_DIR``), reserved before every forward, shared by
worker/reviewer/session and durable across restarts.  Unknown usage is reported
as ``unknown`` (never 0).  Credentials are read from the environment only.

Usage::

    LIGHTGRAVITY_GENERATION_LEDGER_DIR=... DEEPSEEK_API_KEY=... \
        uv run python probes/lg031/phase3/real_worker_closure_probe.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "backend"))
sys.path.insert(0, str(REPO / "tests" / "coordinator"))
sys.path.insert(0, str(REPO / "tests" / "workspaces"))

from lightgravity.adapter import (  # noqa: E402
    AntigravityExecutor,
    DirectoryArtifactSink,
    InMemoryCredentialResolver,
)
from lightgravity.adapter.proxy import configure_generation_ledger, global_generation_counter  # noqa: E402
from lightgravity.collaboration import (  # noqa: E402
    ClaimPolicy,
    CollaborationService,
    ExecutionGrantRegistry,
)
from lightgravity.coordinator import (  # noqa: E402
    DispatchContext,
    GraphDispatcher,
    PlanProposal,
    RawSubtask,
    RoleCatalog,
)
from lightgravity.coordinator.planning import PlanningRequest, PlanningTrigger  # noqa: E402
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
OUT = Path(__file__).resolve().parent / "real_worker_closure.json"
LEDGER_DIR = os.environ.get("LIGHTGRAVITY_GENERATION_LEDGER_DIR") or str(
    Path(__file__).resolve().parent / "ledger"
)
MAX_CALLS = int(os.environ.get("LG031_PHASE3_MAX_CALLS", "14"))
PER_REQUEST_OUTPUT_CAP = 12000


def _credential() -> str | None:
    return os.environ.get("DEEPSEEK_API_KEY") or None


def _init_git_repo(root: Path) -> None:
    import subprocess

    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "probe@local"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "probe"], check=True)
    (root / "SEED.md").write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", "seed"], check=True)


class TwoNodePlan:
    """Program-side plan: one produce write node -> one dependent integrate node.

    The plan ``key`` must be a slug (the program validator rejects paths), so the
    worker learns the *file path to create* from the node's **objective** (which
    the program's discovery projection carries as ``candidate.objective``), not
    from ``candidate.key``.  (A R2-style "key == path" fixture bypasses the
    product planner entirely and is exactly the product-path gap phase3 closes.)
    """

    name = "phase3-two-node"

    async def plan(self, context: DispatchContext) -> PlanProposal:
        return PlanProposal(
            subtasks=(
                RawSubtask(
                    key="produce",
                    objective=(
                        "Create the file out/produce.txt with exactly the single line: "
                        "produced"
                    ),
                    capability="implementation",
                    acceptance=("out/produce.txt exists and contains 'produced'",),
                    write=True,
                ),
                RawSubtask(
                    key="integrate",
                    objective=(
                        "Create the file out/integrate.txt with exactly the single line: "
                        "integrated"
                    ),
                    capability="implementation",
                    acceptance=("out/integrate.txt exists and contains 'integrated'",),
                    depends_on=("produce",),
                    write=True,
                ),
            ),
            source="probe",
        )


def _build_resources(store: FileStore) -> None:
    def create(kind: str, entity_id: str, fields: dict[str, Any], body: str = "") -> None:
        fields.setdefault("title", entity_id)
        fields.setdefault("enabled", True)
        store.create(kind, entity_id, fields, actor="probe", request_id=f"req-{kind}-{entity_id}")

    create(
        "connection",
        "primary",
        {
            "backend": "openai-compat",
            "model": MODEL,
            "credential_ref": CREDENTIAL_REF,
            "base_url": BASE_URL,
        },
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
            "You are a worker in a controlled two-worker collaboration. You work ONLY in "
            "your own workspace. The program fixes your identity; you only REQUEST a "
            "node. Steps, in this order, using as few turns as possible:\n"
            "1. Call discover_and_request_claim with NO arguments to list candidates. "
            "Each candidate has `node_ref`, `objective` and `key` (key is a short slug).\n"
            "2. Decide which candidate to claim from its `objective` (the objective names "
            "the exact relative file path you must create). Immediately call "
            "discover_and_request_claim again with that `node_ref` and a `request_id`.\n"
            "3. The program grants or refuses atomically. If granted, use create_file to "
            "write the file named in the objective with EXACTLY the content the "
            "objective names (one line, no extra text), then stop.\n"
            "Do not repeat discovery you already did. Never invent a grant, never reuse "
            "another worker's candidate, never write outside your workspace."
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
    )


def _build_task_run(store: FileStore, workspace_ref: str) -> tuple[str, str, Any, DispatchContext]:
    from lightgravity.coordinator import RunController  # noqa: E402

    workspace = store.resolve_path(workspace_ref, write=True)
    Path(workspace).mkdir(parents=True, exist_ok=True)
    task_id = new_id("task")
    run_id = new_id("run")
    store.create(
        "task",
        task_id,
        {
            "title": "LG-031 phase3 real two-worker autonomous closure",
            "objective": "Two workers autonomously claim and deliver two files.",
            "acceptance_criteria": [
                "out/produce.txt exists and contains 'produced'",
                "out/integrate.txt exists and contains 'integrated'",
            ],
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
            "budget": {
                "max_workers": 3,
                "max_parallel": 2,
                "max_repair_rounds": 1,
                "max_collab_requests": 4,
            },
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
        objective="Two workers autonomously claim and deliver two files.",
        acceptance_criteria=(
            "out/produce.txt exists and contains 'produced'",
            "out/integrate.txt exists and contains 'integrated'",
        ),
        instructions=(
            "Deliver out/produce.txt ('produced') and, after it passes, "
            "out/integrate.txt ('integrated'). Claim your node through the tool."
        ),
        workspace_path=str(workspace),
        allowed_tools=("view-file", "create-file"),
        agent_ref="developer",
        budget={
            "max_workers": 3,
            "max_parallel": 2,
            "max_repair_rounds": 1,
            "max_collab_requests": 4,
            # Per-worker SDK turn headroom only; the REAL hard cap is the shared
            # persistent generation ledger (14).  A too-tight model-call budget
            # (the R2 lesson) starves the write turn, so leave room for
            # discover + claim + write + finish.
            "max_model_calls": 6,
            "max_tool_calls": 8,
        },
        planning_request=PlanningRequest(
            trigger=PlanningTrigger.USER_REQUEST,
            reason="phase3",
            requested_by="probe",
            max_calls=1,
        ),
        timeout_seconds=110.0,
    )
    return task_id, run_id, controller, context


def _review_sync(store: FileStore, secret_root: Path, task_id: str) -> dict[str, Any]:
    secret_store = FileSecretStore(secret_root)
    service = ConnectionService(store, secret_store=secret_store)
    service.create_connection(
        "reviewer-conn",
        model=MODEL,
        base_url=BASE_URL,
        credential_ref=CREDENTIAL_REF,
        actor="probe",
        request_id="req-conn",
    )
    service.update_settings(
        expected_revision=0,
        actor="probe",
        default_reviewer_connection_ref="reviewer-conn",
    )
    pinned = service.resolve_default(ROLE_REVIEWER)
    support = resolve_reviewer_support(pinned)
    if support is None:
        return {"status": "unavailable", "reason": "no reviewer support"}
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
        service.credential_resolver.resolve,
        timeout_seconds=120.0,
        max_model_calls=1,
    )
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


async def _main() -> int:
    credential = _credential()
    if credential is None:
        print(json.dumps({"status": "skipped", "reason": "no credential in env"}))
        return 0

    import tempfile

    # Persistent, restart-durable generation ledger (single authoritative cap).
    os.environ["LIGHTGRAVITY_GENERATION_LEDGER_DIR"] = LEDGER_DIR
    os.environ["LIGHTGRAVITY_MAX_GENERATION_CALLS"] = str(MAX_CALLS)
    before = configure_generation_ledger(LEDGER_DIR, MAX_CALLS)

    started_all = time.monotonic()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        workspace_root = root / "workspaces"
        workspace_root.mkdir(parents=True, exist_ok=True)
        store = FileStore(root / "data", workspace_root)
        _build_resources(store)
        task_id, run_id, controller, context = _build_task_run(store, "candidate-ws")

        # Real git base + the product worktree provider (real per-node worktrees).
        base_repo = root / "base-ws"
        _init_git_repo(base_repo)
        provider = GraphWorkspaceProvider(WorktreeManager(workspace_root))

        secrets = root / "secrets"
        resolver = InMemoryCredentialResolver({CREDENTIAL_REF: credential})
        executor = AntigravityExecutor(
            store,
            __import__("lightgravity.adapter.compiler", fromlist=["ResourceCompiler"]).ResourceCompiler(store),
            credential_resolver=resolver,
            artifacts=DirectoryArtifactSink(root / "artifacts"),
            workspace_root=workspace_root,
            max_proxy_calls=6,
            model_calls_cap=None,
            upstream_timeout=110.0,
            allow_loopback_upstream=False,
            generation_budget=before,
        )

        collaboration = CollaborationService(
            store,
            policy=ClaimPolicy(enabled=True, lease_seconds=300, collab_requests_enabled=True),
        )
        registry = ExecutionGrantRegistry()
        dispatcher = GraphDispatcher(
            store,
            executor,
            catalog=RoleCatalog({"implementation": ["developer"], "verification": ["verifier"]}),
            planner=TwoNodePlan(),  # type: ignore[arg-type]
            max_parallel=1,
            workspaces=provider,
            collaboration=collaboration,
            grant_registry=registry,
            autonomous_claim=True,
        )

        events: list[dict[str, Any]] = []

        async def emit(event: dict[str, Any]) -> None:
            # Keep the full autonomous claim chain (real model -> program tool ->
            # result) plus session lifecycle; this is the hard-condition evidence
            # that the *worker itself* drove discovery/claim.
            if str(event.get("type", "")).startswith("adapter."):
                events.append(event)

        outcome = await dispatcher.dispatch(context, controller, emit)

        # Extract the worker-initiated claim chain from the real event stream.
        claim_chain: list[dict[str, Any]] = []
        for event in events:
            etype = event.get("type")
            if etype in {"adapter.tool_call", "adapter.tool_result"}:
                name = str(event.get("name"))
                if name == "discover_and_request_claim":
                    claim_chain.append(
                        {
                            "type": etype,
                            "name": name,
                            "args": event.get("args"),
                            "status": event.get("status"),
                            "error": event.get("error"),
                        }
                    )

        # Snapshot the documented handoff from the produced run (the program
        # recorded the dependent node's upstream handoff in its subtask history).
        handoffs: list[str] = []
        subtasks_dir = store.data_dir / "subtasks"
        integrate_ids = [
            p.stem
            for p in subtasks_dir.glob("*.md")
            if "integrate" in p.read_text(encoding="utf-8")
        ]
        for sub_id in integrate_ids:
            entity = store.read("subtask", sub_id).entity
            handoffs.extend(entity.get("upstream_artifact_refs", []) or [])

        # Independent, real ModelReviewer over the program-produced candidate.
        review = await asyncio.to_thread(_review_sync, store, secrets, task_id)

        # ``AntigravityExecutor.execute`` already closes each session and stops
        # its loopback proxy in its ``finally`` (the confirmed-stop fact); there
        # is no bulk ``close`` to call, so we do not fake one here.

        result = {
            "status": "ran",
            "dispatcher_outcome": outcome.state,
            "dispatcher_summary": outcome.summary,
            "task_id": task_id,
            "run_id": run_id,
            "real_workers": 2,
            "autonomous_claim_tool_router": "GraphDispatcher._claim_for_worker",
            "autonomous_claim_chain": claim_chain,
            "handoff_refs": sorted(set(handoffs)),
            "review": review,
            "generation_ledger": before.snapshot(),
            "max_real_calls_budget": MAX_CALLS,
            "per_request_output_cap": PER_REQUEST_OUTPUT_CAP,
            "elapsed_seconds": round(time.monotonic() - started_all, 2),
            "adapter_events": [
                e.get("type") for e in events
            ][:60],
        }
        text = json.dumps(result, indent=2, sort_keys=True)
        print(text)
        OUT.write_text(text + "\n", encoding="utf-8")
        print(f"wrote {OUT}")
        print(f"ledger snapshot: {before.snapshot()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
