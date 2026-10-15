"""LG-031 phase3: the *product* GraphDispatcher autonomous-claim closure.

R2's real probe bypassed the product coordinator (hand-rolled pool grant and
claim callback), so it never exercised the real plan validator, the real
discovery projection or the real ``GraphDispatcher._claim_for_worker`` router.
Driving the real path exposed a genuine compat gap: the restricted claim tool's
discovery projection carried ``node_ref``/``capability``/``key`` but **not** the
program-owned ``objective``, so a product-path worker could not tell which
artifact its claimed node owns.

This test pins the additive fix (``objective``/``write`` in the projection) and
the end-to-end product closure with a deterministic worker simulation (no model,
no network): two nodes, two real per-node git worktrees, autonomous discover ->
claim -> program atomic grant (fence=1, redacted receipt), a versioned+hashed
handoff, and a complete resolvable candidate.  The real DeepSeek chain is the
phase3 probe; this is the offline regression pin.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from lightgravity.adapter import ExecutorResult, ExecutionRef
from lightgravity.collaboration import ClaimPolicy, CollaborationService, ExecutionGrantRegistry
from lightgravity.coordinator import (
    DispatchContext,
    GraphDispatcher,
    PlanProposal,
    RawSubtask,
    RoleCatalog,
)
from lightgravity.coordinator.planning import PlanningRequest, PlanningTrigger
from lightgravity.store import FileStore
from lightgravity.workspaces import GraphWorkspaceProvider, WorktreeManager

_WORKSPACE_TESTS = Path(__file__).resolve().parent.parent / "workspaces"
if str(_WORKSPACE_TESTS) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE_TESTS))

from gitfixtures import GitRepo, init_repo  # noqa: E402
from graph_helpers import build_environment, make_dispatch_setup  # noqa: E402

TWO_TEAM = RoleCatalog({"implementation": ["developer"], "verification": ["verifier"]})


class TwoNodePlan:
    """Slug-keyed two-node plan (the program validator rejects path keys)."""

    name = "phase3-two-node"

    async def plan(self, context: DispatchContext) -> PlanProposal:
        return PlanProposal(
            subtasks=(
                RawSubtask(
                    key="produce",
                    objective="Create out/produce.txt containing 'produced'",
                    capability="implementation",
                    acceptance=("out/produce.txt exists",),
                    write=True,
                ),
                RawSubtask(
                    key="integrate",
                    objective="Create out/integrate.txt containing 'integrated'",
                    capability="implementation",
                    acceptance=("out/integrate.txt exists",),
                    depends_on=("produce",),
                    write=True,
                ),
            ),
            source="test",
        )


class AutonomousWorkerSim:
    """Replays the worker's autonomous discover -> claim -> write sequence."""

    name = "worker-sim"
    version = "0"

    def __init__(self) -> None:
        self.requests = []
        self.receipts = []

    async def execute(self, request, emit):
        self.requests.append(request)
        want = "produce" if "produce" in request.objective else "integrate"
        for tool in request.custom_tools:
            if getattr(tool, "__name__", "") == "discover_and_request_claim":
                discovered = tool()
                candidate = next(
                    c for c in discovered["candidates"] if want in (c.get("objective") or "")
                )
                claim = tool(node_ref=candidate["node_ref"], request_id=f"req-{request.subtask_id}")
                self.receipts.append({"candidate": candidate, "claim": claim})
        target = "out/produce.txt" if "produce" in request.objective else "out/integrate.txt"
        content = "produced" if "produce" in request.objective else "integrated"
        path = Path(request.workspace_path) / target
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content + "\n", encoding="utf-8")
        return ExecutorResult(
            state="succeeded",
            summary="ok",
            artifact_refs=(target,),
            execution_ref=ExecutionRef(
                execution_id="e",
                task_id=request.task_id,
                run_id=request.run_id,
                subtask_id=request.subtask_id,
            ),
            stop_confirmed=True,
        )


@pytest.mark.asyncio
async def test_product_path_autonomous_claim_closes(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    repo = GitRepo(init_repo(root / "task-ws"))
    workspace_root = repo.path.parent
    store = FileStore(tmp_path / "data", workspace_root)
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
        actor="test",
        request_id="req-settings",
        body="# Settings\n",
    )
    _task_id, _run_id, controller, base_context = make_dispatch_setup(
        store,
        budget={
            "max_workers": 3,
            "max_parallel": 1,
            "max_repair_rounds": 1,
            "max_collab_requests": 4,
        },
    )
    from dataclasses import replace

    context = replace(
        base_context,
        planning_request=PlanningRequest(
            trigger=PlanningTrigger.USER_REQUEST,
            reason="phase3",
            requested_by="test",
            max_calls=1,
        ),
    )
    executor = AutonomousWorkerSim()
    registry = ExecutionGrantRegistry()
    dispatcher = GraphDispatcher(
        store,
        executor,
        catalog=TWO_TEAM,
        planner=TwoNodePlan(),  # type: ignore[arg-type]
        max_parallel=1,
        workspaces=GraphWorkspaceProvider(WorktreeManager(workspace_root)),
        collaboration=CollaborationService(
            store, policy=ClaimPolicy(enabled=True, lease_seconds=300, collab_requests_enabled=True)
        ),
        grant_registry=registry,
        autonomous_claim=True,
    )
    outcome = await dispatcher.dispatch(context, controller, lambda e: None)
    assert outcome.state == "succeeded"

    # The discovery projection carries the program-owned objective the worker
    # needs to know which artifact its claimed node owns.
    for receipt in executor.receipts:
        assert receipt["candidate"]["objective"]
        claim = receipt["claim"]
        assert claim["ok"] is True and claim["state"] == "granted"
        assert claim["fence"] == 1
        # The redacted receipt never leaks a grant token.
        assert "token" not in json.dumps(claim).lower()

    # Two workers, each in its own real worktree, distinct from the base repo.
    assert len(executor.requests) == 2
    paths = {Path(r.workspace_path).resolve() for r in executor.requests}
    assert len(paths) == 2
    assert repo.path.resolve() not in paths

    # The dependent node received a versioned+hashed handoff from the program.
    integrate = next(r for r in executor.requests if "integrate" in r.objective)
    assert integrate.upstream_artifact_refs
    for ref in integrate.upstream_artifact_refs:
        subtask_ref, _, rest = ref.partition("@")
        content_hash, _, artifact = rest.partition(":")
        assert subtask_ref and artifact and len(content_hash) == 64

    # Each worker wrote its artifact inside its OWN isolated worktree (the
    # program, not the worker, owns the candidate workspace and consolidation).
    for request in executor.requests:
        target = "out/produce.txt" if "produce" in request.objective else "out/integrate.txt"
        assert (Path(request.workspace_path) / target).is_file()

    # No worker identity outlives its execution.
    assert registry.active_grants() == []
