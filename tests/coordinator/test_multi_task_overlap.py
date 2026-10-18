"""LG-126 multi-Task overlap, honest queuing, isolation and stop scoping."""

from __future__ import annotations

import asyncio
from typing import Any

from lightgravity.adapter import (
    AdapterCapabilities,
    CancelResult,
    ExecuteRequest,
    ExecutionRef,
    ExecutorResult,
    SessionRef,
    adapter_capabilities,
)
from lightgravity.coordinator import (
    Coordinator,
    DispatchContext,
    GraphDispatcher,
    PlanProposal,
    RawSubtask,
    RoleCatalog,
)
from lightgravity.coordinator.capacity import CapacityConfig
from lightgravity.store import FileStore

from graph_helpers import build_environment

TWO_AGENT = RoleCatalog(
    {"implementation": ["developer"], "verification": ["verifier"]}
)


class TwoReadPlan:
    """Two independent read nodes per Task to exercise the global session cap."""

    name = "two-read"

    async def plan(self, context: DispatchContext) -> PlanProposal:
        return PlanProposal(
            subtasks=(
                RawSubtask(
                    key="read-a",
                    objective=f"read first part of {context.objective}",
                    capability="implementation",
                    acceptance=("read a",),
                    write=False,
                ),
                RawSubtask(
                    key="read-b",
                    objective=f"read second part of {context.objective}",
                    capability="implementation",
                    acceptance=("read b",),
                    write=False,
                ),
            ),
            source="test",
        )


class BarrierExecutor:
    """Deterministic executor barrier used to prove real event-loop overlap."""

    name = "barrier"
    version = "0"

    def __init__(self) -> None:
        self.requests: list[ExecuteRequest] = []
        self.active = 0
        self.peak = 0
        self.started: dict[str, asyncio.Event] = {}
        self.release: dict[str, asyncio.Event] = {}

    def capabilities(self) -> AdapterCapabilities:
        return adapter_capabilities()

    async def execute(
        self, request: ExecuteRequest, emit: Any
    ) -> ExecutorResult:
        self.requests.append(request)
        self.active += 1
        self.peak = max(self.peak, self.active)
        self.started.setdefault(request.task_id, asyncio.Event()).set()
        gate = self.release.setdefault(request.task_id, asyncio.Event())
        try:
            await gate.wait()
        finally:
            self.active -= 1
        return ExecutorResult(
            state="succeeded",
            summary=f"barrier:{request.task_id}",
            execution_ref=ExecutionRef(
                execution_id=f"exec_{request.run_id}_{request.subtask_id}",
                task_id=request.task_id,
                run_id=request.run_id,
                subtask_id=request.subtask_id,
            ),
            stop_confirmed=True,
        )

    async def cancel(self, execution_ref: ExecutionRef) -> CancelResult:
        return CancelResult(confirmed=True, state="cancelled", reason="barrier")

    async def close(self, session_ref: SessionRef) -> None:
        return None

    async def wait_started(self, task_id: str, timeout: float = 5.0) -> None:
        event = self.started.setdefault(task_id, asyncio.Event())
        await asyncio.wait_for(event.wait(), timeout=timeout)


def _task(coordinator: Coordinator, request_id: str, workspace: str) -> str:
    result = coordinator.create_task(
        request_id,
        f"Task {request_id}",
        f"implement known output for {request_id}",
        workspace_ref=workspace,
    )
    assert result.task_id is not None
    return result.task_id


def _make(store: FileStore, executor: BarrierExecutor) -> Coordinator:
    dispatcher = GraphDispatcher(
        store, executor, catalog=TWO_AGENT, max_parallel=2
    )
    return Coordinator(
        store,
        dispatcher=dispatcher,
        capacity=CapacityConfig(2, 3, 1, 2),
        poll_interval=0.01,
    )


async def _wait_reason(store: FileStore, task_id: str, reason: str) -> bool:
    for _ in range(500):
        task = store.read("task", task_id).entity
        run_id = task.get("active_run")
        if isinstance(run_id, str) and run_id:
            try:
                run = store.read("run", run_id).entity
            except Exception:  # noqa: BLE001 - run may not exist yet
                run = {}
            for subtask_ref in run.get("subtask_refs") or []:
                try:
                    subtask = store.read("subtask", subtask_ref).entity
                except Exception:  # noqa: BLE001 - still being materialized
                    continue
                if subtask.get("waiting_reason") == reason:
                    return True
        await asyncio.sleep(0.01)
    return False


