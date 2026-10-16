"""Coordinator routing, persistence and non-blocking queries (LG-007)."""

from __future__ import annotations

import asyncio

from lightgravity.store import FileStore

from coordinator_helpers import CONV, FakeExecutor, make_coordinator, message, raw_task, wait_for_phase


async def test_global_and_task_messages_are_persisted(store: FileStore) -> None:
    coordinator = make_coordinator(store)
    await coordinator.submit_global_message(CONV, message("你好", message_id="msg-g1"))
    records = coordinator.read_global_messages(CONV)
    # The user message and its persisted assistant reply (LG-047 QA-R1).
    assert [r["message_id"] for r in records] == ["msg-g1", "assistant:msg-g1"]
    # Persisted on disk in the documented global-conversation location.
    path = store.data_dir / "conversations" / CONV / "messages.jsonl"
    assert path.is_file()

    task_id = coordinator.create_task("req-t", "T", "do").task_id
    assert task_id is not None
    await coordinator.submit_task_message(task_id, message("补充", message_id="msg-t1"))
    task_records = coordinator.read_task_messages(task_id)
    # A follow-up note is not a direct/bounded-read turn, so only the user row
    # is recorded here (the assistant reply path is exercised in test_dialogue).
    assert [r["message_id"] for r in task_records] == ["msg-t1"]


async def test_readonly_request_creates_no_task(store: FileStore) -> None:
    coordinator = make_coordinator(store)
    result = await coordinator.submit_global_message(CONV, message("读这个文件并解释", message_id="msg-r1"))
    assert result.kind == "bounded_read"
    assert result.task_id is None
    assert result.data["creates_task"] is False
    assert len(coordinator.list_tasks()) == 0


async def test_query_does_not_wait_for_running_task(store: FileStore) -> None:
    gate = asyncio.Event()
    executor = FakeExecutor(gate=gate)
    coordinator = make_coordinator(store, executor)
    coordinator.start()
    try:
        task_id = coordinator.create_task("req-q", "T", "do").task_id
        assert task_id is not None
        await asyncio.wait_for(executor.started.wait(), timeout=5)
        assert coordinator.status(task_id)["phase"] == "executing"

        # A status query returns immediately even though the executor is blocked.
        query = await asyncio.wait_for(
            coordinator.submit_task_message(task_id, message("进度如何？", message_id="msg-q1")),
            timeout=1,
        )
        assert query.kind == "query"
        assert query.data["phase"] == "executing"
        # The query did not create another Run.
        assert coordinator.status(task_id)["active_run"] is not None

        gate.set()
        # LG-017 R1 honest default: no real independent reviewer is configured in
        # this unit test, so an unreviewed candidate parks at ``waiting_user``
        # instead of being silently accepted by a machine gate.
        final = await wait_for_phase(coordinator, task_id, {"verifying", "waiting_user", "failed"})
        assert final in {"verifying", "waiting_user"}
    finally:
        await coordinator.stop()


async def test_global_control_with_two_active_tasks_is_ambiguous(store: FileStore) -> None:
    coordinator = make_coordinator(store)
    raw_task(store, status="in-progress", phase="executing")
    raw_task(store, status="in-progress", phase="executing")
    result = await coordinator.submit_global_message(CONV, message("取消", message_id="msg-amb"))
    assert result.kind == "clarify"
    assert len(result.candidates) == 2
    assert result.data["ambiguous"] is True


async def test_global_control_with_no_target_is_clarify(store: FileStore) -> None:
    coordinator = make_coordinator(store)
    result = await coordinator.submit_global_message(CONV, message("取消", message_id="msg-none"))
    assert result.kind == "clarify"
    assert result.candidates == ()


async def test_worker_survives_request_completion(store: FileStore) -> None:
    """The worker is a background task; returning from the request does not stop it."""

    gate = asyncio.Event()
    executor = FakeExecutor(gate=gate)
    coordinator = make_coordinator(store, executor)
    coordinator.start()
    try:
        created = coordinator.create_task("req-w", "T", "do")
        # The request handler has already returned here.
        assert created.queue_state == "queued"
        await asyncio.wait_for(executor.started.wait(), timeout=5)
        assert coordinator.active_run_id is not None
        gate.set()
        final = await wait_for_phase(coordinator, created.task_id, {"verifying", "waiting_user", "failed"})
        assert final in {"verifying", "waiting_user"}
    finally:
        await coordinator.stop()
