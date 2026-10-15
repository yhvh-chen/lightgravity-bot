"""LG-031 phase4: the *real product program planner* autonomous-claim closure.

phase3's probe injected a two-write-node plan as if it were the model planner, so
it never exercised the product-side ``RuleBasedPlanner`` (the default, model-free
plan builder).  This test drives the **unmodified product path**: no injected
planner, the real ``RuleBasedPlanner`` produces ``deliver`` (write) -> ``verify``
(dependent), both workers discover/claim autonomously through the restricted tool,
the program atomically grants a fenced lease, records a versioned+hashed handoff
into the dependent node, and each worker writes inside the workspace the program
assigned it.  Deterministic worker simulation: no model, no network.

It is the offline regression pin for PM's phase4 fixture (real bootstrap/Graph
configuration, objective-not-slug discovery, dependent handoff, grant revocation).
"""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from lightgravity.adapter import ExecutorResult, ExecutionRef
from lightgravity.collaboration import ClaimPolicy, CollaborationService, ExecutionGrantRegistry
from lightgravity.coordinator import (
    DispatchContext,
    GraphDispatcher,
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


class AutonomousWorkerSim:
    """Replays a real worker: discover -> claim the authorized node -> work.

    The worker learns *which* node it owns from the program-owned ``objective``
    projection (never from the plan slug), and only claims a node the program
    actually scheduled for it.
    """

    name = "worker-sim"
    version = "0"

    def __init__(self) -> None:
        self.requests = []
        self.receipts = []

    async def execute(self, request, emit):
        self.requests.append(request)
        for tool in request.custom_tools:
            if getattr(tool, "__name__", "") == "discover_and_request_claim":
                discovered = tool()
                candidates = discovered.get("candidates") or []
                # The worker learns WHICH node it owns from the program-owned
                # ``objective`` projection (never from the plan slug).  The
                # dispatched node's objective appears in its own candidate entry
                # (the verify node's objective embeds the deliver one, so a
                # startswith/equals check selects the right node).
                match = None
                for candidate in candidates:
                    objective = candidate.get("objective") or ""
                    if objective == request.objective or objective.startswith(request.objective):
                        match = candidate
                        break
                if match is None:
                    raise AssertionError(
                        f"no authorized candidate matched objective {request.objective!r}"
                    )
                claim = tool(
                    node_ref=match["node_ref"],
                    request_id=f"req-{request.subtask_id}",
                )
                self.receipts.append(
                    {"request_objective": request.objective, "candidate": match, "claim": claim}
                )
        # A write node writes inside its program-assigned isolated worktree; the
        # read-only verify node writes nothing.
        if request.objective.startswith("Write") and "deliver.txt" in request.objective:
            path = Path(request.workspace_path) / "out" / "deliver.txt"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("delivered\n", encoding="utf-8")
            artifacts: tuple[str, ...] = ("out/deliver.txt",)
        else:
            artifacts = ()
        return ExecutorResult(
            state="succeeded",
            summary="ok",
            artifact_refs=artifacts,
            execution_ref=ExecutionRef(
                execution_id="e",
                task_id=request.task_id,
                run_id=request.run_id,
                subtask_id=request.subtask_id,
            ),
            stop_confirmed=True,
        )


@pytest.mark.asyncio
async def test_real_program_planner_autonomous_closure(tmp_path: Path) -> None:
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
        objective="Write out/deliver.txt containing the word delivered",
        acceptance=("out/deliver.txt exists",),
        budget={
            "max_workers": 3,
            "max_parallel": 1,
            "max_repair_rounds": 1,
            "max_collab_requests": 4,
        },
    )
    context = replace(
        base_context,
        planning_request=PlanningRequest(
            trigger=PlanningTrigger.USER_REQUEST,
            reason="phase4",
            requested_by="test",
            max_calls=1,
        ),
    )
    executor = AutonomousWorkerSim()
    registry = ExecutionGrantRegistry()
    # NOTE: no ``planner=`` is passed -- the real, model-free ``RuleBasedPlanner``
    # is the product default and produces deliver -> verify.
    dispatcher = GraphDispatcher(
        store,
        executor,
        catalog=TWO_TEAM,
        max_parallel=1,
        workspaces=GraphWorkspaceProvider(WorktreeManager(workspace_root)),
        collaboration=CollaborationService(
            store, policy=ClaimPolicy(enabled=True, lease_seconds=300, collab_requests_enabled=True)
        ),
        grant_registry=registry,
        autonomous_claim=True,
    )
    outcome = await dispatcher.dispatch(context, controller, lambda e: None)
    assert outcome.state == "succeeded", outcome.summary

    # Two real workers ran; the program plan produced deliver (write) + verify.
    assert len(executor.requests) == 2
    objectives = {r.objective for r in executor.requests}
    assert any("deliver.txt" in o for o in objectives)

    # Every receipt is a genuine autonomous claim against the program-scheduled
    # node: granted, fence=1, redacted (no token), objective present.
    assert len(executor.receipts) == 2
    for receipt in executor.receipts:
        assert receipt["candidate"]["objective"]
        claim = receipt["claim"]
        assert claim["ok"] is True and claim["state"] == "granted"
        assert claim["fence"] == 1
        assert "token" not in json.dumps(claim).lower()

    # The write node (objective starts with "Write") ran in its own real
    # worktree, distinct from the base repo.
    write_request = next(r for r in executor.requests if r.objective.startswith("Write"))
    assert Path(write_request.workspace_path).resolve() != repo.path.resolve()
    assert (Path(write_request.workspace_path) / "out" / "deliver.txt").is_file()

    # The dependent verify node received the versioned+hashed handoff.
    verify_request = next(r for r in executor.requests if not r.objective.startswith("Write"))
    assert verify_request.upstream_artifact_refs
    for ref in verify_request.upstream_artifact_refs:
        subtask_ref, _, rest = ref.partition("@")
        content_hash, _, artifact = rest.partition(":")
        assert subtask_ref and artifact and len(content_hash) == 64

    # No worker identity outlives its execution.
    assert registry.active_grants() == []
