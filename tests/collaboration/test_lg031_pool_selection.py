"""LG-031 POOL-FIX: true multi-candidate autonomous selection (F1 closure).

LG-032 phase A (F1) found the autonomous path pre-bound a worker to a single
program-scheduled node: the worker could only ever claim that one node even when
several same-capability nodes were genuinely ready and discoverable.  This suite
pins the *candidate-pool* model that closes the gap:

* the program computes the legal ready candidate set for a worker slot and
  freezes it in a multi-candidate pool grant;
* the worker **selects** one node itself (here deliberately a non-first,
  non-program-preferred candidate) and requests the claim;
* the program re-validates the selection against the live graph, atomically
  authorizes *the selected node* through the fenced lease authority, and binds
  its isolation/upstream context;
* the result/manifest/state/handoff are attributed to the **selected** node.

Deterministic worker/executor simulation: real ``FileStore`` + real flock + real
git worktrees, **no SDK/network/model** (provider-substitute).  It is the offline
mechanism pin; a real double-worker SDK proof remains a separate PM-frozen phase.
"""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from lightgravity.adapter import ExecutionRef, ExecutorResult
from lightgravity.collaboration import (
    ClaimPolicy,
    CollaborationService,
    ExecutionGrantRegistry,
)
from lightgravity.coordinator import DispatchContext, GraphDispatcher, RoleCatalog
from lightgravity.coordinator.planning import PlanningRequest, PlanningTrigger
from lightgravity.coordinator.planner import (
    PlanProposal,
    RawSubtask,
)
from lightgravity.store import FileStore
from lightgravity.workspaces import GraphWorkspaceProvider, WorktreeManager

_WORKSPACE_TESTS = Path(__file__).resolve().parent.parent / "workspaces"
if str(_WORKSPACE_TESTS) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE_TESTS))

from gitfixtures import GitRepo, init_repo  # noqa: E402
from graph_helpers import build_environment, make_dispatch_setup  # noqa: E402

TEAM = RoleCatalog({"implementation": ["developer"], "verification": ["verifier"]})


class TwoCandidatePlanner:
    """Program-side plan: two same-capability, simultaneously-ready write nodes.

    No model call; both nodes map to the single developer member, so the worker
    has a genuine two-candidate pool at dispatch time (the F1 scenario).
    """

    name = "pool-test"

    async def plan(self, context):  # noqa: ANN001
        subtasks = [
            RawSubtask(
                key="alpha",
                objective="Write alpha artifact out/alpha.txt",
                capability="implementation",
                acceptance=("alpha exists",),
                write=True,
            ),
            RawSubtask(
                key="beta",
                objective="Write beta artifact out/beta.txt",
                capability="implementation",
                acceptance=("beta exists",),
                write=True,
            ),
        ]
        return PlanProposal(
            subtasks=tuple(subtasks),
            source="rules",
        )


def _enable_settings(store: FileStore) -> None:
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


