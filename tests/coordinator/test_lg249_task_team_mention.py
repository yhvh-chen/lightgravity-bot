"""LG-249: Team Task messages use the same bot-mention gate as Team chat.

Ordinary Team Task messages are persisted only.  Only a message whose first
non-whitespace token is the configured bot mention is stripped and routed to the
existing classifier/responder path.  Single-user mode and message replay keep
their previous behaviour.  All coordinator dependencies here are local fixtures;
no test calls a real model.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from lightgravity.coordinator import Coordinator
from lightgravity.coordinator.classification import Classification, classify_message
from lightgravity.store import FileStore

from coordinator_helpers import CONV, make_coordinator, message


def _recording_doubles() -> tuple[
    list[str],
    list[str],
    Callable[[str], Classification],
    Callable[[str, Classification], str],
]:
    classifier_calls: list[str] = []
    responder_calls: list[str] = []

    def classifier(content: str) -> Classification:
        classifier_calls.append(content)
        return classify_message(content)

    def responder(content: str, classification: Classification) -> str:
        responder_calls.append(content)
        return f"BOT:{content}"

    return classifier_calls, responder_calls, classifier, responder


def _create_task(coordinator: Coordinator) -> str:
    created = coordinator.create_task("req-lg249", "T", "do")
    assert created.task_id is not None
    return created.task_id


async def test_ordinary_team_task_message_persists_only(store: FileStore) -> None:
    classifier_calls, responder_calls, classifier, responder = _recording_doubles()
    coordinator = make_coordinator(
        store, classifier=classifier, responder=responder, team_mode=True
    )
    task_id = _create_task(coordinator)
    before = coordinator.status(task_id)

    result = await coordinator.submit_task_message(
        task_id, message("Ben: the demo looks good", message_id="msg-lg249-plain")
    )

    assert result.kind == "recorded"
    assert result.reply == ""
    assert result.task_id == task_id
    assert result.data == {"intent": "recorded", "creates_task": False}
    assert classifier_calls == []
    assert responder_calls == []
    assert coordinator.status(task_id) == before
    records = coordinator.read_task_messages(task_id)
    assert [record["message_id"] for record in records] == ["msg-lg249-plain"]
    assert records[0]["message"]["content"] == "Ben: the demo looks good"


async def test_ordinary_team_task_message_skips_selected_source_resolution(
    store: FileStore,
) -> None:
    coordinator = make_coordinator(store, team_mode=True)
    task_id = _create_task(coordinator)

    result = await coordinator.submit_task_message(
        task_id,
        message(
            "human feedback with a stale selection",
            message_id="msg-lg249-selection",
            selected_sources=[{"source_id": "missing"}],
        ),
    )

    assert result.kind == "recorded"
    record = coordinator.read_task_messages(task_id)[0]["message"]
    assert record["selected_sources"] == [{"source_id": "missing"}]
    assert "selected_context" not in record


async def test_team_task_mention_is_stripped_and_routes(store: FileStore) -> None:
    classifier_calls, responder_calls, classifier, responder = _recording_doubles()
    coordinator = make_coordinator(
        store, classifier=classifier, responder=responder, team_mode=True
    )
    task_id = _create_task(coordinator)

    result = await coordinator.submit_task_message(
        task_id, message("  @bot  hello there", message_id="msg-lg249-mention")
    )

    assert result.kind == "direct"
    assert classifier_calls == ["hello there"]
    assert responder_calls == ["hello there"]
    entries = coordinator.read_task_messages(task_id)
    assert [entry["message_id"] for entry in entries] == [
        "msg-lg249-mention",
        "assistant:msg-lg249-mention",
    ]
    # The persisted user message keeps the original text; only the routed copy
    # has the mention removed.
    assert entries[0]["message"]["content"] == "  @bot  hello there"


async def test_team_task_mention_query_still_routes(store: FileStore) -> None:
    classifier_calls, responder_calls, classifier, responder = _recording_doubles()
    coordinator = make_coordinator(
        store, classifier=classifier, responder=responder, team_mode=True
    )
    task_id = _create_task(coordinator)

    result = await coordinator.submit_task_message(
        task_id, message("@bot 进度如何？", message_id="msg-lg249-query")
    )

    assert result.kind == "query"
    assert result.task_id == task_id
    assert classifier_calls == ["进度如何？"]
    assert responder_calls == []


async def test_custom_team_mention_aligns_global_and_task(store: FileStore) -> None:
    classifier_calls, responder_calls, classifier, responder = _recording_doubles()
    coordinator = make_coordinator(
        store,
        classifier=classifier,
        responder=responder,
        team_mode=True,
        bot_mention="!lg",
    )
    task_id = _create_task(coordinator)

    # The default @bot is ordinary text under a custom configured mention.
    task_plain = await coordinator.submit_task_message(
        task_id, message("@bot not a call", message_id="msg-lg249-task-default")
    )
    global_plain = await coordinator.submit_global_message(
        CONV, message("@bot not a call", message_id="msg-lg249-global-default")
    )
    assert task_plain.kind == "recorded"
    assert global_plain.kind == "recorded"
    assert classifier_calls == []
    assert responder_calls == []

    task_mention = await coordinator.submit_task_message(
        task_id, message(" !lg task ping", message_id="msg-lg249-task-custom")
    )
    global_mention = await coordinator.submit_global_message(
        CONV, message(" !lg global ping", message_id="msg-lg249-global-custom")
    )
    assert task_mention.kind == "direct"
    assert global_mention.kind == "direct"
    assert classifier_calls == ["task ping", "global ping"]
    assert responder_calls == ["task ping", "global ping"]


async def test_ordinary_team_task_message_replay_is_idempotent(store: FileStore) -> None:
    classifier_calls, responder_calls, classifier, responder = _recording_doubles()
    coordinator = make_coordinator(
        store, classifier=classifier, responder=responder, team_mode=True
    )
    task_id = _create_task(coordinator)
    payload = message("replayed note", message_id="msg-lg249-replay")

    first = await coordinator.submit_task_message(task_id, payload)
    replay = await coordinator.submit_task_message(task_id, payload)

    assert replay.to_dict() == first.to_dict()
    assert classifier_calls == []
    assert responder_calls == []
    assert [entry["message_id"] for entry in coordinator.read_task_messages(task_id)] == [
        "msg-lg249-replay"
    ]


async def test_mentioned_team_task_replay_runs_bot_once(store: FileStore) -> None:
    classifier_calls, responder_calls, classifier, responder = _recording_doubles()
    coordinator = make_coordinator(
        store, classifier=classifier, responder=responder, team_mode=True
    )
    task_id = _create_task(coordinator)
    payload = message("@bot hello", message_id="msg-lg249-mentioned-replay")

    first = await coordinator.submit_task_message(task_id, payload)
    replay = await coordinator.submit_task_message(task_id, payload)

    assert replay.to_dict() == first.to_dict()
    assert classifier_calls == ["hello"]
    assert responder_calls == ["hello"]
    assert [entry["message_id"] for entry in coordinator.read_task_messages(task_id)] == [
        "msg-lg249-mentioned-replay",
        "assistant:msg-lg249-mentioned-replay",
    ]


@pytest.mark.parametrize("content,kind", [
    ("补充：页面颜色用蓝色；不要创建任务。", "append"),
    ("进度如何？", "query"),
])
async def test_single_user_task_routing_does_not_require_mention(
    store: FileStore, content: str, kind: str
) -> None:
    classifier_calls, responder_calls, classifier, responder = _recording_doubles()
    coordinator = make_coordinator(
        store, classifier=classifier, responder=responder
    )
    task_id = _create_task(coordinator)

    result = await coordinator.submit_task_message(
        task_id, message(content, message_id=f"msg-lg249-single-{kind}")
    )

    assert result.kind == kind
    assert classifier_calls == [content]
    assert responder_calls == []
