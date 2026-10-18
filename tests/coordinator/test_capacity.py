"""LG-126 global capacity: config, slots, unknown-stop and restart truth."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from lightgravity.adapter import CancelResult, ExecuteRequest
from lightgravity.config import Settings
from lightgravity.coordinator import Coordinator, GraphDispatcher, RoleCatalog
from lightgravity.coordinator.capacity import CapacityConfig, CapacityGovernor
from lightgravity.coordinator.dispatcher import DispatchContext, DispatchOutcome
from lightgravity.coordinator.state import RunController
from lightgravity.store import ConfigInvalid, FileStore

from graph_helpers import FakeGraphExecutor, build_environment, make_dispatch_setup


def test_capacity_defaults_and_env_validation() -> None:
    config = CapacityConfig.from_env({})
    assert config.to_dict() == {
        "max_active_tasks": 2,
        "max_global_sessions": 3,
        "max_reviewer_sessions": 1,
        "max_parallel_nodes_per_task": 2,
    }

    with pytest.raises(ConfigInvalid) as excinfo:
        Settings.from_env(
            {
                "LIGHTGRAVITY_MAX_ACTIVE_TASKS": "3",
                "LIGHTGRAVITY_MAX_GLOBAL_SESSIONS": "3",
                "LIGHTGRAVITY_MAX_REVIEWER_SESSIONS": "1",
            }
        )
    assert excinfo.value.code.value == "config_invalid"

    with pytest.raises(ConfigInvalid):
        Settings.from_env({"LIGHTGRAVITY_MAX_GLOBAL_SESSIONS": "0"})
    with pytest.raises(ConfigInvalid):
        Settings.from_env(
            {
                "LIGHTGRAVITY_MAX_GLOBAL_SESSIONS": "2",
                "LIGHTGRAVITY_MAX_REVIEWER_SESSIONS": "3",
            }
        )


async def test_governor_reviewer_subcap_and_global_session_pool() -> None:
    governor = CapacityGovernor(CapacityConfig(2, 3, 1, 2))
    first = governor.try_acquire_session("task_a", kind="reviewer")
    assert first is not None
    # Reviewer sub-cap is one; the global pool still has room for workers.
    assert governor.try_acquire_session("task_b", kind="reviewer") is None
    worker = governor.try_acquire_session("task_b", kind="worker")
    assert worker is not None
    worker2 = governor.try_acquire_session("task_c", kind="worker")
    assert worker2 is not None
    # Global pool is full (reviewer + two workers).
    assert governor.try_acquire_session("task_d", kind="worker") is None
    governor.release_session(worker)
    await asyncio.wait_for(
        governor.acquire_session("task_d", kind="worker"), timeout=1.0
    )
    snapshot = governor.snapshot()
    assert snapshot.reviewer_sessions == 1
    assert snapshot.session_count == 3


def test_governor_writer_lock_is_cross_task_and_canonical(tmp_path: Any) -> None:
    governor = CapacityGovernor(CapacityConfig())
    root = tmp_path / "ws"
    root.mkdir()
    first = governor.try_acquire_writer(task_id="task_a", run_id="run_a", path=str(root))
    assert first is not None
    assert governor.try_acquire_writer(
        task_id="task_b", run_id="run_b", path=str(root / ".")
    ) is None
    assert governor.writer_conflict(
        task_id="task_b", run_id="run_b", path=str(root / "..//ws")
    )
    assert governor.release_writer(first)
    second = governor.try_acquire_writer(
        task_id="task_b", run_id="run_b", path=str(root)
    )
    assert second is not None


class UnconfirmedCancelDispatcher:
    """Dispatcher whose stop is unknown: the run must keep its resources."""

    name = "unconfirmed"

    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.cancel_calls = 0

    async def dispatch(
        self, context: DispatchContext, controller: RunController, emit: Any
    ) -> DispatchOutcome:
        controller.set_task_phase("recruiting")
        controller.set_run_state("recruiting")
        controller.set_task_phase("executing")
        controller.set_run_state("executing")
        self.started.set()
        await asyncio.Event().wait()
        return DispatchOutcome(state="succeeded", summary="unreachable")

    async def cancel(self, task_id: str, run_id: str) -> CancelResult:
        self.cancel_calls += 1
        return CancelResult(
            confirmed=False,
            state="unconfirmed",
            reason="adapter could not prove the stop",
        )


async def test_unknown_stop_keeps_task_admission(store: FileStore) -> None:
    dispatcher = UnconfirmedCancelDispatcher()
    coordinator = Coordinator(store, dispatcher=dispatcher)
    coordinator.start()
    try:
        task_id = coordinator.create_task("req-u", "Unknown stop", "do work").task_id
        assert task_id is not None
        await asyncio.wait_for(dispatcher.started.wait(), timeout=5)
        result = await coordinator.request_control(
            task_id, "cancel", request_id="cancel-u"
        )
        assert result.data["confirmed"] is False
        assert coordinator.status(task_id)["phase"] == "cancelling"
        snapshot = coordinator.capacity_snapshot()
        assert snapshot["active_tasks"] == [task_id]
        assert snapshot["admitted_count"] == 1
    finally:
        await coordinator.stop()


async def test_restart_recovery_precedes_admission_and_never_replays(
    store: FileStore,
) -> None:
    build_environment(store)
    task_id, run_id, controller, _context = make_dispatch_setup(store)
    controller.set_task_phase("recruiting")
    controller.set_run_state("recruiting")
    controller.set_task_phase("executing")
    controller.set_run_state("executing")
    executor = FakeGraphExecutor()
    dispatcher = GraphDispatcher(
        store,
        executor,
        catalog=RoleCatalog(
            {"implementation": ["developer"], "verification": ["verifier"]}
        ),
    )
    coordinator = Coordinator(store, dispatcher=dispatcher)

    report = coordinator.run_recovery_scan()
    assert any(item.task_id == task_id for item in report.recovery_required)
    assert store.read("task", task_id).entity["phase"] == "recovery_required"
    assert coordinator.capacity_snapshot()["admitted_count"] == 0

    coordinator.start()
    try:
        await asyncio.sleep(0.15)
        # The interrupted Run is not replayed; it waits for a human decision.
        assert executor.requests == []
        assert store.read("run", run_id).entity["state"] == "executing"
        assert coordinator.capacity_snapshot()["active_tasks"] == []

        workspace = store.resolve_path("fresh-ws", write=True)
        workspace.mkdir(parents=True, exist_ok=True)
        fresh = coordinator.create_task(
            "req-fresh", "Fresh", "implement fresh", workspace_ref="fresh-ws"
        ).task_id
        assert fresh is not None
        for _ in range(300):
            if executor.requests:
                break
            await asyncio.sleep(0.01)
        assert [request.task_id for request in executor.requests] == [fresh]
        assert coordinator.capacity_snapshot()["active_tasks"] == [fresh]
    finally:
        await coordinator.stop()
