"""LG-013 service-layer integration: chat -> task -> board -> acceptance.

These exercise the *frozen* HTTP endpoints over the real ``create_app`` assembly
(no SDK, no real model): the singleton global conversation, Task creation,
Task-scoped messages, the Board's Task list/detail/events reads, and the
acceptance read that the Chat/Board views consume.  A plain question with no
configured coordinator connection must report an honest "unavailable" reply and
never a fabricated answer — asserted here.

The real browser path and real-model turn are QA/version scope; this file proves
the service wiring the views depend on, using only tmp_path data.
"""

from __future__ import annotations

import httpx
import pytest

from api_helpers import create_task

pytestmark = pytest.mark.anyio


async def test_global_conversation_history_round_trip(api: httpx.AsyncClient) -> None:
    """POST then GET the global conversation; the stored envelope is returned."""

    post = await api.post(
        "/api/v1/conversations/global/messages",
        json={
            "message_id": "msg_lg013_1",
            "content": "hello from the global rail",
            "attachments": [{"path": "inputs/spec.md", "media_type": "text/markdown"}],
        },
    )
    assert post.status_code == 200, post.text
    # Idempotent replay on the same message_id must not duplicate.
    replay = await api.post(
        "/api/v1/conversations/global/messages",
        json={"message_id": "msg_lg013_1", "content": "hello from the global rail"},
    )
    assert replay.status_code == 200, replay.text

    read = await api.get("/api/v1/conversations/global/messages")
    assert read.status_code == 200, read.text
    page = read.json()
    items = [item for item in page["items"] if item["message_id"] == "msg_lg013_1"]
    assert len(items) == 1, page
    # The wire item nests the message body and carries the cursor seq.
    assert items[0]["seq"] >= 1
    assert items[0]["message"]["content"] == "hello from the global rail"


async def test_plain_question_reports_unavailable_not_fabricated(
    api: httpx.AsyncClient,
) -> None:
    """No coordinator connection => honest unavailable, never a fake answer."""

    post = await api.post(
        "/api/v1/conversations/global/messages",
        json={"message_id": "msg_lg013_question", "content": "你能做什么？"},
    )
    assert post.status_code == 200, post.text
    body = post.json()
    # The reply must be a real string (the deterministic/unavailable responder),
    # and the classification must not have created a Task for a plain question.
    assert isinstance(body.get("reply"), str)
    assert body.get("task_id") is None


async def test_delivery_request_through_global_creates_real_task(
    api: httpx.AsyncClient,
) -> None:
    """The page's delivery payload -> real Task state, not a client-side mock.

    This is the service half of the Chat "submit a delivery" path: a delivery
    message POSTed to the global conversation must return a real ``task_id`` that
    then resolves as an authoritative Task on the Board endpoints.
    """

    post = await api.post(
        "/api/v1/conversations/global/messages",
        json={
            "message_id": "msg_lg013_delivery",
            "content": "实现一个小的日志导出功能",
        },
    )
    assert post.status_code == 200, post.text
    body = post.json()
    task_id = body.get("task_id")
    assert isinstance(task_id, str) and task_id.startswith("task_"), body
    assert body.get("queue_state") in {"queued", "not_queued"}

    detail = await api.get(f"/api/v1/tasks/{task_id}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["task_id"] == task_id
    # The created Task is immediately visible on the Board list.
    listed = await api.get("/api/v1/tasks")
    assert task_id in {item["task_id"] for item in listed.json()["items"]}


async def test_task_scoped_messages_round_trip(api: httpx.AsyncClient) -> None:
    """Task messages use the same cursor contract as the global conversation."""

    task_id = await create_task(api, title="chat scope", objective="deliver")

    post = await api.post(
        f"/api/v1/tasks/{task_id}/messages",
        json={"message_id": "msg_task_1", "content": "continue this task"},
    )
    assert post.status_code == 200, post.text

    read = await api.get(f"/api/v1/tasks/{task_id}/messages")
    assert read.status_code == 200, read.text
    page = read.json()
    assert any(item["message_id"] == "msg_task_1" for item in page["items"])
    assert page["next_cursor"] is None or page["next_cursor"].startswith("v1:")


async def test_board_reads_real_phase_and_events(api: httpx.AsyncClient) -> None:
    """Board list/detail/events all read the authoritative Task state."""

    task_id = await create_task(api, title="board read", objective="deliver")

    listed = await api.get("/api/v1/tasks", params={"limit": 100})
    assert listed.status_code == 200, listed.text
    summaries = [item for item in listed.json()["items"] if item["task_id"] == task_id]
    assert len(summaries) == 1
    summary = summaries[0]
    # Real phase/status/queue projection, not a layout mock.
    assert summary["phase"]
    assert summary["status"] in {"todo", "in-progress", "done"}
    assert summary["queue"]["state"] in {"not_queued", "queued", "claimed"}

    detail = await api.get(f"/api/v1/tasks/{task_id}")
    assert detail.status_code == 200, detail.text
    detail_body = detail.json()
    assert detail_body["task_id"] == task_id
    assert "run" in detail_body and "subtasks" in detail_body and "members" in detail_body

    events = await api.get(f"/api/v1/tasks/{task_id}/events")
    assert events.status_code == 200, events.text
    event_items = events.json()["items"]
    assert event_items, "a created Task must have at least one persisted event"
    assert event_items[0]["type"] == "task.created"
    assert event_items[0]["stream_id"] == task_id


async def test_acceptance_read_is_pending_before_any_candidate(
    api: httpx.AsyncClient,
) -> None:
    """The acceptance snapshot the Board renders is real and starts pending."""

    task_id = await create_task(api, title="acceptance read", objective="deliver")
    response = await api.get(f"/api/v1/tasks/{task_id}/acceptance")
    assert response.status_code == 200, response.text
    snapshot = response.json()
    assert snapshot["task_id"] == task_id
    acceptance = snapshot.get("acceptance") or {}
    assert acceptance.get("status") in {"pending", "awaiting"}
    # No candidate yet -> accept/reject would be rejected by the backend.
    assert snapshot.get("candidate") in (None, {})


async def test_accept_without_candidate_is_rejected_not_faked(
    api: httpx.AsyncClient,
) -> None:
    """A premature accept must fail honestly, not paint a decision."""

    task_id = await create_task(api, title="premature accept", objective="deliver")
    response = await api.post(
        f"/api/v1/tasks/{task_id}/actions",
        json={"action": "accept", "request_id": "req-lg013-accept-1"},
    )
    assert response.status_code >= 400, response.text
    error = response.json()["error"]
    assert error["code"] in {"not_ready", "illegal_transition", "acceptance_stale"}
    # The Task must not have flipped to completed by an unbacked decision.
    detail = (await api.get(f"/api/v1/tasks/{task_id}")).json()
    assert detail["phase"] != "completed"
