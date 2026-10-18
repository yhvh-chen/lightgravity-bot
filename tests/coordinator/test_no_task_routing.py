"""LG134 routing regressions; responder/executor are bounded local fixtures only."""

from __future__ import annotations

import pytest

from lightgravity.coordinator import Coordinator, SingleSlotDispatcher
from lightgravity.coordinator.classification import Classification, MessageIntent, classify_message
from lightgravity.store import FileStore

from coordinator_helpers import CONV, FakeExecutor, message

ORIGINAL_QUESTION = "@bot 请用一句话回答：2+2 等于多少？不要创建任务。"


def test_original_question_does_not_authorize_delivery() -> None:
    result = classify_message(ORIGINAL_QUESTION)
    assert result.intent == MessageIntent.ANSWER
    assert result.next_action == "direct"
    assert not result.creates_work


@pytest.mark.parametrize("team_mode,content,kind", [
    (False, ORIGINAL_QUESTION, "direct"),
    (True, ORIGINAL_QUESTION, "direct"),
    (True, ORIGINAL_QUESTION.removeprefix("@bot "), "recorded"),
    (True, "@botany 请创建任务", "recorded"),
    (True, "@bot 请修改 index.html；不要创建任务。", "clarify"),
])
async def test_real_global_route_never_creates_work_for_no_task_question(
    store: FileStore, team_mode: bool, content: str, kind: str,
) -> None:
    replies: list[str] = []

    def bounded_fixture(prompt: str, classification: Classification) -> str:
        # Test-only tool-less fixture, not real model/SDK answer evidence.
        assert classification.intent == MessageIntent.ANSWER
        assert classification.bounded_tools == ()
        replies.append(prompt)
        return "fixture: 4"

    executor = FakeExecutor()
    coordinator = Coordinator(
        store, dispatcher=SingleSlotDispatcher(executor),
        responder=bounded_fixture, team_mode=team_mode,
    )
    try:
        result = await coordinator.submit_global_message(CONV, message(content))
        assert result.kind == kind
        assert result.task_id is None
        # Exercise the real queue pump as well as classification/HTTP-independent route.
        assert not await coordinator._pump_once()
        assert coordinator.list_tasks() == []
        assert not list((store.data_dir / "runs").glob("*/RUN.md"))
        assert not list((store.data_dir / "members").glob("*.md"))
        assert executor.requests == []
        assert len(replies) == (1 if kind == "direct" else 0)
    finally:
        await coordinator.stop()


@pytest.mark.parametrize("content,intent", [
    ("请用一句话回答：2+2 等于多少？不要新建任务。", MessageIntent.ANSWER),
    ("2+2 等于多少？别创建新的任务。", MessageIntent.ANSWER),
    ("2+2 等于多少？无需创建一个任务。", MessageIntent.ANSWER),
    ("Answer 2+2. Do not create a new task.", MessageIntent.ANSWER),
    ("Answer 2+2. Don't create any task.", MessageIntent.ANSWER),
    ("Answer 2+2. Never start a new task.", MessageIntent.ANSWER),
    ("读这个文件；不要创建任务。", MessageIntent.BOUNDED_READ),
    ("How do I create a file? Do not create a task.", MessageIntent.ANSWER),
    ("创建任务是什么含义？不要创建任务。", MessageIntent.ANSWER),
    ('回答引用“创建文件”的含义，不要创建任务。', MessageIntent.ANSWER),
    ("请创建一个文件；不要创建任务。", MessageIntent.UNKNOWN),
    ("请回答2+2，并修改 index.html；不要创建任务。", MessageIntent.UNKNOWN),
    ("Read this file and modify index.html; do not create a task.", MessageIntent.UNKNOWN),
    ("Do not create a task. Please create index.html.", MessageIntent.UNKNOWN),
    ("不要创建任务；请创建任务。", MessageIntent.UNKNOWN),
    ("取消当前任务；不要创建任务。", MessageIntent.CONTROL),
    ("请暂停当前任务；不要新建任务。", MessageIntent.CONTROL),
    ("请查询任务状态；不要创建任务。", MessageIntent.STATUS_QUERY),
    ("继续当前任务；不要创建任务。", MessageIntent.RETRY),
    ("补充：页面颜色用蓝色；不要创建任务。", MessageIntent.FOLLOWUP),
    ("创建 index.html，不要部署或发布。", MessageIntent.DELIVERY),
    ('创建一个文件，内容是“不要创建任务”。', MessageIntent.DELIVERY),
    ('Create a file containing "do not create a task".', MessageIntent.DELIVERY),
])
def test_bounded_no_task_vocabulary_preserves_existing_routes(
    content: str, intent: MessageIntent,
) -> None:
    result = classify_message(content)
    assert result.intent == intent
    if intent in {MessageIntent.ANSWER, MessageIntent.BOUNDED_READ, MessageIntent.UNKNOWN}:
        assert not result.creates_work


async def test_existing_task_followup_query_and_control_keep_target(store: FileStore) -> None:
    from coordinator_helpers import make_coordinator, raw_task

    executor = FakeExecutor()
    coordinator = make_coordinator(store, executor)
    task_id = raw_task(store)
    before = coordinator.status(task_id)
    followup = await coordinator.submit_task_message(
        task_id, message("补充：页面颜色用蓝色；不要创建任务。"),
    )
    assert followup.kind == "append"
    assert followup.task_id == task_id
    assert coordinator.status(task_id) == before
    query = await coordinator.submit_global_message(
        CONV, message(f"@bot 查询 {task_id} 状态；不要创建任务。"),
    )
    assert query.kind == "query"
    assert query.task_id == task_id
    controlled = await coordinator.submit_task_message(
        task_id, message("取消当前任务；不要创建任务。"),
    )
    assert controlled.kind == "control"
    assert controlled.task_id == task_id
    assert coordinator.status(task_id)["phase"] == "cancelled"
    assert len(coordinator.list_tasks()) == 1
    assert not list((store.data_dir / "runs").glob("*/RUN.md"))
    assert not list((store.data_dir / "members").glob("*.md"))
    assert executor.requests == []


@pytest.mark.parametrize("team_mode", [False, True])
async def test_positive_delivery_still_enters_real_dispatch(
    store: FileStore, team_mode: bool,
) -> None:
    from coordinator_helpers import make_coordinator

    executor = FakeExecutor()
    coordinator = make_coordinator(store, executor, team_mode=team_mode)
    result = await coordinator.submit_global_message(
        CONV, message("@bot 请创建 index.html，不要部署或发布。"),
    )
    assert result.kind == "task"
    assert result.task_id is not None
    assert len(coordinator.list_tasks()) == 1
    assert await coordinator._process_one()
    assert len(executor.requests) == 1
    assert list((store.data_dir / "runs").glob("*/RUN.md"))
