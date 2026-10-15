"""LG-031 phase4 — one complete real product closure via the REAL program planner.

phase3 injected a two-write-node plan as if it were the model planner, so it never
exercised the product-side ``RuleBasedPlanner`` (the default, model-free plan
builder) and its real chain starved: the *produce* worker spent its whole
per-worker turn budget on repeated discovery, and the dependent worker never ran.

phase4 fixes the two real causes and drives the unmodified product path:

1. **Real planner** — no ``planner=`` injection; the product ``RuleBasedPlanner``
   builds ``deliver`` (write) -> ``verify`` (dependent, read-only).  Workers learn
   their node from the program-owned ``objective`` projection, never the slug.
2. **Aligned ceilings** — the per-session loopback proxy cap now honours the
   frozen per-request ``budget.max_model_calls`` (see ``adapter/executor.py``), so
   the SDK budget reports a clean stop instead of an opaque proxy 429.

What is real (no fake executor, no hand-rolled authority, no injected plan):
* real ``AntigravityExecutor`` SDK workers through the loopback auth proxy to
  DeepSeek, the ``deliver`` worker inside its own real git worktree;
* workers autonomously calling the program's restricted discover/claim tool; the
  program authenticates/validates and atomically grants the fenced lease;
* a versioned+hashed artifact handoff into the dependent node;
* the real product ``ModelReviewer`` (``lightgravity.verify.review``) over the
  program candidate + the ``validate_findings`` machine gate.

Budget: the single authoritative cap is the LG-022 R2 **persistent generation
ledger** rooted at ``probes/lg031/phase4/ledger`` (env
``LIGHTGRAVITY_GENERATION_LEDGER_DIR``), reserved before every forward, shared by
worker/reviewer/session and durable across restarts.  Unknown usage is reported as
``unknown`` (never 0).  Credentials are read from the environment only.  This
probe is written to be run **once** per phase4 attempt: it records the honest
outcome and never re-runs the fixture on failure.

Usage::

    LIGHTGRAVITY_GENERATION_LEDGER_DIR=... DEEPSEEK_API_KEY=... \
        uv run python probes/lg031/phase4/real_worker_closure_probe.py
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
EVIDENCE_OUT = Path(__file__).resolve().parent / "evidence" / "run_real_worker_closure.json"
LEDGER_DIR = os.environ.get("LIGHTGRAVITY_GENERATION_LEDGER_DIR") or str(
    Path(__file__).resolve().parent / "ledger"
)
MAX_CALLS = int(os.environ.get("LG031_PHASE4_MAX_CALLS", "16"))
PER_REQUEST_OUTPUT_CAP = 12000
#: Per-worker ceilings.  The SDK budget and the loopback proxy are aligned so the
#: SDK's ``BudgetConfig`` halts cleanly; a 3-step deliver (discover -> claim ->
#: write -> finish) fits comfortably.  The *global* hard cap remains the ledger.
WORKER_MODEL_CALLS = 6
WORKER_PROXY_CALLS = 6


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
            "You are one worker in a controlled two-worker collaboration. You work ONLY in "
            "your own workspace. The program fixes your identity; you only REQUEST a node. "
            "Your assigned objective is in the user message and it names the exact relative "
            "file path you must create. Use as few turns as possible:\n"
            "1. Call discover_and_request_claim with NO arguments ONCE to list candidates. "
            "Each candidate has `node_ref`, `objective` and `key` (key is a short slug).\n"
            "2. Pick the candidate whose `objective` matches YOUR objective, and IMMEDIATELY "
            "call discover_and_request_claim with that `node_ref` plus a `request_id`. Do "
            "NOT call discovery again afterwards.\n"
            "3. If the program grants it, call create_file ONCE to write the file named in "
            "the objective with EXACTLY the one-line content the objective names, then stop. "
            "If the program refuses, stop and report the refusal.\n"
            "Do not repeat discovery. Do not explore. Never invent a grant, never reuse "
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
        body=(
            "You are the verification worker of a controlled collaboration. You work ONLY in "
            "your workspace and you do not write files. The program fixes your identity; you "
            "only REQUEST your assigned node. Use as few turns as possible:\n"
            "1. Call discover_and_request_claim with NO arguments ONCE to list candidates.\n"
            "2. Pick the candidate whose `objective` matches YOUR objective (it embeds the "
            "deliver objective) and IMMEDIATELY call discover_and_request_claim with that "
            "`node_ref` plus a `request_id`. Do NOT call discovery again afterwards.\n"
            "3. Use view_file to inspect the upstream artifact named in the user message / "
            "objective, then state whether it satisfies the acceptance criteria, then stop. "
            "If the program refuses your claim, stop and report the refusal."
        ),
    )


def _build_task_run(store: FileStore, workspace_ref: str) -> tuple[str, str, Any, DispatchContext]:
    from lightgravity.coordinator import RunController

    workspace = store.resolve_path(workspace_ref, write=True)
    Path(workspace).mkdir(parents=True, exist_ok=True)
    task_id = new_id("task")
    run_id = new_id("run")
    objective = "Create the file out/deliver.txt with exactly the single line: delivered"
    acceptance = ["out/deliver.txt exists and contains 'delivered'"]
    store.create(
        "task",
        task_id,
        {
            "title": "LG-031 phase4 real product closure (real program planner)",
            "objective": objective,
            "acceptance_criteria": list(acceptance),
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
                "max_parallel": 1,
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
        objective=objective,
        acceptance_criteria=tuple(acceptance),
        instructions=(
            "Deliver out/deliver.txt with the single line 'delivered'. Claim your node "
            "through the program tool; the program owns identity and authorization."
        ),
        workspace_path=str(workspace),
        allowed_tools=("view-file", "create-file"),
        agent_ref="developer",
        budget={
            "max_workers": 3,
            "max_parallel": 1,
            "max_repair_rounds": 1,
            "max_collab_requests": 4,
            # Per-node SDK turn budget; the loopback proxy is aligned to the same
            # value (phase4 fix).  A 3-step deliver fits; the global hard cap is
            # the persistent ledger.
            "max_model_calls": WORKER_MODEL_CALLS,
            "max_tool_calls": 8,
        },
        planning_request=PlanningRequest(
            trigger=PlanningTrigger.USER_REQUEST,
            reason="phase4",
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
            max_proxy_calls=WORKER_PROXY_CALLS,
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
        # NOTE: no ``planner=`` -- the real, model-free ``RuleBasedPlanner`` is the
        # product default and produces deliver -> verify.
        dispatcher = GraphDispatcher(
            store,
            executor,
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

        # Wrap the executor so the probe can record, per node, the exact
        # objective and the upstream handoff the program handed the worker.
        _inner_execute = executor.execute

        async def _capturing_execute(request: Any, emit_cb: Any) -> Any:
            request_log.append(
                {
                    "subtask_id": getattr(request, "subtask_id", None),
                    "objective": getattr(request, "objective", None),
                    "upstream_artifact_refs": list(
                        getattr(request, "upstream_artifact_refs", ()) or ()
                    ),
                    "workspace_path": getattr(request, "workspace_path", None),
                    "has_claim_tool": any(
                        getattr(t, "__name__", "") == "discover_and_request_claim"
                        for t in getattr(request, "custom_tools", ()) or ()
                    ),
                }
            )
            return await _inner_execute(request, emit_cb)

        executor.execute = _capturing_execute  # type: ignore[method-assign]
        outcome = await dispatcher.dispatch(context, controller, emit)

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

        # Extract the program-recorded dependency handoff.  Subtask entities live
        # at ``data/subtasks/<id>/SUBTASK.md`` (a subdirectory per entity), so glob
        # one level down -- phase3's probe globbed ``subtasks/*.md`` and silently
        # missed every handoff even when the product recorded one.
        handoffs: list[str] = []
        subtasks_dir = store.data_dir / "subtasks"
        if subtasks_dir.is_dir():
            for sub_dir in sorted(subtasks_dir.iterdir()):
                subtask_md = sub_dir / "SUBTASK.md"
                if subtask_md.is_file():
                    entity = store.read("subtask", sub_dir.name).entity
                    handoffs.extend(list(entity.get("upstream_artifact_refs", []) or []))
        # Also record the *request-level* upload view: what the dependent worker
        # actually received on its own execution request.
        worker_requests: list[dict[str, Any]] = []
        for record in request_log:
            worker_requests.append(record)

        # Independent, real ModelReviewer over the program-produced candidate.
        review = await asyncio.to_thread(_review_sync, store, secrets, task_id)

        result = {
            "status": "ran",
            "plan_source": outcome.summary,
            "dispatcher_outcome": outcome.state,
            "dispatcher_summary": outcome.summary,
            "task_id": task_id,
            "run_id": run_id,
            "real_workers": 2,
            "autonomous_claim_tool_router": "GraphDispatcher._claim_for_worker",
            "autonomous_claim_chain": claim_chain,
            "handoff_refs": sorted(set(handoffs)),
            "worker_requests": worker_requests,
            "review": review,
            "generation_ledger": before.snapshot(),
            "max_real_calls_budget": MAX_CALLS,
            "per_request_output_cap": PER_REQUEST_OUTPUT_CAP,
            "worker_model_calls_cap": WORKER_MODEL_CALLS,
            "worker_proxy_calls_cap": WORKER_PROXY_CALLS,
            "elapsed_seconds": round(time.monotonic() - started_all, 2),
            "adapter_events": [e.get("type") for e in events][:80],
        }
        text = json.dumps(result, indent=2, sort_keys=True)
        print(text)
        OUT.write_text(text + "\n", encoding="utf-8")
        EVIDENCE_OUT.parent.mkdir(parents=True, exist_ok=True)
        EVIDENCE_OUT.write_text(text + "\n", encoding="utf-8")
        print(f"wrote {OUT}")
        print(f"wrote {EVIDENCE_OUT}")
        print(f"ledger snapshot: {before.snapshot()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