class PoolWorkerSim:
    """A two-phase worker: select in phase 1, execute the selected node in phase 2.

    Phase 1 runs on the selection scratch workspace with only the restricted
    claim tool: the worker selects a candidate (``select_key``) and produces **no
    artifact**.  Phase 2 is a separate executor call bound by the program to the
    selected node's isolated workspace/objective; the worker writes that node's
    artifact there.  This mirrors the real SDK two-session lifecycle without a
    real model (the executor is a provider-substitute).
    """

    name = "pool-worker-sim"
    version = "0"

    def __init__(self, select_key: str) -> None:
        self.select_key = select_key
        self.requests = []
        self.selection_requests: list[Any] = []
        self.execution_requests: list[Any] = []
        self.pool_sizes: list[int] = []
        self.claims: list[dict] = []
        self.bindings: list[dict] = []
        self.selected_keys: list[str] = []
        #: Per selected subtask id -> key, so phase 2 knows which node it owns.
        self._selected_by_node: dict[str, str] = {}

    @staticmethod
    def _is_selection(request: Any) -> bool:
        return any(
            getattr(t, "__name__", "") == "discover_and_request_claim"
            for t in request.custom_tools
        )

    async def execute(self, request, emit):  # noqa: ANN001
        self.requests.append(request)
        if self._is_selection(request):
            return await self._phase_select(request)
        return await self._phase_execute(request)

    async def _phase_select(self, request):  # noqa: ANN001
        """Phase 1: pick a candidate; produce no artifact."""

        self.selection_requests.append(request)
        tool = next(
            t for t in request.custom_tools if getattr(t, "__name__", "") == "discover_and_request_claim"
        )
        discovered = tool()
        candidates = discovered.get("candidates") or []
        self.pool_sizes.append(len(candidates))
        match = next((c for c in candidates if c.get("key") == self.select_key), None)
        if match is None and candidates:
            match = candidates[0]
        assert match is not None, f"no legal candidate in {candidates!r}"
        chosen_key = match.get("key")
        claim = tool(node_ref=match["node_ref"], request_id=f"req-{request.subtask_id}")
        self.claims.append(claim)
        assert claim["ok"] is True and claim["state"] == "granted", claim
        binding = claim.get("binding") or {}
        self.bindings.append(binding)
        self.selected_keys.append(chosen_key)
        self._selected_by_node[binding["node_ref"]] = chosen_key
        # No write tools / no product workspace in the selection phase: the
        # session can only report the selection.  Any artifact would be an
        # observable violation, so the sim deliberately produces none.
        assert not request.workspace_path.endswith("task-ws"), request.workspace_path
        return ExecutorResult(
            state="succeeded",
            summary="selected candidate",
            artifact_refs=(),
            execution_ref=ExecutionRef(
                execution_id=f"sel-{request.subtask_id}",
                task_id=request.task_id,
                run_id=request.run_id,
                subtask_id=request.subtask_id,
            ),
            stop_confirmed=True,
        )

    async def _phase_execute(self, request):  # noqa: ANN001
        """Phase 2: the program bound the selected node; write its artifact."""

        self.execution_requests.append(request)
        chosen_key = self._selected_by_node.get(request.subtask_id)
        assert chosen_key is not None, f"unexpected execution for {request.subtask_id}"
        target = Path(request.workspace_path) / "out" / f"{chosen_key}.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"{chosen_key} selected\n", encoding="utf-8")
        return ExecutorResult(
            state="succeeded",
            summary="delivered selected node artifact",
            artifact_refs=(f"out/{chosen_key}.txt",),
            execution_ref=ExecutionRef(
                execution_id=f"exec-{request.subtask_id}",
                task_id=request.task_id,
                run_id=request.run_id,
                subtask_id=request.subtask_id,
            ),
            stop_confirmed=True,
        )


def _make_dispatcher(store: FileStore, workspace_root: Path, executor, registry):  # noqa: ANN001
    return GraphDispatcher(
        store,
        executor,
        catalog=TEAM,
        planner=TwoCandidatePlanner(),  # type: ignore[arg-type]
        max_parallel=1,
        workspaces=GraphWorkspaceProvider(WorktreeManager(workspace_root)),
        collaboration=CollaborationService(
            store,
            policy=ClaimPolicy(enabled=True, lease_seconds=300, collab_requests_enabled=True),
        ),
        grant_registry=registry,
        autonomous_pool=True,
    )


