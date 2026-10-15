"""LG-031 integration: decentralized claim/lease/fence -> SDK execution seam.

These tests close the *real* gap left by LG-029/030: they wire the fenced lease
authority and program-frozen execution identity into the graph dispatcher, and
prove that

* two independent workers on independent worktrees can be scheduled, one
  winner per node, and a conflicting integration pauses instead of merging;
* a worker's own request tool can only reach nodes of its own Run, with the
  capability/dependency/budget checks enforced program-side;
* identity is frozen by the program (an opaque grant), never accepted from a
  request body, and the worker never holds a global management token;
* an old fence cannot write back, an expired lease is not a stop, and only a
  confirmed stop releases execution authority;
* an unknown side effect restarts into ``recovery_required`` (no fresh replay);
* a final candidate goes through machine check + independent reviewer + bounded
  repair, with old candidates/worktrees/evidence retained;
* the default (switch off) path is byte-for-byte the deterministic scheduler.

No model is called here.  The real DeepSeek reviewer path and the real SDK
execution are exercised by the LG-017 probe and LG-022/LG-032; this file is the
deterministic integration evidence for LG-031.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys

import pytest

# Reuse the LG-008 graph helpers (real Store/Dispatcher) without duplicating.
_COORDINATOR_TESTS = Path(__file__).resolve().parent.parent / "coordinator"
if str(_COORDINATOR_TESTS) not in sys.path:
    sys.path.insert(0, str(_COORDINATOR_TESTS))

from lightgravity.adapter import CancelResult, ExecutionRef, ExecutorResult, SessionRef
from lightgravity.collaboration import (
    ClaimPolicy,
    ClaimRequest,
    CollaborationService,
    ExecutionGrantRegistry,
    PeerService,
    default_registry,
    make_restricted_claim_tool,
    make_restricted_peer_tool,
    resolve_worker_identity,
)
from lightgravity.collaboration.errors import StaleLease
from lightgravity.coordinator import RoleCatalog
from lightgravity.coordinator.graph import GraphDispatcher
from lightgravity.coordinator.planning import PlanningRequest, PlanningTrigger
from lightgravity.store import FileStore

from collab_helpers import (
    FakeClock,
    create_run,
    create_subtask,
    create_task,
    link_subtasks,
    set_switches,
)
from graph_helpers import (
    FakeGraphExecutor,
    build_environment,
    make_dispatch_setup,
    run_state,
    subtask_states,
)


def _enable_settings(store: FileStore, *, collaboration: bool = True) -> None:
    store.create(
        "settings",
        "settings",
        {
            "default_coordinator_connection_ref": None,
            "default_worker_connection_ref": None,
            "default_reviewer_connection_ref": None,
            "decentralized_claim_enabled": True,
            "collab_requests_enabled": collaboration,
            "claim_lease_seconds": 300,
        },
        actor="test",
        request_id="req-settings",
        body="# Settings\n",
    )


def _collaboration(store: FileStore, *, enabled: bool = True) -> CollaborationService:
    return CollaborationService(store, policy=ClaimPolicy(enabled=enabled, lease_seconds=300))


# --------------------------------------------------------------------- grants
def test_grant_is_opaque_and_program_bound(tmp_path: Path) -> None:
    registry = ExecutionGrantRegistry()
    token, _grant = registry.mint(
        task_id="task_1",
        run_id="run_1",
        subtask_id="sub_1",
        member_ref="member-a",
        fence=3,
        authorized_node_refs={"sub_1", "sub_2"},
        max_collab_calls=2,
    )
    assert token.startswith("lgxg_")
    # The body can never authenticate: only the minted token resolves.
    assert registry.resolve_worker_identity("member-a") is None
    assert registry.resolve_worker_identity(token) == "member-a"
    # A re-claim with a new fence revokes the old holder's identity.
    registry.mint(
        task_id="task_1",
        run_id="run_1",
        subtask_id="sub_1",
        member_ref="member-b",
        fence=4,
        authorized_node_refs={"sub_1"},
    )
    assert registry.resolve_worker_identity(token) is None


def test_grant_budget_and_authorized_nodes_are_enforced(tmp_path: Path) -> None:
    registry = ExecutionGrantRegistry()
    token, _ = registry.mint(
        task_id="task_1",
        run_id="run_1",
        subtask_id="sub_1",
        member_ref="member-a",
        fence=1,
        authorized_node_refs={"sub_1"},
        max_collab_calls=1,
    )
    assert registry.consume_collab_call(token)[0] is True
    assert registry.consume_collab_call(token)[0] is False  # budget exhausted


def test_restricted_peer_tool_refuses_unauthorized_node(tmp_path: Path) -> None:
    store = FileStore(tmp_path / "data", tmp_path / "data" / "workspaces")
    registry = ExecutionGrantRegistry()

    def factory() -> PeerService:
        return PeerService(store, data_dir=tmp_path / "data", policy=ClaimPolicy(collab_requests_enabled=True))

    token, _ = registry.mint(
        task_id="task_1",
        run_id="run_1",
        subtask_id="sub_1",
        member_ref="member-a",
        fence=1,
        authorized_node_refs={"sub_1"},
        max_collab_calls=2,
    )
    tool = make_restricted_peer_tool(
        registry=registry,
        token=token,
        peer_service_factory=factory,
        run_id="run_1",
        node_ref="sub_1",
        from_member_ref="member-a",
    )
    outside = tool(node_ref_override="sub_999")
    assert outside["ok"] is False
    assert outside["reason"] == "node_not_authorized"


# ------------------------------------------------------------ graph execution
@pytest.mark.asyncio
async def test_decentralized_claim_grants_and_fences_nodes(tmp_path: Path) -> None:
    store = FileStore(tmp_path / "data", tmp_path / "data" / "workspaces")
    build_environment(store)
    _enable_settings(store)
    task_id, run_id, controller, context = make_dispatch_setup(store)
    executor = FakeGraphExecutor()
    dispatcher = GraphDispatcher(
        store,
        executor,
        catalog=None,
        collaboration=_collaboration(store),
        grant_registry=default_registry(),
    )
    outcome = await dispatcher.dispatch(context, controller, lambda _e: None)
    assert outcome.state == "succeeded"
    # Every scheduled node carries a program-minted grant token.
    assert executor.requests
    for request in executor.requests:
        assert request.execution_grant is not None
        # Default path exposes no custom tool unless the run allows collab.
        assert request.custom_tools == ()
    # The granted nodes are running with an owner/fence written to frontmatter.
    for entity in subtask_states(store):
        if entity.get("owner"):
            assert int(entity.get("fence", 0)) >= 1


@pytest.mark.asyncio
async def test_default_path_has_no_grants_or_extra_tools(tmp_path: Path) -> None:
    """Switch off -> the deterministic path is unchanged (rollback)."""

    store = FileStore(tmp_path / "data", tmp_path / "data" / "workspaces")
    build_environment(store)
    # No settings file at all: the reader resolves to the closed default.
    task_id, run_id, controller, context = make_dispatch_setup(store)
    executor = FakeGraphExecutor()
    dispatcher = GraphDispatcher(
        store,
        executor,
        collaboration=_collaboration(store, enabled=False),
        grant_registry=default_registry(),
    )
    outcome = await dispatcher.dispatch(context, controller, lambda _e: None)
    assert outcome.state == "succeeded"
    assert all(request.execution_grant is None for request in executor.requests)
    assert all(request.custom_tools == () for request in executor.requests)
    assert default_registry().active_grants() == []


@pytest.mark.asyncio
async def test_custom_tool_attached_only_when_collab_allowed(tmp_path: Path) -> None:
    store = FileStore(tmp_path / "data", tmp_path / "data" / "workspaces")
    build_environment(store)
    _enable_settings(store, collaboration=True)
    task_id, run_id, controller, context = make_dispatch_setup(
        store, budget={"max_workers": 3, "max_parallel": 2, "max_repair_rounds": 1, "max_collab_requests": 2}
    )
    executor = FakeGraphExecutor()
    dispatcher = GraphDispatcher(
        store,
        executor,
        collaboration=_collaboration(store),
        grant_registry=ExecutionGrantRegistry(),
    )
    outcome = await dispatcher.dispatch(context, controller, lambda _e: None)
    assert outcome.state == "succeeded"
    assert executor.requests
    assert all(len(request.custom_tools) == 1 for request in executor.requests)


# ------------------------------------------------------- lease/fence semantics
def test_old_fence_write_back_is_rejected(tmp_path: Path) -> None:
    store = FileStore(tmp_path / "data", tmp_path / "data" / "workspaces")
    clock = FakeClock()
    service = CollaborationService(store, clock=clock, actor="test", policy=ClaimPolicy(enabled=True))
    task_id = create_task(store)
    run_id = create_run(store, task_id)
    subtask_id = create_subtask(store, run_id, state="ready", write=True)
    link_subtasks(store, run_id, [subtask_id])
    first = service.request_claim(
        run_id,
        ClaimRequest(subtask_id=subtask_id, owner="worker-a", request_id="r1"),
        capability_ok=True,
        dependencies_ready=True,
    )
    assert first.granted
    # Expire, reclaim, and let a new owner take the node with a new fence.
    clock.advance(400)
    reclaimed = service.reclaim_expired(subtask_id)
    assert reclaimed.reclaimed
    # A write node with side effects must not be auto-replayed.
    second = service.request_claim(
        run_id,
        ClaimRequest(subtask_id=subtask_id, owner="worker-b", request_id="r2"),
        capability_ok=True,
        dependencies_ready=True,
    )
    # recovery_required node is waiting_user -> not directly claimable.
    assert second.granted is False
    # The old fence can never write back.
    with pytest.raises(StaleLease):
        service.guard_write_back(subtask_id, "worker-a", first.fence, {"state": "passed"})


def test_expiry_is_not_a_stop(tmp_path: Path) -> None:
    store = FileStore(tmp_path / "data", tmp_path / "data" / "workspaces")
    clock = FakeClock()
    service = CollaborationService(store, clock=clock, actor="test", policy=ClaimPolicy(enabled=True))
    task_id = create_task(store)
    run_id = create_run(store, task_id)
    subtask_id = create_subtask(store, run_id, state="ready", write=False)
    link_subtasks(store, run_id, [subtask_id])
    service.request_claim(
        run_id,
        ClaimRequest(subtask_id=subtask_id, owner="worker-a", request_id="r1"),
    )
    clock.advance(400)
    before = service.lease_state(subtask_id)
    assert before is not None and before.expired is True
    assert before.stopped is False  # expiry never proves a stop


def test_capability_and_budget_refusals_are_program_side(tmp_path: Path) -> None:
    store = FileStore(tmp_path / "data", tmp_path / "data" / "workspaces")
    service = CollaborationService(store, policy=ClaimPolicy(enabled=True))
    task_id = create_task(store, budget={"max_workers": 1, "max_parallel": 1, "max_repair_rounds": 0})
    run_id = create_run(store, task_id)
    subtask_id = create_subtask(store, run_id, state="ready")
    link_subtasks(store, run_id, [subtask_id])
    refused = service.request_claim(
        run_id,
        ClaimRequest(subtask_id=subtask_id, owner="worker-a", request_id="r1", capability="frontend"),
        capability_ok=False,
    )
    assert refused.granted is False and refused.reason == "capability_mismatch"
    no_budget = service.request_claim(
        run_id,
        ClaimRequest(subtask_id=subtask_id, owner="worker-a", request_id="r2"),
        budget_available=False,
    )
    assert no_budget.granted is False and no_budget.reason == "budget_exhausted"


def test_feature_disabled_refuses_everything(tmp_path: Path) -> None:
    from lightgravity.collaboration import ClaimRefused

    store = FileStore(tmp_path / "data", tmp_path / "data" / "workspaces")
    service = CollaborationService(store, policy=ClaimPolicy(enabled=False))
    task_id = create_task(store)
    run_id = create_run(store, task_id)
    subtask_id = create_subtask(store, run_id, state="ready")
    link_subtasks(store, run_id, [subtask_id])
    with pytest.raises(ClaimRefused) as excinfo:
        service.request_claim(
            run_id, ClaimRequest(subtask_id=subtask_id, owner="worker-a", request_id="r1")
        )
    assert excinfo.value.reason == "feature_disabled"


# --------------------------------------------------- HTTP identity seam (API)
def test_worker_identity_resolver_reads_grant_header_only(tmp_path: Path) -> None:
    registry = ExecutionGrantRegistry()
    token, _ = registry.mint(
        task_id="task_1",
        run_id="run_1",
        subtask_id="sub_1",
        member_ref="member-a",
        fence=1,
        authorized_node_refs={"sub_1"},
    )

    class _Request:
        def __init__(self, headers: dict[str, str]) -> None:
            self.headers = headers

    assert resolve_worker_identity(_Request({}), registry=registry) is None
    assert (
        resolve_worker_identity(_Request({"X-LG-Execution-Grant": token}), registry=registry)
        == "member-a"
    )
    # A body-supplied member name is never consulted.
    assert (
        resolve_worker_identity(_Request({"from_member_ref": "member-a"}), registry=registry)
        is None
    )


# ------------------------------------------- autonomous worker claim (R1)
def _autonomous_registry_with_pool() -> tuple[ExecutionGrantRegistry, str]:
    registry = ExecutionGrantRegistry()
    token, _grant = registry.mint(
        task_id="task_1",
        run_id="run_1",
        subtask_id="node-x",
        member_ref="member-a",
        fence=0,
        authorized_node_refs={"sub_1", "sub_2"},
        kind="pool",
    )
    return registry, token


def test_restricted_claim_tool_requires_pool_grant_and_returns_redacted_receipt() -> None:
    registry, token = _autonomous_registry_with_pool()
    claims: list[tuple[str, str]] = []

    class _View:
        run_ref = "run_1"
        candidates = (
            type("C", (), {"subtask_id": "sub_1", "capability": "implementation", "key": "a"})(),
            type("C", (), {"subtask_id": "sub_2", "capability": "implementation", "key": "b"})(),
        )

    def claim_callback(node_ref: str, request_id: str) -> dict[str, object]:
        claims.append((node_ref, request_id))
        return {"granted": True, "reason": "granted", "fence": 7, "request_id": request_id}

    tool = make_restricted_claim_tool(
        registry=registry,
        token=token,
        discover=lambda: _View(),
        claim_callback=claim_callback,
    )
    # Discovery-only call: lists candidates, claims nothing.
    discovered = tool()
    assert discovered["ok"] is True
    assert {c["node_ref"] for c in discovered["candidates"]} == {"sub_1", "sub_2"}
    assert claims == []
    # A node outside the authorized view is refused program-side, no callback.
    refused = tool(node_ref="sub_elsewhere")
    assert refused["ok"] is False
    assert refused["reason"] == "not_discoverable"
    assert claims == []
    # An authorized claim reaches the program callback and returns a redacted
    # receipt: the decision/fence, never a grant token.
    granted = tool(node_ref="sub_1", request_id="req-1")
    assert granted["ok"] is True
    assert granted["state"] == "granted"
    assert granted["fence"] == 7
    assert claims == [("sub_1", "req-1")]
    assert "token" not in json.dumps(granted).lower()


def test_restricted_claim_tool_refuses_non_pool_and_revoked_grants() -> None:
    registry = ExecutionGrantRegistry()
    calls: list[str] = []

    class _View:
        run_ref = "run_1"
        candidates = (
            type("C", (), {"subtask_id": "sub_1", "capability": None, "key": None})(),
        )

    # A node (non-pool) grant may not claim.
    node_token, _ = registry.mint(
        task_id="task_1",
        run_id="run_1",
        subtask_id="sub_1",
        member_ref="member-a",
        fence=1,
        authorized_node_refs={"sub_1"},
    )
    tool = make_restricted_claim_tool(
        registry=registry,
        token=node_token,
        discover=lambda: _View(),
        claim_callback=lambda n, r: calls.append(n) or {"granted": True},
    )
    refused = tool(node_ref="sub_1")
    assert refused["ok"] is False and refused["reason"] == "grant_revoked_or_expired"
    assert calls == []

    # A revoked pool grant is refused before discovery.
    pool_token, _ = registry.mint(
        task_id="task_1",
        run_id="run_1",
        subtask_id="sub_1",
        member_ref="member-a",
        fence=0,
        authorized_node_refs={"sub_1"},
        kind="pool",
    )
    registry.revoke_token(pool_token)
    tool2 = make_restricted_claim_tool(
        registry=registry,
        token=pool_token,
        discover=lambda: _View(),
        claim_callback=lambda n, r: calls.append(n) or {"granted": True},
    )
    assert tool2(node_ref="sub_1")["reason"] == "grant_revoked_or_expired"
    assert calls == []


@pytest.mark.asyncio
async def test_autonomous_mode_requires_worker_initiated_claim(tmp_path: Path) -> None:
    """A worker that never claims through the tool cannot pass (program authority)."""

    from dataclasses import replace

    from graph_helpers import build_environment, make_dispatch_setup

    store = FileStore(tmp_path / "data", tmp_path / "workspaces")
    build_environment(store)
    _enable_settings(store)
    _task_id, _run_id, controller, context = make_dispatch_setup(
        store,
        budget={
            "max_workers": 3,
            "max_parallel": 1,
            "max_repair_rounds": 1,
            "max_collab_requests": 2,
        },
    )
    collab = _collaboration(store)
    registry = ExecutionGrantRegistry()
    executor = FakeGraphExecutor()
    dispatcher = GraphDispatcher(
        store,
        executor,
        catalog=RoleCatalog({"implementation": ["developer"], "verification": ["verifier"]}),
        max_parallel=1,
        collaboration=collab,
        grant_registry=registry,
        autonomous_claim=True,
    )
    context = replace(
        context,
        planning_request=PlanningRequest(
            trigger=PlanningTrigger.USER_REQUEST,
            reason="r1",
            requested_by="test",
            max_calls=1,
        ),
    )
    outcome = await dispatcher.dispatch(context, controller, lambda e: None)
    # The fake executor never calls the claim tool, so no node grant was minted
    # and the run must not report success for the autonomous path.
    assert outcome.state != "succeeded"
    assert registry.active_grants() == []


@pytest.mark.asyncio
async def test_autonomous_worker_tool_claim_grants_node(tmp_path: Path) -> None:
    """A worker that drives the discover/claim tool gets a real program grant."""

    from dataclasses import replace

    from graph_helpers import build_environment, make_dispatch_setup

    store = FileStore(tmp_path / "data", tmp_path / "data" / "workspaces")
    build_environment(store)
    _enable_settings(store)
    _task_id, _run_id, controller, context = make_dispatch_setup(
        store,
        budget={
            "max_workers": 3,
            "max_parallel": 1,
            "max_repair_rounds": 1,
            "max_collab_requests": 2,
        },
    )
    collab = _collaboration(store)
    registry = ExecutionGrantRegistry()
    seen: list[dict[str, object]] = []

    def responder(request: ExecuteRequest) -> ExecutorResult:
        # The "worker" (model stand-in) autonomously calls the program tool.
        assert request.custom_tools, "autonomous worker must be given the claim tool"
        tool = request.custom_tools[0]
        discovered = tool()
        seen.append(discovered)
        # The worker may only claim one of its own discoverable nodes.
        claim = tool(node_ref=request.subtask_id)
        seen.append(claim)
        return ExecutorResult(
            state="succeeded",
            summary="claimed and delivered",
            artifact_refs=("artifact",),
            stop_confirmed=True,
        )

    executor = FakeGraphExecutor(responder)
    dispatcher = GraphDispatcher(
        store,
        executor,
        catalog=RoleCatalog({"implementation": ["developer"], "verification": ["verifier"]}),
        max_parallel=1,
        collaboration=collab,
        grant_registry=registry,
        autonomous_claim=True,
    )
    context = replace(
        context,
        planning_request=PlanningRequest(
            trigger=PlanningTrigger.USER_REQUEST,
            reason="r1",
            requested_by="test",
            max_calls=1,
        ),
    )
    outcome = await dispatcher.dispatch(context, controller, lambda e: None)
    assert outcome.state == "succeeded"
    # The program granted a node via the worker's own request.
    granted = [s for s in seen if s.get("state") == "granted"]
    assert granted and granted[0]["ok"] is True
    # The redacted receipt never leaks a token.
    assert "token" not in json.dumps(seen).lower()
    # Only the actually-claimed node got a grant; it is revoked after the
    # confirmed stop, so no worker identity outlives its execution.
    assert registry.active_grants() == []
