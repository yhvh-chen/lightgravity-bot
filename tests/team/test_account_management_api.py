"""LG-062 admin account-management + self password HTTP behaviour.

Runs against the real FastAPI app over ASGI transports (real routes, real
sessions, real store file).  Two independent clients model two human sessions
so session invalidation is observed from the target's own cookie.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from lightgravity.api import events as events_module
from lightgravity.team import TeamAccounts, TeamAuthService

from team_helpers import (
    ADMIN_PASSWORD,
    MEMBER_PASSWORD,
    error_code,
    login,
    login_admin,
    login_member,
    seeded_accounts,
    team_app,
    team_client,
    team_settings,
)

CANARY = "lg-canary-do-not-echo-3f9a"


@asynccontextmanager
async def fresh_client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """A second independent session against the same app (no shared cookies)."""

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


async def _accounts(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    response = await client.get("/api/v1/accounts")
    assert response.status_code == 200, response.text
    return response.json()["accounts"]


def _find(accounts: list[dict[str, Any]], username: str) -> dict[str, Any]:
    return next(account for account in accounts if account["username"] == username)


# ------------------------------------------------------------------ authority


async def test_anonymous_account_endpoints_are_401(team_client: httpx.AsyncClient) -> None:
    for method, path, body in [
        ("GET", "/api/v1/accounts", None),
        ("POST", "/api/v1/accounts", {"username": "x", "password": "y"}),
        ("PATCH", "/api/v1/accounts/alice", {"enabled": False}),
        ("POST", "/api/v1/accounts/alice/password", {"password": "z"}),
        ("POST", "/api/v1/account/password", {"current_password": "a", "new_password": "b", "confirmation": "b"}),
    ]:
        response = await team_client.request(method, path, json=body)
        assert response.status_code == 401, f"{method} {path}: {response.text}"
        assert error_code(response) == "unauthorized"


async def test_member_cannot_use_admin_account_surface(team_client: httpx.AsyncClient) -> None:
    assert (await login_member(team_client)).status_code == 200
    assert (await team_client.get("/api/v1/accounts")).status_code == 403
    assert (await team_client.post("/api/v1/accounts", json={"username": "x", "password": "y"})).status_code == 403
    assert (await team_client.patch("/api/v1/accounts/alice", json={"enabled": False})).status_code == 403
    reset = await team_client.post("/api/v1/accounts/alice/password", json={"password": "z"})
    assert reset.status_code == 403
    assert error_code(reset) == "forbidden"


async def test_account_routes_absent_in_single_mode(tmp_path: Any) -> None:
    from lightgravity.api.app import create_app
    from lightgravity.config import Settings

    settings = Settings(
        data_dir=tmp_path / "data",
        workspace_root=tmp_path / "data" / "workspaces",
        secret_store=tmp_path / "secrets",
    )
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        assert (await client.get("/api/v1/accounts")).status_code == 404
        assert (
            await client.post(
                "/api/v1/account/password",
                json={"current_password": "a", "new_password": "b", "confirmation": "b"},
            )
        ).status_code == 404


# ------------------------------------------------------------------- reading


async def test_admin_lists_accounts_without_secret_material(
    team_client: httpx.AsyncClient, seeded_accounts: TeamAccounts
) -> None:
    await login_admin(team_client)
    accounts = await _accounts(team_client)
    assert {account["username"] for account in accounts} == {"admin", "alice"}
    for account in accounts:
        assert set(account) == {"username", "role", "enabled", "created_at", "revision"}
        assert isinstance(account["enabled"], bool)
        assert isinstance(account["revision"], int)
    raw = await team_client.get("/api/v1/accounts")
    lowered = raw.text.lower()
    assert "salt" not in lowered
    assert "hash" not in lowered
    assert "pbkdf2" not in lowered
    assert ADMIN_PASSWORD not in raw.text
    assert MEMBER_PASSWORD not in raw.text


# ------------------------------------------------------------------ creating


async def test_admin_creates_account_and_it_can_login(
    team_client: httpx.AsyncClient, team_app: FastAPI
) -> None:
    await login_admin(team_client)
    created = await team_client.post(
        "/api/v1/accounts",
        json={"username": "carol", "password": "carol-test-pw", "role": "member"},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["username"] == "carol"
    assert body["role"] == "member"
    assert body["enabled"] is True
    assert body["revision"] == 0
    assert "password" not in body and "hash" not in body and "salt" not in body

    async with fresh_client(team_app) as carol:
        assert (await login(carol, "carol", "carol-test-pw")).status_code == 200
        assert (await carol.get("/api/v1/auth/me")).json()["username"] == "carol"


async def test_create_duplicate_and_invalid_input(
    team_client: httpx.AsyncClient,
) -> None:
    await login_admin(team_client)
    duplicate = await team_client.post(
        "/api/v1/accounts", json={"username": "alice", "password": "pw", "role": "member"}
    )
    assert duplicate.status_code == 400
    assert error_code(duplicate) == "invalid_request"

    invalid_role = await team_client.post(
        "/api/v1/accounts", json={"username": "dave", "password": "pw", "role": "root"}
    )
    assert invalid_role.status_code == 422
    assert error_code(invalid_role) == "validation_failed"


# ---------------------------------------------------- enable/disable + roles


async def test_disable_invalidates_existing_session(
    team_client: httpx.AsyncClient,
    team_app: FastAPI,
    seeded_accounts: TeamAccounts,
) -> None:
    async with fresh_client(team_app) as alice:
        assert (await login_member(alice)).status_code == 200
        assert (await alice.get("/api/v1/files")).status_code == 200
        await login_admin(team_client)
        disabled = await team_client.patch(
            "/api/v1/accounts/alice", json={"enabled": False}
        )
        assert disabled.status_code == 200, disabled.text
        assert disabled.json()["enabled"] is False
        # The old cookie is rejected on the very next request.
        assert (await alice.get("/api/v1/files")).status_code == 401
        # And a fresh login is refused while disabled.
        assert (await login(alice, "alice", MEMBER_PASSWORD)).status_code == 401


async def test_reenable_does_not_revive_old_cookie(
    team_client: httpx.AsyncClient,
    team_app: FastAPI,
    seeded_accounts: TeamAccounts,
) -> None:
    async with fresh_client(team_app) as alice:
        assert (await login_member(alice)).status_code == 200
        old_cookie = alice.cookies.get("lg_session")
        assert old_cookie
        await login_admin(team_client)
        assert (
            await team_client.patch("/api/v1/accounts/alice", json={"enabled": False})
        ).status_code == 200
        assert (
            await team_client.patch("/api/v1/accounts/alice", json={"enabled": True})
        ).status_code == 200
        # Replay the original cookie: it must stay invalid.
        replay = await alice.get(
            "/api/v1/files", headers={"cookie": f"lg_session={old_cookie}"}
        )
        assert replay.status_code == 401
        # A brand-new login works and gets the latest state.
        alice.cookies.clear()
        assert (await login_member(alice)).status_code == 200


async def test_role_change_invalidates_and_role_is_fresh(
    team_client: httpx.AsyncClient,
    team_app: FastAPI,
    seeded_accounts: TeamAccounts,
) -> None:
    async with fresh_client(team_app) as alice:
        assert (await login_member(alice)).status_code == 200
        await login_admin(team_client)
        promoted = await team_client.patch(
            "/api/v1/accounts/alice", json={"role": "admin"}
        )
        assert promoted.status_code == 200, promoted.text
        assert promoted.json()["role"] == "admin"
        # Old member session is dead; no stale role survives.
        assert (await alice.get("/api/v1/settings")).status_code == 401
        alice.cookies.clear()
        assert (await login_member(alice)).status_code == 200
        assert (await alice.get("/api/v1/auth/me")).json()["role"] == "admin"
        # Fresh admin session can read an admin surface.
        assert (await alice.get("/api/v1/settings")).status_code == 200


async def test_password_reset_invalidates_target_session(
    team_client: httpx.AsyncClient,
    team_app: FastAPI,
    seeded_accounts: TeamAccounts,
) -> None:
    async with fresh_client(team_app) as alice:
        assert (await login_member(alice)).status_code == 200
        await login_admin(team_client)
        reset = await team_client.post(
            "/api/v1/accounts/alice/password", json={"password": "new-alice-pw"}
        )
        assert reset.status_code == 200, reset.text
        assert (await alice.get("/api/v1/files")).status_code == 401
        assert (await login(alice, "alice", MEMBER_PASSWORD)).status_code == 401
        assert (await login(alice, "alice", "new-alice-pw")).status_code == 200


async def test_last_active_admin_protected_via_api(
    team_client: httpx.AsyncClient, seeded_accounts: TeamAccounts
) -> None:
    await login_admin(team_client)
    disabled = await team_client.patch("/api/v1/accounts/admin", json={"enabled": False})
    assert disabled.status_code == 409, disabled.text
    assert error_code(disabled) == "illegal_transition"
    assert disabled.json()["error"]["details"]["reason"] == "last_active_admin"
    demoted = await team_client.patch("/api/v1/accounts/admin", json={"role": "member"})
    assert demoted.status_code == 409
    assert demoted.json()["error"]["details"]["reason"] == "last_active_admin"


async def test_stale_revision_rejected_via_api(
    team_client: httpx.AsyncClient, seeded_accounts: TeamAccounts
) -> None:
    await login_admin(team_client)
    alice = _find(await _accounts(team_client), "alice")
    ok = await team_client.patch(
        "/api/v1/accounts/alice",
        json={"enabled": False, "expected_revision": alice["revision"]},
    )
    assert ok.status_code == 200
    stale = await team_client.patch(
        "/api/v1/accounts/alice",
        json={"enabled": True, "expected_revision": alice["revision"]},
    )
    assert stale.status_code == 409
    assert error_code(stale) == "revision_conflict"


# ------------------------------------------------------------ own password


async def test_own_password_change_requires_current_and_clears_session(
    team_client: httpx.AsyncClient, seeded_accounts: TeamAccounts
) -> None:
    assert (await login_member(team_client)).status_code == 200
    wrong = await team_client.post(
        "/api/v1/account/password",
        json={
            "current_password": "not-right",
            "new_password": "brand-new-pw",
            "confirmation": "brand-new-pw",
        },
    )
    assert wrong.status_code == 401
    assert error_code(wrong) == "unauthorized"

    mismatch = await team_client.post(
        "/api/v1/account/password",
        json={
            "current_password": MEMBER_PASSWORD,
            "new_password": "brand-new-pw",
            "confirmation": "different",
        },
    )
    assert mismatch.status_code == 400

    ok = await team_client.post(
        "/api/v1/account/password",
        json={
            "current_password": MEMBER_PASSWORD,
            "new_password": "brand-new-pw",
            "confirmation": "brand-new-pw",
        },
    )
    assert ok.status_code == 200, ok.text
    assert ok.json() == {"username": "alice", "signed_out": True}
    # The current session is signed out; the old password is gone.
    assert (await team_client.get("/api/v1/files")).status_code == 401
    assert (await login(team_client, "alice", MEMBER_PASSWORD)).status_code == 401
    assert (await login(team_client, "alice", "brand-new-pw")).status_code == 200


async def test_own_password_change_only_touches_self(
    team_client: httpx.AsyncClient, seeded_accounts: TeamAccounts
) -> None:
    assert (await login_member(team_client)).status_code == 200
    ok = await team_client.post(
        "/api/v1/account/password",
        json={
            "current_password": MEMBER_PASSWORD,
            "new_password": "alice-new-pw",
            "confirmation": "alice-new-pw",
        },
    )
    assert ok.status_code == 200
    # admin's credential and session are unaffected
    assert (await login_admin(team_client)).status_code == 200
    assert (await team_client.get("/api/v1/accounts")).status_code == 200


# ------------------------------------------------------------ secret canary


async def test_validation_errors_never_echo_secret_input(
    team_client: httpx.AsyncClient,
) -> None:
    await login_admin(team_client)
    cases = [
        ("/api/v1/accounts", {"username": "canary-user", "password": [CANARY]}),
        ("/api/v1/accounts/admin/password", {"password": [CANARY]}),
    ]
    for path, body in cases:
        response = await team_client.post(path, json=body)
        assert response.status_code == 422, response.text
        assert CANARY not in response.text
        assert "password" in response.text  # field name may appear, value must not

    # Own password endpoint too.
    assert (await login_member(team_client)).status_code == 200
    own = await team_client.post(
        "/api/v1/account/password",
        json={
            "current_password": {"nested": CANARY},
            "new_password": [CANARY],
            "confirmation": "x",
        },
    )
    assert own.status_code == 422
    assert CANARY not in own.text


# ---------------------------------------------------------- real SSE stream


class _FakeSubscription:
    def __init__(self) -> None:
        self.closed = False

    async def receive(self, timeout: float) -> Any:
        await asyncio.sleep(0.005)
        raise TimeoutError

    def close(self) -> None:
        self.closed = True


class _FakeStore:
    def read_events(self, *args: Any, **kwargs: Any) -> list[Any]:
        return []


async def test_real_service_disable_ends_sse_stream(
    team_settings: Any, monkeypatch: Any
) -> None:
    monkeypatch.setattr(events_module, "_SESSION_CHECK_SECONDS", 0.02)
    store = TeamAccounts(team_settings.team_accounts_path)
    store.add("alice", "pw", "member")
    service = TeamAuthService(store, session_ttl_seconds=60)
    identity = service.authenticate("alice", "pw")
    assert identity is not None
    session_id = service.create_session(identity)
    subscription = _FakeSubscription()
    ctx = SimpleNamespace(
        broker=SimpleNamespace(subscribe=lambda: subscription),
        store=_FakeStore(),
        team=service,
    )

    async def consume() -> None:
        async for _chunk in events_module._event_source(ctx, None, session_id):
            pass

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.05)
    assert not task.done()
    store.set_enabled("alice", False)
    await asyncio.wait_for(task, timeout=2.0)
    assert task.done()
    assert subscription.closed is True
