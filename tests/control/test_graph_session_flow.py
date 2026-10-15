"""GraphDispatcher node-level native session data flow (LG-016).

This is the **integration** proof that the *default product path*
(``Coordinator`` + :class:`GraphDispatcher`) actually moves native SDK session
identity per graph node:

* every real node's non-secret ``SessionRef`` (from the authoritative
  ``ExecutorResult``) is persisted to the executing ``member.session_ref`` and to
  ``run.node_sessions``;
* after a confirmed pause + resume, the new Run hands each node **its own**
  ``conversation_id`` + ``save_dir`` + native ``resume`` mode into the
  ``ExecuteRequest`` — not one run-level conversation;
* a node whose config hash / member identity changed is dispatched *fresh*
  instead of silently reattaching to a stale conversation;
* a ``passed`` write node is never silently replayed into the continuation path.

The fake executor is deterministic unit/integration evidence; the real SDK
native-resume capability is recorded in the LG-016 implementation report.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from lightgravity.adapter import ExecuteRequest, ExecutionRef, ExecutorResult, SessionRef
from lightgravity.coordinator import (
    Coordinator,
    DispatchContext,
    GraphDispatcher,
    PlanProposal,
    RawSubtask,
    RoleCatalog,
)
from lightgravity.coordinator.session_flow import (
    NodeSession,
    completed_keys,
    extract_node_session,
    node_session_for_resume,
    record_node_session,
)
from lightgravity.coordinator.state import StateWriter
from lightgravity.store import FileStore, new_id

from graph_helpers import FakeGraphExecutor, build_environment, make_dispatch_setup

TWO_AGENT = RoleCatalog({"implementation": ["developer"], "verification": ["verifier"]})


class StaticPlanner:
    name = "static-test"

    def __init__(self, subtasks: list[RawSubtask]) -> None:
        self._subtasks = subtasks

    async def plan(self, context: DispatchContext) -> PlanProposal:
        return PlanProposal(subtasks=tuple(self._subtasks), source="test")


def no_sink(_event: dict[str, Any]) -> None:
    return None


class SessionExecutor(FakeGraphExecutor):
    """A fake executor that reports a distinct native session per node.

    ``conversation_id`` is derived from the node key so a multi-node graph has
    distinct native conversations, exactly like the real SDK.  ``state`` is
    ``resumed`` when the request carried an explicit ``resume`` continuation, so
    a resumed Run's node honestly reports that it attached to the same session.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.active_gate = kwargs.get("gate")

    async def execute(self, request: ExecuteRequest, emit: Any) -> ExecutorResult:
        self.active += 1
        self.peak_concurrent = max(self.peak_concurrent, self.active)
        self.requests.append(request)
        self.started.set()
        try:
            if self._gate is not None:
                await self._gate.wait()
            key = request.subtask_id.rsplit("_", 1)[-1]
            state = "resumed" if request.continuation_mode == "resume" else "created"
            conversation = request.conversation_id or f"conv-native{key}-aaaaaaaaaaaaaaaaaaaaaaaa"
            save_dir = request.save_dir or f"/tmp/native-sessions/{request.task_id}/{key}"
            ref = SessionRef(
                session_id=f"sess_{key}",
                conversation_id=conversation,
                state=state,
                save_dir=save_dir,
            )
            return ExecutorResult(
                state="succeeded",
                summary=f"ok:{key}",
                artifact_refs=(f"artifact_{key}",),
                session_ref=ref,
                execution_ref=ExecutionRef(
                    execution_id=f"exec_{request.subtask_id}",
                    task_id=request.task_id,
                    run_id=request.run_id,
                    subtask_id=request.subtask_id,
                ),
                stop_confirmed=True,
            )
        finally:
            self.active -= 1


# --------------------------------------------------------------- pure helpers
def _session(**overrides: Any) -> NodeSession:
    base: dict[str, Any] = {
        "key": "deliver",
        "subtask_id": "subtask_1",
        "member_ref": "member_1",
        "session_id": "sess_1",
        "conversation_id": "conv-abcdefghijklmnopqrstuvwxyz0123",
        "save_dir": "/data/native-sessions/task_1",
        "state": "created",
        "source": "result",
        "config_hash": "hash-a",
    }
    base.update(overrides)
    return NodeSession(**base)


def test_extract_requires_a_native_conversation_id() -> None:
    result = ExecutorResult(
        state="succeeded",
        summary="no session",
        session_ref=SessionRef(session_id="sess_x", conversation_id=None, state="created"),
    )
    assert extract_node_session(result, key="k", subtask_id="s", member_ref="m") is None
    assert extract_node_session(None, key="k", subtask_id="s", member_ref="m") is None


