"""GraphDispatcher end-to-end via the LG-007 Dispatcher seam (LG-008).

Uses an in-process fake executor as unit evidence; the real SDK/DeepSeek path
is LG-010.  All state lives under pytest ``tmp_path``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from lightgravity.adapter import ExecuteRequest, ExecutorResult, FailureInfo
from lightgravity.coordinator import (
    DispatchContext,
    GraphDispatcher,
    PlanProposal,
    RawSubtask,
    RoleCatalog,
)
from lightgravity.coordinator.scheduler import parse_handoff_ref
from lightgravity.coordinator.service import Coordinator
from lightgravity.contracts import EventType
from lightgravity.store import FileStore

from coordinator_helpers import wait_for_phase
from graph_helpers import (
    FakeGraphExecutor,
    build_environment,
    make_dispatch_setup,
    subtask_states,
    task_phase,
)

TWO_AGENT = RoleCatalog({"implementation": ["developer"], "verification": ["verifier"]})
ONE_AGENT = RoleCatalog({"implementation": ["developer"], "verification": ["developer"]})


class StaticPlanner:
    """Test planner emitting a fixed node list (still program-validated)."""

    name = "static-test"

    def __init__(self, subtasks: list[RawSubtask]) -> None:
        self._subtasks = subtasks

    async def plan(self, context: DispatchContext) -> PlanProposal:
        return PlanProposal(subtasks=tuple(self._subtasks), source="test")


def no_sink(_event: dict[str, object]) -> None:
    return None


def member_states(store: FileStore) -> list[str]:
    base = store.data_dir / "members"
    if not base.is_dir():
        return []
    return [str(store.read("member", child.stem).entity["state"]) for child in base.glob("*.md")]


async def _wait_for(predicate: Callable[[], bool], *, timeout: float = 3.0) -> bool:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.01)
    return predicate()


async def test_two_node_graph_hands_off_artifacts(store: FileStore) -> None:
    build_environment(store)
    executor = FakeGraphExecutor()
    dispatcher = GraphDispatcher(store, executor, catalog=TWO_AGENT)
    task_id, run_id, controller, context = make_dispatch_setup(store)

    outcome = await dispatcher.dispatch(context, controller, no_sink)

    assert outcome.state == "succeeded"
    assert len(executor.requests) == 2
    states = subtask_states(store)
    assert {state["state"] for state in states} == {"passed"}
    assert {state["capability"] for state in states} == {"implementation", "verification"}
    for state in states:
        assert state["acceptance"]["status"] == "passed"
        assert state["acceptance"]["evidence_refs"]

    deliver = next(req for req in executor.requests if req.objective == context.objective)
    verify = next(req for req in executor.requests if req.objective != context.objective)
    assert deliver.upstream_artifact_refs == ()
    assert len(verify.upstream_artifact_refs) == 1
    subtask_ref, content_hash, artifact = parse_handoff_ref(verify.upstream_artifact_refs[0])
    assert subtask_ref == deliver.subtask_id
    assert content_hash and artifact

    run = store.read("run", run_id).entity
    assert run["plan_hash"]
    assert run["plan"]["source"] == "rules"
    assert len(run["subtask_refs"]) == 2
    assert len(run["team_refs"]) == 2
    assert task_phase(store, task_id) == "executing"  # Coordinator writes verifying
    assert member_states(store) == ["released", "released"]


async def test_minimal_team_reuses_single_agent(store: FileStore) -> None:
    build_environment(store)
    executor = FakeGraphExecutor()
    dispatcher = GraphDispatcher(store, executor, catalog=ONE_AGENT)
    _task_id, _run_id, controller, context = make_dispatch_setup(store)

    outcome = await dispatcher.dispatch(context, controller, no_sink)

    assert outcome.state == "succeeded"
    members = [
        store.read("member", child.stem).entity
        for child in (store.data_dir / "members").glob("*.md")
    ]
    assert len(members) == 1
    assert members[0]["role_ref"] == "developer"
    assert len(members[0]["assigned_subtask_refs"]) == 2
    assert members[0]["state"] == "released"


async def test_recruit_failure_records_reason_and_never_executes(store: FileStore) -> None:
    build_environment(store)
    executor = FakeGraphExecutor()
    only_impl = RoleCatalog({"implementation": ["developer"], "verification": []})
    dispatcher = GraphDispatcher(store, executor, catalog=only_impl)
    task_id, _run_id, controller, context = make_dispatch_setup(store)

    outcome = await dispatcher.dispatch(context, controller, no_sink)

    assert outcome.state == "failed"
    assert outcome.failure_code == "capability_unavailable"
    assert executor.requests == []
    assert subtask_states(store) == []
    events = store.read_events(task_id)
    assert any(
        event.type == EventType.ERROR_RECORDED.value and event.event["payload"]["mode"] == "recruit"
        for event in events
    )


async def test_failed_dependency_blocks_downstream(store: FileStore) -> None:
    build_environment(store)
    _task_id, _run_id, controller, context = make_dispatch_setup(store)

    def responder(request: ExecuteRequest) -> ExecutorResult:
        if request.objective == context.objective:
            return ExecutorResult(
                state="failed",
                summary="boom",
                failure=FailureInfo("tool_failed", "boom"),
            )
        return FakeGraphExecutor._default_responder(request)

    executor = FakeGraphExecutor(responder)
    dispatcher = GraphDispatcher(store, executor, catalog=TWO_AGENT)
    _task_id, _run_id, controller, context = make_dispatch_setup(store)

    outcome = await dispatcher.dispatch(context, controller, no_sink)

    assert outcome.state == "failed"
    assert outcome.failure_code == "tool_failed"
    assert len(executor.requests) == 1  # dependent node never ran
    states = {state["key"]: state for state in subtask_states(store)}
    assert states["deliver"]["state"] == "failed"
    assert states["verify"]["state"] == "failed"
    assert states["verify"]["acceptance"]["status"] == "blocked"
    assert states["verify"]["blocked_by"] == [states["deliver"]["id"]]


async def test_cancel_stops_inflight_and_reports_confirmed(store: FileStore) -> None:
    build_environment(store)
    gate = asyncio.Event()
    executor = FakeGraphExecutor(gate=gate)
    dispatcher = GraphDispatcher(store, executor, catalog=TWO_AGENT)
    _task_id, run_id, controller, context = make_dispatch_setup(store)

    dispatch_task = asyncio.ensure_future(dispatcher.dispatch(context, controller, no_sink))
    assert await _wait_for(lambda: executor.requests != [])

    cancel = await dispatcher.cancel(context.task_id, run_id)
    assert cancel.confirmed is True
    outcome = await asyncio.wait_for(dispatch_task, timeout=3.0)
    assert outcome.state == "cancelled"
    assert outcome.stop_confirmed is True
    assert any(state["state"] == "cancelled" for state in subtask_states(store))


async def test_read_only_nodes_run_in_parallel_up_to_limit(store: FileStore) -> None:
    build_environment(store)
    gate = asyncio.Event()
    executor = FakeGraphExecutor(gate=gate)
    planner = StaticPlanner(
        [
            RawSubtask(key="a", objective="a", capability="implementation", acceptance=("ok",)),
            RawSubtask(key="b", objective="b", capability="implementation", acceptance=("ok",)),
        ]
    )
    dispatcher = GraphDispatcher(store, executor, catalog=TWO_AGENT, planner=planner, max_parallel=2)
    _task_id, _run_id, controller, context = make_dispatch_setup(store)

    dispatch_task = asyncio.ensure_future(dispatcher.dispatch(context, controller, no_sink))
    assert await _wait_for(lambda: len(executor.requests) == 2)
    assert executor.peak_concurrent == 2
    gate.set()
    outcome = await asyncio.wait_for(dispatch_task, timeout=3.0)
    assert outcome.state == "succeeded"


async def test_same_workspace_write_nodes_serialize(store: FileStore) -> None:
    build_environment(store)
    executor = FakeGraphExecutor(delay=0.03)
    planner = StaticPlanner(
        [
            RawSubtask(
                key="a", objective="a", capability="implementation", acceptance=("ok",), write=True
            ),
            RawSubtask(
                key="b", objective="b", capability="implementation", acceptance=("ok",), write=True
            ),
        ]
    )
    dispatcher = GraphDispatcher(store, executor, catalog=TWO_AGENT, planner=planner, max_parallel=2)
    _task_id, _run_id, controller, context = make_dispatch_setup(store)

    outcome = await dispatcher.dispatch(context, controller, no_sink)

    assert outcome.state == "succeeded"
    assert len(executor.requests) == 2
    assert executor.peak_concurrent == 1  # single writer per workspace


async def test_subtask_config_hash_is_stable_across_runs(store: FileStore) -> None:
    build_environment(store)
    seen: list[dict[str, str]] = []
    for _ in range(2):
        executor = FakeGraphExecutor()
        dispatcher = GraphDispatcher(store, executor, catalog=TWO_AGENT)
        _task_id, run_id, controller, context = make_dispatch_setup(store)
        outcome = await dispatcher.dispatch(context, controller, no_sink)
        assert outcome.state == "succeeded"
        run = store.read("run", run_id).entity
        seen.append(
            {
                store.read("subtask", subtask_id).entity["key"]: store.read(
                    "subtask", subtask_id
                ).entity["config_hash"]
                for subtask_id in run["subtask_refs"]
            }
        )
    assert set(seen[0]) == {"deliver", "verify"}
    assert seen[0] == seen[1]


async def test_coordinator_integration_reaches_verifying(store: FileStore) -> None:
    build_environment(store)
    executor = FakeGraphExecutor()
    coordinator = Coordinator(store, dispatcher=GraphDispatcher(store, executor, catalog=TWO_AGENT))
    created = coordinator.create_task(
        "req-int",
        "Integration",
        "implement login",
        acceptance_criteria=("it works",),
        workspace_ref="task-ws",
    )
    assert created.task_id is not None
    coordinator.start()
    try:
        phase = await wait_for_phase(coordinator, created.task_id, {"verifying"}, timeout=5.0)
    finally:
        await coordinator.stop()
    assert phase == "verifying"
    assert len(executor.requests) == 2
    snapshot = coordinator.status(created.task_id)
    assert snapshot["phase"] == "verifying"
    assert snapshot["queue"]["state"] == "not_queued"
