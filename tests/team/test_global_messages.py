"""Global message author injection and @bot gating (LG-050 §5)."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from lightgravity.api.app import create_app
from lightgravity.config import Settings
from lightgravity.team import TeamAccounts

from team_helpers import (
    login_member,
    seeded_accounts,
    team_settings,
)


def _app_with_responder(settings: Settings, calls: list[str]) -> FastAPI:
    def responder(content: str, classification: Any) -> str:
        calls.append(content)
        return f"BOT:{content}"

    return create_app(settings, responder=responder)


@pytest.fixture
def responder_app(team_settings: Settings, seeded_accounts: TeamAccounts) -> tuple[FastAPI, list[str]]:
    calls: list[str] = []
    return _app_with_responder(team_settings, calls), calls


async def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    )


async def test_ordinary_message_records_only_with_author(
    responder_app: tuple[FastAPI, list[str]],
) -> None:
    app, calls = responder_app
    async with app.router.lifespan_context(app):
        async with await _client(app) as client:
            assert (await login_member(client)).status_code == 200
            response = await client.post(
                "/api/v1/conversations/global/messages",
                json={"message_id": "msg_plain_1", "content": "just a note"},
            )
            assert response.status_code == 200
            body = response.json()
            assert body["kind"] == "recorded"
            assert body["reply"] is None
            assert body["data"] == {"intent": "recorded", "creates_task": False}
            assert calls == []  # zero bot/model activity

            history = await client.get("/api/v1/conversations/global/messages")
            items = {item["message_id"]: item for item in history.json()["items"]}
            author = items["msg_plain_1"]["message"]["author"]
            assert author == {"kind": "user", "username": "alice", "role": "member"}


async def test_bot_mention_routes_and_reply_carries_bot_author(
    responder_app: tuple[FastAPI, list[str]],
) -> None:
    app, calls = responder_app
    async with app.router.lifespan_context(app):
        async with await _client(app) as client:
            assert (await login_member(client)).status_code == 200
            response = await client.post(
                "/api/v1/conversations/global/messages",
                json={"message_id": "msg_bot_1", "content": "  @bot  hello there"},
            )
            assert response.status_code == 200
            assert response.json()["kind"] != "recorded"
            assert len(calls) == 1

            history = await client.get("/api/v1/conversations/global/messages")
            entries = history.json()["items"]
            assistant = [
                item
                for item in entries
                if item["message"].get("role") == "assistant"
            ]
            assert assistant, entries
            assert assistant[0]["message"]["author"] == {
                "kind": "bot",
                "username": "bot",
                "role": "assistant",
            }


async def test_concurrent_duplicate_message_runs_bot_once(
    responder_app: tuple[FastAPI, list[str]],
) -> None:
    app, calls = responder_app
    async with app.router.lifespan_context(app):
        async with await _client(app) as client:
            assert (await login_member(client)).status_code == 200

            async def send() -> httpx.Response:
                return await client.post(
                    "/api/v1/conversations/global/messages",
                    json={"message_id": "msg_dup_1", "content": "@bot ping"},
                )

            first, second = await asyncio.gather(send(), send())
            assert first.status_code == 200
            assert second.status_code == 200
            assert len(calls) == 1


async def test_task_messages_are_not_subject_to_bot_gating(
    team_settings: Settings, seeded_accounts: TeamAccounts
) -> None:
    calls: list[str] = []
    app = _app_with_responder(team_settings, calls)
    async with app.router.lifespan_context(app):
        async with await _client(app) as client:
            assert (await login_member(client)).status_code == 200
            created = await client.post(
                "/api/v1/tasks",
                json={
                    "request_id": "req_task_1",
                    "title": "Demo",
                    "objective": "Demo task",
                },
            )
            assert created.status_code == 200, created.text
            task_id = created.json()["task_id"]
            # No @bot prefix: Task messages always use the existing route.
            message = await client.post(
                f"/api/v1/tasks/{task_id}/messages",
                json={"message_id": "msg_task_1", "content": "hello task"},
            )
            assert message.status_code == 200, message.text
            assert message.json()["kind"] != "recorded"
            assert len(calls) == 1