@pytest.mark.asyncio
async def test_worker_selects_non_first_candidate_and_result_lands_on_it(tmp_path: Path) -> None:
    """The worker picks the *second* candidate; its result must land on that node."""

    root = tmp_path / "ws"
    repo = GitRepo(init_repo(root / "task-ws"))
    workspace_root = repo.path.parent
    store = FileStore(tmp_path / "data", workspace_root)
    build_environment(store)
    _enable_settings(store)
    _task_id, _run_id, controller, base_context = make_dispatch_setup(
        store,
        budget={
            "max_workers": 3,
            "max_parallel": 1,
            "max_repair_rounds": 1,
            "max_collab_requests": 4,
        },
    )
    context = replace(
        base_context,
        objective="produce both artifacts",
        planning_request=PlanningRequest(
            trigger=PlanningTrigger.USER_REQUEST,
            reason="pool-test",
            requested_by="test",
            max_calls=1,
        ),
    )
    registry = ExecutionGrantRegistry()
    # Deliberately select beta (not the program-first alpha) so a pre-selection
    # bug would be observable: beta is not the first pool item.
    executor = PoolWorkerSim(select_key="beta")
    dispatcher = _make_dispatcher(store, workspace_root, executor, registry)

    # Two slots run (one per node); the first selection is deliberately the
    # non-first candidate beta, and the second closes the remaining alpha.
    outcome = await dispatcher.dispatch(context, controller, lambda e: None)
    assert executor.pool_sizes and executor.pool_sizes[0] == 2, "pool must be multi-candidate"
    assert executor.selected_keys[0] == "beta", "worker must be able to pick a non-first node"

    # The first claim was for beta and produced a binding to beta's workspace.
    first_claim = executor.claims[0]
    assert "token" not in json.dumps(first_claim).lower()
    assert first_claim["binding"]["key"] == "beta"

    # Both nodes passed and each result landed on the node whose key it wrote.
    subtasks = store.read("run", _run_id).entity.get("subtask_refs") or []
    by_key = {
        store.read("subtask", ref).entity.get("key"): store.read("subtask", ref).entity
        for ref in subtasks
    }
    assert by_key["beta"]["state"] == "passed"
    assert by_key["alpha"]["state"] == "passed"
    # The beta node's recorded evidence is beta's artifact, not alpha's.
    beta_evidence = by_key["beta"]["acceptance"]["evidence_refs"]
    alpha_evidence = by_key["alpha"]["acceptance"]["evidence_refs"]
    assert any("beta.txt" in ref for ref in beta_evidence)
    assert any("alpha.txt" in ref for ref in alpha_evidence)
    assert not any("alpha.txt" in ref for ref in beta_evidence)

    # Every worker identity is revoked once the execution stopped.
    assert registry.active_grants() == []


@pytest.mark.asyncio
async def test_two_phase_sdk_lifecycle_selects_then_binds_selected_node(
    tmp_path: Path,
) -> None:
    """Phase 1 selects with no write authority; phase 2 binds the selected node.

    This pins the *two-phase* SDK lifecycle: the selection session runs on a
    dedicated scratch workspace with no product write tools, and the execution
    session is a separate call whose request is bound to the *selected* node's
    isolated worktree/objective.  A single-call (no-rebind) implementation would
    make the selection request and the execution request identical and would
    write into the slot workspace, which this test rejects.
    """

    root = tmp_path / "ws"
    repo = GitRepo(init_repo(root / "task-ws"))
    workspace_root = repo.path.parent
    store = FileStore(tmp_path / "data", workspace_root)
    build_environment(store)
    _enable_settings(store)
    _task_id, _run_id, controller, base_context = make_dispatch_setup(
        store,
        budget={
            "max_workers": 3,
            "max_parallel": 1,
            "max_repair_rounds": 1,
            "max_collab_requests": 4,
        },
    )
    context = replace(
        base_context,
        objective="produce both artifacts",
        planning_request=PlanningRequest(
            trigger=PlanningTrigger.USER_REQUEST,
            reason="pool-test",
            requested_by="test",
            max_calls=1,
        ),
    )
    registry = ExecutionGrantRegistry()
    executor = PoolWorkerSim(select_key="beta")
    dispatcher = _make_dispatcher(store, workspace_root, executor, registry)
    await dispatcher.dispatch(context, controller, lambda e: None)

    # Two distinct phases ran per worker slot: selection, then execution.
    assert len(executor.selection_requests) == 2
    assert len(executor.execution_requests) == 2
    first_selection = executor.selection_requests[0]
    # Phase 1 has no product write tools and runs on a scratch workspace that is
    # not the node's isolated worktree and not the shared base workspace.
    assert first_selection.allowed_tools == ()
    assert ".lg-pool-selection" in first_selection.workspace_path
    assert first_selection.workspace_path != context.workspace_path
    # Phase 1 exposes only the restricted claim tool and no peer write tool.
    assert [getattr(t, "__name__", "") for t in first_selection.custom_tools] == [
        "discover_and_request_claim"
    ]
    # The execution request is bound to the *selected* node: a real node subtask
    # id (not the slot), the node objective, and its isolated worktree.
    selected_exec = executor.execution_requests[0]
    assert "out/beta.txt" in selected_exec.objective or "out/alpha.txt" in selected_exec.objective
    assert selected_exec.subtask_id != first_selection.subtask_id
    assert "pool-slot" not in selected_exec.subtask_id