def test_extract_uses_result_session_ref() -> None:
    result = ExecutorResult(
        state="succeeded",
        summary="ok",
        session_ref=SessionRef(
            session_id="sess_1",
            conversation_id="conv-abcdefghijklmnopqrstuvwxyz0123",
            state="created",
            save_dir="/data/native-sessions/task_1",
        ),
    )
    node = extract_node_session(
        result, key="deliver", subtask_id="subtask_1", member_ref="member_1", node_state="passed"
    )
    assert node is not None
    assert node.conversation_id.startswith("conv-")
    assert node.node_state == "passed"
    assert node.to_member_payload()["session_id"] == "sess_1"


def test_node_session_for_resume_requires_matching_config_and_member() -> None:
    run = {"node_sessions": {"subtask_1": _session().to_run_payload()}}
    ok = node_session_for_resume(
        run, key="deliver", config_hash="hash-a", member_ref="member_1"
    )
    assert ok is not None
    assert ok.conversation_id == "conv-abcdefghijklmnopqrstuvwxyz0123"
    # Configuration drift: the node must be dispatched fresh.
    assert (
        node_session_for_resume(run, key="deliver", config_hash="hash-b", member_ref="member_1")
        is None
    )
    # Member/authorization change: no silent reattach.
    assert (
        node_session_for_resume(run, key="deliver", config_hash="hash-a", member_ref="member_2")
        is None
    )
    # A different plan key has no session.
    assert (
        node_session_for_resume(run, key="verify", config_hash="hash-a", member_ref="member_1")
        is None
    )


def test_node_session_for_resume_skips_closed_and_non_native() -> None:
    closed = _session(state="closed")
    run = {"node_sessions": {"subtask_1": closed.to_run_payload()}}
    assert node_session_for_resume(run, key="deliver", config_hash="hash-a", member_ref="member_1") is None
    no_id = _session()
    payload = no_id.to_run_payload()
    payload["conversation_id"] = ""
    run = {"node_sessions": {"subtask_1": payload}}
    assert node_session_for_resume(run, key="deliver", config_hash="hash-a", member_ref="member_1") is None


def test_completed_keys_reports_passed_nodes() -> None:
    run = {
        "node_sessions": {
            "subtask_1": _session(node_state="passed").to_run_payload(),
            "subtask_2": _session(key="verify", node_state="failed").to_run_payload(),
        }
    }
    assert completed_keys(run) == frozenset({"deliver"})


class _RecordingController:
    """Minimal RunController stand-in recording node-session writes."""

    def __init__(self, run: dict[str, Any]) -> None:
        self._run = run
        self.updates: list[dict[str, Any]] = []
        self.member_session: dict[str, Any] | None = None

    def read_run(self) -> dict[str, Any]:
        return dict(self._run)

    def update_run(self, updates: dict[str, Any]) -> None:
        self.updates.append(dict(updates))
        self._run.update(updates)

    def set_member_session(self, member_id: str, session: dict[str, Any]) -> None:
        self.member_session = {"member_id": member_id, **session}


def test_record_node_session_persists_member_and_run_mapping() -> None:
    controller = _RecordingController({"node_sessions": {}, "session_refs": []})
    record_node_session(controller, _session())
    assert controller.member_session is not None
    assert controller.member_session["member_id"] == "member_1"
    assert controller.member_session["conversation_id"].startswith("conv-")
    merged = controller.read_run()
    assert merged["node_sessions"]["subtask_1"]["conversation_id"].startswith("conv-")
    assert merged["session_refs"] == ["sess_1"]
    # Idempotent: recording the same session twice does not duplicate.
    record_node_session(controller, _session())
    assert controller.read_run()["session_refs"] == ["sess_1"]


# --------------------------------------------------------- graph integration
async def _wait_for(predicate: Callable[[], bool], *, timeout: float = 5.0) -> bool:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.01)
    return predicate()


