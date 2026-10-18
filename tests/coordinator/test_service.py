"""Coordinator routing, persistence and non-blocking queries (LG-007)."""

from __future__ import annotations

import asyncio

import pytest

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


@pytest.mark.parametrize("prompt,expected", [
    ("Build a landing page. Include a separate deployment guide.", "Build a landing page"),
    ("Build index.html. Include a short report.", "Build index.html"),
    ("Build a page across\nwrapped lines. Then test it.", "Build a page across wrapped lines"),
    ("  @bot Build a launch page! Include an FAQ.", "Build a launch page"),
    ("创建一个登陆页面。然后添加测试。", "创建一个登陆页面"),
    ("@bot: Build a launch page. Include an FAQ.", "Build a launch page"),
    ("", "New task"),
])
def test_delivery_title_uses_first_requirement_sentence(prompt, expected):
    from lightgravity.coordinator.service import _delivery_title
    assert _delivery_title(prompt, "@bot") == expected


@pytest.mark.parametrize("prompt", [
    "Using the selected sources, build a one-page launch landing page (index.html) for the product in the brief, and a short report.",
    "Implement " + "a" * 120,
    "实" * 120,
])
def test_long_delivery_title_is_readable_and_bounded(prompt):
    from lightgravity.coordinator.service import _delivery_title
    title = _delivery_title(prompt, "@bot")
    assert len(title) <= 60
    assert title.endswith("…")
    assert "\n" not in title


async def test_short_title_preserves_full_delivery_request_and_retry_identity(store):
    coordinator = make_coordinator(store, team_mode=True)
    objective = (
        "Build a launch landing page. Include index.html and a short report.\n"
        "Preserve every requirement and use the selected source material."
    )
    msg = message("@bot " + objective, message_id="short-delivery-title")
    first = await coordinator.submit_global_message(CONV, msg)
    replay = await coordinator.submit_global_message(CONV, msg)
    assert replay.to_dict() == first.to_dict()
    assert len(coordinator.list_tasks()) == 1
    task = store.read("task", first.task_id)
    assert task.entity["title"] == "Build a launch landing page"
    assert task.entity["objective"] == objective
    assert objective in task.body
    assert coordinator.read_global_messages(CONV)[0]["message"]["content"] == "@bot " + objective
    assert len(coordinator.read_global_messages(CONV)) == 2


def test_explicit_new_task_title_is_not_rewritten(store):
    coordinator = make_coordinator(store)
    title = "User title " + "with extra detail " * 6
    result = coordinator.create_task("explicit-title", title, "Full objective")
    assert store.read("task", result.task_id).entity["title"] == title