@pytest.mark.asyncio
async def test_pool_selection_uses_isolated_worktree_per_selected_node(tmp_path: Path) -> None:
    """Each selected node writes in its own real worktree, distinct from base."""

    root = tmp_path / "ws"
    repo = GitRepo(init_repo(root / "task-ws"))
    workspace_root = repo.path.parent
    store = FileStore(tmp_path / "data", workspace_root)
    build_environment(store)
    _enable_settings(store)
    _task_id, _run_id, controller, base_context = make_dispatch_setup(
        store,
        budget={"max_workers": 3, "max_parallel": 1, "max_repair_rounds": 1, "max_collab_requests": 6},
    )
    context = replace(
        base_context,
        objective="produce both artifacts",
        planning_request=PlanningRequest(
            trigger=PlanningTrigger.USER_REQUEST,
            reason="pool-test",
            requested_by="test",
            max_calls=1,
        ),
    )
    registry = ExecutionGrantRegistry()
    executor = PoolWorkerSim(select_key="beta")
    dispatcher = _make_dispatcher(store, workspace_root, executor, registry)

    await dispatcher.dispatch(context, controller, lambda e: None)

    binding = executor.bindings[0]
    workspace = Path(binding["workspace_path"]).resolve()
    assert workspace != repo.path.resolve()
    assert (workspace / "out" / "beta.txt").is_file()


@pytest.mark.asyncio
async def test_default_off_has_no_pool_and_no_pool_tools(tmp_path: Path) -> None:
    """With the decentralized switch off the candidate-pool path is inert."""

    store = FileStore(tmp_path / "data", tmp_path / "data" / "workspaces")
    build_environment(store)
    # No settings enabled -> ClaimPolicyReader resolves to closed; here we simply
    # never enable collaboration, so the pool mode is inert even if requested.
    _task_id, _run_id, controller, base_context = make_dispatch_setup(
        store, budget={"max_workers": 3, "max_parallel": 1, "max_repair_rounds": 1}
    )
    context = replace(
        base_context,
        objective="produce both artifacts",
        planning_request=PlanningRequest(
            trigger=PlanningTrigger.USER_REQUEST,
            reason="pool-test",
            requested_by="test",
            max_calls=1,
        ),
    )

    seen_pools: list[tuple] = []

    class _Plain:
        name = "plain"
        version = "0"

        async def execute(self, request, emit):  # noqa: ANN001
            seen_pools.append(request.candidate_bindings)
            assert request.custom_tools == ()
            return ExecutorResult(state="succeeded", summary="ok", artifact_refs=("a",), stop_confirmed=True)

    dispatcher = GraphDispatcher(
        store,
        _Plain(),  # type: ignore[arg-type]
        catalog=TEAM,
        planner=TwoCandidatePlanner(),  # type: ignore[arg-type]
        max_parallel=1,
        # no collaboration supplied -> deterministic-ish path; pool must be inert
        autonomous_pool=True,
    )
    outcome = await dispatcher.dispatch(context, controller, lambda e: None)
    assert outcome.state == "succeeded"
    assert all(pool == () for pool in seen_pools)


# ------------------------------------------------ negative / boundary tests
class _NoClaimExecutor:
    """Executor that records requests but never claims (for no-claim tests)."""

    name = "no-claim"
    version = "0"

    def __init__(self) -> None:
        self.requests = []

    async def execute(self, request, emit):  # noqa: ANN001
        self.requests.append(request)
        return ExecutorResult(
            state="succeeded", summary="produced", artifact_refs=("x",), stop_confirmed=True
        )


class _CaptureExecutor:
    """Executor that captures the pool bindings and then stops the slot."""

    name = "capture"
    version = "0"

    def __init__(self) -> None:
        self.bindings: tuple = ()

    async def execute(self, request, emit):  # noqa: ANN001
        self.bindings = tuple(request.candidate_bindings)
        return ExecutorResult(state="failed", summary="stop after capture")


