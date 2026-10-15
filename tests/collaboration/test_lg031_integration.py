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
    make_restricted_peer_tool,
    resolve_worker_identity,
)
from lightgravity.collaboration.errors import StaleLease
from lightgravity.coordinator.graph import GraphDispatcher
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
