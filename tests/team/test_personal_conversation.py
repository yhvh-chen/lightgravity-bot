"""Private Personal conversation isolation and idempotency (LG-054).

These are real-HTTPServer-level tests over the FastAPI app with a deterministic
responder (no product model call).  They assert the LG-054 guarantees:

* the private conversation is derived from the authenticated server session,
  never from a request body/query field;
* two users (and the admin) can never read or write each other's private
  history, and the shared global history never contains private content;
* Personal is chat-only: a delivery request returns switch-to-Team guidance
  with zero shared side effects (no Task/Run, no shared log/event);
* idempotency keys isolate channels and users;
* shared materials/sources are rejected with a clear Team hint;
* single-user mode preserves the legacy global conversation and behaviour.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from lightgravity.api.app import create_app
from lightgravity.api.conversations import (
    GLOBAL_CONVERSATION_ID,
    personal_conversation_id,
)
from lightgravity.config import Settings
from lightgravity.contracts import API_PREFIX
from lightgravity.team import TeamAccounts

from team_helpers import (  # noqa: F401  (fixtures imported for pytest discovery)
    ADMIN_PASSWORD,
    MEMBER_PASSWORD,
    login_admin,
    login_member,
    seeded_accounts,
    team_settings,
)

BOB_PASSWORD = "bob-secret-pw"
PERSONAL_PATH = f"{API_PREFIX}/conversations/personal/messages"
GLOBAL_PATH = f"{API_PREFIX}/conversations/global/messages"


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    )


async def _login(
    client: httpx.AsyncClient, username: str, password: str
) -> httpx.Response:
    return await client.post(
        f"{API_PREFIX}/auth/login", json={"username": username, "password": password}
    )


def _contents(response: httpx.Response) -> list[str]:
    return [
        item["message"]["content"] for item in response.json()["items"]
    ]


def test_personal_conversation_id_is_stable_and_well_formed() -> None:
    first = personal_conversation_id("alice")
    assert first == personal_conversation_id("alice")
    assert first != personal_conversation_id("bob")
    assert first != GLOBAL_CONVERSATION_ID
    assert first.startswith("conv_")
    body = first[len("conv_") :]
    assert len(body) == 26
    assert set(body) <= set("0123456789ABCDEFGHJKMNPQRSTVWXYZ")
    # The raw username never leaks into the file path.
    assert "alice" not in first


@pytest.fixture
def two_member_accounts(seeded_accounts: TeamAccounts) -> TeamAccounts:
    seeded_accounts.add("bob", BOB_PASSWORD, "member")
    return seeded_accounts


async def test_private_history_is_isolated_per_user_and_from_global(
    team_settings: Settings, two_member_accounts: TeamAccounts
) -> None:
    calls: list[str] = []
    app = create_app(
        team_settings, responder=lambda content, _c: calls.append(content) or f"BOT:{content}"
    )
    async with app.router.lifespan_context(app):
        async with (
             _client(app) as alice,
             _client(app) as bob,
             _client(app) as admin,
        ):
            assert (await login_member(alice)).status_code == 200
            assert (await _login(bob, "bob", BOB_PASSWORD)).status_code == 200
            assert (await login_admin(admin)).status_code == 200

            posted = await alice.post(
                PERSONAL_PATH,
                json={"message_id": "msg_alice_1", "content": "private hello from alice"},
            )
            assert posted.status_code == 200, posted.text
            assert posted.json()["kind"] == "direct"
            assert len(calls) == 1

            alice_history = await alice.get(PERSONAL_PATH)
            assert "private hello from alice" in _contents(alice_history)
            assert any(c.startswith("BOT:") for c in _contents(alice_history))

            # Bob and the admin derive their own distinct empty private log.
            bob_history = await bob.get(PERSONAL_PATH)
            admin_history = await admin.get(PERSONAL_PATH)
            assert _contents(bob_history) == []
            assert _contents(admin_history) == []
            assert "private hello from alice" not in bob_history.text
            assert "private hello from alice" not in admin_history.text

            # The shared global conversation never receives private content.
            shared = await alice.get(GLOBAL_PATH)
            assert "private hello from alice" not in shared.text
            # And Bob cannot read Alice by writing a different owner field.
            forged = await bob.post(
                PERSONAL_PATH,
                json={
                    "message_id": "msg_forge",
                    "content": "forged",
                    "owner": "alice",
                },
            )
            assert forged.status_code == 422
            assert forged.json()["error"]["code"] == "validation_failed"


async def test_personal_delivery_request_has_no_shared_side_effects(
    team_settings: Settings, seeded_accounts: TeamAccounts
) -> None:
    calls: list[str] = []
    app = create_app(
        team_settings, responder=lambda content, _c: calls.append(content) or "BOT"
    )
    async with app.router.lifespan_context(app):
        async with _client(app) as alice:
            assert (await login_member(alice)).status_code == 200
            response = await alice.post(
                PERSONAL_PATH,
                json={
                    "message_id": "msg_deliver_1",
                    "content": "implement a new feature in the codebase",
                },
            )
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["kind"] == "switch_to_team"
            assert body["data"]["creates_task"] is False
            assert body["data"]["requires_team"] is True
            assert "Team" in body["reply"]
            assert calls == []  # never invoked the responder for delivery

            tasks = await alice.get(f"{API_PREFIX}/tasks")
            assert tasks.json()["items"] == []
            shared = await alice.get(GLOBAL_PATH)
            assert "implement a new feature" not in shared.text


async def test_personal_idempotency_is_isolated_by_owner(
    team_settings: Settings, two_member_accounts: TeamAccounts
) -> None:
    calls: list[str] = []
    app = create_app(
        team_settings, responder=lambda content, _c: calls.append(content) or f"BOT:{content}"
    )
    async with app.router.lifespan_context(app):
        async with (
             _client(app) as alice,
             _client(app) as bob,
        ):
            assert (await login_member(alice)).status_code == 200
            assert (await _login(bob, "bob", BOB_PASSWORD)).status_code == 200

            # Same client message id retried by the same user runs the model once.
            first = await alice.post(
                PERSONAL_PATH, json={"message_id": "msg_same", "content": "ping"}
            )
            second = await alice.post(
                PERSONAL_PATH, json={"message_id": "msg_same", "content": "ping"}
            )
            assert first.status_code == second.status_code == 200
            assert len(calls) == 1
            # No duplicate rows in the private log.
            alice_history = await alice.get(PERSONAL_PATH)
            user_rows = [
                item
                for item in alice_history.json()["items"]
                if item["message"].get("role") == "user"
            ]
            assert len(user_rows) == 1

            # The same message id from another owner is its own conversation.
            bob_post = await bob.post(
                PERSONAL_PATH, json={"message_id": "msg_same", "content": "ping from bob"}
            )
            assert bob_post.status_code == 200
            assert len(calls) == 2
            bob_history = await bob.get(PERSONAL_PATH)
            assert "ping from bob" in _contents(bob_history)
            assert "ping from bob" not in _contents(await alice.get(PERSONAL_PATH))


async def test_personal_unavailable_without_model(
    team_settings: Settings, seeded_accounts: TeamAccounts
) -> None:
    app = create_app(team_settings)  # no responder -> deterministic fallback only
    async with app.router.lifespan_context(app):
        async with _client(app) as alice:
            assert (await login_member(alice)).status_code == 200
            response = await alice.post(
                PERSONAL_PATH,
                json={"message_id": "msg_no_model", "content": "hello there"},
            )
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["kind"] == "unavailable"
            assert body["data"]["unavailable"] is True
            assert "no model" in body["reply"].lower()


@pytest.mark.parametrize(
    "extra,field",
    [
        # LG-119 replaces the old wholesale attachment rejection: a shared path
        # shape is now a 422 validation error (covered in
        # tests/api/test_private_attachments.py). Selected sources and workspace
        # refs remain unsupported with the Team hint.
        ({"selected_sources": [{"source_id": "src_1"}]}, "selected_sources"),
        ({"workspace_ref": "project"}, "workspace_ref"),
    ],
)
async def test_personal_rejects_shared_materials_with_team_hint(
    team_settings: Settings,
    seeded_accounts: TeamAccounts,
    extra: dict[str, Any],
    field: str,
) -> None:
    app = create_app(team_settings, responder=lambda content, _c: "BOT")
    async with app.router.lifespan_context(app):
        async with _client(app) as alice:
            assert (await login_member(alice)).status_code == 200
            response = await alice.post(
                PERSONAL_PATH,
                json={"message_id": f"msg_{field}", "content": "hi", **extra},
            )
            assert response.status_code == 503, response.text
            error = response.json()["error"]
            assert error["code"] == "capability_unavailable"
            assert error["details"]["field"] == field
            assert error["details"]["hint"] == "switch_to_team"
            assert "Team" in error["message"]


async def test_personal_requires_a_session(
    team_settings: Settings, seeded_accounts: TeamAccounts
) -> None:
    app = create_app(team_settings, responder=lambda content, _c: "BOT")
    async with app.router.lifespan_context(app):
        async with _client(app) as anon:
            assert (await anon.get(PERSONAL_PATH)).status_code == 401
            post = await anon.post(
                PERSONAL_PATH, json={"message_id": "msg_anon", "content": "hi"}
            )
            assert post.status_code == 401


async def test_single_mode_personal_preserves_global_history_and_delivery(
    settings: Settings,
) -> None:
    """Single-user mode reuses the legacy global conversation id/behaviour."""

    app = create_app(settings, responder=lambda content, _c: f"BOT:{content}")
    async with app.router.lifespan_context(app):
        async with _client(app) as client:
            # Seed through the legacy global endpoint, then read it back via
            # Personal: single-mode Personal is the same durable conversation.
            legacy = await client.post(
                GLOBAL_PATH, json={"message_id": "msg_legacy", "content": "legacy hello"}
            )
            assert legacy.status_code == 200, legacy.text
            personal_history = await client.get(PERSONAL_PATH)
            assert "legacy hello" in _contents(personal_history)

            # Delivery still works in single mode (there is no team to route to).
            delivery = await client.post(
                PERSONAL_PATH,
                json={
                    "message_id": "msg_single_deliver",
                    "content": "implement a new feature",
                },
            )
            assert delivery.status_code == 200, delivery.text
            assert delivery.json()["kind"] == "task"
            assert delivery.json()["task_id"]

            # And the global endpoint reflects the same single conversation.
            shared = await client.get(GLOBAL_PATH)
            assert "legacy hello" in _contents(shared)
