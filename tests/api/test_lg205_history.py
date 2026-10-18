"""LG-205 read-only Team conversation history projection."""

from __future__ import annotations

import sys
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from lightgravity.api.app import create_app
from lightgravity.api.conversations import GLOBAL_CONVERSATION_ID
from lightgravity.config import Settings
from lightgravity.store.atomic import append_jsonl
from lightgravity.team import TeamAccounts

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "team"))
from team_helpers import (  # noqa: E402
    login_member,
    seeded_accounts,
    team_settings,
)


@pytest.fixture
def history_app(team_settings: Settings, seeded_accounts: TeamAccounts) -> FastAPI:
    return create_app(team_settings, enable_intake_worker=False)


def _write(path: Path, records: list[dict[str, object]]) -> None:
    for record in records:
        append_jsonl(path, record)


def _conversation(data_dir: Path, task_id: str) -> Path:
    return data_dir / "tasks" / task_id / "conversation.jsonl"


async def _create_task(client: httpx.AsyncClient, request_id: str, title: str) -> str:
    response = await client.post(
        "/api/v1/tasks",
        json={"request_id": request_id, "title": title, "objective": title},
    )
    assert response.status_code == 200, response.text
    return str(response.json()["task_id"])


async def test_history_requires_a_team_session(history_app: FastAPI) -> None:
    async with history_app.router.lifespan_context(history_app):
        transport = httpx.ASGITransport(app=history_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get("/api/v1/conversations/history")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_history_uses_actual_last_message_time_and_omits_empty_tasks(
    history_app: FastAPI, team_settings: Settings
) -> None:
    async with history_app.router.lifespan_context(history_app):
        transport = httpx.ASGITransport(app=history_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            assert (await login_member(client)).status_code == 200
            older = await _create_task(client, "req-history-older", "Older task")
            newest = await _create_task(client, "req-history-newest", "Newest task")
            empty = await _create_task(client, "req-history-empty", "No messages yet")

            data_dir = team_settings.data_dir
            _write(
                _conversation(data_dir, older),
                [
                    {"message_id": "msg_old_1", "seq": 1, "at": "2026-10-18T10:00:00.000Z"},
                    {"message_id": "msg_old_2", "seq": 2, "at": "2026-10-18T10:05:00.000Z"},
                ],
            )
            partial = _conversation(data_dir, older)
            with partial.open("ab") as handle:
                # An interrupted append must be skipped, not treated as recency.
                handle.write(b'{"message_id":"msg_partial"')

            _write(
                _conversation(data_dir, newest),
                [{"message_id": "msg_new_1", "seq": 1, "at": "2026-10-18T11:00:00.000Z"}],
            )
            _write(
                data_dir / "conversations" / GLOBAL_CONVERSATION_ID / "messages.jsonl",
                [{"message_id": "msg_global_1", "seq": 1, "at": "2026-10-18T10:30:00.000Z"}],
            )

            response = await client.get("/api/v1/conversations/history")
            assert response.status_code == 200, response.text
            items = response.json()["items"]

    assert [item["kind"] for item in items] == ["task", "general", "task"]
    assert [item["task_ref"] for item in items] == [newest, None, older]
    assert all(item["task_ref"] != empty for item in items)
    assert items[0] == {
        "kind": "task",
        "task_ref": newest,
        "title": "Newest task",
        "last_message_at": "2026-10-18T11:00:00.000Z",
        "last_message_seq": 1,
    }
    assert items[1] == {
        "kind": "general",
        "task_ref": None,
        "title": "General",
        "last_message_at": "2026-10-18T10:30:00.000Z",
        "last_message_seq": 1,
    }
    # The trailing partial line was ignored; the real last record is seq 2.
    assert items[2]["task_ref"] == older
    assert items[2]["last_message_at"] == "2026-10-18T10:05:00.000Z"
    assert items[2]["last_message_seq"] == 2


async def test_history_general_is_always_present_and_limit_is_bounded(
    history_app: FastAPI,
) -> None:
    async with history_app.router.lifespan_context(history_app):
        transport = httpx.ASGITransport(app=history_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            assert (await login_member(client)).status_code == 200
            first = await _create_task(client, "req-history-one", "One")
            second = await _create_task(client, "req-history-two", "Two")
            data_dir = history_app.state.context.data_dir
            _write(
                _conversation(data_dir, first),
                [{"message_id": "msg_one", "seq": 1, "at": "2026-10-18T09:00:00.000Z"}],
            )
            _write(
                _conversation(data_dir, second),
                [{"message_id": "msg_two", "seq": 1, "at": "2026-10-18T09:30:00.000Z"}],
            )

            response = await client.get("/api/v1/conversations/history", params={"limit": 2})
            assert response.status_code == 200, response.text
            items = response.json()["items"]
            assert len(items) == 2
            assert [item["task_ref"] for item in items] == [second, first]
