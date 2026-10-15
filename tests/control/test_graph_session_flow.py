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
    """A resumed Run hands its in-flight node *its own* prior native session.

    This drives the exact ``GraphDispatcher`` dispatch a resumed Run performs:
    the previous Run entity (with ``node_sessions``) is supplied as
    ``context.prior_run`` (what ``Coordinator._build_context`` sets for a
    ``resume`` decision).  Only a node that had **not** completed may be
    re-dispatched, and its ``ExecuteRequest`` must carry that node's own
    ``conversation_id``/``save_dir`` with native ``resume`` — proving the
    parameters actually reach the request the graph builds, not merely that
    ``member.session_ref`` is non-null.

    The first node (``deliver``) completes and writes; the second (``verify``)
    is held in flight and then stopped.  On resume, ``deliver`` must **not** be
    re-executed (its side effect already happened); only ``verify`` reattaches.
    """

    build_environment(store)
    gate = asyncio.Event()
    first_executor = SecondNodeGateExecutor(gate)
    first_dispatcher = GraphDispatcher(store, first_executor, catalog=TWO_AGENT)
    task_id, first_run_id, _, context = make_dispatch_setup(store)
    first_controller = _controller(store, task_id, first_run_id)
    dispatch_task = asyncio.ensure_future(first_dispatcher.dispatch(context, first_controller, no_sink))
    assert await _wait_for(lambda: first_executor.blocked_started.is_set())
    assert await _wait_for(
        lambda: bool(store.read("run", first_run_id).entity.get("node_sessions"))
    )
    # Stop the first Run while ``verify`` is still in flight.
    await first_dispatcher.cancel(task_id, first_run_id)
    gate.set()
    try:
        await dispatch_task
    except Exception:  # noqa: BLE001 - stopping is expected to interrupt the graph
        pass

    first_run = dict(store.read("run", first_run_id).entity)
    prior_sessions = first_run.get("node_sessions") or {}
    # Only the completed ``deliver`` node recorded a session; ``verify`` was
    # still in flight and produced none.
    prior_by_key = {entry["key"]: entry for entry in prior_sessions.values()}
    assert "deliver" in prior_by_key

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
        save_dir=context2.save_dir,
        conversation_id=context2.conversation_id,
        continuation_mode="resume",
        prior_run=first_run,
    )

    second_executor = SessionExecutor()
    second_dispatcher = GraphDispatcher(store, second_executor, catalog=TWO_AGENT)
    outcome2 = await second_dispatcher.dispatch(
        resumed_context, _controller(store, task2, second_run_id), no_sink
    )
    assert outcome2.state == "succeeded"

    # The completed write node ``deliver`` was **not** re-executed; only the
    # in-flight ``verify`` node was dispatched.
    dispatched_keys = {_request_key(store, request.subtask_id) for request in second_executor.requests}
    assert "deliver" not in dispatched_keys
    assert "verify" in dispatched_keys


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
    """End-to-end: Coordinator pause→resume never replays a completed write node.

    The first Run lets ``deliver`` complete (recording a write handoff) while the
    ``verify`` node stays in flight; a confirmed pause stops it.  On resume the
    completed ``deliver`` node must be reused from its verified checkpoint (its
    side effect already happened) and must **not** be re-executed.  Only the
    never-completed ``verify`` node is dispatched again.  This is the
    scheduler-level anti-replay proof.
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
        # ``deliver`` (the only other node) recorded its native session + handoff.
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

        # The completed write node ``deliver`` is never re-dispatched on resume.
        resumed_keys = {
            _request_key(store, request.subtask_id) for request in executor.requests
        }
        assert "deliver" not in resumed_keys
        # ``deliver`` is recorded passed on the resumed Run via checkpoint reuse
        # (its side effect already happened), not re-executed.
        deliver_reused = None
        for ref in second_run.get("subtask_refs", []):
            entity = store.read("subtask", ref).entity
            if entity.get("key") == "deliver":
                deliver_reused = entity
                break
        assert deliver_reused is not None
        assert deliver_reused.get("state") == "passed"
        assert "reused" in str(deliver_reused.get("skip_reason", ""))
    finally:
        gate.set()
        await coordinator.stop()


# ------------------------------------------------ stable reuse identity (LG-016)
class _SingleNodePlanner:
    """Deterministic one-node plan for stable-identity integration checks."""

    name = "single-node"

    async def plan(self, context: DispatchContext) -> PlanProposal:
        return PlanProposal(
            subtasks=(
                RawSubtask(
                    key="deliver",
                    objective="write the change",
                    capability="implementation",
                    acceptance=("done",),
                    write=True,
                ),
            ),
            source="test",
        )


async def _run_single_node(
    store: FileStore, *, conversation_id: str, save_dir: str
) -> str:
    """Dispatch the one-node plan and return the persisted ``reuse_identity``."""

    task_id, run_id, controller, base = make_dispatch_setup(store)
    context = DispatchContext(
        task_id=task_id,
        run_id=run_id,
        attempt=1,
        objective=base.objective,
        acceptance_criteria=base.acceptance_criteria,
        instructions=base.instructions,
        workspace_path=base.workspace_path,
        allowed_tools=base.allowed_tools,
        agent_ref=base.agent_ref,
        save_dir=save_dir,
        conversation_id=conversation_id,
    )
    dispatcher = GraphDispatcher(
        store, SessionExecutor(), planner=_SingleNodePlanner(), catalog=TWO_AGENT
    )
    outcome = await dispatcher.dispatch(context, controller, no_sink)
    assert outcome.state == "succeeded"
    run = store.read("run", run_id).entity
    subtask_id = run["subtask_refs"][0]
    entity = store.read("subtask", subtask_id).entity
    return str(entity["reuse_identity"])


async def test_reuse_identity_stable_across_conversation_coordinate_change(
    store: FileStore,
) -> None:
    """Real compiler: a resume-coordinate change is NOT a config drift.

    The member's compiled ``config_hash`` folds in the session profile's
    ``conversation_id`` (``CompiledAgentConfig``), so it necessarily changes on
    every resume — comparing it can *never* prove reuse.  The persisted stable
    ``reuse_identity`` must be unchanged when only the continuation coordinate
    moves, while a genuine permission change must still change it.  This drives
    the real ``GraphDispatcher`` + real ``ResourceCompiler``; a fake compiler
    with a fixed hash would hide the bug.
    """

    build_environment(store)
    identity_a = await _run_single_node(
        store, conversation_id="conv-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", save_dir="/tmp/native/a"
    )
    identity_b = await _run_single_node(
        store, conversation_id="conv-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", save_dir="/tmp/native/b"
    )
    assert identity_a
    assert identity_a == identity_b, "moving only the resume coordinate must not drift the identity"

    # A genuine permission/config change *does* change the identity.  Use a
    # separate store so the narrowed tool policy is a fresh, clean environment.
    import tempfile
    from pathlib import Path as _Path

    other_root = _Path(tempfile.mkdtemp())
    narrowed_store = FileStore(other_root / "data", other_root / "ws")
    build_environment(narrowed_store, tool_refs=("view-file",))
    identity_narrowed = await _run_single_node(
        narrowed_store,
        conversation_id="conv-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        save_dir="/tmp/native/a",
    )
    assert identity_narrowed != identity_a, "a permission change must change the identity"


async def test_no_trusted_reuse_blocks_resume_without_redispatch(store: FileStore) -> None:
    """A completed write node with no trusted reuse fails closed, never replays.

    The prior Run recorded ``deliver`` as ``passed`` but with no persisted
    artifact handoff (e.g. an interrupted/unknown-side-effect write).  Resume
    must neither silently re-execute ``deliver`` (replaying a possibly-written
    side effect) nor pretend it succeeded via an untrusted fresh Run: it fails
    with an explicit ``recovery_required`` decision and dispatches nothing.
    """

    build_environment(store)
    gate = asyncio.Event()
    executor = SecondNodeGateExecutor(gate)
    first_dispatcher = GraphDispatcher(store, executor, catalog=TWO_AGENT)
    task_id, first_run_id, _, context = make_dispatch_setup(store)
    dispatch_task = asyncio.ensure_future(
        first_dispatcher.dispatch(context, _controller(store, task_id, first_run_id), no_sink)
    )
    assert await _wait_for(lambda: executor.blocked_started.is_set())
    assert await _wait_for(
        lambda: bool(store.read("run", first_run_id).entity.get("node_sessions"))
    )
    await first_dispatcher.cancel(task_id, first_run_id)
    gate.set()
    try:
        await dispatch_task
    except Exception:  # noqa: BLE001 - stopping interrupts the graph
        pass

    first_run = dict(store.read("run", first_run_id).entity)
    # Strip the trusted handoff from the completed write node's record so reuse
    # cannot be proven (the pre-LG-016 / unknown-side-effect case).
    node_sessions = dict(first_run.get("node_sessions") or {})
    for entry in node_sessions.values():
        entry.pop("handoff", None)
    first_run["node_sessions"] = node_sessions

    task2, second_run_id, controller2, base2 = make_dispatch_setup(store)
    resumed_context = DispatchContext(
        task_id=task2,
        run_id=second_run_id,
        attempt=2,
        objective=base2.objective,
        acceptance_criteria=base2.acceptance_criteria,
        instructions=base2.instructions,
        workspace_path=base2.workspace_path,
        allowed_tools=base2.allowed_tools,
        agent_ref=base2.agent_ref,
        save_dir=base2.save_dir,
        conversation_id=base2.conversation_id,
        continuation_mode="resume",
        prior_run=first_run,
    )
    second_executor = SessionExecutor()
    second_dispatcher = GraphDispatcher(store, second_executor, catalog=TWO_AGENT)
    outcome = await second_dispatcher.dispatch(resumed_context, controller2, no_sink)

    assert outcome.state == "recovery_required"
    assert outcome.failure_code == "recovery_required"
    # No node — especially not the completed write node ``deliver`` — was run.
    assert second_executor.requests == []


async def test_coordinator_resume_without_trusted_reuse_fails_closed(
    store: FileStore,
) -> None:
    """End-to-end: an unpovavable completed write node blocks the resume.

    First Run: ``deliver`` completes (writes) while ``verify`` is in flight; a
    confirmed pause stops the Run.  The completed node's trusted handoff is then
    removed (simulating a pre-LG-016 record / unknown side effect).  Resume must
    fail closed with an explicit ``recovery_required`` decision and must not
    re-dispatch ``deliver``.
    """

    build_environment(store)
    gate = asyncio.Event()
    executor = SecondNodeGateExecutor(gate)
    dispatcher = GraphDispatcher(store, executor, catalog=TWO_AGENT)
    coordinator = Coordinator(store, dispatcher=dispatcher)
    created = coordinator.create_task(
        "req-guard",
        "Guard resume",
        "implement",
        acceptance_criteria=("ok",),
        workspace_ref="task-ws",
    )
    assert created.task_id is not None
    task_id = created.task_id
    coordinator.start()
    try:
        assert await _wait_for(lambda: executor.blocked_started.is_set())
        first_run_id = store.read("task", task_id).entity["active_run"]
        assert await _wait_for(
            lambda: bool(store.read("run", first_run_id).entity.get("node_sessions"))
        )
        first_run = dict(store.read("run", first_run_id).entity)

        # Remove the trusted handoff from the completed write node's record.
        # ``Store.write`` deep-merges, so explicitly blank the handoff fields
        # (an empty content hash / no artifact refs cannot prove reuse).
        node_sessions = dict(first_run.get("node_sessions") or {})
        for subtask_ref, entry in node_sessions.items():
            if isinstance(entry, dict):
                entry["handoff"] = {"content_hash": "", "artifacts": []}
        StateWriter(store, actor="test").write_run(
            first_run_id, {"node_sessions": node_sessions}
        )

        pause = await coordinator.request_control(task_id, "pause", request_id="req-pause")
        assert pause.data["confirmed"] is True

        executor.requests.clear()
        gate.set()
        executor.blocked_started.clear()
        resume = await coordinator.request_control(task_id, "resume", request_id="req-resume")
        assert resume.data["confirmed"] is True

        # The resumed Run ends in an explicit recovery decision; Task is parked.
        for _ in range(300):
            task = store.read("task", task_id).entity
            if task.get("phase") == "recovery_required":
                break
            await asyncio.sleep(0.02)
        assert store.read("task", task_id).entity.get("phase") == "recovery_required"
        # No node (especially not the completed write node) was re-executed.
        assert all(
            _request_key(store, r.subtask_id) != "deliver" for r in executor.requests
        ), "the completed write node must never be re-dispatched"
    finally:
        gate.set()
        await coordinator.stop()
