"""Team auth endpoints: me/login/logout, cookies, throttling, origin (LG-050)."""

from __future__ import annotations

import httpx
import pytest

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


async def test_me_anonymous_reports_team_unauthenticated(
    team_client: httpx.AsyncClient,
) -> None:
    response = await team_client.get("/api/v1/auth/me")
    assert response.status_code == 200
    assert response.json() == {
        "mode": "team",
        "authenticated": False,
        "username": None,
        "role": None,
    }


async def test_login_sets_httponly_cookie_and_me_reports_role(
    team_client: httpx.AsyncClient,
) -> None:
    response = await login_member(team_client)
    assert response.status_code == 200
    assert response.json() == {"username": "alice", "role": "member"}
    set_cookie = response.headers["set-cookie"]
    assert "lg_session=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie or "samesite=lax" in set_cookie.lower()

    me = await team_client.get("/api/v1/auth/me")
    assert me.json() == {
        "mode": "team",
        "authenticated": True,
        "username": "alice",
        "role": "member",
    }


async def test_login_wrong_password_and_unknown_user_same_envelope(
    team_client: httpx.AsyncClient,
) -> None:
    wrong = await login(team_client, "alice", "not-the-password")
    unknown = await login(team_client, "ghost", "whatever")
    assert wrong.status_code == 401
    assert unknown.status_code == 401
    assert error_code(wrong) == "unauthorized"
    assert error_code(unknown) == "unauthorized"
    assert wrong.json()["error"] == unknown.json()["error"]
    assert "password" not in wrong.text.lower() or "invalid username or password" in wrong.text


async def test_logout_revokes_session_and_repeat_is_idempotent(
    team_client: httpx.AsyncClient,
) -> None:
    assert (await login_member(team_client)).status_code == 200
    session_cookie = team_client.cookies.get("lg_session")
    assert session_cookie
    first = await team_client.post("/api/v1/auth/logout")
    assert first.status_code == 204
    # cookie is cleared; business access now 401
    assert (await team_client.get("/api/v1/files")).status_code == 401
    # A still-present (already revoked) cookie is an idempotent 204, never 500.
    repeat = await team_client.post(
        "/api/v1/auth/logout", headers={"cookie": f"lg_session={session_cookie}"}
    )
    assert repeat.status_code == 204


async def test_logout_without_cookie_is_401(team_client: httpx.AsyncClient) -> None:
    response = await team_client.post("/api/v1/auth/logout")
    assert response.status_code == 401
    assert error_code(response) == "unauthorized"


async def test_login_rate_limited_after_repeated_failures(
    team_client: httpx.AsyncClient,
) -> None:
    for _ in range(5):
        response = await login(team_client, "alice", "bad")
        assert response.status_code == 401
    limited = await login(team_client, "alice", "bad")
    assert limited.status_code == 429
    assert error_code(limited) == "budget_exhausted"
    # A different identity is not blocked by alice's failures.
    assert (await login_admin(team_client)).status_code == 200


async def test_cross_origin_login_rejected(team_client: httpx.AsyncClient) -> None:
    response = await team_client.post(
        "/api/v1/auth/login",
        json={"username": "alice", "password": MEMBER_PASSWORD},
        headers={"origin": "http://evil.example"},
    )
    assert response.status_code == 403
    assert error_code(response) == "forbidden"


async def test_admin_login_works(team_client: httpx.AsyncClient) -> None:
    response = await login_admin(team_client)
    assert response.status_code == 200
    assert response.json()["role"] == "admin"
    assert ADMIN_PASSWORD not in response.text
