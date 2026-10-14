"""Single execution slot, Run uniqueness and control lifecycle (LG-007)."""

from __future__ import annotations

import asyncio

import pytest

from lightgravity.contracts import AppError, ErrorCode
from lightgravity.store import FileStore

from coordinator_helpers import FakeExecutor, make_coordinator, message, wait_for_phase


async def test_single_execution_slot(store: FileStore) -> None:
    gate = asyncio.Event()
    executor = FakeExecutor(gate=gate)
    coordinator = make_coordinator(store, executor)
    coordinator.start()
    try:
        first = coordinator.create_task("req-1", "First", "do first").task_id
        second = coordinator.create_task("req-2", "Second", "do second").task_id
        assert first is not None and second is not None
        await asyncio.wait_for(executor.started.wait(), timeout=5)
        # Only the first task is executing; the second stays queued.
        assert coordinator.status(first)["phase"] == "executing"
        assert coordinator.status(second)["phase"] == "queued"
        assert coordinator.status(second)["queue"]["state"] == "queued"
        assert len(executor.requests) == 1

        gate.set()
        await wait_for_phase(coordinator, first, {"verifying", "failed"})
        # The slot is released and the second task is dispatched.
        for _ in range(500):
            if len(executor.requests) == 2:
                break
            await asyncio.sleep(0.01)
        assert len(executor.requests) == 2
        assert coordinator.status(second)["phase"] in {"executing", "verifying", "failed"}
    finally:
        gate.set()
        await coordinator.stop()


async def test_task_cannot_open_second_nonterminal_run(store: FileStore) -> None:
    gate = asyncio.Event()
    executor = FakeExecutor(gate=gate)
    coordinator = make_coordinator(store, executor)
    coordinator.start()
    try:
        task_id = coordinator.create_task("req-u", "T", "do").task_id
        assert task_id is not None
        await asyncio.wait_for(executor.started.wait(), timeout=5)
        with pytest.raises(AppError) as excinfo:
            coordinator._open_run(store.read("task", task_id))
        assert excinfo.value.code == ErrorCode.ILLEGAL_TRANSITION
    finally:
        gate.set()
        await coordinator.stop()


async def test_failed_outcome_clears_active_run(store: FileStore) -> None:
    executor = FakeExecutor(state="failed")
    coordinator = make_coordinator(store, executor)
    coordinator.start()
    try:
        task_id = coordinator.create_task("req-f", "T", "do").task_id
        assert task_id is not None
        await wait_for_phase(coordinator, task_id, {"failed", "verifying"})
        snapshot = coordinator.status(task_id)
        assert snapshot["phase"] == "failed"
        assert snapshot["active_run"] is None
        assert snapshot["queue"]["state"] == "not_queued"
    finally:
        await coordinator.stop()


async def test_cancel_during_execution_confirms_stop(store: FileStore) -> None:
    gate = asyncio.Event()
    executor = FakeExecutor(gate=gate)
    coordinator = make_coordinator(store, executor)
    coordinator.start()
    try:
        task_id = coordinator.create_task("req-c", "T", "do").task_id
        assert task_id is not None
        await asyncio.wait_for(executor.started.wait(), timeout=5)
        result = await asyncio.wait_for(
            coordinator.request_control(task_id, "cancel", request_id="req-cancel"),
            timeout=5,
        )
        assert result.data["confirmed"] is True
        snapshot = coordinator.status(task_id)
        assert snapshot["phase"] == "cancelled"
        assert snapshot["active_run"] is None
        # The worker loop survives and can still process new work.
        assert coordinator.active_run_id is None
    finally:
        gate.set()
        await coordinator.stop()


async def test_cancel_message_flows_through_task_conversation(store: FileStore) -> None:
    gate = asyncio.Event()
    executor = FakeExecutor(gate=gate)
    coordinator = make_coordinator(store, executor)
    coordinator.start()
    try:
        task_id = coordinator.create_task("req-cm", "T", "do").task_id
        assert task_id is not None
        await asyncio.wait_for(executor.started.wait(), timeout=5)
        result = await coordinator.submit_task_message(
            task_id, message("取消", message_id="msg-cancel")
        )
        assert result.kind == "control"
        assert coordinator.status(task_id)["phase"] == "cancelled"
    finally:
        gate.set()
        await coordinator.stop()