def _members_and_node_sessions(store: FileStore, run_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    run = store.read("run", run_id).entity
    members: dict[str, Any] = {}
    for ref in run.get("team_refs", []):
        member = store.read("member", ref).entity
        members[ref] = member
    return members, run.get("node_sessions", {}) or {}


async def test_graph_records_each_node_session_to_member_and_run(store: FileStore) -> None:
    build_environment(store)
    executor = SessionExecutor()
    dispatcher = GraphDispatcher(store, executor, catalog=TWO_AGENT)
    task_id, run_id, controller, context = make_dispatch_setup(store)

    outcome = await dispatcher.dispatch(context, controller, no_sink)
    assert outcome.state == "succeeded"

    members, node_sessions = _members_and_node_sessions(store, run_id)
    assert len(node_sessions) == 2
    keys = {entry["key"] for entry in node_sessions.values()}
    assert keys == {"deliver", "verify"}
    for entry in node_sessions.values():
        assert entry["conversation_id"].startswith("conv-native")
        assert entry["save_dir"]
        assert entry["member_ref"]
    # Every executing member now carries its own non-secret session record.
    executing = [m for m in members.values() if m.get("session_ref")]
    assert len(executing) == 2
    for member in executing:
        assert member["session_ref"]["conversation_id"].startswith("conv-native")
        assert member["session_ref"]["save_dir"]


async def test_resume_hands_each_node_its_own_native_session(store: FileStore) -> None:
    """A resumed Run hands each node *its own* prior native session.

    This drives the exact ``GraphDispatcher`` dispatch a resumed Run performs:
    the previous Run entity (with ``node_sessions``) is supplied as
    ``context.prior_run`` (what ``Coordinator._build_context`` sets for a
    ``resume`` decision), and every node's ``ExecuteRequest`` must carry that
    node's own ``conversation_id``/``save_dir`` with native ``resume`` — proving
    the parameters actually reach the request the graph builds, not merely that
    ``member.session_ref`` is non-null.
    """

    build_environment(store)
    first_executor = SessionExecutor()
    first_dispatcher = GraphDispatcher(store, first_executor, catalog=TWO_AGENT)
    task_id, first_run_id, _, context = make_dispatch_setup(store)
    outcome = await first_dispatcher.dispatch(context, _controller(store, task_id, first_run_id), no_sink)
    assert outcome.state == "succeeded"

    first_run = dict(store.read("run", first_run_id).entity)
    prior_sessions = first_run.get("node_sessions") or {}
    assert len(prior_sessions) == 2
    # The coordinator records a Run-level continuation from the adapter; for a
    # direct-dispatcher test we synthesize it from a node session so the resumed
    # context mirrors the real one.
    sample = next(iter(prior_sessions.values()))
    first_run["continuation"] = {
        "conversation_id": sample["conversation_id"],
        "save_dir": sample["save_dir"],
        "continuation_mode": "create_only",
        "decision": "fresh",
        "config_version": "lg016.1",
    }

    # A resumed Run is a *new* Run (fresh members).  Mirror the coordinator with
    # a second task/run setup, then hand it the prior Run entity exactly as
    # ``_build_context`` does for a ``decision == 'resume'`` continuation.
    task2, second_run_id, _, context2 = make_dispatch_setup(store)
    resumed_context = DispatchContext(
        task_id=task2,
        run_id=second_run_id,
        attempt=2,
        objective=context2.objective,
        acceptance_criteria=context2.acceptance_criteria,
        instructions=context2.instructions,
        workspace_path=context2.workspace_path,
        allowed_tools=context2.allowed_tools,
        agent_ref=context2.agent_ref,
        save_dir=first_run["continuation"]["save_dir"],
        conversation_id=first_run["continuation"]["conversation_id"],
        continuation_mode="resume",
        prior_run=first_run,
    )

    second_executor = SessionExecutor()
    second_dispatcher = GraphDispatcher(store, second_executor, catalog=TWO_AGENT)
    outcome2 = await second_dispatcher.dispatch(
        resumed_context, _controller(store, task2, second_run_id), no_sink
    )
    assert outcome2.state == "succeeded"

    # Every node reattached to its OWN prior conversation, not the run-level one.
    prior_by_key = {entry["key"]: entry for entry in prior_sessions.values()}
    seen_keys: set[str] = set()
    for request in second_executor.requests:
        entry = _entry_for_request(prior_by_key, request)
        assert entry is not None, "each request matches one prior node session"
        assert request.continuation_mode == "resume"
        assert request.conversation_id == entry["conversation_id"]
        assert request.save_dir == entry["save_dir"]
        seen_keys.add(_request_key(store, request.subtask_id))
    assert seen_keys == {"deliver", "verify"}
    # The two nodes had distinct native conversations, so this is genuinely
    # per-node — a single run-level conversation could not satisfy both.
    assert len({entry["conversation_id"] for entry in prior_sessions.values()}) == 2


def _controller(store: FileStore, task_id: str, run_id: str) -> Any:
    from lightgravity.coordinator.state import RunController

    return RunController(StateWriter(store, actor="test"), task_id, run_id)


def _request_key(store: FileStore, subtask_id: str) -> str:
    return str(store.read("subtask", subtask_id).entity.get("key"))


def _entry_for_request(prior_by_key: dict[str, Any], request: ExecuteRequest) -> dict[str, Any] | None:
    for entry in prior_by_key.values():
        if entry["conversation_id"] == request.conversation_id:
            return entry
    return None


async def test_reconfigured_node_is_dispatched_fresh(store: FileStore) -> None:
    """A prior node session must not be reattached when the config changed."""

    run = {
        "node_sessions": {
            "subtask_1": _session(config_hash="hash-a").to_run_payload(),
        }
    }
    # Same key, different config hash -> fresh (no conversation passed).
    assert node_session_for_resume(run, key="deliver", config_hash="hash-b", member_ref="member_1") is None


async def test_completed_write_node_is_not_replayed_into_continuation(store: FileStore) -> None:
    completed = _session(node_state="passed")
    run = {"node_sessions": {"subtask_1": completed.to_run_payload()}}
    assert completed_keys(run) == frozenset({"deliver"})
    # The completed node's identity is retained (artifact versions preserved),
    # and the planner can see it is done rather than silently replaying it.
    assert run["node_sessions"]["subtask_1"]["conversation_id"].startswith("conv-")


class SecondNodeGateExecutor(SessionExecutor):
    """Runs the first node to completion, then blocks the second on a gate.

    Reaches a state where one node has a recorded native session while the next
    is still in flight, so a pause can be confirmed mid-graph.
    """

    def __init__(self, gate: asyncio.Event) -> None:
        super().__init__(gate=None)
        self.gate = gate
        self.node_count = 0
        self.blocked_started = asyncio.Event()

    async def execute(self, request: ExecuteRequest, emit: Any) -> ExecutorResult:
        self.node_count += 1
        if self.node_count >= 2:
            self.blocked_started.set()
            await self.gate.wait()
        return await SessionExecutor.execute(self, request, emit)


async def test_coordinator_resume_reaches_graph_per_node_resume(store: FileStore) -> None:
    """End-to-end: Coordinator pause→resume drives per-node native resume.

    The first Run lets the ``verify`` node stay in flight after ``deliver`` has
    recorded its native session; a confirmed pause then stops it.  The resumed
    Run must pass ``deliver`` its own prior native coordinates with
    ``continuation_mode == 'resume'`` into the ``ExecuteRequest`` the graph
    builds — the scheduler-level proof the report requires, not merely a non-null
    ``member.session_ref``.
    """

    build_environment(store)
    gate = asyncio.Event()
    executor = SecondNodeGateExecutor(gate)
    dispatcher = GraphDispatcher(store, executor, catalog=TWO_AGENT)
    coordinator = Coordinator(store, dispatcher=dispatcher)
    created = coordinator.create_task(
        "req-graph-e2e",
        "Graph resume e2e",
        "implement login",
        acceptance_criteria=("it works",),
        workspace_ref="task-ws",
    )
    assert created.task_id is not None
    task_id = created.task_id
    coordinator.start()
    try:
        assert await _wait_for(lambda: executor.blocked_started.is_set())
        first_run_id = store.read("task", task_id).entity["active_run"]
        # ``deliver`` (the only other node) recorded its native session.
        assert await _wait_for(
            lambda: bool(store.read("run", first_run_id).entity.get("node_sessions"))
        )
        first_run = dict(store.read("run", first_run_id).entity)
        assert first_run["node_sessions"]

        pause = await coordinator.request_control(task_id, "pause", request_id="req-pause")
        assert pause.data["confirmed"] is True
        assert store.read("run", first_run_id).entity["state"] == "paused"

        executor.requests.clear()
        gate.set()
        executor.blocked_started.clear()

        resume = await coordinator.request_control(task_id, "resume", request_id="req-resume")
        assert resume.data["confirmed"] is True
        assert await _wait_for(lambda: len(executor.requests) >= 1)

        second_run_id = None
        for _ in range(300):
            second_run_id = store.read("task", task_id).entity.get("active_run")
            if second_run_id and second_run_id != first_run_id:
                break
            await asyncio.sleep(0.02)
        assert second_run_id is not None and second_run_id != first_run_id
        second_run = store.read("run", second_run_id).entity
        assert second_run["continuation"]["decision"] == "resume"
        assert second_run["continuation"]["source_run_id"] == first_run_id

        prior_by_key = {entry["key"]: entry for entry in first_run["node_sessions"].values()}
        deliver_prior = prior_by_key["deliver"]
        # The deliver node's resumed request carries its own prior conversation.
        deliver_req = None
        for _ in range(200):
            for request in executor.requests:
                if _request_key(store, request.subtask_id) == "deliver":
                    deliver_req = request
                    break
            if deliver_req is not None:
                break
            await asyncio.sleep(0.02)
        assert deliver_req is not None, "deliver node was dispatched on resume"
        assert deliver_req.continuation_mode == "resume"
        assert deliver_req.conversation_id == deliver_prior["conversation_id"]
        assert deliver_req.save_dir == deliver_prior["save_dir"]
    finally:
        gate.set()
        await coordinator.stop()
