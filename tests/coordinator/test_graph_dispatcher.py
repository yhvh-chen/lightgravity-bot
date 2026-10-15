"""GraphDispatcher end-to-end via the LG-007 Dispatcher seam (LG-008).

Uses an in-process fake executor as unit evidence; the real SDK/DeepSeek path
is LG-010.  All state lives under pytest ``tmp_path``.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from pathlib import Path

from lightgravity.adapter import (
    ExecuteRequest,
    ExecutionRef,
    ExecutorResult,
    FailureInfo,
)
from lightgravity.coordinator import (
    DispatchContext,
    GraphDispatcher,
    ModelPlanner,
    PlanProposal,
    PlanningRequest,
    PlanningTrigger,
    RawSubtask,
    RoleCatalog,
)
from lightgravity.coordinator.scheduler import parse_handoff_ref
from lightgravity.coordinator.service import Coordinator
from lightgravity.contracts import EventType
from lightgravity.store import FileStore
from lightgravity.verify import (
    CheckContext,
    default_check_registry,
    load_candidate,
    run_checks,
)

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


class CountingPlanner(StaticPlanner):
    """On-demand proposal stub that counts how often it is consulted."""

    def __init__(self, subtasks: list[RawSubtask]) -> None:
        super().__init__(subtasks)
        self.calls = 0

    async def plan(self, context: DispatchContext) -> PlanProposal:
        self.calls += 1
        return await super().plan(context)


def no_sink(_event: dict[str, object]) -> None:
    return None


def _single_node_propose(calls: list[str]):
    """A real ``ModelPlanner.propose`` fake (no model/SDK); records run ids."""

    def propose(context: DispatchContext) -> dict[str, object]:
        calls.append(context.run_id)
        return {
            "subtasks": [
                {
                    "key": "deliver",
                    "objective": "implement",
                    "capability": "implementation",
                    "acceptance": ["ok"],
                    "write": True,
                }
            ]
        }

    return propose


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


async def test_executor_diff_ref_is_canonicalized_into_task_evidence(store: FileStore) -> None:
    """A trusted executor's absolute diff path becomes a canonical evidence ref.

    Regression for the LG-010 blocker: the recorded evidence must never be a
    raw absolute path, and the ``artifacts-in-workspace`` check must validate
    it inside the Task/Run evidence root instead of rejecting it.
    """

    build_environment(store)
    sink = Path(store.data_dir).parent / "artifact-sink"
    sink.mkdir(parents=True, exist_ok=True)
    diff_file = sink / "lg006-diff.patch"
    diff_file.write_text("--- a/x\n+++ b/x\n", encoding="utf-8")

    def responder(request: ExecuteRequest) -> ExecutorResult:
        return ExecutorResult(
            state="succeeded",
            summary="ok",
            artifact_refs=(),
            diff_ref=str(diff_file),
            execution_ref=ExecutionRef(
                execution_id=f"exec_{request.subtask_id}",
                task_id=request.task_id,
                run_id=request.run_id,
                subtask_id=request.subtask_id,
            ),
            stop_confirmed=True,
        )

    executor = FakeGraphExecutor(responder)
    dispatcher = GraphDispatcher(store, executor, catalog=ONE_AGENT)
    task_id, run_id, controller, context = make_dispatch_setup(store)

    outcome = await dispatcher.dispatch(context, controller, no_sink)
    assert outcome.state == "succeeded"

    candidate = load_candidate(store, task_id)
    assert candidate.diff_ref is not None
    assert candidate.diff_ref.startswith("evidence:")
    assert all(not os.path.isabs(ref) for ref in candidate.artifact_refs)
    assert candidate.diff_ref in candidate.artifact_refs

    report = run_checks(
        default_check_registry(),
        ["artifacts-in-workspace"],
        CheckContext(
            task_id=task_id,
            run_id=run_id,
            candidate=candidate,
            store=store,
            workspace_path=candidate.workspace_path,
        ),
    )
    assert report.satisfied is True, report.to_dict()

    # Post-hoc tampering with the imported artifact is detected by digest.
    from lightgravity.evidence import evidence_root, parse_evidence_ref

    parsed = parse_evidence_ref(candidate.diff_ref)
    assert parsed is not None and parsed.digest
    canonical = evidence_root(store.data_dir, task_id) / run_id / parsed.name
    assert canonical.is_file()
    canonical.write_text("tampered\n", encoding="utf-8")
    tampered = run_checks(
        default_check_registry(),
        ["artifacts-in-workspace"],
        CheckContext(
            task_id=task_id,
            run_id=run_id,
            candidate=candidate,
            store=store,
            workspace_path=candidate.workspace_path,
        ),
    )
    assert tampered.satisfied is False


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
    _task_id, _run_id, controller, context = make_dispatch_setup(
        store,
        planning_request=PlanningRequest(
            trigger=PlanningTrigger.USER_REQUEST, reason="split two independent steps"
        ),
    )

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
    _task_id, _run_id, controller, context = make_dispatch_setup(
        store,
        planning_request=PlanningRequest(
            trigger=PlanningTrigger.AMBIGUOUS_REQUIREMENT, reason="two writer steps"
        ),
    )

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


async def test_injected_model_planner_is_on_demand_only(store: FileStore) -> None:
    """An injected proposal interface is never a per-Run prerequisite.

    Without an explicit :class:`PlanningRequest` the dispatcher builds the
    program-side minimal plan and never consults the planner.  With one, the
    proposal is consulted exactly once and its trigger/reason are frozen into
    the validated plan snapshot; there is no hidden automatic planning loop.
    """

    build_environment(store)
    executor = FakeGraphExecutor()
    planner = CountingPlanner(
        [
            RawSubtask(
                key="deliver",
                objective="implement",
                capability="implementation",
                acceptance=("ok",),
                write=True,
            )
        ]
    )
    dispatcher = GraphDispatcher(store, executor, catalog=ONE_AGENT, planner=planner)

    _task, run_id, controller, context = make_dispatch_setup(store)
    outcome = await dispatcher.dispatch(context, controller, no_sink)
    assert outcome.state == "succeeded"
    assert planner.calls == 0  # default path is program-side, model-free
    run = store.read("run", run_id).entity
    assert run["plan"]["source"] == "rules"
    assert all("on-demand" not in note for note in run["plan"]["notes"])

    request = PlanningRequest(
        trigger=PlanningTrigger.USER_REQUEST, reason="split the delivery into steps"
    )
    _task2, run_id2, controller2, context2 = make_dispatch_setup(
        store, planning_request=request
    )
    outcome2 = await dispatcher.dispatch(context2, controller2, no_sink)
    assert outcome2.state == "succeeded"
    assert planner.calls == 1  # bounded: one proposal per Run, no loop
    run2 = store.read("run", run_id2).entity
    assert run2["plan"]["source"] == "test"
    assert any(
        "trigger=user_request" in note and "split the delivery into steps" in note
        for note in run2["plan"]["notes"]
    )


async def test_default_dispatcher_has_no_model_planner(store: FileStore) -> None:
    build_environment(store)
    dispatcher = GraphDispatcher(store, FakeGraphExecutor(), catalog=TWO_AGENT)
    assert dispatcher.planner is None  # no resident orchestration model wired
    # Even a context-level request cannot reach a model when none is injected.
    _task2, run_id2, controller2, context2 = make_dispatch_setup(
        store,
        planning_request=PlanningRequest(
            trigger=PlanningTrigger.BLOCKED, reason="needs decomposition"
        ),
    )
    assert context2.planning_request is not None
    outcome = await dispatcher.dispatch(context2, controller2, no_sink)
    assert outcome.state == "succeeded"
    assert store.read("run", run_id2).entity["plan"]["source"] == "rules"


async def test_real_model_planner_budget_is_per_run_when_shared(store: FileStore) -> None:
    """QA-1: one shared real ``ModelPlanner`` is not capped across Runs.

    Each Run carrying its own explicit ``PlanningRequest`` gets its own bounded
    proposal; the budget is enforced by the dispatcher, not by a process-global
    instance counter.
    """

    build_environment(store)
    calls: list[str] = []
    planner = ModelPlanner(_single_node_propose(calls))  # default: no ceiling
    dispatcher = GraphDispatcher(store, FakeGraphExecutor(), catalog=ONE_AGENT, planner=planner)

    for index in (1, 2):
        request = PlanningRequest(
            trigger=PlanningTrigger.USER_REQUEST,
            reason=f"explicit decomposition {index}",
        )
        _task, run_id, controller, context = make_dispatch_setup(
            store, planning_request=request
        )
        outcome = await dispatcher.dispatch(context, controller, no_sink)
        assert outcome.state == "succeeded", outcome.summary
        assert store.read("run", run_id).entity["plan"]["source"] == "model"

    assert len(calls) == 2
    assert planner.calls == 2


async def test_real_model_planner_same_run_redispatch_does_not_loop(store: FileStore) -> None:
    """QA-1: re-dispatching the same Run cannot open a new model loop."""

    build_environment(store)
    calls: list[str] = []
    planner = ModelPlanner(_single_node_propose(calls))
    dispatcher = GraphDispatcher(store, FakeGraphExecutor(), catalog=ONE_AGENT, planner=planner)
    request = PlanningRequest(
        trigger=PlanningTrigger.BLOCKED, reason="needs decomposition"
    )
    _task, _run, controller, context = make_dispatch_setup(store, planning_request=request)

    first = await dispatcher.dispatch(context, controller, no_sink)
    assert first.state == "succeeded"

    second = await dispatcher.dispatch(context, controller, no_sink)
    assert second.state == "failed"  # clean DispatchOutcome, not an exception
    assert second.failure_code
    assert len(calls) == 1
    assert planner.calls == 1


async def test_real_model_planner_failed_attempts_consume_run_budget(store: FileStore) -> None:
    """QA-1: failed proposal attempts count against ``PlanningRequest.max_calls``."""

    build_environment(store)
    attempts: list[str] = []

    def propose(context: DispatchContext) -> dict[str, object]:
        attempts.append(context.run_id)
        raise RuntimeError("model backend exploded")

    planner = ModelPlanner(propose)
    dispatcher = GraphDispatcher(store, FakeGraphExecutor(), catalog=ONE_AGENT, planner=planner)
    request = PlanningRequest(
        trigger=PlanningTrigger.REPAIR_CAP, reason="bounded retry", max_calls=2
    )
    _task, _run, controller, context = make_dispatch_setup(store, planning_request=request)

    first = await dispatcher.dispatch(context, controller, no_sink)
    assert first.state == "failed"
    second = await dispatcher.dispatch(context, controller, no_sink)
    assert second.state == "failed"

    # The third dispatch is refused by the program *before* calling the model
    # again, because the two failed attempts consumed the max_calls=2 budget.
    third = await dispatcher.dispatch(context, controller, no_sink)
    assert third.state == "failed"
    assert "budget exhausted" in (third.summary or "")
    assert len(attempts) == 2


async def test_dispatch_wraps_plan_request_recording_errors(
    store: FileStore, monkeypatch
) -> None:
    """QA-2: a malformed request/recording bug cannot escape as a raw exception."""

    build_environment(store)
    planner = ModelPlanner(_single_node_propose([]))
    dispatcher = GraphDispatcher(store, FakeGraphExecutor(), catalog=ONE_AGENT, planner=planner)

    def boom(_proposal: PlanProposal, _request: PlanningRequest) -> PlanProposal:
        raise AttributeError("'str' object has no attribute 'value'")

    monkeypatch.setattr(dispatcher, "_record_planning_request", boom)
    request = PlanningRequest(trigger=PlanningTrigger.USER_REQUEST, reason="valid request")
    _task, _run, controller, context = make_dispatch_setup(store, planning_request=request)

    outcome = await dispatcher.dispatch(context, controller, no_sink)
    assert outcome.state == "failed"
    assert outcome.failure_code == "internal_error"
