"""Persistent idempotency for messages and Task creation (LG-007)."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor

from lightgravity.coordinator import Coordinator

from coordinator_helpers import CONV, FakeExecutor, make_coordinator, message


async def test_global_message_id_is_idempotent(store) -> None:
    coordinator = make_coordinator(store)
    msg = message("你能做什么？", message_id="msg_same")
    first = await coordinator.submit_global_message(CONV, msg)
    second = await coordinator.submit_global_message(CONV, msg)
    assert first.to_dict() == second.to_dict()
    records = coordinator.read_global_messages(CONV)
    assert len(records) == 1
    assert records[0]["message_id"] == "msg_same"


async def test_global_delivery_message_creates_one_task(store) -> None:
    coordinator = make_coordinator(store)
    msg = message("实现新的登录页面", message_id="msg_delivery")
    first = await coordinator.submit_global_message(CONV, msg)
    second = await coordinator.submit_global_message(CONV, msg)
    assert first.task_id == second.task_id
    assert len(coordinator.list_tasks()) == 1


async def test_task_message_id_is_idempotent(store) -> None:
    coordinator = make_coordinator(store)
    task_id = coordinator.create_task("req-1", "T", "do").task_id
    assert task_id is not None
    msg = message("补充说明", message_id="msg_task_same")
    await coordinator.submit_task_message(task_id, msg)
    await coordinator.submit_task_message(task_id, msg)
    records = coordinator.read_task_messages(task_id)
    assert len(records) == 1


async def test_duplicate_task_message_does_not_repeat_control(store) -> None:
    # A duplicate 'cancel' message must not re-trigger a second control action.
    executor = FakeExecutor(gate=asyncio.Event())
    coordinator = make_coordinator(store, executor)
    coordinator.start()
    try:
        task_id = coordinator.create_task("req-c", "T", "do").task_id
        assert task_id is not None
        await asyncio.wait_for(executor.started.wait(), timeout=5)
        cancel = message("取消", message_id="msg_cancel")
        await coordinator.submit_task_message(task_id, cancel)
        await coordinator.submit_task_message(task_id, cancel)
        # The idempotency record holds the first result; state stays cancelled.
        assert coordinator.status(task_id)["phase"] == "cancelled"
    finally:
        await coordinator.stop()


def test_create_task_request_id_is_idempotent_concurrently(store) -> None:
    coordinator = make_coordinator(store)

    def call() -> str | None:
        return coordinator.create_task("req-shared", "T", "do").task_id

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: call(), range(4)))
    assert len(set(results)) == 1
    assert len(coordinator.list_tasks()) == 1


async def test_idempotency_persists_across_coordinator_instances(store) -> None:
    first = make_coordinator(store)
    created = first.create_task("req-persist", "T", "do")
    second = Coordinator(store)
    again = second.create_task("req-persist", "T", "do")
    assert created.task_id == again.task_id