def _pool_env(tmp_path: Path):
    """Build a two-candidate ready graph + collaboration store (real git/store)."""

    root = tmp_path / "ws"
    repo = GitRepo(init_repo(root / "task-ws"))
    workspace_root = repo.path.parent
    store = FileStore(tmp_path / "data", workspace_root)
    build_environment(store)
    _enable_settings(store)
    _task_id, _run_id, controller, base_context = make_dispatch_setup(
        store,
        budget={"max_workers": 3, "max_parallel": 1, "max_repair_rounds": 1, "max_collab_requests": 6},
    )
    context = replace(
        base_context,
        objective="produce both artifacts",
        planning_request=PlanningRequest(
            trigger=PlanningTrigger.USER_REQUEST,
            reason="pool-test",
            requested_by="test",
            max_calls=1,
        ),
    )
    return store, controller, context, workspace_root, repo


@pytest.mark.asyncio
async def test_worker_that_never_claims_writes_nothing(tmp_path: Path) -> None:
    """A worker that never claims is a bounded no-op: no candidate passes."""

    store, controller, context, workspace_root, _repo = _pool_env(tmp_path)
    registry = ExecutionGrantRegistry()
    executor = _NoClaimExecutor()
    dispatcher = _make_dispatcher(store, workspace_root, executor, registry)

    outcome = await dispatcher.dispatch(context, controller, lambda e: None)
    # No claim -> no candidate may be passed; the run must not fake success.
    assert outcome.state != "succeeded"
    refs = store.read("run", context.run_id).entity.get("subtask_refs") or []
    for ref in refs:
        assert store.read("subtask", ref).entity.get("state") != "passed"
    # The worker cannot write control state: no owner/fence was ever persisted.
    for ref in refs:
        entity = store.read("subtask", ref).entity
        assert entity.get("owner") is None
        assert int(entity.get("fence") or 0) == 0
    assert registry.active_grants() == []


def _store_bindings(store, run_id: str) -> list[dict]:
    """Build candidate bindings directly from the persisted run (no dispatch)."""

    refs = store.read("run", run_id).entity.get("subtask_refs") or []
    out = []
    for ref in refs:
        entity = store.read("subtask", ref).entity
        out.append(
            {
                "node_ref": ref,
                "key": entity.get("key"),
                "capability": entity.get("capability"),
                "objective": entity.get("objective"),
                "write": bool(entity.get("write")),
                "workspace_path": "",
                "member_ref": entity.get("assignee_member_ref"),
            }
        )
    return out


def _capture_pool(tmp_path: Path):
    """Dispatch once with a capturing executor and return (store, ctx, bindings)."""

    import asyncio

    store, controller, context, workspace_root, repo = _pool_env(tmp_path)
    registry = ExecutionGrantRegistry()
    capture = _CaptureExecutor()
    dispatcher = _make_dispatcher(store, workspace_root, capture, registry)
    asyncio.get_event_loop().run_until_complete(
        dispatcher.dispatch(context, controller, lambda e: None)
    )
    return store, context, workspace_root, capture.bindings, repo


def _direct_pool(tmp_path: Path, member_id: str):
    """Build a run with two ready same-capability nodes assigned to one member."""

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from collab_helpers import (
        create_run,
        create_subtask,
        create_task,
        link_subtasks,
        set_switches,
    )

    store = FileStore(tmp_path / "data", tmp_path / "data" / "workspaces")
    build_environment(store)
    set_switches(store, enabled=True, lease_seconds=300)
    task = create_task(store)
    run = create_run(store, task)
    alpha = create_subtask(
        store, run, key="alpha", capability="implementation", write=False,
        assignee_member_ref=member_id,
    )
    beta = create_subtask(
        store, run, key="beta", capability="implementation", write=False,
        assignee_member_ref=member_id,
    )
    link_subtasks(store, run, [alpha, beta])
    bindings = {
        alpha: {"node_ref": alpha, "key": "alpha", "capability": "implementation", "write": False,
                "workspace_path": "", "member_ref": member_id},
        beta: {"node_ref": beta, "key": "beta", "capability": "implementation", "write": False,
               "workspace_path": "", "member_ref": member_id},
    }
    return store, task, run, alpha, beta, bindings


