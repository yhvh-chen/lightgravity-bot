"""Persistent idempotency for messages and Task creation (LG-007)."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor

import pytest

from lightgravity.coordinator import Coordinator

from coordinator_helpers import CONV, FakeExecutor, make_coordinator, message


async def test_global_message_id_is_idempotent(store) -> None:
    coordinator = make_coordinator(store)
    msg = message("你能做什么？", message_id="msg_same")
    first = await coordinator.submit_global_message(CONV, msg)
    second = await coordinator.submit_global_message(CONV, msg)
    assert first.to_dict() == second.to_dict()
    records = coordinator.read_global_messages(CONV)
    # The user message plus exactly one persisted assistant reply (LG-047): a
    # retried message_id never appends a second reply.
    assert [r["message_id"] for r in records] == ["msg_same", "assistant:msg_same"]
    assert records[1]["message"]["role"] == "assistant"


async def test_global_delivery_message_creates_one_task(store) -> None:
    coordinator = make_coordinator(store)
    msg = message("实现新的登录页面", message_id="msg_delivery")
    first = await coordinator.submit_global_message(CONV, msg)
    second = await coordinator.submit_global_message(CONV, msg)
    assert first.task_id == second.task_id
    assert len(coordinator.list_tasks()) == 1
    records = coordinator.read_global_messages(CONV)
    assert [r["message_id"] for r in records] == ["msg_delivery", "assistant:msg_delivery"]
    reply = records[1]["message"]
    assert reply["content"] == first.reply
    assert reply["data"]["task_id"] == first.task_id
    assert reply["data"]["creates_task"] is True
    # Reopening from a fresh coordinator retains the receipt and the replay.
    reopened = make_coordinator(store)
    again = await reopened.submit_global_message(CONV, msg)
    assert again.to_dict() == first.to_dict()
    assert reopened.read_global_messages(CONV) == records


@pytest.mark.parametrize("team_mode", [False, True])
async def test_delivery_retry_after_reply_append_failure_is_durable_and_unique(store, monkeypatch, team_mode) -> None:
    coordinator = make_coordinator(store, team_mode=team_mode)
    msg = message("@bot Implement a login page", message_id="delivery-receipt-retry")
    original = coordinator._persist_assistant_reply

    def append_then_fail(**kwargs):
        original(**kwargs)
        raise RuntimeError("fixture: response interrupted after durable append")

    monkeypatch.setattr(coordinator, "_persist_assistant_reply", append_then_fail)
    with pytest.raises(RuntimeError, match="response interrupted"):
        await coordinator.submit_global_message(CONV, msg)
    assert len(coordinator.list_tasks()) == 1
    reopened = make_coordinator(store, team_mode=team_mode)
    result = await reopened.submit_global_message(CONV, msg)
    replay = await reopened.submit_global_message(CONV, msg)
    assert replay.to_dict() == result.to_dict()
    assert len(reopened.list_tasks()) == 1
    records = reopened.read_global_messages(CONV)
    assert [r["message_id"] for r in records] == [
        "delivery-receipt-retry", "assistant:delivery-receipt-retry",
    ]
    assert records[1]["message"]["content"] == result.reply
    assert records[1]["message"]["data"]["task_id"] == result.task_id
    if team_mode:
        assert records[1]["message"]["author"]["kind"] == "bot"


async def test_task_message_id_is_idempotent(store) -> None:
    coordinator = make_coordinator(store)
    task_id = coordinator.create_task("req-1", "T", "do").task_id
    assert task_id is not None
    msg = message("补充说明", message_id="msg_task_same")
    await coordinator.submit_task_message(task_id, msg)
    await coordinator.submit_task_message(task_id, msg)
    records = coordinator.read_task_messages(task_id)
    # A follow-up note appends only the user row; the duplicate message_id must
    # not append a second one (LG-047 idempotency).
    assert [r["message_id"] for r in records] == ["msg_task_same"]


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