async def test_two_tasks_actually_overlap_then_third_queues_and_cancel_scopes(
    store: FileStore,
) -> None:
    build_environment(store)
    for name in ("ws-a", "ws-b", "ws-c"):
        store.resolve_path(name, write=True).mkdir(parents=True, exist_ok=True)
    executor = BarrierExecutor()
    coordinator = _make(store, executor)
    coordinator.start()
    try:
        first = _task(coordinator, "first", "ws-a")
        second = _task(coordinator, "second", "ws-b")
        third = _task(coordinator, "third", "ws-c")
        await executor.wait_started(first)
        await executor.wait_started(second)
        # Both executors are simultaneously blocked inside execute(): genuine
        # overlap, not a queued/serial pair.
        assert executor.peak >= 2
        assert len(executor.requests) == 2
        assert coordinator.status(third)["phase"] == "queued"
        assert coordinator.status(third)["queue"]["waiting_reason"] == "active_task_limit"
        snapshot = coordinator.capacity_snapshot()
        assert snapshot["admitted_count"] == 2
        assert set(snapshot["active_tasks"]) == {first, second}
        assert snapshot["session_count"] == 2

        cancelled = await coordinator.request_control(
            first, "cancel", request_id="cancel-first"
        )
        assert cancelled.data["confirmed"] is True
        assert coordinator.status(first)["phase"] == "cancelled"
        # B keeps running under its own Run/workspace/session.
        assert coordinator.status(second)["phase"] == "executing"
        assert coordinator.status(second)["active_run"] is not None

        executor.release[second].set()
        await executor.wait_started(third)
        assert coordinator.status(third)["phase"] == "executing"
        assert executor.release.get(third) is not None
    finally:
        for gate in executor.release.values():
            gate.set()
        await coordinator.stop()


async def test_same_canonical_workspace_writer_is_serialized_across_tasks(
    store: FileStore,
) -> None:
    build_environment(store)
    store.resolve_path("shared-ws", write=True).mkdir(parents=True, exist_ok=True)
    executor = BarrierExecutor()
    coordinator = _make(store, executor)
    coordinator.start()
    try:
        first = _task(coordinator, "writer-a", "shared-ws")
        second = _task(coordinator, "writer-b", "shared-ws")
        await executor.wait_started(first)
        assert second not in executor.started
        assert await _wait_reason(store, second, "workspace_write_conflict")
        assert executor.peak == 1
        executor.release[first].set()
        await executor.wait_started(second)
        assert executor.peak == 1
    finally:
        for gate in executor.release.values():
            gate.set()
        await coordinator.stop()


async def test_global_session_pool_starts_three_and_queues_the_fourth_node(
    store: FileStore,
) -> None:
    build_environment(store)
    for name in ("session-a", "session-b"):
        store.resolve_path(name, write=True).mkdir(parents=True, exist_ok=True)
    executor = BarrierExecutor()
    dispatcher = GraphDispatcher(
        store, executor, catalog=TWO_AGENT, max_parallel=2
    )
    # The program planner remains the product default; this test substitutes a
    # deterministic two-node plan only to observe the 3-session global cap.
    dispatcher._program_planner = TwoReadPlan()  # type: ignore[assignment]
    coordinator = Coordinator(
        store,
        dispatcher=dispatcher,
        capacity=CapacityConfig(2, 3, 1, 2),
        poll_interval=0.01,
    )
    coordinator.start()
    try:
        first = _task(coordinator, "session-a", "session-a")
        second = _task(coordinator, "session-b", "session-b")
        for _ in range(600):
            if len(executor.requests) >= 3:
                break
            await asyncio.sleep(0.01)
        assert len(executor.requests) == 3
        assert executor.peak == 3
        snapshot = coordinator.capacity_snapshot()
        assert snapshot["session_count"] == 3
        assert await _wait_reason(store, first, "global_session_limit") or await _wait_reason(
            store, second, "global_session_limit"
        )
        executor.release[first].set()
        for _ in range(600):
            if len(executor.requests) >= 4:
                break
            await asyncio.sleep(0.01)
        assert len(executor.requests) == 4
    finally:
        for gate in executor.release.values():
            gate.set()
        await coordinator.stop()