def _pool_handler_dispatcher(store: FileStore, member_id: str, owner: str = "graph-dispatcher:a"):
    from lightgravity.coordinator import GraphDispatcher

    return GraphDispatcher(
        store,
        _NoClaimExecutor(),  # type: ignore[arg-type]
        collaboration=CollaborationService(
            store, policy=ClaimPolicy(enabled=True, lease_seconds=300, collab_requests_enabled=True)
        ),
        grant_registry=ExecutionGrantRegistry(),
        autonomous_pool=True,
        owner=owner,
    )


def _slot(member_id: str):
    from types import SimpleNamespace

    return SimpleNamespace(
        subtask_id="slot_direct",
        member_id=member_id,
        member=SimpleNamespace(capabilities=("implementation",)),
    )


def test_claim_outside_pool_is_refused(tmp_path: Path) -> None:
    """The program refuses a claim for a node outside the frozen candidate pool."""

    member_id = "member-pool"
    store, _task, run, alpha, beta, bindings = _direct_pool(tmp_path, member_id)
    dispatcher = _pool_handler_dispatcher(store, member_id)
    context = _run_ctx(store, run)
    refused = dispatcher._claim_for_worker_pool(
        _slot(member_id),
        context,
        "subtask_foreign",
        "req-foreign",
        pool_refs=(alpha, beta),
        bindings=bindings,
    )
    assert refused["granted"] is False
    assert refused["reason"] == "node_not_in_candidate_pool"
    # Nothing was written.
    assert store.read("subtask", alpha).entity.get("owner") is None


def test_claim_selects_non_first_node_and_binds_it(tmp_path: Path) -> None:
    """Selecting the *second* candidate grants that node and returns its binding."""

    member_id = "member-pool"
    store, _task, run, alpha, beta, bindings = _direct_pool(tmp_path, member_id)
    dispatcher = _pool_handler_dispatcher(store, member_id)
    context = _run_ctx(store, run)
    chosen = dispatcher._claim_for_worker_pool(
        _slot(member_id), context, beta, "req-beta", pool_refs=(alpha, beta), bindings=bindings
    )
    assert chosen["granted"] is True
    assert chosen["binding"]["key"] == "beta"
    assert store.read("subtask", beta).entity["state"] == "running"
    # LG-031 runtime integration: the lease owner is the program-frozen *worker
    # instance* identity (the dispatcher), while the grant keeps the member ref
    # as the authenticated identity; the same frozen owner claims, renews and
    # releases over HTTP.
    assert store.read("subtask", beta).entity["owner"] == "graph-dispatcher:a"
    # The non-selected node is untouched: no owner/fence, still pending.
    untouched = store.read("subtask", alpha).entity
    assert untouched["state"] == "pending" and untouched.get("owner") is None
    assert "token" not in json.dumps(chosen).lower()


def test_race_two_owners_same_node_only_one_winner(tmp_path: Path) -> None:
    """Two distinct owners racing the same candidate: exactly one wins."""

    member_id = "member-pool"
    store, _task, run, alpha, beta, bindings = _direct_pool(tmp_path, member_id)
    context = _run_ctx(store, run)
    first_d = _pool_handler_dispatcher(store, member_id, owner="graph-dispatcher:a")
    other_d = _pool_handler_dispatcher(store, member_id, owner="graph-dispatcher:b")
    first = first_d._claim_for_worker_pool(
        _slot(member_id), context, beta, "req-a", pool_refs=(alpha, beta), bindings=bindings
    )
    other = other_d._claim_for_worker_pool(
        _slot(member_id), context, beta, "req-b", pool_refs=(alpha, beta), bindings=bindings
    )
    assert first["granted"] is True
    assert other["granted"] is False
    assert other["reason"] in {"held_by_other", "candidate_no_longer_available"}
    assert int(store.read("subtask", beta).entity["fence"]) == 1
    # The loser may still discover and claim the remaining legal candidate.
    remaining = other_d._claim_for_worker_pool(
        _slot(member_id), context, alpha, "req-c", pool_refs=(alpha, beta), bindings=bindings
    )
    assert remaining["granted"] is True
    assert remaining["binding"]["key"] == "alpha"


