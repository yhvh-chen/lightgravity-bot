#!/usr/bin/env python3
"""LG-032 phase A independent mechanism probe — autonomous semantics boundary.

Independent QA probe (NOT authored by LG-028/029/030/031 implementers/integrators).
Runs the *product* path (real ``RuleBasedPlanner`` + ``GraphDispatcher`` with
``autonomous_claim=True``) against a real ``FileStore`` and a deterministic,
model-free worker simulation. This probe is **provider-substitute**: no SDK, no
network, no DeepSeek. It answers the frozen-contract question:

    Does the program pre-select the worker's unique node before the tool is
    attached, or does a worker genuinely choose among multiple discoverable
    candidates?

It records, per worker execution:
  * the full authorized discovery candidate set the tool returned;
  * the worker's own scheduled/objective node;
  * whether claiming a *different* discoverable node is refused
    (``node_not_scheduled_for_worker``);
  * the pool-grant scope and whether the receipt is redacted;
  * live grant count before/after execution.

Output is JSON written under ``--out`` (create-only, never overwrite); durable
work dir under ``--work`` (create-only).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import replace
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "backend"))
sys.path.insert(0, str(REPO / "tests" / "coordinator"))
sys.path.insert(0, str(REPO / "tests" / "workspaces"))

from lightgravity.adapter import ExecuteRequest, ExecutorResult, ExecutionRef  # noqa: E402
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
from lightgravity.store import FileStore  # noqa: E402
from lightgravity.workspaces import GraphWorkspaceProvider, WorktreeManager  # noqa: E402

from gitfixtures import GitRepo, init_repo  # noqa: E402
from graph_helpers import build_environment, make_dispatch_setup  # noqa: E402

TWO_TEAM = RoleCatalog({"implementation": ["developer"], "verification": ["verifier"]})


class BoundaryWorkerSim:
    """Records the discovery/claim surface the product exposes to a worker."""

    name = "boundary-sim"
    version = "0"

    def __init__(self, registry: ExecutionGrantRegistry) -> None:
        self.registry = registry
        self.records: list[dict] = []

    async def execute(self, request: ExecuteRequest, emit) -> ExecutorResult:
        record: dict = {
            "subtask_id": request.subtask_id,
            "objective": request.objective,
        }
        tool = next(
            (t for t in request.custom_tools if getattr(t, "__name__", "") == "discover_and_request_claim"),
            None,
        )
        record["has_claim_tool"] = tool is not None
        record["active_grants_before"] = len(self.registry.active_grants())
        if tool is not None:
            discovered = tool()
            candidates = discovered.get("candidates") or []
            record["discovery_count"] = len(candidates)
            record["discovery_nodes"] = [c.get("node_ref") for c in candidates]
            # Which candidate is "this worker's" node per the program projection?
            mine = [
                c
                for c in candidates
                if (c.get("objective") or "").startswith(request.objective)
                or (c.get("objective") or "") == request.objective
            ]
            record["matching_candidates"] = len(mine)
            # Claim a DIFFERENT discoverable node if one exists -> tests the
            # program's node_not_scheduled_for_worker guard.
            other = next(
                (c["node_ref"] for c in candidates if c["node_ref"] not in {m.get("node_ref") for m in mine}),
                None,
            )
            record["other_candidate"] = other
            if other is not None:
                record["other_claim"] = tool(node_ref=other, request_id=f"x-{request.subtask_id}")
            if mine:
                claim = tool(node_ref=mine[0]["node_ref"], request_id=f"req-{request.subtask_id}")
                record["claim"] = claim
                record["claim_pool_count"] = len(self.registry.active_grants())
        self.records.append(record)
        # Produce a write artifact for the deliver node so the graph can pass.
        artifacts: tuple[str, ...] = ()
        if request.objective.startswith("Write") and "deliver.txt" in request.objective:
            path = Path(request.workspace_path) / "out" / "deliver.txt"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("delivered\n", encoding="utf-8")
            artifacts = ("out/deliver.txt",)
        return ExecutorResult(
            state="succeeded",
            summary="ok",
            artifact_refs=artifacts,
            execution_ref=ExecutionRef(
                execution_id=f"e-{request.subtask_id}",
                task_id=request.task_id,
                run_id=request.run_id,
                subtask_id=request.subtask_id,
            ),
            stop_confirmed=True,
        )


async def run(work: Path, out: Path) -> dict:
    ws_root = work / "ws"
    ws_root.mkdir(parents=True, exist_ok=True)
    repo = GitRepo(init_repo(ws_root / "task-ws"))
    store = FileStore(work / "data", repo.path.parent)
    build_environment(store)
    store.create(
        "settings",
        "settings",
        {
            "default_coordinator_connection_ref": None,
            "default_worker_connection_ref": None,
            "default_reviewer_connection_ref": None,
            "decentralized_claim_enabled": True,
            "collab_requests_enabled": True,
            "claim_lease_seconds": 300,
        },
        actor="qa",
        request_id="req-settings",
        body="# Settings\n",
    )
    _task_id, run_id, controller, base_context = make_dispatch_setup(
        store,
        objective="Write out/deliver.txt containing the word delivered",
        acceptance=("out/deliver.txt exists",),
        budget={"max_workers": 3, "max_parallel": 1, "max_repair_rounds": 1, "max_collab_requests": 4},
    )
    context = replace(
        base_context,
        planning_request=PlanningRequest(
            trigger=PlanningTrigger.USER_REQUEST, reason="qa", requested_by="qa", max_calls=1
        ),
    )
    registry = ExecutionGrantRegistry()
    sim = BoundaryWorkerSim(registry)
    dispatcher = GraphDispatcher(
        store,
        sim,
        catalog=TWO_TEAM,
        max_parallel=1,
        workspaces=GraphWorkspaceProvider(WorktreeManager(repo.path.parent)),
        collaboration=CollaborationService(
            store,
            policy=ClaimPolicy(enabled=True, lease_seconds=300, collab_requests_enabled=True),
        ),
        grant_registry=registry,
        autonomous_claim=True,
    )
    outcome = await dispatcher.dispatch(context, controller, lambda e: None)

    # Inspect the plan the program produced (deterministic RuleBasedPlanner).
    run_entity = store.read("run", run_id).entity
    plan = run_entity.get("plan") or {}
    subtasks = [
        {"key": s.get("key"), "capability": s.get("capability"), "write": s.get("write"),
         "depends_on": s.get("depends_on")}
        for s in (plan.get("subtasks") or [])
    ]
    # Which member is each node bound to (program scheduling authority)?
    node_bindings = []
    for ref in run_entity.get("subtask_refs") or []:
        e = store.read("subtask", ref).entity
        node_bindings.append(
            {"subtask_ref": ref, "key": e.get("key"), "assignee_member_ref": e.get("assignee_member_ref")}
        )
    result = {
        "outcome": {"state": outcome.state, "summary": outcome.summary},
        "plan_source": run_entity.get("plan_source"),
        "plan_subtasks": subtasks,
        "node_bindings": node_bindings,
        "workers": sim.records,
        "active_grants_after": len(registry.active_grants()),
        "provider_substitute": "no SDK, no network, no model",
    }
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    work = Path(args.work)
    out = Path(args.out)
    if out.exists():
        print(f"refusing to overwrite existing out: {out}", file=sys.stderr)
        return 2
    work.mkdir(parents=True, exist_ok=True)
    result = asyncio.run(run(work, out))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
