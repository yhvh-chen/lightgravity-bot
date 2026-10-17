"""LG-066: global/Team Task-ID status query (docs/04 §2, §4).

Covers the shared Team Chat path with two authenticated members:

* an exact legal ``task_<ULID>`` pasted in the message resolves to the persisted
  status snapshot (running and completed), with artifact facts, while a worker is
  busy and without creating/dispatching any Task or Run;
* the reply is persisted into the shared global conversation so the other member
  sees it (and a repeated ``message_id`` is idempotent);
* missing / malformed / unknown / multiple distinct ids return an honest
  ``clarify`` and never pick an arbitrary first target;
* ordinary Team messages, anonymous callers and Personal chat keep their
  existing boundaries.

The suite uses the deterministic ``FakeExecutor`` only as a controllable
execution seam; it is not real-model evidence.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest

from lightgravity.api.app import create_app
from lightgravity.config import Settings
from lightgravity.team import TeamAccounts

from coordinator_helpers import FakeExecutor, raw_task

GLOBAL = "/api/v1/conversations/global/messages"
PERSONAL = "/api/v1/conversations/personal/messages"
TASKS = "/api/v1/tasks"

ALICE_PASSWORD = "alice-lg066-pw"
BOB_PASSWORD = "bob-lg066-pw"

#: A well-formed but never-created ULID (all zeros is a legal Crockford token).
UNKNOWN_TASK_ID = "task_00000000000000000000000000"


def _team_settings(data_dir: Path, workspace_root: Path) -> Settings:
    return Settings(
        data_dir=data_dir,
        workspace_root=workspace_root,
        secret_store=data_dir.parent / "secrets",
        team_mode=True,
    )


def _seed_accounts(settings: Settings) -> None:
    accounts = TeamAccounts(settings.team_accounts_path)
    accounts.add("alice", ALICE_PASSWORD, "member")
    accounts.add("bob", BOB_PASSWORD, "member")


async def _login(client: httpx.AsyncClient, username: str, password: str) -> None:
    response = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200, response.text


@pytest.fixture
async def env(data_dir: Path, workspace_root: Path) -> AsyncIterator[dict[str, Any]]:
    """Two logged-in members over one resident coordinator with a gated executor."""

    settings = _team_settings(data_dir, workspace_root)
    _seed_accounts(settings)
    gate = asyncio.Event()
    executor = FakeExecutor(gate=gate)
    app = create_app(settings, executor=executor)
    transport = httpx.ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with (
            httpx.AsyncClient(transport=transport, base_url="http://testserver") as alice,
            httpx.AsyncClient(transport=transport, base_url="http://testserver") as bob,
        ):
            await _login(alice, "alice", ALICE_PASSWORD)
            await _login(bob, "bob", BOB_PASSWORD)
            try:
                yield {
                    "app": app,
                    "transport": transport,
                    "alice": alice,
                    "bob": bob,
                    "gate": gate,
                    "executor": executor,
                }
            finally:
                # Release the gated worker so shutdown cannot hang.
                gate.set()


async def _task_count(client: httpx.AsyncClient) -> int:
    response = await client.get(TASKS)
    assert response.status_code == 200, response.text
    return len(response.json()["items"])


async def _start_running_task(env: dict[str, Any]) -> str:
    """Create one real Task through the shared delivery path and block its Run."""

    created = await env["alice"].post(
        GLOBAL,
        json={"message_id": "msg-create-running", "content": "@bot 开发一个网页小工具"},
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["kind"] == "task", body
    task_id = str(body["task_id"])
    await asyncio.wait_for(env["executor"].started.wait(), timeout=5)
    return task_id


async def test_shared_query_by_id_is_visible_to_both_and_creates_nobody(
    env: dict[str, Any],
) -> None:
    task_id = await _start_running_task(env)
    before_tasks = await _task_count(env["alice"])
    before_dispatch = len(env["executor"].requests)

    query = await env["bob"].post(
        GLOBAL,
        json={
            "message_id": "msg-bob-query",
            "content": f"@bot 请查询共享任务 {task_id} 的当前状态",
        },
    )
    assert query.status_code == 200, query.text
    body = query.json()
    assert body["kind"] == "query"
    assert body["task_id"] == task_id
    assert body["data"]["phase"] == "executing"
    assert body["data"]["creates_task"] is False
    assert body["data"]["creates_run"] is False
    assert task_id in body["reply"]

    # A status query never creates a Task/Run or dispatches a worker.
    assert await _task_count(env["alice"]) == before_tasks
    assert len(env["executor"].requests) == before_dispatch

    # The query reply is written to the shared conversation, so alice sees it.
    history = (await env["alice"].get(GLOBAL)).json()["items"]
    replies = [
        item["message"]
        for item in history
        if item["message"].get("message_id") == "assistant:msg-bob-query"
    ]
    assert replies, "bob's shared query reply must be visible to alice"
    assert replies[0]["content"] == body["reply"]
    assert replies[0]["author"] == {"kind": "bot", "username": "bot", "role": "assistant"}


async def test_query_completed_task_reports_persisted_facts(
    env: dict[str, Any],
) -> None:
    store = env["app"].state.store
    task_id = raw_task(store, status="done", phase="completed")

    response = await env["bob"].post(
        GLOBAL,
        json={"message_id": "msg-done", "content": f"@bot 查询任务 {task_id} 的状态"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["kind"] == "query"
    assert body["task_id"] == task_id
    assert body["data"]["status"] == "done"
    assert body["data"]["phase"] == "completed"
    assert body["data"]["creates_task"] is False


async def test_missing_id_clarifies_without_guessing_an_active_task(
    env: dict[str, Any],
) -> None:
    # Two active tasks: the legacy "one active target" guess must not apply.
    store = env["app"].state.store
    raw_task(store, status="in-progress", phase="executing")
    raw_task(store, status="in-progress", phase="executing")

    response = await env["bob"].post(
        GLOBAL, json={"message_id": "msg-no-id", "content": "@bot 查询当前状态"}
    )
    body = response.json()
    assert body["kind"] == "clarify"
    assert body["task_id"] is None
    assert body["data"]["missing_task_id"] is True


async def test_invalid_id_clarifies(env: dict[str, Any]) -> None:
    response = await env["bob"].post(
        GLOBAL, json={"message_id": "msg-invalid", "content": "@bot 查询 task_123 的状态"}
    )
    body = response.json()
    assert body["kind"] == "clarify"
    assert body["data"]["invalid_task_ids"] == ["task_123"]


async def test_unknown_id_clarifies(env: dict[str, Any]) -> None:
    response = await env["bob"].post(
        GLOBAL,
        json={
            "message_id": "msg-unknown",
            "content": f"@bot 查询 {UNKNOWN_TASK_ID} 的状态",
        },
    )
    body = response.json()
    assert body["kind"] == "clarify"
    assert body["data"]["unknown_task_id"] == UNKNOWN_TASK_ID


async def test_multiple_ids_clarify(env: dict[str, Any]) -> None:
    store = env["app"].state.store
    first = raw_task(store, status="done", phase="completed")
    second = raw_task(store, status="done", phase="completed")

    response = await env["bob"].post(
        GLOBAL,
        json={
            "message_id": "msg-multiple",
            "content": f"@bot 查询 {first} 和 {second} 的状态",
        },
    )
    body = response.json()
    assert body["kind"] == "clarify"
    assert body["task_id"] is None
    assert body["data"]["ambiguous"] is True
    assert set(body["data"]["task_ids"]) == {first, second}


async def test_repeated_message_id_is_idempotent(env: dict[str, Any]) -> None:
    store = env["app"].state.store
    task_id = raw_task(store, status="done", phase="completed")
    payload = {"message_id": "msg-retry", "content": f"@bot 查询 {task_id} 的状态"}

    first = (await env["bob"].post(GLOBAL, json=payload)).json()
    second = (await env["bob"].post(GLOBAL, json=payload)).json()
    assert first == second

    history = (await env["alice"].get(GLOBAL)).json()["items"]
    replies = [
        item
        for item in history
        if item["message"].get("message_id") == "assistant:msg-retry"
    ]
    assert len(replies) == 1


async def test_ordinary_team_message_does_not_query(env: dict[str, Any]) -> None:
    store = env["app"].state.store
    task_id = raw_task(store, status="done", phase="completed")
    before = await _task_count(env["alice"])

    response = await env["alice"].post(
        GLOBAL,
        json={"message_id": "msg-plain", "content": f"note {task_id} 状态"},
    )
    body = response.json()
    assert body["kind"] == "recorded"
    assert body["reply"] is None
    assert await _task_count(env["alice"]) == before

    history = (await env["alice"].get(GLOBAL)).json()["items"]
    assert not any(
        item["message"].get("message_id") == "assistant:msg-plain" for item in history
    )


async def test_anonymous_cannot_query(env: dict[str, Any]) -> None:
    async with httpx.AsyncClient(
        transport=env["transport"], base_url="http://testserver"
    ) as anon:
        response = await anon.post(
            GLOBAL, json={"message_id": "msg-anon", "content": "@bot 查询状态"}
        )
        assert response.status_code == 401


async def test_personal_query_is_chat_only_and_isolated(env: dict[str, Any]) -> None:
    store = env["app"].state.store
    task_id = raw_task(store, status="done", phase="completed")

    response = await env["alice"].post(
        PERSONAL,
        json={"message_id": "msg-personal", "content": f"查询 {task_id} 的状态"},
    )
    body = response.json()
    assert body["kind"] == "switch_to_team"
    assert body["task_id"] is None

    # No shared side effect: bob sees nothing in the global conversation...
    global_history = (await env["bob"].get(GLOBAL)).json()["items"]
    assert not any(
        item["message"].get("message_id") == "assistant:msg-personal"
        for item in global_history
    )
    # ...and bob cannot read alice's private conversation.
    bob_personal = (await env["bob"].get(PERSONAL)).json()["items"]
    assert not any(
        item["message"].get("message_id") == "assistant:msg-personal"
        for item in bob_personal
    )
    alice_personal = (await env["alice"].get(PERSONAL)).json()["items"]
    assert any(
        item["message"].get("message_id") == "assistant:msg-personal"
        for item in alice_personal
    )