def test_unknown_or_stale_selection_is_refused(tmp_path: Path) -> None:
    """A selection that is no longer live (unknown/terminal) is refused."""

    member_id = "member-pool"
    store, _task, run, alpha, beta, bindings = _direct_pool(tmp_path, member_id)
    context = _run_ctx(store, run)
    dispatcher = _pool_handler_dispatcher(store, member_id)
    # Unknown node not in the pool.
    assert (
        dispatcher._claim_for_worker_pool(
            _slot(member_id), context, "subtask_missing", "r1", pool_refs=(alpha, beta), bindings=bindings
        )["reason"]
        == "node_not_in_candidate_pool"
    )
    # Terminal node: mark beta passed, then try to claim it via the live check.
    from lightgravity.store import new_id  # noqa: F401

    store.write(
        "subtask",
        beta,
        {"state": "passed"},
        expected_revision=store.read("subtask", beta).revision,
        actor="test",
    )
    stale = dispatcher._claim_for_worker_pool(
        _slot(member_id), context, beta, "r2", pool_refs=(alpha, beta), bindings=bindings
    )
    assert stale["granted"] is False
    assert stale["reason"] == "candidate_no_longer_available"


def _run_ctx(store: FileStore, run_id: str):
    from lightgravity.coordinator import DispatchContext

    run = store.read("run", run_id).entity
    return DispatchContext(
        task_id=str(run["task_ref"]),
        run_id=run_id,
        attempt=1,
        objective="pool direct",
        acceptance_criteria=(),
        instructions="# task\n",
        workspace_path=str(store.resolve_path("task-ws", write=True)),
        budget={"max_collab_requests": 6},
    )


class TwoMemberPlanner:
    """Program-side plan: two capabilities -> two members, one node each."""

    name = "pool-two-member"

    async def plan(self, context):  # noqa: ANN001
        return PlanProposal(
            subtasks=(
                RawSubtask(
                    key="impl",
                    objective="Write implementation artifact",
                    capability="implementation",
                    acceptance=("impl exists",),
                    write=True,
                ),
                RawSubtask(
                    key="check",
                    objective="Write verification artifact",
                    capability="verification",
                    acceptance=("check exists",),
                    write=True,
                ),
            ),
            source="rules",
        )


@pytest.mark.asyncio
async def test_two_member_pools_run_in_parallel_without_writer_collision(tmp_path: Path) -> None:
    """Two members with isolated write nodes run in parallel; each pool is 1."""

    root = tmp_path / "ws"
    repo = GitRepo(init_repo(root / "task-ws"))
    workspace_root = repo.path.parent
    store = FileStore(tmp_path / "data", workspace_root)
    build_environment(store)
    _enable_settings(store)
    _task_id, _run_id, controller, base_context = make_dispatch_setup(
        store,
        budget={"max_workers": 3, "max_parallel": 2, "max_repair_rounds": 1, "max_collab_requests": 6},
    )
    context = replace(
        base_context,
        objective="produce two artifacts",
        planning_request=PlanningRequest(
            trigger=PlanningTrigger.USER_REQUEST,
            reason="pool-test",
            requested_by="test",
            max_calls=1,
        ),
    )
    registry = ExecutionGrantRegistry()
    executor = PoolWorkerSim(select_key="impl")
    dispatcher = GraphDispatcher(
        store,
        executor,
        catalog=TEAM,
        planner=TwoMemberPlanner(),  # type: ignore[arg-type]
        max_parallel=2,
        workspaces=GraphWorkspaceProvider(WorktreeManager(workspace_root)),
        collaboration=CollaborationService(
            store, policy=ClaimPolicy(enabled=True, lease_seconds=300, collab_requests_enabled=True)
        ),
        grant_registry=registry,
        autonomous_pool=True,
    )
    outcome = await dispatcher.dispatch(context, controller, lambda e: None)
    assert outcome.state == "succeeded"
    # Two distinct workers ran, each with a single-candidate pool, in distinct
    # isolated worktrees.  The two-phase lifecycle makes 2 executor calls per
    # worker (selection session + execution session): 2 select + 2 execute.
    assert len(executor.selection_requests) == 2
    assert len(executor.execution_requests) == 2
    assert len(executor.requests) == 4
    workspaces = {Path(b["workspace_path"]).resolve() for b in executor.bindings if b.get("workspace_path")}
    assert len(workspaces) == 2
    assert repo.path.resolve() not in workspaces
    assert registry.active_grants() == []


# ---------------------------------------------------------------------------
# LG-032 workspace-boundary regression (product defect found by LG-032 arm B)
#
# The real ``AntigravityExecutor`` authorizes only ``Settings.workspace_root``.
# The product default sets that root to ``<data_dir>/workspaces`` -- a
# *subdirectory* of data_dir -- while the Task ``save_dir`` lives at
# ``<data_dir>/native-sessions/<task>``.  The selection scratch used to be
# created under ``save_dir``, so a real executor honestly rejected it
# ("escapes the authorized root") and every arm-B Run failed.  These tests pin
# the boundary: the scratch must live inside the authorized root, and a path
# outside it must still be rejected (authority is not widened).
# ---------------------------------------------------------------------------


def _real_executor(workspace_root: Path, store: FileStore):
    from lightgravity.adapter import ResourceCompiler
    from lightgravity.adapter.executor import AntigravityExecutor

    return AntigravityExecutor(
        store,
        ResourceCompiler(store),
        workspace_root=workspace_root,
    )


def test_selection_scratch_lives_inside_authorized_root(tmp_path: Path) -> None:
    """The selection scratch must be inside ``workspace_root`` (real executor)."""

    root = tmp_path / "ws"
    repo = GitRepo(init_repo(root / "task-ws"))
    workspace_root = repo.path.parent
    store = FileStore(tmp_path / "data", workspace_root)
    # A Task save_dir deliberately OUTSIDE workspace_root, exactly as the
    # product default produces (data_dir/native-sessions/<task>).
    save_dir = tmp_path / "data" / "native-sessions" / "task_regression"

    provider = GraphWorkspaceProvider(WorktreeManager(workspace_root))
    context = DispatchContext(
        task_id="task_regression",
        run_id="run_01REGRESSIONBOUNDARY",
        attempt=1,
        objective="select a candidate",
        workspace_path=str(repo.path),
        save_dir=str(save_dir),
    )
    dispatcher = GraphDispatcher(
        store,
        _real_executor(workspace_root, store),
        catalog=TEAM,
        workspaces=provider,
        autonomous_pool=True,
    )

    scratch = dispatcher._selection_workspace(context, "slot_run_regression_0")
    scratch_path = Path(scratch).resolve()
    root_real = Path(workspace_root).resolve()

    # Legal selector scratch: inside the executor's authorized root.
    assert scratch_path == root_real or root_real in scratch_path.parents
    # ...and NOT under the (outside-root) save_dir.
    assert not str(scratch_path).startswith(str(save_dir.resolve()))

    # The real executor accepts it (no "escapes the authorized root").
    assert dispatcher._selection_scratch_root(context) is not None
    resolved = _real_executor(workspace_root, store)._resolve_workspace(scratch)
    assert resolved == scratch_path


def test_selection_scratch_out_of_root_still_rejected(tmp_path: Path) -> None:
    """A workspace outside the authorized root is still honestly rejected."""

    from lightgravity.adapter.executor import AdapterConfigInvalid

    root = tmp_path / "ws"
    repo = GitRepo(init_repo(root / "task-ws"))
    workspace_root = repo.path.parent
    store = FileStore(tmp_path / "data", workspace_root)
    executor = _real_executor(workspace_root, store)

    outside = tmp_path / "outside" / "somewhere"
    outside.mkdir(parents=True)
    with pytest.raises(AdapterConfigInvalid):
        executor._resolve_workspace(str(outside))


def test_selection_scratch_without_provider_falls_back(tmp_path: Path) -> None:
    """With no worktree provider the scratch falls back; never a hard crash."""

    root = tmp_path / "ws"
    repo = GitRepo(init_repo(root / "task-ws"))
    workspace_root = repo.path.parent
    store = FileStore(tmp_path / "data", workspace_root)
    dispatcher = GraphDispatcher(
        store,
        _real_executor(workspace_root, store),
        catalog=TEAM,
        autonomous_pool=True,
    )
    context = DispatchContext(
        task_id="task_regression",
        run_id="run_01NOROVIDER",
        attempt=1,
        objective="select a candidate",
        workspace_path=str(repo.path),
        save_dir=str(tmp_path / "data" / "native-sessions" / "task_regression"),
    )
    scratch = dispatcher._selection_workspace(context, "slot_x")
    assert scratch == str(repo.path)
